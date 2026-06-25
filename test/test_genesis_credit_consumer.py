import json
from unittest.mock import MagicMock

from src.workers import genesis_credit_consumer as consumer


CREDIT_EVENT = {
    "event_type": "wallet.credit.issued",
    "occurred_at": "2026-06-25T12:00:00Z",
    "source": "users-service",
    "data": {
        "credit_id": "user-123",
        "from": "SYSTEM_REWARD",
        "to": "a1b2c3d4e5f678901234567890abcdef12345678",
        "amount": 100.0,
        "type": "GENESIS",
        "status": "CONFIRMED",
        "timestamp": "2026-06-25T12:00:00Z",
    },
}


def test_build_credit_document_maps_contract_to_offchain_confirmed():
    doc = consumer.build_credit_document(CREDIT_EVENT["data"])

    assert doc == {
        "from": "SYSTEM_REWARD",
        "to": "a1b2c3d4e5f678901234567890abcdef12345678",
        "amount": 100.0,
        "type": "GENESIS",
        "status": "CONFIRMED",
        "block_index": None,
        "credit_id": "user-123",
        "timestamp": "2026-06-25T12:00:00Z",
    }


def test_persist_credit_upserts_idempotently_by_credit_id():
    transactions = MagicMock()

    consumer.persist_credit(transactions, CREDIT_EVENT["data"])

    transactions.update_one.assert_called_once()
    args, kwargs = transactions.update_one.call_args
    assert args[0] == {"credit_id": "user-123"}
    assert "$setOnInsert" in args[1]
    assert args[1]["$setOnInsert"]["status"] == "CONFIRMED"
    assert args[1]["$setOnInsert"]["block_index"] is None
    assert kwargs["upsert"] is True


def test_process_credit_event_parses_envelope_and_persists():
    transactions = MagicMock()

    consumer.process_credit_event(transactions, json.dumps(CREDIT_EVENT).encode())

    transactions.update_one.assert_called_once()
    assert transactions.update_one.call_args[0][0] == {"credit_id": "user-123"}


def test_ensure_indexes_creates_unique_sparse_index_on_credit_id():
    transactions = MagicMock()

    consumer.ensure_indexes(transactions)

    transactions.create_index.assert_called_once_with(
        "credit_id",
        unique=True,
        sparse=True,
        name="transactions_credit_id_unique",
    )


def test_callback_acks_on_success():
    transactions = MagicMock()
    channel = MagicMock()
    method = MagicMock(delivery_tag=7)
    callback = consumer._build_callback(transactions)

    callback(channel, method, None, json.dumps(CREDIT_EVENT).encode())

    channel.basic_ack.assert_called_once_with(delivery_tag=7)
    channel.basic_nack.assert_not_called()


def test_callback_nacks_without_requeue_on_error():
    transactions = MagicMock()
    channel = MagicMock()
    method = MagicMock(delivery_tag=9)
    callback = consumer._build_callback(transactions)

    callback(channel, method, None, b"not-json")

    channel.basic_ack.assert_not_called()
    channel.basic_nack.assert_called_once_with(delivery_tag=9, requeue=False)
