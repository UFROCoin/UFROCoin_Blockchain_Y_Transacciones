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
