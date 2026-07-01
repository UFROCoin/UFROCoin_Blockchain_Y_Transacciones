import json
import logging
import os
from typing import Any

from src.core.constants import BLOCKCHAIN_EVENTS_EXCHANGE, TRANSACTION_EVENT_ROUTING_KEY

LOGGER = logging.getLogger(__name__)

_connection = None
_channel = None


def _basic_properties():
    properties = None
    try:
        import pika

        properties = pika.BasicProperties(
            content_type="application/json",
            delivery_mode=2,
        )
    except ImportError:
        LOGGER.warning("pika no disponible para definir propiedades del mensaje")
    return properties


def _publish_retry_exceptions():
    try:
        import pika

        return (pika.exceptions.AMQPError, pika.exceptions.StreamLostError, OSError)
    except ImportError:
        return (OSError,)


def _reset_connection() -> None:
    global _connection, _channel

    for resource in (_channel, _connection):
        if resource is not None and getattr(resource, "is_closed", True) is False:
            try:
                resource.close()
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("No se pudo cerrar recurso RabbitMQ: %s", exc)

    _channel = None
    _connection = None


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
    channel.exchange_declare(
        exchange=BLOCKCHAIN_EVENTS_EXCHANGE,
        exchange_type="topic",
        durable=True,
    )
    _channel = channel
    return _channel


def publish_event(routing_key: str, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    properties = None
    properties_loaded = False

    for attempt in (1, 2):
        try:
            channel = get_rabbitmq_channel()
            if not properties_loaded:
                properties = _basic_properties()
                properties_loaded = True
            channel.basic_publish(
                exchange=BLOCKCHAIN_EVENTS_EXCHANGE,
                routing_key=routing_key,
                body=body,
                properties=properties,
            )
            return
        except _publish_retry_exceptions() as exc:
            LOGGER.warning(
                "publish intento %s falló (%s); reconectando",
                attempt,
                exc,
            )
            _reset_connection()
            if attempt == 2:
                raise


def close_rabbitmq_connection() -> None:
    _reset_connection()


class RabbitMQPublisher:
    def __init__(self, routing_key: str = TRANSACTION_EVENT_ROUTING_KEY):
        self.routing_key = routing_key

    def publish_transaction(self, transaction_data: dict[str, Any]) -> None:
        publish_event(self.routing_key, transaction_data)
