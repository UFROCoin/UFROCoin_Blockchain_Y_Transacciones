from datetime import datetime, timezone

from src.core.constants import TRANSACTION_EVENT_ROUTING_KEY
from src.models.transaction import Transaction
from src.core.rabbitmq_publisher import RabbitMQPublisher
from src.services.external_wallet_service import ExternalWalletService

# --- Lógica de Negocio ---

class TransactionService:
    def __init__(self, db_client):
        self.db = db_client.blockchain_db
        self.publisher = RabbitMQPublisher()
        self.wallet_service = ExternalWalletService
    
    # --- Validaciones ---

    def calculate_balance(self, address: str) -> float:
        balance = 0.0

        block = self.db.blocks.find()
        for block in blocks:
            for tx in block.get("transactions", []):
                if tx.get("to") == address:
                    balance += tx.get("amount", 0.0)
                if tx.get("from") == address:
                    balance -= tx.get("amount", 0.0)

        pending_txs = self.dpending_txs = self.db.transacciones.find({"from": address, "status": "PENDING"})
        for tx in pending_txs:
            balance -= tx.get("amount", 0.0)

        return balance

    # --- Gestión de Transferencias ---

    def create_transfer(self, transaction_data: dict) -> dict:
        if not self.wallet_service.check_wallet_exist(transaction_data.get("to")):
            raise ValueError("La wallet de destino es invalida o no existe")
        
        if transaction_data.get("type") == "TRANSFER":
            current_balance = self.calculate_balance(transaction_data.get("from"))
            if current_balance < transaction_data.get("amount"):
                raise ValueError(f"Saldo insuficiente. Saldo disponible: {current_balance}")


        new_transaction = Transaction(**transaction_data)
        transaction_dict = new_transaction.model_dump(by_alias=True)
        
        result = self.db.transacciones.insert_one(transaction_dict)
        transaction_dict["_id"] = str(result.inserted_id)

        self.publisher.publish_transaction(
            {
                "event_type": TRANSACTION_EVENT_ROUTING_KEY,
                "occurred_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "source": "transaction-service",
                "data": {
                    "transaction_id": transaction_dict["_id"],
                    "from": transaction_dict["from"],
                    "to": transaction_dict["to"],
                    "amount": transaction_dict["amount"],
                    "timestamp": transaction_dict["timestamp"],
                    "type": transaction_dict["type"],
                    "status": transaction_dict["status"],
                },
            }
        )

        return transaction_dict
