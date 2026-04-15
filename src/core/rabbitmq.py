import json
import logging
import os
from typing import Any

from src.core.constants import BLOCKCHAIN_EVENTS_EXCHANGE

LOGGER = logging.getLogger(__name__)

_connection = None
_channel = None


def get_rabbitmq_connection():
    global _connection
    if _connection is not None and getattr(_connection, "is_closed", False) is False:
        return _connection

    try:
        import pika
    except ImportError as exc:
        raise RuntimeError("pika is required to publish RabbitMQ events") from exc

    parameters = pika.URLParameters(
        os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F")
    )
    _connection = pika.BlockingConnection(parameters)
    return _connection


def get_rabbitmq_channel():
    global _channel
    if _channel is not None and getattr(_channel, "is_closed", False) is False:
        return _channel

    channel = get_rabbitmq_connection().channel()
    channel.exchange_declare(exchange=BLOCKCHAIN_EVENTS_EXCHANGE, exchange_type="topic", durable=True)
    _channel = channel
    return _channel


def publish_event(routing_key: str, payload: dict[str, Any]) -> None:
    channel = get_rabbitmq_channel()
    body = json.dumps(payload, sort_keys=True, ensure_ascii=True)

    properties = None
    try:
        import pika

        properties = pika.BasicProperties(content_type="application/json", delivery_mode=2)
    except ImportError:
        LOGGER.warning("pika no disponible para definir propiedades del mensaje")

    channel.basic_publish(
        exchange=BLOCKCHAIN_EVENTS_EXCHANGE,
        routing_key=routing_key,
        body=body,
        properties=properties,
    )


def close_rabbitmq_connection() -> None:
    global _connection, _channel
    if _channel is not None and getattr(_channel, "is_closed", True) is False:
        _channel.close()
    if _connection is not None and getattr(_connection, "is_closed", True) is False:
        _connection.close()
    _channel = None
    _connection = None
