from datetime import datetime, timezone
import logging

from src.core.constants import TRANSACTION_EVENT_ROUTING_KEY
from src.core.database import (
    get_blocks_collection_name,
    get_database_name,
    get_transactions_collection_name,
)
from src.models.transaction import Transaction
from src.core.rabbitmq_publisher import RabbitMQPublisher
from src.services.external_wallet_service import ExternalWalletService

LOGGER = logging.getLogger(__name__)

# --- Inicialización de servicio ---

class TransactionService:
    def __init__(self, db_client):
        database = db_client[get_database_name()]
        self.blocks_collection = database[get_blocks_collection_name()]
        self.transactions_collection = database[get_transactions_collection_name()]
        self.publisher = RabbitMQPublisher()
        self.wallet_service = ExternalWalletService()
    
    # --- Validaciones ---

    def calculate_balance(self, address: str) -> float:
        balance = 0.0

        blocks = self.blocks_collection.find()
        for block in blocks:
            for tx in block.get("transactions", []):
                tx_to = tx.get("to") or tx.get("to_address")
                tx_from = tx.get("from") or tx.get("from_address")
                if tx_to == address:
                    balance += tx.get("amount", 0.0)
                if tx_from == address:
                    balance -= tx.get("amount", 0.0)

        # Créditos de emisión off-chain (wallet.credit.issued): confirmados pero no minados.
        genesis_credits = self.transactions_collection.find(
            {"to": address, "status": "CONFIRMED", "block_index": None}
        )
        for tx in genesis_credits:
            balance += tx.get("amount", 0.0)

        pending_txs = self.transactions_collection.find({"from": address, "status": "PENDING"})
        for tx in pending_txs:
            balance -= tx.get("amount", 0.0)

        return balance

    # --- Gestión de Transferencias ---

    def create_transfer(self, transaction_data: dict) -> dict:
        amount = transaction_data.get("amount", 0.0)

        # Validación de monto
        if amount <= 0:
            raise ValueError("El monto de la transacción debe ser mayor a cero")
        
        # Validación de decimales
        if "." in str(amount) and len(str(amount).split(".")[1]) > 2:
            raise ValueError("El monto de la transacción no puede tener más de 2 decimales")
        
        # Validación de existencia de wallets
        if not self.wallet_service.check_wallet_exist(transaction_data.get("from")):
            raise ValueError("La wallet de origen es invalida o no existe")
        
        # Validación de existencia de wallet destino
        if not self.wallet_service.check_wallet_exist(transaction_data.get("to")):
            raise ValueError("La wallet de destino es invalida o no existe")
        
        # Validación de transacciones pendientes
        from_address = transaction_data.get("from")
        pending_count = self.transactions_collection.count_documents({"from": from_address, "status": "PENDING"})
        if pending_count >= 10:
            raise ValueError("No se pueden crear más de 10 transacciones pendientes para la misma wallet de origen")
        
        # Validación de saldo suficiente
        if transaction_data.get("type") == "TRANSFER":
            current_balance = self.calculate_balance(transaction_data.get("from"))
            if current_balance < transaction_data.get("amount"):
                raise ValueError(f"Saldo insuficiente. Saldo disponible: {current_balance}")
            
        # --- Creación de transacción ---
        new_transaction = Transaction(**transaction_data)
        transaction_dict = new_transaction.model_dump(by_alias=True)
        
        # Guardar transacción en la base de datos
        result = self.transactions_collection.insert_one(transaction_dict)
        transaction_dict["_id"] = str(result.inserted_id)

        # Publicar evento de transacción creada
        try:
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
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("No se pudo publicar transaction.created: %s", exc)

        return transaction_dict

    def get_pending_transactions(self) -> list[dict]:
        pending_txs = self.transactions_collection.find({"status": "PENDING"})

        return [
            {
                "id": str(tx.get("_id", "")),
                "from": tx.get("from"),
                "to": tx.get("to"),
                "amount": tx.get("amount"),
                "timestamp": tx.get("timestamp"),
            }
            for tx in pending_txs
        ]

    def get_transaction_by_id(self, transaction_id: str) -> dict | None:
        """Busca una transacción por su ID en el mempool y en los bloques confirmados."""
        from bson import ObjectId
        from bson.errors import InvalidId

        # 1. Buscar en el mempool (colección transactions)
        try:
            obj_id = ObjectId(transaction_id)
        except (InvalidId, Exception):
            obj_id = None

        if obj_id is not None:
            tx = self.transactions_collection.find_one({"_id": obj_id})
            if tx is not None:
                return {
                    "id": str(tx["_id"]),
                    "from": tx.get("from"),
                    "to": tx.get("to"),
                    "amount": tx.get("amount"),
                    "type": tx.get("type", "TRANSFER"),
                    "status": tx.get("status", "PENDING"),
                    "timestamp": tx.get("timestamp"),
                    "block_index": tx.get("block_index"),
                }

        # 2. Buscar en las transacciones dentro de los bloques confirmados
        blocks = self.blocks_collection.find()
        for block in blocks:
            for tx in block.get("transactions", []):
                tx_id = tx.get("id") or str(tx.get("_id", ""))
                if tx_id == transaction_id:
                    return {
                        "id": tx_id,
                        "from": tx.get("from"),
                        "to": tx.get("to"),
                        "amount": tx.get("amount"),
                        "type": tx.get("type", "TRANSFER"),
                        "status": "CONFIRMED",
                        "timestamp": tx.get("timestamp"),
                        "block_index": block.get("index"),
                    }

        return None
    
    #--- Historial de Transacciones ---

    def get_transaction_history(self, address: str) -> list:
        history = []

        blocks = self.blocks_collection.find()
        for block in blocks:
            for tx in block.get("transactions", []):
                if tx.get("from") == address or tx.get("to") == address:
                    tx_type = tx.get("type")
                    if tx_type == "TRANSFER":
                        tx_type = "SEND" if tx.get("from") == address else "RECEIVE"

                    history.append({
                        "_id": str(tx.get("id", "")),
                        "type": tx_type,
                        "from": tx.get("from"),
                        "to": tx.get("to"),
                        "amount": float(tx.get("amount", 0.00)),
                        "timestamp": tx.get("timestamp"),
                        "status": "CONFIRMED"
                    })

        pending_txs = self.transactions_collection.find({
            "$or": [{"from": address}, {"to": address}]
        })
        for tx in pending_txs:
            tx_type = tx.get("type")
            if tx_type == "TRANSFER":
                tx_type = "SEND" if tx.get("from") == address else "RECEIVE"

                history.append({
                    "_id": str(tx.get("_id")),
                    "type": tx_type,
                    "from": tx.get("from"),
                    "to": tx.get("to"),
                    "amount": float(tx.get("amount", 0.00)),
                    "timestamp": tx.get("timestamp"),
                    "status": tx.get("status", "PENDING")
                })
        
        history.sort(key=lambda item: item.get("timestamp",""), reverse=True)
        return history
