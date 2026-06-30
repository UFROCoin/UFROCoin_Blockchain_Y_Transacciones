from bson import ObjectId

from src.services import history_service


def test_wallet_history_excludes_block_anchored_transaction_copies(monkeypatch):
    wallet = "a1b2c3d4e5f678901234567890abcdef12345678"
    recipient = "b1b2c3d4e5f678901234567890abcdef12345678"
    mined_tx_id = "683f1a2b3c4d5e6f7a8b9c0d"

    captured_query = {}

    class TransactionsCollection:
        def find(self, query):
            captured_query.update(query)
            return [
                {
                    "_id": ObjectId("683f1a2b3c4d5e6f7a8b9c0e"),
                    "from": wallet,
                    "to": recipient,
                    "amount": 5.0,
                    "type": "TRANSFER",
                    "status": "PENDING",
                    "timestamp": "2026-06-29T10:00:00+00:00",
                    "block_index": None,
                },
                {
                    "_id": ObjectId("683f1a2b3c4d5e6f7a8b9c0f"),
                    "from": "SYSTEM",
                    "to": wallet,
                    "amount": 100.0,
                    "type": "GENESIS",
                    "status": "CONFIRMED",
                    "timestamp": "2026-06-29T09:00:00+00:00",
                    "block_index": None,
                },
            ]

    class BlocksCollection:
        def find(self, _query):
            return [
                {
                    "index": 3,
                    "transactions": [
                        {
                            "id": mined_tx_id,
                            "from": wallet,
                            "to": recipient,
                            "amount": 25.0,
                            "type": "TRANSFER",
                            "timestamp": "2026-06-29T11:00:00+00:00",
                        }
                    ],
                }
            ]

    monkeypatch.setattr(
        history_service,
        "get_transactions_collection",
        lambda: TransactionsCollection(),
    )
    monkeypatch.setattr(
        history_service,
        "get_blocks_collection",
        lambda: BlocksCollection(),
    )

    history = history_service.get_wallet_history(wallet)

    assert captured_query == {
        "$or": [{"from": wallet}, {"to": wallet}],
        "block_index": None,
    }
    assert sum(1 for tx in history if tx.get("id") == mined_tx_id) == 1
    assert any(tx["type"] == "GENESIS" and tx["status"] == "CONFIRMED" for tx in history)
    assert any(tx["type"] == "TRANSFER" and tx["status"] == "PENDING" for tx in history)

    mined_tx = next(tx for tx in history if tx.get("id") == mined_tx_id)
    assert mined_tx["status"] == "CONFIRMED"
    assert mined_tx["block_index"] == 3
