import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from bson import ObjectId

from src.workers import block_mined_consumer as consumer


TRANSACTION_ID = "683f1a2b3c4d5e6f7a8b9c0d"


BLOCK = {
    "index": 1,
    "timestamp": "2026-06-25T12:00:00Z",
    "transactions": [
        {
            "from": "alice",
            "to": "bob",
            "amount": 10,
            "timestamp": "2026-06-25T11:59:00Z",
        }
    ],
    "previous_hash": "0" * 64,
    "nonce": 42,
    "hash": "a" * 64,
}

BLOCK_MINED_EVENT = {
    "event_type": "block.mined",
    "occurred_at": "2026-06-25T12:00:00Z",
    "source": "mining-service",
    "data": BLOCK,
}


def test_persist_block_upserts_idempotently_by_hash():
    blocks = MagicMock()

    consumer.persist_block(blocks, BLOCK)

    blocks.update_one.assert_called_once_with(
        {"hash": "a" * 64},
        {"$setOnInsert": BLOCK},
        upsert=True,
    )


def test_process_block_mined_event_parses_envelope_and_persists():
    blocks = MagicMock()

    consumer.process_block_mined_event(blocks, json.dumps(BLOCK_MINED_EVENT).encode())

    blocks.update_one.assert_called_once()
    assert blocks.update_one.call_args[0][0] == {"hash": "a" * 64}


def test_confirm_block_transactions_marks_matching_transactions_confirmed():
    transactions = MagicMock()
    block = {
        **BLOCK,
        "transactions": [
            {"transaction_id": TRANSACTION_ID, "amount": 10},
            {"amount": 5},
        ],
    }

    consumer.confirm_block_transactions(transactions, block)

    transactions.update_one.assert_called_once_with(
        {"_id": ObjectId(TRANSACTION_ID)},
        {"$set": {"status": "CONFIRMED", "block_index": 1}},
    )


def test_process_block_mined_event_confirms_transactions_when_collection_is_provided():
    blocks = MagicMock()
    transactions = MagicMock()
    block = {
        **BLOCK,
        "transactions": [{"transaction_id": TRANSACTION_ID, "amount": 10}],
    }
    event = {**BLOCK_MINED_EVENT, "data": block}

    consumer.process_block_mined_event(blocks, json.dumps(event).encode(), transactions)

    blocks.update_one.assert_called_once()
    transactions.update_one.assert_called_once_with(
        {"_id": ObjectId(TRANSACTION_ID)},
        {"$set": {"status": "CONFIRMED", "block_index": 1}},
    )


def test_ensure_indexes_creates_unique_index_on_hash():
    blocks = MagicMock()

    consumer.ensure_indexes(blocks)

    blocks.create_index.assert_called_once_with(
        "hash",
        unique=True,
        name="blocks_hash_unique",
    )


def test_handle_message_acks_on_success():
    blocks = MagicMock()
    message = AsyncMock()
    message.body = json.dumps(BLOCK_MINED_EVENT).encode()

    asyncio.run(consumer._handle_message(blocks, message))

    message.ack.assert_awaited_once()
    message.nack.assert_not_awaited()


def test_handle_message_nacks_without_requeue_on_error():
    blocks = MagicMock()
    message = AsyncMock()
    message.body = b"not-json"

    asyncio.run(consumer._handle_message(blocks, message))

    message.ack.assert_not_awaited()
    message.nack.assert_awaited_once_with(requeue=False)


def test_handle_message_acks_duplicate_key_as_consensus_rejection(monkeypatch):
    from pymongo.errors import DuplicateKeyError

    blocks = MagicMock()
    message = AsyncMock()
    message.body = json.dumps(BLOCK_MINED_EVENT).encode()

    def raise_duplicate_key(*_args, **_kwargs):
        raise DuplicateKeyError("duplicate index", code=11000)

    monkeypatch.setattr(consumer, "process_block_mined_event", raise_duplicate_key)

    asyncio.run(consumer._handle_message(blocks, message))

    message.ack.assert_awaited_once()
    message.nack.assert_not_awaited()
