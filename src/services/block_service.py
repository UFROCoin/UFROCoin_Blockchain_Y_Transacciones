from typing import Any
from importlib import import_module

from src.core.database import get_blocks_collection


class BlockService:
    def __init__(self) -> None:
        self.blocks_collection = get_blocks_collection()

    def get_last_block(self) -> dict[str, Any] | None:
        try:
            pymongo = import_module("pymongo")
        except ImportError as exc:
            raise RuntimeError("pymongo is required to query blocks") from exc
        return self.blocks_collection.find_one(sort=[("index", pymongo.DESCENDING)])

    def create_genesis_block(self, block: dict[str, Any]) -> dict[str, Any]:
        return self.save_block(block)

    def save_block(self, block: dict[str, Any]) -> dict[str, Any]:
        self.blocks_collection.insert_one(block)
        return block
