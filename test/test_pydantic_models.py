import pytest
from pydantic import ValidationError

from src.models.block import (
    BlockData,
    ChainStatsResponse,
    ChainSuccessResponse,
    ChainValidateResponse,
)
from src.models.chain_metadata import ChainMetadata
from src.models.history import TransactionHistoryItem
from src.models.transaction import (
    PendingTransactionData,
    PendingTransactionsResponse,
    Transaction,
    TransactionDetail,
)


VALID_HASH = "a" * 64


def test_transaction_accepts_valid_contract_with_aliases():
    transaction = Transaction(
        **{
            "from": "wallet-a",
            "to": "wallet-b",
            "amount": 10.5,
            "type": "TRANSFER",
            "status": "PENDING",
        }
    )

    assert transaction.sender == "wallet-a"
    assert transaction.receiver == "wallet-b"
    assert transaction.model_dump(by_alias=True)["from"] == "wallet-a"


@pytest.mark.parametrize("amount", [0, -1])
def test_transaction_rejects_non_positive_amount(amount):
    with pytest.raises(ValidationError):
        Transaction(**{"from": "wallet-a", "to": "wallet-b", "amount": amount})


def test_transaction_rejects_invalid_type():
    with pytest.raises(ValidationError):
        Transaction(**{"from": "wallet-a", "to": "wallet-b", "amount": 1, "type": "BAD"})


def test_transaction_rejects_invalid_status():
    with pytest.raises(ValidationError):
        Transaction(
            **{"from": "wallet-a", "to": "wallet-b", "amount": 1, "status": "BAD"}
        )


def test_pending_transaction_response_contract():
    item = PendingTransactionData(
        **{
            "id": "tx-1",
            "from": "wallet-a",
            "to": "wallet-b",
            "amount": 1.25,
            "timestamp": "2026-06-03T22:45:00+00:00",
        }
    )
    response = PendingTransactionsResponse(status="ok", data=[item])

    assert response.status == "ok"
    assert response.data[0].sender == "wallet-a"


def test_pending_transactions_response_rejects_non_ok_status():
    with pytest.raises(ValidationError):
        PendingTransactionsResponse(status="error", data=[])


def valid_transaction_detail_payload() -> dict:
    return {
        "id": "683f1a2b3c4d5e6f7a8b9c0d",
        "from": "wallet-a",
        "to": "wallet-b",
        "amount": 25.0,
        "type": "TRANSFER",
        "status": "CONFIRMED",
        "timestamp": "2026-06-03T22:45:00+00:00",
        "block_index": 3,
    }


def test_transaction_detail_accepts_aliases_and_serializes_aliases():
    detail = TransactionDetail(**valid_transaction_detail_payload())

    assert detail.sender == "wallet-a"
    assert detail.receiver == "wallet-b"
    assert detail.model_dump(by_alias=True)["to"] == "wallet-b"


def test_transaction_detail_forbids_extra_fields():
    payload = valid_transaction_detail_payload()
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        TransactionDetail(**payload)


def test_transaction_detail_rejects_negative_block_index():
    payload = valid_transaction_detail_payload()
    payload["block_index"] = -1

    with pytest.raises(ValidationError):
        TransactionDetail(**payload)


def test_block_data_accepts_valid_contract():
    block = BlockData(
        index=0,
        timestamp="2026-04-13T18:45:00Z",
        transactions=[],
        previous_hash=VALID_HASH,
        nonce=0,
        hash=VALID_HASH,
    )

    assert block.index == 0
    assert block.hash == VALID_HASH


@pytest.mark.parametrize("field", ["previous_hash", "hash"])
def test_block_data_rejects_invalid_hashes(field):
    payload = {
        "index": 0,
        "timestamp": "2026-04-13T18:45:00Z",
        "transactions": [],
        "previous_hash": VALID_HASH,
        "nonce": 0,
        "hash": VALID_HASH,
    }
    payload[field] = "not-a-sha256"

    with pytest.raises(ValidationError):
        BlockData(**payload)


@pytest.mark.parametrize("field", ["index", "nonce"])
def test_block_data_rejects_negative_numbers(field):
    payload = {
        "index": 0,
        "timestamp": "2026-04-13T18:45:00Z",
        "transactions": [],
        "previous_hash": VALID_HASH,
        "nonce": 0,
        "hash": VALID_HASH,
    }
    payload[field] = -1

    with pytest.raises(ValidationError):
        BlockData(**payload)


def test_chain_success_response_contract():
    response = ChainSuccessResponse(success=True, message="ok", data=[], error=None)

    assert response.success is True
    assert response.error is None


def test_chain_stats_response_contract():
    response = ChainStatsResponse(
        status="ok",
        data={
            "total_blocks": 1,
            "last_block_time": "2026-04-13T18:45:00Z",
            "total_transactions": 2,
            "total_ufrocoins_emitidos": 100.0,
        },
    )

    assert response.status == "ok"
    assert response.data.total_blocks == 1


def test_chain_validate_response_contract():
    response = ChainValidateResponse(valid=False, error_at_block=2)

    assert response.valid is False
    assert response.error_at_block == 2


def test_chain_metadata_accepts_contract_and_ignores_extra_fields():
    metadata = ChainMetadata(
        genesis_created=True,
        last_block_index=0,
        last_block_hash=VALID_HASH,
        total_blocks=1,
        ignored="value",
    )

    assert metadata.genesis_created is True
    assert "ignored" not in metadata.model_dump()


def test_transaction_history_item_accepts_id_alias():
    item = TransactionHistoryItem(
        **{
            "_id": "tx-1",
            "type": "SEND",
            "from": "wallet-a",
            "to": "wallet-b",
            "amount": 5.0,
            "timestamp": "2026-06-03T22:45:00+00:00",
            "status": "CONFIRMED",
        }
    )

    assert item.id == "tx-1"
    assert item.from_address == "wallet-a"
