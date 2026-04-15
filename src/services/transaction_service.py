from src.models.transaction import Transaction
from src.core.rabbitmq_publisher import RabbitMQPublisher

# --- Lógica de Negocio ---

class TransactionService:
    def __init__(self, db_client):
        self.db = db_client.blockchain_db
        self.publisher = RabbitMQPublisher()

    # --- Gestión de Transferencias ---

    def create_transfer(self, transaction_data: dict) -> dict:
        new_transaction = Transaction(**transaction_data)
        transaction_dict = new_transaction.model_dump(by_alias=True)
        
        result = self.db.transacciones.insert_one(transaction_dict)
        transaction_dict["_id"] = str(result.inserted_id)

        self.publisher.publish_transaction({
            "transaction_id": transaction_dict["_id"],
            "from": transaction_dict["from"],
            "to": transaction_dict["to"],
            "amount": transaction_dict["amount"],
            "timestamp": transaction_dict["timestamp"]
        })

        return transaction_dict