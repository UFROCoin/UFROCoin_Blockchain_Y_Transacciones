from typing import Any
from importlib import import_module

from src.core.database import get_blocks_collection
from src.models.block import Block


class BlockService:
    def __init__(self) -> None:
        self.blocks_collection = get_blocks_collection()

    def get_last_block(self) -> dict[str, Any] | None:
        try:
            pymongo = import_module("pymongo")
        except ImportError as exc:
            raise RuntimeError("pymongo is required to query blocks") from exc
        return self.blocks_collection.find_one(sort=[("index", pymongo.DESCENDING)])

    def create_genesis_block(self, block: Block) -> dict[str, Any]:
        return self.save_block(block)

    def save_block(self, block: Block | dict[str, Any]) -> dict[str, Any]:
        block_document = block.model_dump(exclude_none=True) if isinstance(block, Block) else block
        self.blocks_collection.insert_one(block_document)
        return block_document

    def get_chain(self, page: int = 1, limit: int = 10) -> tuple[list[dict[str, Any]], int]:
        """
        Retorna bloques en orden cronológico (index ASC) con paginación.

        Parámetros:
            page: número de página (base 1).
            limit: cantidad máxima de bloques por página.

        Retorna:
            Tupla (lista_de_bloques, total_de_bloques_en_la_cadena).
        """
        try:
            pymongo = import_module("pymongo")
        except ImportError as exc:
            raise RuntimeError("pymongo is required to query the chain") from exc

        skip = (page - 1) * limit
        total = self.blocks_collection.count_documents({})
        cursor = self.blocks_collection.find(
            {},
            {"_id": 0},  # excluir _id interno de MongoDB de la respuesta
        ).sort("index", pymongo.ASCENDING).skip(skip).limit(limit)
        return [self._with_confirmed_transaction_indexes(block) for block in cursor], total

    def get_block_by_index(self, index: int) -> dict[str, Any] | None:
        block = self.blocks_collection.find_one({"index": index}, {"_id": 0})
        if block is None:
            return None
        return self._with_confirmed_transaction_indexes(block)

    def get_block_by_hash(self, block_hash: str) -> dict[str, Any] | None:
        block = self.blocks_collection.find_one({"hash": block_hash}, {"_id": 0})
        if block is None:
            return None
        return self._with_confirmed_transaction_indexes(block)

    def get_chain_stats(self) -> dict[str, Any]:
        """
        Calcula estadísticas en tiempo real recorriendo todos los bloques de la cadena.

        Retorna:
            Diccionario con total_blocks, last_block_time, total_transactions
            y total_ufrocoins_emitidos.
        """
        try:
            pymongo = import_module("pymongo")
        except ImportError as exc:
            raise RuntimeError("pymongo is required to query the chain") from exc

        total_blocks = self.blocks_collection.count_documents({})
        total_transactions = 0
        total_ufrocoins_emitidos = 0.0
        last_block_time: str | None = None

        # Obtener timestamp del último bloque (índice más alto)
        last_block = self.blocks_collection.find_one(
            {}, {"timestamp": 1, "_id": 0}, sort=[("index", pymongo.DESCENDING)]
        )
        if last_block:
            last_block_time = last_block.get("timestamp")

        # Recorrer toda la cadena acumulando transacciones y montos
        cursor = self.blocks_collection.find({}, {"transactions": 1, "_id": 0})
        for block in cursor:
            for tx in block.get("transactions", []):
                if isinstance(tx, dict):
                    total_transactions += 1
                    total_ufrocoins_emitidos += float(tx.get("amount", 0.0))

        return {
            "total_blocks": total_blocks,
            "last_block_time": last_block_time,
            "total_transactions": total_transactions,
            "total_ufrocoins_emitidos": total_ufrocoins_emitidos,
        }

    @staticmethod
    def _with_confirmed_transaction_indexes(block: dict[str, Any]) -> dict[str, Any]:
        block_document = dict(block)
        block_index = block_document.get("index")
        transactions = []

        for transaction in block_document.get("transactions", []):
            if not isinstance(transaction, dict):
                transactions.append(transaction)
                continue

            transaction_document = dict(transaction)
            transaction_document.setdefault("status", "CONFIRMED")
            transaction_document["block_index"] = block_index
            transactions.append(transaction_document)

        block_document["transactions"] = transactions
        return block_document
