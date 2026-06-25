"""
Tests unitarios para CheckpointService y compute_merkle_root.

Estrategia:
- Las colecciones MongoDB se mockean con MagicMock (sin base de datos real).
- Se verifica el comportamiento del servicio ante distintos escenarios:
  cadena vacía, cadena con menos bloques que la frecuencia, rangos exactos,
  múltiples rangos, duplicados y errores en el cálculo Merkle.
- Se testea compute_merkle_root de forma aislada con distintos tamaños de entrada.
"""

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from src.services.checkpoint_service import CheckpointService
from src.utils.merkle_utils import compute_merkle_root


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_block(index: int) -> dict:
    """Genera un bloque mínimo con index y hash determinístico para tests."""
    block_hash = hashlib.sha256(f"block-{index}".encode()).hexdigest()
    return {"index": index, "hash": block_hash}


def _make_service(blocks: list[dict], existing_checkpoints: list[dict] | None = None) -> CheckpointService:
    """
    Crea un CheckpointService con colecciones mockeadas.

    - blocks_collection.find() retorna los bloques dados (ya paginados/ordenados).
    - checkpoints_collection.find_one() retorna None por defecto (sin duplicados).
    - checkpoints_collection.insert_one() no hace nada (MagicMock).
    """
    blocks_col = MagicMock()

    # find() debe retornar un iterable con sort() encadenado.
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = iter(blocks)
    blocks_col.find.return_value = mock_cursor

    checkpoints_col = MagicMock()

    # Por defecto no hay checkpoints previos.
    existing = existing_checkpoints or []
    existing_map = {(cp["from_block"], cp["to_block"]): cp for cp in existing}

    def _find_one_side_effect(query, projection=None):
        key = (query.get("from_block"), query.get("to_block"))
        return existing_map.get(key)

    checkpoints_col.find_one.side_effect = _find_one_side_effect
    checkpoints_col.find.return_value = MagicMock(
        sort=lambda *a, **kw: iter(existing)
    )

    return CheckpointService(
        blocks_collection=blocks_col,
        checkpoints_collection=checkpoints_col,
    )


# ---------------------------------------------------------------------------
# Tests — compute_merkle_root
# ---------------------------------------------------------------------------


class TestComputeMerkleRoot:
    """Tests unitarios para la función compute_merkle_root en merkle_utils.py."""

    def test_empty_list_returns_sha256_of_empty_string(self):
        """Una lista vacía debe retornar SHA-256 de cadena vacía."""
        expected = hashlib.sha256(b"").hexdigest()
        assert compute_merkle_root([]) == expected

    def test_single_hash_returns_itself(self):
        """Con un solo hash, la raíz debe ser ese mismo hash (en minúsculas)."""
        h = "a" * 64
        assert compute_merkle_root([h]) == h.lower()

    def test_two_hashes_computed_correctly(self):
        """Con dos hashes, el root debe ser SHA-256 de su concatenación."""
        h1 = "a" * 64
        h2 = "b" * 64
        expected = hashlib.sha256((h1 + h2).encode("utf-8")).hexdigest()
        assert compute_merkle_root([h1, h2]) == expected

    def test_odd_number_of_hashes_duplicates_last(self):
        """Con 3 hashes, el tercero se duplica antes de combinar pares."""
        h1 = "a" * 64
        h2 = "b" * 64
        h3 = "c" * 64
        # Nivel 0: [h1, h2, h3, h3]  (h3 duplicado)
        # Nivel 1: [sha256(h1+h2), sha256(h3+h3)]
        parent_left = hashlib.sha256((h1 + h2).encode()).hexdigest()
        parent_right = hashlib.sha256((h3 + h3).encode()).hexdigest()
        expected = hashlib.sha256((parent_left + parent_right).encode()).hexdigest()
        assert compute_merkle_root([h1, h2, h3]) == expected

    def test_four_hashes_computed_correctly(self):
        """Con 4 hashes (árbol balanceado de 2 niveles), el resultado es correcto."""
        hashes = [hashlib.sha256(f"h{i}".encode()).hexdigest() for i in range(4)]
        p1 = hashlib.sha256((hashes[0] + hashes[1]).encode()).hexdigest()
        p2 = hashlib.sha256((hashes[2] + hashes[3]).encode()).hexdigest()
        expected = hashlib.sha256((p1 + p2).encode()).hexdigest()
        assert compute_merkle_root(hashes) == expected

    def test_uppercase_input_normalized_to_lowercase(self):
        """Los hashes en mayúsculas deben producir el mismo resultado que en minúsculas."""
        h = "A" * 64
        result_upper = compute_merkle_root([h])
        result_lower = compute_merkle_root([h.lower()])
        assert result_upper == result_lower

    def test_result_is_valid_sha256_hex(self):
        """El resultado siempre debe ser un string hexadecimal de 64 caracteres."""
        hashes = [hashlib.sha256(f"block-{i}".encode()).hexdigest() for i in range(5)]
        result = compute_merkle_root(hashes)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)


# ---------------------------------------------------------------------------
# Tests — CheckpointService.get_checkpoint_frequency
# ---------------------------------------------------------------------------


class TestGetCheckpointFrequency:
    """Tests para la lectura de la frecuencia desde variables de entorno."""

    def test_default_frequency_when_env_not_set(self):
        """Sin variable de entorno, debe retornar DEFAULT_CHECKPOINT_FREQUENCY (100)."""
        with patch.dict("os.environ", {}, clear=False):
            # Eliminar la variable si existe
            import os
            os.environ.pop("CHECKPOINT_FREQUENCY", None)
            freq = CheckpointService.get_checkpoint_frequency()
        assert freq == 100

    def test_reads_frequency_from_env(self):
        """Debe retornar el valor entero de CHECKPOINT_FREQUENCY si está definido."""
        with patch.dict("os.environ", {"CHECKPOINT_FREQUENCY": "50"}):
            freq = CheckpointService.get_checkpoint_frequency()
        assert freq == 50

    def test_invalid_env_value_falls_back_to_default(self):
        """Un valor no numérico en CHECKPOINT_FREQUENCY debe usar el default."""
        with patch.dict("os.environ", {"CHECKPOINT_FREQUENCY": "invalid"}):
            freq = CheckpointService.get_checkpoint_frequency()
        assert freq == 100

    def test_zero_env_value_falls_back_to_default(self):
        """CHECKPOINT_FREQUENCY=0 debe caer al default (debe ser >= 1)."""
        with patch.dict("os.environ", {"CHECKPOINT_FREQUENCY": "0"}):
            freq = CheckpointService.get_checkpoint_frequency()
        assert freq == 100

    def test_negative_env_value_falls_back_to_default(self):
        """CHECKPOINT_FREQUENCY negativo debe caer al default."""
        with patch.dict("os.environ", {"CHECKPOINT_FREQUENCY": "-5"}):
            freq = CheckpointService.get_checkpoint_frequency()
        assert freq == 100


# ---------------------------------------------------------------------------
# Tests — CheckpointService.generate_checkpoints
# ---------------------------------------------------------------------------


class TestGenerateCheckpoints:
    """Tests de generación de checkpoints en distintos escenarios de cadena."""

    def test_empty_chain_returns_empty_result(self):
        """Con cadena vacía, no se genera ningún checkpoint."""
        service = _make_service(blocks=[], existing_checkpoints=[])
        result = service.generate_checkpoints(frequency=100)
        assert result["generated"] == 0
        assert result["skipped"] == 0
        assert result["errors"] == 0
        assert result["data"] == []

    def test_fewer_blocks_than_frequency_returns_empty(self):
        """Con menos bloques que la frecuencia, no hay rangos completos."""
        blocks = [_make_block(i) for i in range(50)]
        service = _make_service(blocks=blocks)
        result = service.generate_checkpoints(frequency=100)
        assert result["generated"] == 0
        assert result["data"] == []

    def test_exactly_one_frequency_generates_one_checkpoint(self):
        """Con exactamente N bloques, se genera un checkpoint."""
        blocks = [_make_block(i) for i in range(100)]
        service = _make_service(blocks=blocks)
        result = service.generate_checkpoints(frequency=100)
        assert result["generated"] == 1
        assert result["errors"] == 0
        assert len(result["data"]) == 1
        cp = result["data"][0]
        assert cp["from_block"] == 0
        assert cp["to_block"] == 99
        assert cp["status"] == "CREATED"

    def test_two_full_frequencies_generates_two_checkpoints(self):
        """Con 2N bloques, se generan dos checkpoints con rangos correctos."""
        blocks = [_make_block(i) for i in range(200)]
        service = _make_service(blocks=blocks)
        result = service.generate_checkpoints(frequency=100)
        assert result["generated"] == 2
        cps = result["data"]
        assert cps[0]["from_block"] == 0
        assert cps[0]["to_block"] == 99
        assert cps[1]["from_block"] == 100
        assert cps[1]["to_block"] == 199

    def test_partial_last_group_is_not_generated(self):
        """150 bloques con frecuencia 100 → solo un checkpoint (rango 0–99)."""
        blocks = [_make_block(i) for i in range(150)]
        service = _make_service(blocks=blocks)
        result = service.generate_checkpoints(frequency=100)
        assert result["generated"] == 1
        assert result["data"][0]["from_block"] == 0
        assert result["data"][0]["to_block"] == 99

    def test_existing_checkpoint_is_skipped(self):
        """Un rango que ya tiene checkpoint no se regenera."""
        blocks = [_make_block(i) for i in range(100)]
        existing = [{
            "from_block": 0,
            "to_block": 99,
            "merkle_root": "x" * 64,
            "last_block_hash": "y" * 64,
            "created_at": "2026-06-25T00:00:00Z",
            "status": "CREATED",
        }]
        service = _make_service(blocks=blocks, existing_checkpoints=existing)
        result = service.generate_checkpoints(frequency=100)
        assert result["generated"] == 0
        assert result["skipped"] == 1
        # No se llamó a insert_one
        service.checkpoints_collection.insert_one.assert_not_called()

    def test_merkle_error_does_not_persist_checkpoint(self):
        """Si compute_merkle_root lanza excepción, el rango no se persiste."""
        blocks = [_make_block(i) for i in range(100)]
        service = _make_service(blocks=blocks)

        with patch("src.services.checkpoint_service.compute_merkle_root", side_effect=ValueError("boom")):
            result = service.generate_checkpoints(frequency=100)

        assert result["generated"] == 0
        assert result["errors"] == 1
        service.checkpoints_collection.insert_one.assert_not_called()

    def test_checkpoint_contains_correct_last_block_hash(self):
        """El campo last_block_hash debe corresponder al hash del último bloque del rango."""
        blocks = [_make_block(i) for i in range(100)]
        expected_last_hash = blocks[-1]["hash"]
        service = _make_service(blocks=blocks)
        result = service.generate_checkpoints(frequency=100)
        assert result["data"][0]["last_block_hash"] == expected_last_hash

    def test_checkpoint_has_created_at_in_iso_format(self):
        """El campo created_at debe ser un string ISO 8601 que contenga 'T'."""
        blocks = [_make_block(i) for i in range(100)]
        service = _make_service(blocks=blocks)
        result = service.generate_checkpoints(frequency=100)
        created_at = result["data"][0]["created_at"]
        assert "T" in created_at

    def test_custom_frequency_overrides_default(self):
        """Pasar frequency=50 genera el rango [0, 49] con 100 bloques disponibles."""
        blocks = [_make_block(i) for i in range(100)]
        service = _make_service(blocks=blocks)
        result = service.generate_checkpoints(frequency=50)
        # 100 bloques / 50 = 2 checkpoints
        assert result["generated"] == 2
        assert result["data"][0]["to_block"] == 49
        assert result["data"][1]["from_block"] == 50
        assert result["data"][1]["to_block"] == 99

    def test_merkle_root_is_deterministic(self):
        """El mismo conjunto de bloques siempre produce el mismo Merkle root."""
        blocks = [_make_block(i) for i in range(100)]
        service1 = _make_service(blocks=blocks)
        service2 = _make_service(blocks=blocks)
        result1 = service1.generate_checkpoints(frequency=100)
        result2 = service2.generate_checkpoints(frequency=100)
        assert result1["data"][0]["merkle_root"] == result2["data"][0]["merkle_root"]


# ---------------------------------------------------------------------------
# Tests — CheckpointService.list_checkpoints
# ---------------------------------------------------------------------------


class TestListCheckpoints:
    """Tests para la consulta de checkpoints."""

    def test_list_returns_empty_when_no_checkpoints(self):
        """Sin checkpoints en la BD, retorna lista vacía."""
        service = _make_service(blocks=[], existing_checkpoints=[])
        # El mock de find().sort() ya retorna iter([])
        result = service.list_checkpoints()
        assert result == []

    def test_list_returns_all_checkpoints(self):
        """Retorna todos los checkpoints disponibles."""
        existing = [
            {
                "from_block": 0, "to_block": 99,
                "merkle_root": "a" * 64, "last_block_hash": "b" * 64,
                "created_at": "2026-06-25T00:00:00Z", "status": "CREATED",
            },
            {
                "from_block": 100, "to_block": 199,
                "merkle_root": "c" * 64, "last_block_hash": "d" * 64,
                "created_at": "2026-06-25T01:00:00Z", "status": "CREATED",
            },
        ]
        service = _make_service(blocks=[], existing_checkpoints=existing)

        # Reconfigurar el find mock para list_checkpoints
        mock_cursor = MagicMock()
        mock_cursor.sort.return_value = iter(existing)
        service.checkpoints_collection.find.return_value = mock_cursor

        result = service.list_checkpoints()
        assert len(result) == 2
        assert result[0]["from_block"] == 0
        assert result[1]["from_block"] == 100


# ---------------------------------------------------------------------------
# Tests — CheckpointService.get_checkpoint_by_range
# ---------------------------------------------------------------------------


class TestGetCheckpointByRange:
    """Tests para la búsqueda de checkpoint por rango exacto."""

    def test_returns_none_when_not_found(self):
        """Si no existe checkpoint para el rango, retorna None."""
        service = _make_service(blocks=[], existing_checkpoints=[])
        result = service.get_checkpoint_by_range(from_block=0, to_block=99)
        assert result is None

    def test_returns_checkpoint_when_found(self):
        """Si existe el checkpoint, lo retorna."""
        existing = [{
            "from_block": 0, "to_block": 99,
            "merkle_root": "a" * 64, "last_block_hash": "b" * 64,
            "created_at": "2026-06-25T00:00:00Z", "status": "CREATED",
        }]
        service = _make_service(blocks=[], existing_checkpoints=existing)
        result = service.get_checkpoint_by_range(from_block=0, to_block=99)
        assert result is not None
        assert result["from_block"] == 0
        assert result["to_block"] == 99
