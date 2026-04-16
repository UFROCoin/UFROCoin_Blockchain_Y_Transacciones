import logging
from datetime import datetime, timezone
from importlib import import_module
from typing import Any
from uuid import uuid4

from src.core.constants import (
    CHAIN_METADATA_ID,
    GENESIS_BLOCK_INDEX,
    GENESIS_EVENT_ROUTING_KEY,
    GENESIS_PREVIOUS_HASH,
    GENESIS_TRANSACTION_TYPE,
    REWARD_POOL,
    SYSTEM_ADDRESS,
    SYSTEM_REWARD,
)
from src.core.database import get_chain_metadata_collection
from src.core.rabbitmq_publisher import publish_event
from src.models.block import Block
from src.models.chain_metadata import ChainMetadata
from src.services.block_service import BlockService
from src.utils.hash_utils import calculate_block_hash

LOGGER = logging.getLogger(__name__)


def _is_duplicate_key_error(exc: Exception) -> bool:
    try:
        pymongo_errors = import_module("pymongo.errors")
    except ImportError:
        return False
    return isinstance(exc, pymongo_errors.DuplicateKeyError)


class GenesisService:
    def __init__(self, block_service: BlockService | None = None) -> None:
        self.block_service = block_service or BlockService()
        self.chain_metadata_collection = get_chain_metadata_collection()

    def create_genesis_if_needed(self) -> dict[str, Any] | None:
        metadata = self.chain_metadata_collection.find_one({"_id": CHAIN_METADATA_ID})
        if metadata and metadata.get("genesis_created"):
            return None

        last_block = self.block_service.get_last_block()
        if last_block is not None:
            self._sync_metadata_from_existing_chain(last_block)
            return None

        genesis_transaction = self.build_genesis_transaction()
        genesis_block = self.build_genesis_block(genesis_transaction)
        genesis_block_document = genesis_block.model_dump(exclude_none=True)

        try:
            self.block_service.create_genesis_block(genesis_block)
        except Exception as exc:  # noqa: BLE001
            if not _is_duplicate_key_error(exc):
                raise
            LOGGER.warning("Genesis block ya existe; omitiendo recreacion")
            return None

        genesis_block_hash = genesis_block_document["hash"]

        metadata_model = ChainMetadata(
            genesis_created=True,
            last_block_index=genesis_block.index,
            last_block_hash=genesis_block_hash,
            total_blocks=1,
        )
        self.chain_metadata_collection.update_one(
            {"_id": CHAIN_METADATA_ID},
            {"$set": metadata_model.model_dump()},
            upsert=True,
        )

        event_payload = self._build_genesis_created_event(genesis_block_document)
        try:
            publish_event(GENESIS_EVENT_ROUTING_KEY, event_payload)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("No se pudo publicar genesis.created: %s", exc)

        return genesis_block_document

    def build_genesis_transaction(self) -> dict[str, Any]:
        timestamp = self._utc_now_iso()
        return {
            "tx_id": f"genesis-{uuid4().hex}",
            "type": GENESIS_TRANSACTION_TYPE,
            "from_address": SYSTEM_ADDRESS,
            "to_address": REWARD_POOL,
            "amount": SYSTEM_REWARD,
            "timestamp": timestamp,
            "metadata": {
                "reason": "initial_system_issuance",
            },
        }

    def build_genesis_block(self, genesis_transaction: dict[str, Any]) -> Block:
        timestamp = self._utc_now_iso()
        block = Block(
            index=GENESIS_BLOCK_INDEX,
            previous_hash=GENESIS_PREVIOUS_HASH,
            timestamp=timestamp,
            transactions=[genesis_transaction],
            nonce=0,
        )
        block.hash = calculate_block_hash(block.model_dump(exclude_none=True))
        return block

    def _sync_metadata_from_existing_chain(self, last_block: dict[str, Any]) -> None:
        total_blocks = self.block_service.blocks_collection.count_documents({})
        metadata_model = ChainMetadata(
            genesis_created=True,
            last_block_index=last_block["index"],
            last_block_hash=last_block["hash"],
            total_blocks=total_blocks,
        )
        self.chain_metadata_collection.update_one(
            {"_id": CHAIN_METADATA_ID},
            {"$set": metadata_model.model_dump()},
            upsert=True,
        )

    def _build_genesis_created_event(self, genesis_block: dict[str, Any]) -> dict[str, Any]:
        return {
            "event_type": GENESIS_EVENT_ROUTING_KEY,
            "occurred_at": self._utc_now_iso(),
            "source": "blockchain-core",
            "data": {
                "block_index": genesis_block["index"],
                "block_hash": genesis_block["hash"],
                "previous_hash": genesis_block["previous_hash"],
                "transaction_count": len(genesis_block["transactions"]),
                "genesis_created": True,
            },
        }

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
