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
        return list(cursor), total
