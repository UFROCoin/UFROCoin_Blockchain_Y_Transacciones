"""
Tests unitarios para src.utils.hash_utils.

Estrategia:
- Sin mocks: todas las funciones son puras (sin I/O ni estado externo).
- Se verifican propiedades matemáticas: determinismo, idempotencia, y que
  cambios mínimos en el input produzcan un hash distinto (efecto avalancha).
- Los valores de hash esperados se calculan una vez de forma manual y se usan
  como constantes para anclar la implementación.
"""

import hashlib
import json
from datetime import datetime, timezone

import pytest

from src.utils.hash_utils import (
    _normalize_value,
    calculate_block_hash,
    calculate_concatenated_block_hash,
    serialize_block_fields_for_concatenation,
    serialize_block_for_hash,
)


# ---------------------------------------------------------------------------
# Helpers de test
# ---------------------------------------------------------------------------

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# _normalize_value
# ---------------------------------------------------------------------------


class TestNormalizeValue:
    """Normalización recursiva de valores para serialización determinística."""

    def test_string_passthrough(self):
        """Strings simples no se alteran."""
        assert _normalize_value("hello") == "hello"

    def test_int_passthrough(self):
        """Enteros no se alteran."""
        assert _normalize_value(42) == 42

    def test_float_passthrough(self):
        """Floats no se alteran."""
        assert _normalize_value(3.14) == 3.14

    def test_none_passthrough(self):
        """None no se altera."""
        assert _normalize_value(None) is None

    def test_datetime_aware_utc(self):
        """Un datetime con timezone UTC se serializa a ISO 8601 terminando en Z."""
        dt = datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)
        result = _normalize_value(dt)
        assert result == "2026-04-09T12:00:00Z"

    def test_datetime_naive_treated_as_utc(self):
        """Un datetime naive se trata como UTC y termina en Z."""
        dt = datetime(2026, 4, 9, 12, 0, 0)  # sin tzinfo
        result = _normalize_value(dt)
        assert result == "2026-04-09T12:00:00Z"

    def test_dict_excludes_id_key(self):
        """El campo _id es excluido del dict normalizado."""
        data = {"_id": "some_mongo_id", "index": 1}
        result = _normalize_value(data)
        assert "_id" not in result
        assert result["index"] == 1

    def test_dict_excludes_hash_key(self):
        """El campo hash es excluido del dict normalizado."""
        data = {"hash": "abc123", "index": 0}
        result = _normalize_value(data)
        assert "hash" not in result
        assert result["index"] == 0

    def test_dict_keeps_other_keys(self):
        """Los demás campos del dict se preservan."""
        data = {"nonce": 99, "previous_hash": "0" * 64, "_id": "drop"}
        result = _normalize_value(data)
        assert result["nonce"] == 99
        assert result["previous_hash"] == "0" * 64

    def test_nested_dict(self):
        """La normalización es recursiva sobre dicts anidados."""
        data = {"tx": {"_id": "drop", "amount": 10.0}}
        result = _normalize_value(data)
        assert "_id" not in result["tx"]
        assert result["tx"]["amount"] == 10.0

    def test_list_normalizes_each_element(self):
        """La normalización es recursiva sobre listas."""
        data = [{"_id": "drop", "value": 1}, {"_id": "drop", "value": 2}]
        result = _normalize_value(data)
        assert result == [{"value": 1}, {"value": 2}]

    def test_empty_dict(self):
        """Un dict vacío permanece vacío."""
        assert _normalize_value({}) == {}

    def test_empty_list(self):
        """Una lista vacía permanece vacía."""
        assert _normalize_value([]) == []


# ---------------------------------------------------------------------------
# serialize_block_for_hash
# ---------------------------------------------------------------------------


class TestSerializeBlockForHash:
    """Serialización JSON determinística eliminando _id y hash."""

    BLOCK = {
        "_id": "mongo_internal_id",
        "index": 1,
        "timestamp": "2026-04-10T10:00:00Z",
        "transactions": [],
        "previous_hash": "a" * 64,
        "nonce": 12345,
        "hash": "b" * 64,
    }

    def test_excludes_id_and_hash(self):
        """La serialización no contiene _id ni hash."""
        result = serialize_block_for_hash(self.BLOCK)
        parsed = json.loads(result)
        assert "_id" not in parsed
        assert "hash" not in parsed

    def test_contains_required_fields(self):
        """La serialización contiene index, timestamp, transactions, previous_hash, nonce."""
        result = serialize_block_for_hash(self.BLOCK)
        parsed = json.loads(result)
        for field in ("index", "timestamp", "transactions", "previous_hash", "nonce"):
            assert field in parsed, f"Campo requerido ausente: {field}"

    def test_is_deterministic(self):
        """La misma entrada produce exactamente la misma salida."""
        r1 = serialize_block_for_hash(self.BLOCK)
        r2 = serialize_block_for_hash(self.BLOCK)
        assert r1 == r2

    def test_different_nonce_produces_different_output(self):
        """Un cambio en un campo produce una serialización distinta."""
        block_a = {**self.BLOCK, "nonce": 1}
        block_b = {**self.BLOCK, "nonce": 2}
        assert serialize_block_for_hash(block_a) != serialize_block_for_hash(block_b)

    def test_keys_sorted(self):
        """Las claves JSON están ordenadas alfabéticamente (sort_keys=True)."""
        result = serialize_block_for_hash(self.BLOCK)
        parsed = json.loads(result)
        keys = list(parsed.keys())
        assert keys == sorted(keys)

    def test_no_spaces_in_separators(self):
        """No hay espacios extra en separadores (compact JSON)."""
        result = serialize_block_for_hash(self.BLOCK)
        assert ": " not in result
        assert ", " not in result


# ---------------------------------------------------------------------------
# serialize_block_fields_for_concatenation
# ---------------------------------------------------------------------------


class TestSerializeBlockFieldsForConcatenation:
    """Serialización por concatenación de campos para el bloque génesis."""

    GENESIS_BLOCK = {
        "index": 0,
        "previous_hash": "0" * 64,
        "timestamp": "2026-04-09T12:00:00Z",
        "transactions": [
            {
                "tx_id": "genesis-001",
                "type": "GENESIS_ISSUANCE",
                "from_address": "SYSTEM",
                "to_address": "REWARD_POOL",
                "amount": 1_000_000,
            }
        ],
        "nonce": 0,
        "hash": "to_be_excluded",
    }

    def test_starts_with_index(self):
        """La cadena concatenada comienza con el índice del bloque."""
        result = serialize_block_fields_for_concatenation(self.GENESIS_BLOCK)
        assert result.startswith("0")

    def test_contains_previous_hash(self):
        """La cadena contiene el previous_hash."""
        result = serialize_block_fields_for_concatenation(self.GENESIS_BLOCK)
        assert "0" * 64 in result

    def test_contains_nonce(self):
        """La cadena contiene el nonce al final."""
        result = serialize_block_fields_for_concatenation(self.GENESIS_BLOCK)
        assert result.endswith("0")

    def test_is_deterministic(self):
        """El mismo bloque produce exactamente la misma cadena."""
        r1 = serialize_block_fields_for_concatenation(self.GENESIS_BLOCK)
        r2 = serialize_block_fields_for_concatenation(self.GENESIS_BLOCK)
        assert r1 == r2

    def test_hash_excluded_from_transactions(self):
        """El campo 'hash' del bloque no aparece en la cadena concatenada."""
        result = serialize_block_fields_for_concatenation(self.GENESIS_BLOCK)
        # "hash" excluido por _normalize_value
        assert "to_be_excluded" not in result

    def test_different_transactions_produce_different_output(self):
        """Transacciones distintas producen cadenas distintas."""
        block_a = {**self.GENESIS_BLOCK, "transactions": []}
        block_b = {**self.GENESIS_BLOCK, "transactions": [{"id": "x", "amount": 1}]}
        assert serialize_block_fields_for_concatenation(block_a) != \
               serialize_block_fields_for_concatenation(block_b)


# ---------------------------------------------------------------------------
# calculate_block_hash
# ---------------------------------------------------------------------------


class TestCalculateBlockHash:
    """SHA-256 basado en serialización JSON del bloque."""

    BLOCK = {
        "index": 1,
        "timestamp": "2026-04-10T10:00:00Z",
        "transactions": [],
        "previous_hash": "a" * 64,
        "nonce": 48271,
    }

    def test_returns_64_hex_characters(self):
        """El hash resultante es una cadena hexadecimal de 64 caracteres."""
        result = calculate_block_hash(self.BLOCK)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_is_deterministic(self):
        """El mismo bloque produce el mismo hash."""
        assert calculate_block_hash(self.BLOCK) == calculate_block_hash(self.BLOCK)

    def test_different_nonce_produces_different_hash(self):
        """Un nonce distinto produce un hash distinto (efecto avalancha mínimo)."""
        block_a = {**self.BLOCK, "nonce": 1}
        block_b = {**self.BLOCK, "nonce": 2}
        assert calculate_block_hash(block_a) != calculate_block_hash(block_b)

    def test_different_index_produces_different_hash(self):
        """Un índice distinto produce un hash distinto."""
        block_a = {**self.BLOCK, "index": 1}
        block_b = {**self.BLOCK, "index": 2}
        assert calculate_block_hash(block_a) != calculate_block_hash(block_b)

    def test_matches_manual_sha256(self):
        """El resultado coincide con el SHA-256 calculado manualmente."""
        serialized = serialize_block_for_hash(self.BLOCK)
        expected = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        assert calculate_block_hash(self.BLOCK) == expected

    def test_id_field_excluded_from_hash(self):
        """Agregar _id al bloque no cambia el hash (excluido en la serialización)."""
        block_without_id = self.BLOCK.copy()
        block_with_id = {**self.BLOCK, "_id": "some_mongo_id"}
        assert calculate_block_hash(block_without_id) == calculate_block_hash(block_with_id)

    def test_hash_field_excluded_from_hash(self):
        """El campo hash no se incluye en el cálculo de hash (evita circularidad)."""
        block_without_hash = self.BLOCK.copy()
        block_with_hash = {**self.BLOCK, "hash": "old_hash_value"}
        assert calculate_block_hash(block_without_hash) == calculate_block_hash(block_with_hash)


# ---------------------------------------------------------------------------
# calculate_concatenated_block_hash
# ---------------------------------------------------------------------------


class TestCalculateConcatenatedBlockHash:
    """SHA-256 por concatenación de campos (usado en bloque génesis)."""

    GENESIS_BLOCK = {
        "index": 0,
        "previous_hash": "0" * 64,
        "timestamp": "2026-04-09T12:00:00Z",
        "transactions": [
            {
                "tx_id": "genesis-001",
                "type": "GENESIS_ISSUANCE",
                "from_address": "SYSTEM",
                "to_address": "REWARD_POOL",
                "amount": 1_000_000,
            }
        ],
        "nonce": 0,
    }

    def test_returns_64_hex_characters(self):
        """El hash resultante es una cadena hexadecimal de 64 caracteres."""
        result = calculate_concatenated_block_hash(self.GENESIS_BLOCK)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_is_deterministic(self):
        """El mismo bloque produce el mismo hash."""
        r1 = calculate_concatenated_block_hash(self.GENESIS_BLOCK)
        r2 = calculate_concatenated_block_hash(self.GENESIS_BLOCK)
        assert r1 == r2

    def test_matches_manual_sha256(self):
        """El resultado coincide con el SHA-256 calculado manualmente."""
        concatenated = serialize_block_fields_for_concatenation(self.GENESIS_BLOCK)
        expected = hashlib.sha256(concatenated.encode("utf-8")).hexdigest()
        assert calculate_concatenated_block_hash(self.GENESIS_BLOCK) == expected

    def test_different_from_json_hash(self):
        """La función de concatenación produce un hash distinto al JSON-hash para el mismo bloque."""
        json_hash = calculate_block_hash(self.GENESIS_BLOCK)
        concat_hash = calculate_concatenated_block_hash(self.GENESIS_BLOCK)
        assert json_hash != concat_hash

    def test_different_transactions_produce_different_hash(self):
        """Transacciones distintas producen hashes distintos."""
        block_a = {**self.GENESIS_BLOCK, "transactions": []}
        block_b = self.GENESIS_BLOCK.copy()
        assert calculate_concatenated_block_hash(block_a) != \
               calculate_concatenated_block_hash(block_b)

    def test_different_nonce_produces_different_hash(self):
        """Un nonce distinto produce un hash distinto."""
        block_a = {**self.GENESIS_BLOCK, "nonce": 0}
        block_b = {**self.GENESIS_BLOCK, "nonce": 1}
        assert calculate_concatenated_block_hash(block_a) != \
               calculate_concatenated_block_hash(block_b)
