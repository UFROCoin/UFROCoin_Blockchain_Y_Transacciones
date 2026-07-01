import hashlib
import json
import logging
import re
from datetime import datetime
from importlib import import_module
from typing import Any

logger = logging.getLogger(__name__)

from src.core.constants import GENESIS_BLOCK_INDEX, GENESIS_PREVIOUS_HASH
from src.models.block import BlockValidationRequest
from src.utils.hash_utils import calculate_concatenated_block_hash


HEX_64_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_BLOCK_FIELDS = {
    "index",
    "timestamp",
    "transactions",
    "previous_hash",
    "nonce",
    "hash",
}


def _is_iso_8601_datetime(value: str) -> bool:
    if "T" not in value:
        return False

    # Normaliza el sufijo Z para compatibilidad con fromisoformat.
    normalized_value = value.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(normalized_value)
        return True
    except ValueError:
        return False


class BlockValidationService:
    def __init__(self, db_client: Any | None = None, db_name: str | None = None):
        self.db = None
        if db_client is not None and db_name is not None:
            self.db = db_client[db_name]

    def validate_block_integrity(self, block_data: BlockValidationRequest | dict[str, Any]) -> bool:
        normalized_block_data = self._normalize_block_data(block_data)

        # Verifica estructura y consistencia del hash recalculado.
        if not self._validate_block_structure_from_dict(normalized_block_data):
            return False

        computed_hash = self._calculate_block_hash_from_dict(normalized_block_data)
        if computed_hash != normalized_block_data["hash"].lower():
            return False

        if self.db is not None and not self._is_next_expected_block(normalized_block_data):
            return False

        return True

    def _is_next_expected_block(self, normalized_block_data: dict[str, Any]) -> bool:
        blocks_collection = self.db["blocks"]
        block_index = normalized_block_data["index"]

        if blocks_collection.find_one({"index": block_index}, {"_id": 1}):
            return False

        last_block = blocks_collection.find_one(sort=[("index", -1)])
        if last_block is None:
            return self._is_genesis_block(normalized_block_data)

        expected_index = last_block["index"] + 1
        if block_index != expected_index:
            return False

        return normalized_block_data["previous_hash"].lower() == last_block["hash"].lower()

    def validate_chain_integrity(self) -> dict[str, Any]:
        """
        Recorre la blockchain completa de principio a fin (index ASC) y verifica:
          1. Que el hash almacenado de cada bloque coincida con el hash recalculado
             en tiempo real usando los datos crudos del bloque.
          2. Que el previous_hash de cada bloque (a partir del índice 1) coincida
             con el hash almacenado del bloque anterior (continuidad de la cadena).

        Esta operación es estrictamente read-only: no modifica ningún documento.

        Retorna un dict con:
            - chain_valid (bool): True si todos los bloques son íntegros.
            - error_at_block (int | None): Índice del primer bloque corrupto, o None.
            - total_blocks (int): Cantidad de bloques evaluados.
            - blocks (list[dict]): Detalle por bloque con index, stored_hash,
              computed_hash y valid.
        """
        if self.db is None:
            raise RuntimeError(
                "validate_chain_integrity requires a database connection. "
                "Instantiate BlockValidationService with db_client and db_name."
            )

        try:
            pymongo = import_module("pymongo")
        except ImportError as exc:
            raise RuntimeError("pymongo is required to validate the chain") from exc

        blocks_cursor = (
            self.db["blocks"]
            .find({}, {"_id": 0})
            .sort("index", pymongo.ASCENDING)
        )

        results: list[dict[str, Any]] = []
        chain_valid = True
        error_at_block: int | None = None
        previous_stored_hash: str | None = None

        for raw_block in blocks_cursor:
            block_index: int = raw_block.get("index", -1)
            stored_hash: str = raw_block.get("hash", "")
            computed_hash: str = self._calculate_block_hash_from_dict(raw_block)

            # Verificación 1: integridad individual del hash.
            hash_valid: bool = stored_hash.lower() == computed_hash.lower()

            # Verificación 2: continuidad del previous_hash (aplica desde el bloque 1).
            link_valid: bool = True
            if previous_stored_hash is not None:
                block_previous_hash: str = raw_block.get("previous_hash", "")
                link_valid = block_previous_hash.lower() == previous_stored_hash.lower()

            block_valid: bool = hash_valid and link_valid

            if not block_valid and chain_valid:
                # Registra el primer bloque corrupto encontrado.
                chain_valid = False
                error_at_block = block_index
                logger.error(
                    "Chain integrity failure detected at block %d — "
                    "hash_valid=%s, link_valid=%s",
                    block_index,
                    hash_valid,
                    link_valid,
                )

            results.append({
                "index": block_index,
                "stored_hash": stored_hash,
                "computed_hash": computed_hash,
                "valid": block_valid,
            })

            previous_stored_hash = stored_hash

        return {
            "chain_valid": chain_valid,
            "error_at_block": error_at_block,
            "total_blocks": len(results),
            "blocks": results,
        }

    @staticmethod
    def _calculate_block_hash_from_dict(normalized_block_data: dict[str, Any]) -> str:
        if BlockValidationService._is_genesis_block(normalized_block_data):
            return calculate_concatenated_block_hash(normalized_block_data)

        # Construye una carga determinística excluyendo el hash actual.
        payload = {
            "index": normalized_block_data["index"],
            "timestamp": normalized_block_data["timestamp"],
            "transactions": normalized_block_data["transactions"],
            "previous_hash": normalized_block_data["previous_hash"],
            "nonce": normalized_block_data["nonce"],
        }
        normalized_payload = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(normalized_payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _is_genesis_block(normalized_block_data: dict[str, Any]) -> bool:
        return (
            normalized_block_data.get("index") == GENESIS_BLOCK_INDEX
            and normalized_block_data.get("previous_hash") == GENESIS_PREVIOUS_HASH
        )

    @staticmethod
    def _validate_block_structure_from_dict(normalized_block_data: dict[str, Any]) -> bool:
        # Verifica existencia y completitud de campos obligatorios.
        if not REQUIRED_BLOCK_FIELDS.issubset(normalized_block_data.keys()):
            return False

        for field_name in REQUIRED_BLOCK_FIELDS:
            if normalized_block_data.get(field_name) is None:
                return False

        # Valida tipos base del bloque.
        if not isinstance(normalized_block_data["index"], int) or isinstance(
            normalized_block_data["index"], bool
        ):
            return False
        if not isinstance(normalized_block_data["timestamp"], str):
            return False
        if not isinstance(normalized_block_data["transactions"], list):
            return False
        if not isinstance(normalized_block_data["previous_hash"], str):
            return False
        if not isinstance(normalized_block_data["nonce"], int) or isinstance(
            normalized_block_data["nonce"], bool
        ):
            return False
        if not isinstance(normalized_block_data["hash"], str):
            return False

        # Valida formato ISO 8601 en timestamp.
        if not _is_iso_8601_datetime(normalized_block_data["timestamp"]):
            return False

        # Valida formato hexadecimal de 64 caracteres para hashes.
        previous_hash = normalized_block_data["previous_hash"].lower()
        current_hash = normalized_block_data["hash"].lower()

        if not HEX_64_PATTERN.fullmatch(previous_hash):
            return False
        if not HEX_64_PATTERN.fullmatch(current_hash):
            return False

        return True

    @staticmethod
    def _normalize_block_data(
        block_data: BlockValidationRequest | dict[str, Any],
    ) -> dict[str, Any]:
        # Convierte el modelo Pydantic a dict para usar una sola ruta de validación.
        if isinstance(block_data, BlockValidationRequest):
            return block_data.model_dump()
        if isinstance(block_data, dict):
            return block_data
        return {}
