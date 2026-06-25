"""
Tests unitarios para CheckpointService.validate_fast() y los helpers
_find_first_corrupted_block, _recompute_block_hash y _linear_scan_first_corrupted.

Estrategia:
- Las colecciones MongoDB se mockean con MagicMock (sin base de datos real).
- Los bloques se construyen con hashes calculados desde su contenido para que
  _recompute_block_hash() pueda verificar su integridad.
- Se usan bloques simples (no génesis) para que BlockValidationService
  use la ruta JSON determinística estándar.
"""

import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest

from src.services.checkpoint_service import CheckpointService
from src.utils.merkle_utils import compute_merkle_root


# ---------------------------------------------------------------------------
# Helpers para construir bloques con hashes reales
# ---------------------------------------------------------------------------


def _make_real_block(index: int, previous_hash: str = "a" * 64) -> dict:
    """
    Construye un bloque cuyo hash sea consistente con el algoritmo de
    BlockValidationService._calculate_block_hash_from_dict (ruta JSON, no génesis).
    """
    payload = {
        "index": index,
        "timestamp": f"2026-06-25T{index:02d}:00:00Z",
        "transactions": [],
        "previous_hash": previous_hash,
        "nonce": index * 100,
    }
    block_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {**payload, "hash": block_hash}


def _corrupt_block_hash(block: dict) -> dict:
    """Devuelve una copia del bloque con el hash adulterado."""
    corrupted = dict(block)
    corrupted["hash"] = "0" * 64
    return corrupted


def _make_service_with_blocks(
    blocks: list[dict],
    checkpoints: list[dict] | None = None,
) -> CheckpointService:
    """
    Construye un CheckpointService con colecciones mockeadas.

    - blocks_collection.find() retorna los bloques dados.
    - checkpoints_collection.find() retorna los checkpoints dados.
    """
    blocks_col = MagicMock()
    checkpoints_col = MagicMock()

    # Mock de find() para la colección de bloques (soporta filtros por index).
    def _blocks_find(query=None, projection=None):
        q = query or {}
        index_filter = q.get("index", {})
        gte = index_filter.get("$gte", None)
        lte = index_filter.get("$lte", None)
        if gte is not None and lte is not None:
            filtered = [b for b in blocks if gte <= b["index"] <= lte]
        else:
            filtered = list(blocks)
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = iter(filtered)
        return mock_cursor

    blocks_col.find.side_effect = _blocks_find

    # Mock de find() para la colección de checkpoints.
    cp_list = checkpoints or []
    cp_cursor = MagicMock()
    cp_cursor.sort.return_value = iter(cp_list)
    checkpoints_col.find.return_value = cp_cursor

    return CheckpointService(
        blocks_collection=blocks_col,
        checkpoints_collection=checkpoints_col,
    )


# ---------------------------------------------------------------------------
# Tests — validate_fast: sin checkpoints
# ---------------------------------------------------------------------------


class TestValidateFastNoCheckpoints:
    """Escenario: no existen checkpoints registrados."""

    def test_returns_valid_false(self):
        """Sin checkpoints, valid debe ser False."""
        service = _make_service_with_blocks(blocks=[], checkpoints=[])
        result = service.validate_fast()
        assert result["valid"] is False

    def test_returns_checkpoints_not_found_reason(self):
        """Sin checkpoints, reason debe ser CHECKPOINTS_NOT_FOUND."""
        service = _make_service_with_blocks(blocks=[], checkpoints=[])
        result = service.validate_fast()
        assert result["reason"] == "CHECKPOINTS_NOT_FOUND"

    def test_corrupted_range_is_none_when_no_checkpoints(self):
        """Sin checkpoints, corrupted_range debe ser None."""
        service = _make_service_with_blocks(blocks=[], checkpoints=[])
        result = service.validate_fast()
        assert result["corrupted_range"] is None

    def test_message_is_none_when_no_checkpoints(self):
        """Sin checkpoints, message debe ser None."""
        service = _make_service_with_blocks(blocks=[], checkpoints=[])
        result = service.validate_fast()
        assert result["message"] is None


# ---------------------------------------------------------------------------
# Tests — validate_fast: todos los checkpoints válidos
# ---------------------------------------------------------------------------


class TestValidateFastAllValid:
    """Escenario: los checkpoints existen y los Merkle roots coinciden."""

    def _make_valid_checkpoint(self, blocks: list[dict]) -> dict:
        """Genera un checkpoint cuyo merkle_root coincida con los hashes actuales."""
        hashes = [b["hash"] for b in blocks]
        return {
            "from_block": blocks[0]["index"],
            "to_block": blocks[-1]["index"],
            "merkle_root": compute_merkle_root(hashes),
            "last_block_hash": blocks[-1]["hash"],
            "created_at": "2026-06-25T00:00:00Z",
            "status": "CREATED",
        }

    def test_valid_true_when_all_roots_match(self):
        """Si todos los Merkle roots coinciden, valid debe ser True."""
        blocks = [_make_real_block(i) for i in range(1, 4)]
        checkpoint = self._make_valid_checkpoint(blocks)
        service = _make_service_with_blocks(blocks=blocks, checkpoints=[checkpoint])
        result = service.validate_fast()
        assert result["valid"] is True

    def test_message_is_set_when_valid(self):
        """Con cadena íntegra, message debe ser el string definido en los criterios."""
        blocks = [_make_real_block(i) for i in range(1, 4)]
        checkpoint = self._make_valid_checkpoint(blocks)
        service = _make_service_with_blocks(blocks=blocks, checkpoints=[checkpoint])
        result = service.validate_fast()
        assert result["message"] == "Blockchain integrity verified using checkpoints and hash tree"

    def test_reason_is_none_when_valid(self):
        """Con cadena íntegra, reason debe ser None."""
        blocks = [_make_real_block(i) for i in range(1, 4)]
        checkpoint = self._make_valid_checkpoint(blocks)
        service = _make_service_with_blocks(blocks=blocks, checkpoints=[checkpoint])
        result = service.validate_fast()
        assert result["reason"] is None

    def test_corrupted_range_is_none_when_valid(self):
        """Con cadena íntegra, corrupted_range debe ser None."""
        blocks = [_make_real_block(i) for i in range(1, 4)]
        checkpoint = self._make_valid_checkpoint(blocks)
        service = _make_service_with_blocks(blocks=blocks, checkpoints=[checkpoint])
        result = service.validate_fast()
        assert result["corrupted_range"] is None

    def test_multiple_valid_checkpoints_returns_valid(self):
        """Dos checkpoints válidos → valid=True."""
        blocks1 = [_make_real_block(i) for i in range(1, 4)]
        blocks2 = [_make_real_block(i) for i in range(4, 7)]
        cp1 = self._make_valid_checkpoint(blocks1)
        cp2 = self._make_valid_checkpoint(blocks2)
        service = _make_service_with_blocks(
            blocks=blocks1 + blocks2,
            checkpoints=[cp1, cp2],
        )
        result = service.validate_fast()
        assert result["valid"] is True


# ---------------------------------------------------------------------------
# Tests — validate_fast: discrepancia detectada
# ---------------------------------------------------------------------------


class TestValidateFastCorruption:
    """Escenario: un checkpoint tiene Merkle root que ya no coincide."""

    def _make_corrupted_checkpoint(self, blocks: list[dict]) -> dict:
        """Genera un checkpoint con merkle_root de bloques originales (íntegros)."""
        hashes = [b["hash"] for b in blocks]
        return {
            "from_block": blocks[0]["index"],
            "to_block": blocks[-1]["index"],
            "merkle_root": compute_merkle_root(hashes),
            "last_block_hash": blocks[-1]["hash"],
            "created_at": "2026-06-25T00:00:00Z",
            "status": "CREATED",
        }

    def test_valid_false_when_merkle_mismatch(self):
        """Si el Merkle root actual difiere del almacenado, valid=False."""
        blocks = [_make_real_block(i) for i in range(1, 4)]
        checkpoint = self._make_corrupted_checkpoint(blocks)

        # Corromper el hash del segundo bloque.
        corrupted_blocks = [
            blocks[0],
            _corrupt_block_hash(blocks[1]),
            blocks[2],
        ]
        service = _make_service_with_blocks(
            blocks=corrupted_blocks, checkpoints=[checkpoint]
        )
        result = service.validate_fast()
        assert result["valid"] is False

    def test_reason_is_merkle_root_mismatch(self):
        """Con discrepancia, reason debe ser MERKLE_ROOT_MISMATCH."""
        blocks = [_make_real_block(i) for i in range(1, 4)]
        checkpoint = self._make_corrupted_checkpoint(blocks)
        corrupted_blocks = [blocks[0], _corrupt_block_hash(blocks[1]), blocks[2]]
        service = _make_service_with_blocks(blocks=corrupted_blocks, checkpoints=[checkpoint])
        result = service.validate_fast()
        assert result["reason"] == "MERKLE_ROOT_MISMATCH"

    def test_corrupted_range_matches_checkpoint_range(self):
        """El rango corrupto debe coincidir con el rango del checkpoint afectado."""
        blocks = [_make_real_block(i) for i in range(1, 4)]
        checkpoint = self._make_corrupted_checkpoint(blocks)
        corrupted_blocks = [blocks[0], _corrupt_block_hash(blocks[1]), blocks[2]]
        service = _make_service_with_blocks(blocks=corrupted_blocks, checkpoints=[checkpoint])
        result = service.validate_fast()
        assert result["corrupted_range"]["from_block"] == blocks[0]["index"]
        assert result["corrupted_range"]["to_block"] == blocks[-1]["index"]

    def test_expected_root_matches_checkpoint(self):
        """expected_root debe ser el merkle_root del checkpoint."""
        blocks = [_make_real_block(i) for i in range(1, 4)]
        checkpoint = self._make_corrupted_checkpoint(blocks)
        corrupted_blocks = [blocks[0], _corrupt_block_hash(blocks[1]), blocks[2]]
        service = _make_service_with_blocks(blocks=corrupted_blocks, checkpoints=[checkpoint])
        result = service.validate_fast()
        assert result["expected_root"] == checkpoint["merkle_root"]

    def test_actual_root_differs_from_expected(self):
        """actual_root no debe ser igual a expected_root cuando hay corrupción."""
        blocks = [_make_real_block(i) for i in range(1, 4)]
        checkpoint = self._make_corrupted_checkpoint(blocks)
        corrupted_blocks = [blocks[0], _corrupt_block_hash(blocks[1]), blocks[2]]
        service = _make_service_with_blocks(blocks=corrupted_blocks, checkpoints=[checkpoint])
        result = service.validate_fast()
        assert result["actual_root"] != result["expected_root"]

    def test_first_corrupted_block_is_identified(self):
        """Debe identificar el índice del primer bloque alterado."""
        blocks = [_make_real_block(i) for i in range(1, 4)]
        checkpoint = self._make_corrupted_checkpoint(blocks)
        # El bloque en índice 2 está corrupto (el segundo de la lista).
        corrupted_blocks = [blocks[0], _corrupt_block_hash(blocks[1]), blocks[2]]
        service = _make_service_with_blocks(blocks=corrupted_blocks, checkpoints=[checkpoint])
        result = service.validate_fast()
        assert result["first_corrupted_block"] == blocks[1]["index"]

    def test_first_block_corrupted(self):
        """Si el primer bloque del rango está corrupto, lo identifica correctamente."""
        blocks = [_make_real_block(i) for i in range(1, 5)]
        checkpoint = self._make_corrupted_checkpoint(blocks)
        corrupted_blocks = [_corrupt_block_hash(blocks[0])] + blocks[1:]
        service = _make_service_with_blocks(blocks=corrupted_blocks, checkpoints=[checkpoint])
        result = service.validate_fast()
        assert result["first_corrupted_block"] == blocks[0]["index"]

    def test_last_block_corrupted(self):
        """Si el último bloque del rango está corrupto, lo identifica correctamente."""
        blocks = [_make_real_block(i) for i in range(1, 5)]
        checkpoint = self._make_corrupted_checkpoint(blocks)
        corrupted_blocks = blocks[:-1] + [_corrupt_block_hash(blocks[-1])]
        service = _make_service_with_blocks(blocks=corrupted_blocks, checkpoints=[checkpoint])
        result = service.validate_fast()
        assert result["first_corrupted_block"] == blocks[-1]["index"]

    def test_stops_at_first_corrupted_checkpoint(self):
        """Si el primer checkpoint está corrupto, no evalúa el segundo."""
        # Dos checkpoints: el primero corrupto.
        blocks1 = [_make_real_block(i) for i in range(1, 4)]
        blocks2 = [_make_real_block(i) for i in range(4, 7)]
        cp1 = self._make_corrupted_checkpoint(blocks1)
        cp2_hashes = [b["hash"] for b in blocks2]
        cp2 = {
            "from_block": blocks2[0]["index"],
            "to_block": blocks2[-1]["index"],
            "merkle_root": compute_merkle_root(cp2_hashes),
            "last_block_hash": blocks2[-1]["hash"],
            "created_at": "2026-06-25T01:00:00Z",
            "status": "CREATED",
        }
        # Corromper el primer rango.
        corrupted = [_corrupt_block_hash(blocks1[0])] + blocks1[1:] + blocks2
        service = _make_service_with_blocks(blocks=corrupted, checkpoints=[cp1, cp2])
        result = service.validate_fast()
        # Solo informa el primer rango corrupto.
        assert result["corrupted_range"]["from_block"] == blocks1[0]["index"]
        assert result["corrupted_range"]["to_block"] == blocks1[-1]["index"]


# ---------------------------------------------------------------------------
# Tests — _linear_scan_first_corrupted
# ---------------------------------------------------------------------------


class TestLinearScanFirstCorrupted:
    """Tests para el escaneo lineal de respaldo."""

    def test_returns_none_for_intact_blocks(self):
        """Si todos los bloques son íntegros, retorna None."""
        blocks = [_make_real_block(i) for i in range(1, 4)]
        result = CheckpointService._linear_scan_first_corrupted(blocks)
        assert result is None

    def test_finds_first_corrupted_block(self):
        """Retorna el índice del primer bloque corrupto."""
        blocks = [_make_real_block(i) for i in range(1, 5)]
        corrupted = [blocks[0], _corrupt_block_hash(blocks[1]), blocks[2], blocks[3]]
        result = CheckpointService._linear_scan_first_corrupted(corrupted)
        assert result == blocks[1]["index"]

    def test_returns_none_for_empty_list(self):
        """Lista vacía retorna None."""
        result = CheckpointService._linear_scan_first_corrupted([])
        assert result is None
