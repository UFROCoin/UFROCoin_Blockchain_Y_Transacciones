import hashlib
import json
import re
from datetime import datetime
from typing import Any

from src.models.block import BlockValidationRequest


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
    def __init__(self, db_client: Any | None = None):
        self.db = None
        if db_client is not None:
            self.db = db_client.blockchain_db

    def calculate_block_hash(self, block_data: BlockValidationRequest | dict[str, Any]) -> str:
        normalized_block_data = self._normalize_block_data(block_data)

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

    def validate_block_structure(self, block_data: BlockValidationRequest | dict[str, Any]) -> bool:
        normalized_block_data = self._normalize_block_data(block_data)

        if not isinstance(normalized_block_data, dict):
            return False

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

    def validate_block_integrity(self, block_data: BlockValidationRequest | dict[str, Any]) -> bool:
        normalized_block_data = self._normalize_block_data(block_data)

        # Verifica estructura y consistencia del hash recalculado.
        if not self.validate_block_structure(normalized_block_data):
            return False

        computed_hash = self.calculate_block_hash(normalized_block_data)
        return computed_hash == normalized_block_data["hash"].lower()

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
