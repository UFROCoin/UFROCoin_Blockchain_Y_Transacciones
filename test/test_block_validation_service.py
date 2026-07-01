"""
Tests unitarios para src.services.block_validation_service.BlockValidationService.

Estrategia:
- validate_block_integrity: usa datos reales (hashes calculados con hash_utils) para
  confirmar que el servicio acepta bloques válidos y rechaza bloques corruptos.
- validate_chain_integrity: mockea la colección MongoDB para evitar dependencia de infra.
- Se testea también _is_iso_8601_datetime (función de módulo) de forma directa.
"""

import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest

from src.core.constants import GENESIS_BLOCK_INDEX, GENESIS_PREVIOUS_HASH
from src.services.block_validation_service import (
    BlockValidationService,
    _is_iso_8601_datetime,
)
from src.utils.hash_utils import (
    calculate_concatenated_block_hash,
    serialize_block_fields_for_concatenation,
)


# ---------------------------------------------------------------------------
# Helpers para construir bloques con hashes reales
# ---------------------------------------------------------------------------


def _build_non_genesis_hash(block_data: dict) -> str:
    """Recalcula el hash SHA-256 JSON-based para un bloque no-génesis."""
    payload = {
        "index": block_data["index"],
        "timestamp": block_data["timestamp"],
        "transactions": block_data["transactions"],
        "previous_hash": block_data["previous_hash"],
        "nonce": block_data["nonce"],
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def make_valid_genesis_block() -> dict:
    """Construye un bloque génesis cuyo hash es correcto (calculado con concatenación)."""
    block = {
        "index": GENESIS_BLOCK_INDEX,
        "timestamp": "2026-04-09T12:00:00Z",
        "transactions": [
            {
                "tx_id": "genesis-abc",
                "type": "GENESIS_ISSUANCE",
                "from_address": "SYSTEM",
                "to_address": "REWARD_POOL",
                "amount": 1_000_000,
            }
        ],
        "previous_hash": GENESIS_PREVIOUS_HASH,
        "nonce": 0,
    }
    block["hash"] = calculate_concatenated_block_hash(block)
    return block


def make_valid_non_genesis_block(previous_hash: str, index: int = 1) -> dict:
    """Construye un bloque no-génesis cuyo hash es correcto (SHA-256 JSON-based)."""
    block = {
        "index": index,
        "timestamp": "2026-04-10T10:00:00Z",
        "transactions": [],
        "previous_hash": previous_hash,
        "nonce": 48271,
    }
    block["hash"] = _build_non_genesis_hash(block)
    return block


# ---------------------------------------------------------------------------
# _is_iso_8601_datetime (función de módulo)
# ---------------------------------------------------------------------------


class TestIsIso8601Datetime:
    """Validación del formato ISO 8601 para el campo timestamp del bloque."""

    def test_valid_utc_z_suffix(self):
        """Timestamps terminando en Z son válidos."""
        assert _is_iso_8601_datetime("2026-04-09T12:00:00Z") is True

    def test_valid_with_offset(self):
        """Timestamps con offset de zona horaria son válidos."""
        assert _is_iso_8601_datetime("2026-04-09T12:00:00+00:00") is True

    def test_valid_with_negative_offset(self):
        """Timestamps con offset negativo son válidos."""
        assert _is_iso_8601_datetime("2026-06-01T08:00:00-04:00") is True

    def test_invalid_without_T(self):
        """Una cadena sin 'T' que separe fecha y hora no es válida."""
        assert _is_iso_8601_datetime("2026-04-09 12:00:00") is False

    def test_invalid_plain_date(self):
        """Una fecha sin hora no es válida."""
        assert _is_iso_8601_datetime("2026-04-09") is False

    def test_invalid_garbage_string(self):
        """Una cadena arbitraria no es válida."""
        assert _is_iso_8601_datetime("not-a-date") is False

    def test_invalid_partial_datetime(self):
        """Una cadena con T pero formato incompleto no es válida."""
        assert _is_iso_8601_datetime("2026-04T12") is False


# ---------------------------------------------------------------------------
# validate_block_integrity
# ---------------------------------------------------------------------------


class TestValidateBlockIntegrity:
    """Tests para BlockValidationService.validate_block_integrity."""

    service = BlockValidationService()

    def test_valid_genesis_block_returns_true(self):
        """Un bloque génesis con hash correcto debe retornar True."""
        block = make_valid_genesis_block()
        assert self.service.validate_block_integrity(block) is True

    def test_valid_non_genesis_block_returns_true(self):
        """Un bloque no-génesis con hash correcto debe retornar True."""
        genesis = make_valid_genesis_block()
        block = make_valid_non_genesis_block(previous_hash=genesis["hash"])
        assert self.service.validate_block_integrity(block) is True

    def test_tampered_hash_returns_false(self):
        """Si el hash almacenado fue manipulado, debe retornar False."""
        block = make_valid_genesis_block()
        block["hash"] = "a" * 64  # hash incorrecto pero hex-64 válido
        assert self.service.validate_block_integrity(block) is False

    def test_missing_required_field_returns_false(self):
        """Un bloque al que le falta un campo requerido debe retornar False."""
        block = make_valid_genesis_block()
        del block["nonce"]
        assert self.service.validate_block_integrity(block) is False

    def test_invalid_timestamp_format_returns_false(self):
        """Un timestamp sin 'T' retorna False."""
        block = make_valid_genesis_block()
        block["timestamp"] = "2026-04-09 12:00:00"
        assert self.service.validate_block_integrity(block) is False

    def test_index_as_bool_returns_false(self):
        """Un bool en el campo index es rechazado (bool es subclase de int)."""
        block = make_valid_genesis_block()
        block["index"] = True
        assert self.service.validate_block_integrity(block) is False

    def test_nonce_as_bool_returns_false(self):
        """Un bool en el campo nonce es rechazado."""
        block = make_valid_genesis_block()
        block["nonce"] = False
        assert self.service.validate_block_integrity(block) is False

    def test_non_hex_hash_returns_false(self):
        """Un hash con caracteres no hexadecimales retorna False."""
        block = make_valid_genesis_block()
        block["hash"] = "z" * 64
        assert self.service.validate_block_integrity(block) is False

    def test_short_hash_returns_false(self):
        """Un hash con menos de 64 caracteres retorna False."""
        block = make_valid_genesis_block()
        block["hash"] = "abc123"
        assert self.service.validate_block_integrity(block) is False

    def test_transactions_not_a_list_returns_false(self):
        """El campo transactions debe ser una lista; un dict retorna False."""
        block = make_valid_genesis_block()
        block["transactions"] = {"invalid": "value"}
        assert self.service.validate_block_integrity(block) is False

    def test_accepts_block_validation_request_model(self):
        """También acepta un BlockValidationRequest de Pydantic (no solo dict)."""
        from src.models.block import BlockValidationRequest

        block_dict = make_valid_non_genesis_block(previous_hash="a" * 64)
        request = BlockValidationRequest(**block_dict)
        assert self.service.validate_block_integrity(request) is True

    def test_empty_dict_returns_false(self):
        """Un dict vacío retorna False."""
        assert self.service.validate_block_integrity({}) is False

    def test_valid_next_block_with_current_chain_state_returns_true(self):
        """Un bloque con índice siguiente y previous_hash vigente pasa consenso."""
        genesis = make_valid_genesis_block()
        block = make_valid_non_genesis_block(previous_hash=genesis["hash"], index=1)
        service = _make_service_for_submit_validation(last_block=genesis)

        assert service.validate_block_integrity(block) is True

    def test_duplicate_block_index_returns_false(self):
        """Falla 11: un índice ya persistido debe rechazarse antes del consumer."""
        last_block = make_valid_non_genesis_block(previous_hash="a" * 64, index=9)
        block = make_valid_non_genesis_block(previous_hash=last_block["hash"], index=10)
        service = _make_service_for_submit_validation(
            last_block=last_block,
            existing_indexes={10},
        )

        assert service.validate_block_integrity(block) is False

    def test_skipped_block_index_returns_false(self):
        """Un bloque que no es último + 1 no puede anexarse a la cadena."""
        last_block = make_valid_non_genesis_block(previous_hash="a" * 64, index=9)
        block = make_valid_non_genesis_block(previous_hash=last_block["hash"], index=11)
        service = _make_service_for_submit_validation(last_block=last_block)

        assert service.validate_block_integrity(block) is False

    def test_stale_previous_hash_returns_false(self):
        """Un bloque con índice correcto pero anclaje obsoleto debe rechazarse."""
        last_block = make_valid_non_genesis_block(previous_hash="a" * 64, index=9)
        block = make_valid_non_genesis_block(previous_hash="b" * 64, index=10)
        service = _make_service_for_submit_validation(last_block=last_block)

        assert service.validate_block_integrity(block) is False

    def test_genesis_block_with_empty_chain_returns_true(self):
        """El caso génesis sigue siendo válido si la cadena está vacía."""
        block = make_valid_genesis_block()
        service = _make_service_for_submit_validation(last_block=None)

        assert service.validate_block_integrity(block) is True


# ---------------------------------------------------------------------------
# validate_chain_integrity
# ---------------------------------------------------------------------------


def _make_db_with_blocks(blocks: list[dict]) -> MagicMock:
    """Construye un db mock cuya colección 'blocks' retorna los bloques dados."""
    db_client = MagicMock()
    db = MagicMock()
    db_client.__getitem__.return_value = db

    # El cursor debe ordenarse: se mockea el método sort() retornando los bloques directamente
    cursor = MagicMock()
    cursor.__iter__ = MagicMock(return_value=iter(blocks))
    db.__getitem__.return_value.find.return_value.sort.return_value = cursor

    return db_client


def _make_service_for_submit_validation(
    last_block: dict | None,
    existing_indexes: set[int] | None = None,
) -> BlockValidationService:
    """Construye un servicio con colección blocks fake para validar submits."""
    existing_indexes = existing_indexes or set()
    db_client = MagicMock()
    db = MagicMock()
    blocks_collection = MagicMock()

    db_client.__getitem__.return_value = db
    db.__getitem__.return_value = blocks_collection

    def find_one(query=None, projection=None, **kwargs):
        if "sort" in kwargs:
            return last_block
        if query and query.get("index") in existing_indexes:
            return {"_id": "existing-block"}
        return None

    blocks_collection.find_one.side_effect = find_one
    return BlockValidationService(db_client=db_client, db_name="ufrocoin")


class TestValidateChainIntegrity:
    """Tests para BlockValidationService.validate_chain_integrity con DB mockeada."""

    def test_raises_runtime_error_without_db(self):
        """Sin conexión de DB, validate_chain_integrity lanza RuntimeError."""
        service = BlockValidationService()  # sin db_client
        with pytest.raises(RuntimeError, match="requires a database connection"):
            service.validate_chain_integrity()

    def test_empty_chain_is_valid(self):
        """Una blockchain vacía retorna chain_valid=True y total_blocks=0."""
        db_client = _make_db_with_blocks([])
        service = BlockValidationService(db_client=db_client, db_name="ufrocoin")

        result = service.validate_chain_integrity()

        assert result["chain_valid"] is True
        assert result["total_blocks"] == 0
        assert result["blocks"] == []
        assert result["error_at_block"] is None

    def test_single_valid_genesis_block(self):
        """Una cadena de un solo bloque génesis válido es íntegra."""
        genesis = make_valid_genesis_block()
        db_client = _make_db_with_blocks([genesis])
        service = BlockValidationService(db_client=db_client, db_name="ufrocoin")

        result = service.validate_chain_integrity()

        assert result["chain_valid"] is True
        assert result["total_blocks"] == 1
        assert result["blocks"][0]["valid"] is True
        assert result["error_at_block"] is None

    def test_two_valid_linked_blocks(self):
        """Una cadena de dos bloques correctamente enlazados es íntegra."""
        genesis = make_valid_genesis_block()
        block1 = make_valid_non_genesis_block(previous_hash=genesis["hash"], index=1)

        db_client = _make_db_with_blocks([genesis, block1])
        service = BlockValidationService(db_client=db_client, db_name="ufrocoin")

        result = service.validate_chain_integrity()

        assert result["chain_valid"] is True
        assert result["total_blocks"] == 2
        assert result["error_at_block"] is None

    def test_tampered_hash_invalidates_chain(self):
        """Un hash manipulado en un bloque marca la cadena como inválida."""
        genesis = make_valid_genesis_block()
        block1 = make_valid_non_genesis_block(previous_hash=genesis["hash"], index=1)
        block1["hash"] = "d" * 64  # hash corrupto pero hex-64 válido

        db_client = _make_db_with_blocks([genesis, block1])
        service = BlockValidationService(db_client=db_client, db_name="ufrocoin")

        result = service.validate_chain_integrity()

        assert result["chain_valid"] is False
        assert result["error_at_block"] == 1

    def test_broken_previous_hash_link_invalidates_chain(self):
        """Un previous_hash que no coincide con el hash del bloque anterior invalida la cadena."""
        genesis = make_valid_genesis_block()
        block1 = make_valid_non_genesis_block(previous_hash="e" * 64, index=1)
        # Recalcula hash con el previous_hash falso (para que la integridad individual pase)

        db_client = _make_db_with_blocks([genesis, block1])
        service = BlockValidationService(db_client=db_client, db_name="ufrocoin")

        result = service.validate_chain_integrity()

        # El enlace entre génesis y bloque1 está roto
        assert result["chain_valid"] is False

    def test_result_includes_computed_and_stored_hash(self):
        """El resultado por bloque incluye stored_hash, computed_hash e index."""
        genesis = make_valid_genesis_block()
        db_client = _make_db_with_blocks([genesis])
        service = BlockValidationService(db_client=db_client, db_name="ufrocoin")

        result = service.validate_chain_integrity()

        block_result = result["blocks"][0]
        assert "index" in block_result
        assert "stored_hash" in block_result
        assert "computed_hash" in block_result
        assert "valid" in block_result

    def test_first_corrupted_block_is_reported(self):
        """error_at_block señala el índice del PRIMER bloque corrupto, no el último."""
        genesis = make_valid_genesis_block()
        block1 = make_valid_non_genesis_block(previous_hash=genesis["hash"], index=1)
        block2 = make_valid_non_genesis_block(previous_hash=block1["hash"], index=2)

        # Corromper bloque 1 (el del medio)
        corrupted_block1 = {**block1, "hash": "f" * 64}

        db_client = _make_db_with_blocks([genesis, corrupted_block1, block2])
        service = BlockValidationService(db_client=db_client, db_name="ufrocoin")

        result = service.validate_chain_integrity()

        assert result["error_at_block"] == 1  # bloque con index=1 es el primero corrupto
