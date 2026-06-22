from unittest.mock import MagicMock, patch

from src.core.constants import TRANSACTION_EVENT_ROUTING_KEY
from src.services.transaction_service import TransactionService


FROM_ADDRESS = "a" * 40
TO_ADDRESS = "b" * 40


def make_db_client():
    client = MagicMock()
    db = MagicMock()
    transactions = MagicMock()
    blocks = MagicMock()

    client.__getitem__.return_value = db
    db.__getitem__.side_effect = {
        "transactions": transactions,
        "blocks": blocks,
        "chain_metadata": MagicMock(),
    }.__getitem__

    blocks.find.return_value = [
        {
            "transactions": [
                {
                    "from": "SYSTEM",
                    "to": FROM_ADDRESS,
                    "amount": 100.0,
                    "type": "GENESIS",
                    "status": "CONFIRMED",
                }
            ]
        }
    ]
    transactions.find.return_value = []
    transactions.count_documents.return_value = 0
    insert_result = MagicMock()
    insert_result.inserted_id = "tx-created-123"
    transactions.insert_one.return_value = insert_result

    return client, transactions


def test_create_transfer_persists_transaction_and_publishes_domain_event():
    db_client, transactions = make_db_client()
    publisher = MagicMock()
    wallet_service = MagicMock()
    wallet_service.check_wallet_exist.return_value = True

    with (
        patch("src.services.transaction_service.RabbitMQPublisher", return_value=publisher),
        patch("src.services.transaction_service.ExternalWalletService", return_value=wallet_service),
    ):
        service = TransactionService(db_client)
        result = service.create_transfer(
            {
                "from": FROM_ADDRESS,
                "to": TO_ADDRESS,
                "amount": 25.0,
                "type": "TRANSFER",
                "timestamp": "2026-04-13T12:00:00Z",
            }
        )

    assert result["_id"] == "tx-created-123"
    transactions.insert_one.assert_called_once()
    wallet_service.check_wallet_exist.assert_any_call(FROM_ADDRESS)
    wallet_service.check_wallet_exist.assert_any_call(TO_ADDRESS)
    publisher.publish_transaction.assert_called_once()

    event = publisher.publish_transaction.call_args.args[0]
    assert event["event_type"] == TRANSACTION_EVENT_ROUTING_KEY
    assert event["source"] == "transaction-service"
    assert event["occurred_at"].endswith("Z")
    assert event["data"] == {
        "transaction_id": "tx-created-123",
        "from": FROM_ADDRESS,
        "to": TO_ADDRESS,
        "amount": 25.0,
        "timestamp": "2026-04-13T12:00:00Z",
        "type": "TRANSFER",
        "status": "PENDING",
    }


def test_create_transfer_does_not_fail_when_event_publication_fails():
    db_client, _transactions = make_db_client()
    publisher = MagicMock()
    publisher.publish_transaction.side_effect = RuntimeError("broker unavailable")
    wallet_service = MagicMock()
    wallet_service.check_wallet_exist.return_value = True

    with (
        patch("src.services.transaction_service.RabbitMQPublisher", return_value=publisher),
        patch("src.services.transaction_service.ExternalWalletService", return_value=wallet_service),
    ):
        service = TransactionService(db_client)
        result = service.create_transfer(
            {
                "from": FROM_ADDRESS,
                "to": TO_ADDRESS,
                "amount": 25.0,
                "type": "TRANSFER",
                "timestamp": "2026-04-13T12:00:00Z",
            }
        )

    assert result["_id"] == "tx-created-123"
    publisher.publish_transaction.assert_called_once()
