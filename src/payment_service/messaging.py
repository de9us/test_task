from uuid import UUID

import aio_pika
from aio_pika import ExchangeType as AMQPExchangeType
from faststream.rabbit import Channel, RabbitBroker, RabbitExchange

from payment_service.config import Settings
from payment_service.schemas import PaymentEvent

EVENTS_EXCHANGE = RabbitExchange("payments.events", durable=True)
RETRY_EXCHANGE = RabbitExchange("payments.retries", durable=True)
DLX_NAME = "payments.dlx"
MAIN_QUEUE = "payments.new"
DLQ_NAME = "payments.dlq"
RETRY_DELAY_MS = {1: 2_000, 2: 4_000}


def make_broker(settings: Settings, *, prefetch_count: int | None = None) -> RabbitBroker:
    return RabbitBroker(
        settings.rabbitmq_url,
        default_channel=Channel(
            prefetch_count=prefetch_count,
            publisher_confirms=True,
            on_return_raises=True,
        ),
    )


async def declare_topology(settings: Settings) -> None:
    """Queues must exist even when no consumer is connected (e.g. during a deploy)."""
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    try:
        channel = await connection.channel(publisher_confirms=True)
        events = await channel.declare_exchange(
            EVENTS_EXCHANGE.name, AMQPExchangeType.DIRECT, durable=True
        )
        retries = await channel.declare_exchange(
            RETRY_EXCHANGE.name, AMQPExchangeType.DIRECT, durable=True
        )
        dlx = await channel.declare_exchange(DLX_NAME, AMQPExchangeType.DIRECT, durable=True)

        dead_queue = await channel.declare_queue(DLQ_NAME, durable=True)
        await dead_queue.bind(dlx, routing_key="payments.dead")

        main_queue = await channel.declare_queue(
            MAIN_QUEUE,
            durable=True,
            arguments={
                "x-dead-letter-exchange": DLX_NAME,
                "x-dead-letter-routing-key": "payments.dead",
            },
        )
        await main_queue.bind(events, routing_key=MAIN_QUEUE)

        for failed_attempt, delay_ms in RETRY_DELAY_MS.items():
            name = f"payments.retry.{failed_attempt}"
            queue = await channel.declare_queue(
                name,
                durable=True,
                arguments={
                    "x-message-ttl": delay_ms,
                    "x-dead-letter-exchange": EVENTS_EXCHANGE.name,
                    "x-dead-letter-routing-key": MAIN_QUEUE,
                },
            )
            await queue.bind(retries, routing_key=name)
    finally:
        await connection.close()


async def publish_payment_event(
    broker: RabbitBroker, *, event_id: UUID, payment_id: UUID
) -> None:
    event = PaymentEvent(event_id=event_id, payment_id=payment_id)
    confirmation = await broker.publish(
        event.model_dump(mode="json"),
        queue=MAIN_QUEUE,
        exchange=EVENTS_EXCHANGE,
        message_id=str(event_id),
        mandatory=True,
        persist=True,
        timeout=10.0,
    )
    if confirmation is False:
        raise RuntimeError("RabbitMQ negatively acknowledged publish")


async def publish_retry(broker: RabbitBroker, event: PaymentEvent) -> None:
    if event.attempt >= 3:
        raise ValueError("maximum attempts exceeded")
    name = f"payments.retry.{event.attempt}"
    retry = event.model_copy(update={"attempt": event.attempt + 1})
    confirmation = await broker.publish(
        retry.model_dump(mode="json"),
        queue=name,
        exchange=RETRY_EXCHANGE,
        message_id=str(event.event_id),
        mandatory=True,
        persist=True,
        timeout=10.0,
    )
    if confirmation is False:
        raise RuntimeError("RabbitMQ negatively acknowledged publish")
