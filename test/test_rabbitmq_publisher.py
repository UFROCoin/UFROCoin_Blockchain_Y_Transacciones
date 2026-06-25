import builtins
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.core import rabbitmq_publisher
from src.core.constants import BLOCKCHAIN_EVENTS_EXCHANGE, TRANSACTION_EVENT_ROUTING_KEY


@pytest.fixture(autouse=True)
def reset_rabbitmq_globals():
    rabbitmq_publisher._connection = None
    rabbitmq_publisher._channel = None
    yield
    rabbitmq_publisher._connection = None
    rabbitmq_publisher._channel = None


@pytest.fixture()
def fake_pika(monkeypatch):
    connection = MagicMock()
    connection.is_closed = False
    channel = MagicMock()
    channel.is_closed = False
    connection.channel.return_value = channel

    module = SimpleNamespace()
    module.URLParameters = MagicMock(side_effect=lambda url: {"url": url})
    module.BlockingConnection = MagicMock(return_value=connection)
    module.BasicProperties = MagicMock(return_value={"content_type": "application/json"})

    monkeypatch.setitem(sys.modules, "pika", module)
    return module, connection, channel


def test_get_connection_uses_default_rabbitmq_url(fake_pika):
    pika, connection, _channel = fake_pika

    result = rabbitmq_publisher.get_rabbitmq_connection()

    assert result is connection
    pika.URLParameters.assert_called_once_with("amqp://guest:guest@localhost:5672/%2F")
    pika.BlockingConnection.assert_called_once_with({"url": "amqp://guest:guest@localhost:5672/%2F"})


def test_get_connection_uses_env_rabbitmq_url(fake_pika, monkeypatch):
    pika, connection, _channel = fake_pika
    monkeypatch.setenv("RABBITMQ_URL", "amqp://user:pass@broker:5672/%2F")

    result = rabbitmq_publisher.get_rabbitmq_connection()

    assert result is connection
    pika.URLParameters.assert_called_once_with("amqp://user:pass@broker:5672/%2F")


def test_get_connection_reuses_open_connection(fake_pika):
    pika, connection, _channel = fake_pika
    rabbitmq_publisher._connection = connection

    result = rabbitmq_publisher.get_rabbitmq_connection()

    assert result is connection
    pika.BlockingConnection.assert_not_called()


def test_get_connection_reconnects_closed_connection(fake_pika):
    pika, connection, _channel = fake_pika
    closed_connection = MagicMock()
    closed_connection.is_closed = True
    rabbitmq_publisher._connection = closed_connection

    result = rabbitmq_publisher.get_rabbitmq_connection()

    assert result is connection
    pika.BlockingConnection.assert_called_once()


def test_get_connection_raises_clear_error_when_pika_is_missing(monkeypatch):
    original_import = builtins.__import__

    def import_without_pika(name, *args, **kwargs):
        if name == "pika":
            raise ImportError("missing pika")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_pika)

    with pytest.raises(RuntimeError, match="pika is required"):
        rabbitmq_publisher.get_rabbitmq_connection()


def test_get_channel_declares_blockchain_exchange(fake_pika):
    _pika, _connection, channel = fake_pika

    result = rabbitmq_publisher.get_rabbitmq_channel()

    assert result is channel
    channel.exchange_declare.assert_called_once_with(
        exchange=BLOCKCHAIN_EVENTS_EXCHANGE,
        exchange_type="topic",
        durable=True,
    )


def test_get_channel_reuses_open_channel(fake_pika):
    _pika, connection, channel = fake_pika
    rabbitmq_publisher._channel = channel


    result = rabbitmq_publisher.get_rabbitmq_channel()

    assert result is channel
    connection.channel.assert_not_called()


def test_publish_event_serializes_json_and_sets_persistent_properties(fake_pika):
    pika, _connection, channel = fake_pika
    payload = {"z": "ultimo", "a": "primero", "texto": "ñ"}

    rabbitmq_publisher.publish_event("transaction.created", payload)

    pika.BasicProperties.assert_called_once_with(
        content_type="application/json",
        delivery_mode=2,
    )
    publish_kwargs = channel.basic_publish.call_args.kwargs
    assert publish_kwargs["exchange"] == BLOCKCHAIN_EVENTS_EXCHANGE
    assert publish_kwargs["routing_key"] == "transaction.created"
    assert publish_kwargs["body"] == json.dumps(payload, sort_keys=True, ensure_ascii=True)
    assert json.loads(publish_kwargs["body"]) == payload
    assert publish_kwargs["properties"] == {"content_type": "application/json"}


def test_publish_event_continues_without_basic_properties_when_pika_import_fails(
    fake_pika,
    monkeypatch,
):
    _pika, _connection, channel = fake_pika
    original_import = builtins.__import__
    import_count = {"pika": 0}

    def fail_second_pika_import(name, *args, **kwargs):
        if name == "pika":
            import_count["pika"] += 1
            if import_count["pika"] == 2:
                raise ImportError("missing properties")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_second_pika_import)

    rabbitmq_publisher.publish_event("transaction.created", {"id": "tx-1"})

    assert channel.basic_publish.call_args.kwargs["properties"] is None


def test_close_rabbitmq_connection_closes_open_resources():
    connection = MagicMock()
    connection.is_closed = False
    channel = MagicMock()
    channel.is_closed = False
    rabbitmq_publisher._connection = connection
    rabbitmq_publisher._channel = channel

    rabbitmq_publisher.close_rabbitmq_connection()

    channel.close.assert_called_once()
    connection.close.assert_called_once()
    assert rabbitmq_publisher._connection is None
    assert rabbitmq_publisher._channel is None


def test_close_rabbitmq_connection_ignores_already_closed_resources():
    connection = MagicMock()
    connection.is_closed = True
    channel = MagicMock()
    channel.is_closed = True
    rabbitmq_publisher._connection = connection
    rabbitmq_publisher._channel = channel

    rabbitmq_publisher.close_rabbitmq_connection()

    channel.close.assert_not_called()
    connection.close.assert_not_called()


def test_rabbitmq_publisher_delegates_transaction_publication(monkeypatch):
    publish_event = MagicMock()
    monkeypatch.setattr(rabbitmq_publisher, "publish_event", publish_event)
    payload = {"transaction_id": "tx-1"}

    publisher = rabbitmq_publisher.RabbitMQPublisher()
    publisher.publish_transaction(payload)

    publish_event.assert_called_once_with(TRANSACTION_EVENT_ROUTING_KEY, payload)
