import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://payments:payments@localhost/payments")
os.environ.setdefault("RABBITMQ_URL", "amqp://payments:payments@localhost/")
os.environ.setdefault("API_KEY", "test-api-key-long-enough-123")
os.environ.setdefault("WEBHOOK_SIGNING_SECRET", "test-webhook-secret-long-enough-123")
