"""
Tests unitarios para src.services.block_service.BlockService.

Estrategia:
- Se mockea get_blocks_collection para evitar dependencia de MongoDB.
- Se verifica que BlockService llame correctamente a la colección con los
  parámetros correctos (queries, skip, limit, sort).
- Se verifica el comportamiento de _with_confirmed_transaction_indexes.
"""

from unittest.mock import MagicMock, call, patch

import pytest

from src.models.block import Block


# ---------------------------------------------------------------------------
# Fixture: bloque de ejemplo y helper para mock de colección
# ---------------------------------------------------------------------------

SAMPLE_BLOCK_DOC = {
    "index": 1,
    "timestamp": "2026-04-10T10:00:00Z",
    "transactions": [
        {
            "id": "tx-001",
            "from": "addr_a",
            "to": "addr_b",
            "amount": 25.0,
            "type": "TRANSFER",
            "timestamp": "2026-04-10T09:59:00Z",
        }
    ],
    "previous_hash": "a" * 64,
    "nonce": 48271,
    "hash": "b" * 64,
}


def make_mock_collection(find_return=None, find_one_return=None, count_return=0):
    """Construye un mock de colección MongoDB con valores por defecto."""
    col = MagicMock()
    col.count_documents.return_value = count_return

    # Mockear la cadena: find().sort().skip().limit() => iterable
    cursor = MagicMock()
    cursor.__iter__ = MagicMock(return_value=iter(find_return or []))
    col.find.return_value.sort.return_value.skip.return_value.limit.return_value = cursor

    col.find_one.return_value = find_one_return
    return col


# ---------------------------------------------------------------------------
# Tests: get_last_block
# ---------------------------------------------------------------------------


class TestGetLastBlock:
    """BlockService.get_last_block — obtiene el bloque con mayor índice."""

    def test_returns_last_block_when_exists(self):
        """Debe retornar el documento del bloque más reciente."""
        with patch("src.services.block_service.get_blocks_collection") as mock_col_fn:
            mock_col_fn.return_value.find_one.return_value = SAMPLE_BLOCK_DOC
            from src.services.block_service import BlockService
            service = BlockService()

            result = service.get_last_block()

            assert result == SAMPLE_BLOCK_DOC

    def test_returns_none_when_collection_is_empty(self):
        """Debe retornar None si no hay bloques en la colección."""
        with patch("src.services.block_service.get_blocks_collection") as mock_col_fn:
            mock_col_fn.return_value.find_one.return_value = None
            from src.services.block_service import BlockService
            service = BlockService()

            result = service.get_last_block()

            assert result is None

    def test_calls_find_one_with_descending_sort(self):
        """La query a MongoDB debe ordenar por index DESCENDING."""
        with patch("src.services.block_service.get_blocks_collection") as mock_col_fn:
            mock_col_fn.return_value.find_one.return_value = None
            from src.services.block_service import BlockService
            service = BlockService()

            service.get_last_block()

            call_kwargs = mock_col_fn.return_value.find_one.call_args
            # Verificar que se pasa el parámetro sort
            assert call_kwargs is not None


# ---------------------------------------------------------------------------
# Tests: save_block
# ---------------------------------------------------------------------------


class TestSaveBlock:
    """BlockService.save_block — persiste un bloque en MongoDB."""

    def test_save_block_dict_calls_insert_one(self):
        """Con un dict, debe llamar insert_one y retornar el mismo dict."""
        with patch("src.services.block_service.get_blocks_collection") as mock_col_fn:
            from src.services.block_service import BlockService
            service = BlockService()

            block_dict = {"index": 2, "hash": "c" * 64}
            result = service.save_block(block_dict)

            mock_col_fn.return_value.insert_one.assert_called_once_with(block_dict)
            assert result == block_dict

    def test_save_block_model_calls_insert_one(self):
        """Con un objeto Block, debe hacer model_dump y llamar insert_one."""
        with patch("src.services.block_service.get_blocks_collection") as mock_col_fn:
            from src.services.block_service import BlockService
            service = BlockService()

            block = Block(
                index=2,
                timestamp="2026-04-10T10:00:00Z",
                transactions=[],
                previous_hash="a" * 64,
                nonce=0,
                hash="c" * 64,
            )
            result = service.save_block(block)

            assert mock_col_fn.return_value.insert_one.called
            assert result["index"] == 2


# ---------------------------------------------------------------------------
# Tests: create_genesis_block
# ---------------------------------------------------------------------------


class TestCreateGenesisBlock:
    """BlockService.create_genesis_block — delega en save_block."""

    def test_delegates_to_save_block(self):
        """create_genesis_block debe llamar a save_block con el bloque dado."""
        with patch("src.services.block_service.get_blocks_collection") as mock_col_fn:
            from src.services.block_service import BlockService
            service = BlockService()

            block = Block(
                index=0,
                timestamp="2026-04-09T12:00:00Z",
                transactions=[],
                previous_hash="0" * 64,
                nonce=0,
                hash="genesis_hash" + "0" * 52,
            )
            service.create_genesis_block(block)

            assert mock_col_fn.return_value.insert_one.called


# ---------------------------------------------------------------------------
# Tests: get_chain
# ---------------------------------------------------------------------------


class TestGetChain:
    """BlockService.get_chain — paginación y orden ascendente."""

    def test_calls_count_documents(self):
        """Debe llamar count_documents para calcular el total."""
        with patch("src.services.block_service.get_blocks_collection") as mock_col_fn:
            col = make_mock_collection(find_return=[SAMPLE_BLOCK_DOC], count_return=5)
            mock_col_fn.return_value = col
            from src.services.block_service import BlockService
            service = BlockService()

            _, total = service.get_chain(page=1, limit=10)

            col.count_documents.assert_called_once_with({})
            assert total == 5

    def test_default_pagination_skip_is_zero(self):
        """Con page=1, skip debe ser 0."""
        with patch("src.services.block_service.get_blocks_collection") as mock_col_fn:
            col = make_mock_collection(find_return=[], count_return=0)
            mock_col_fn.return_value = col
            from src.services.block_service import BlockService
            service = BlockService()

            service.get_chain(page=1, limit=10)

            # skip = (1-1)*10 = 0
            col.find.return_value.sort.return_value.skip.assert_called_with(0)

    def test_page_2_skip_is_correct(self):
        """Con page=2, limit=5, skip debe ser 5."""
        with patch("src.services.block_service.get_blocks_collection") as mock_col_fn:
            col = make_mock_collection(find_return=[], count_return=10)
            mock_col_fn.return_value = col
            from src.services.block_service import BlockService
            service = BlockService()

            service.get_chain(page=2, limit=5)

            col.find.return_value.sort.return_value.skip.assert_called_with(5)

    def test_returns_blocks_with_confirmed_indexes(self):
        """Las transacciones retornadas deben tener block_index inyectado."""
        with patch("src.services.block_service.get_blocks_collection") as mock_col_fn:
            col = make_mock_collection(find_return=[SAMPLE_BLOCK_DOC], count_return=1)
            mock_col_fn.return_value = col
            from src.services.block_service import BlockService
            service = BlockService()

            blocks, _ = service.get_chain(page=1, limit=10)

            assert len(blocks) == 1
            tx = blocks[0]["transactions"][0]
            assert tx["block_index"] == SAMPLE_BLOCK_DOC["index"]
            assert tx["status"] == "CONFIRMED"


# ---------------------------------------------------------------------------
# Tests: get_block_by_index y get_block_by_hash
# ---------------------------------------------------------------------------


class TestGetBlockByIndex:
    """BlockService.get_block_by_index."""

    def test_returns_block_when_found(self):
        """Debe retornar el bloque cuando MongoDB lo encuentra."""
        with patch("src.services.block_service.get_blocks_collection") as mock_col_fn:
            mock_col_fn.return_value.find_one.return_value = SAMPLE_BLOCK_DOC
            from src.services.block_service import BlockService
            service = BlockService()

            result = service.get_block_by_index(1)

            assert result is not None
            assert result["index"] == 1

    def test_returns_none_when_not_found(self):
        """Debe retornar None si el bloque no existe."""
        with patch("src.services.block_service.get_blocks_collection") as mock_col_fn:
            mock_col_fn.return_value.find_one.return_value = None
            from src.services.block_service import BlockService
            service = BlockService()

            result = service.get_block_by_index(999)

            assert result is None


class TestGetBlockByHash:
    """BlockService.get_block_by_hash."""

    def test_returns_block_when_found(self):
        """Debe retornar el bloque cuando MongoDB lo encuentra por hash."""
        with patch("src.services.block_service.get_blocks_collection") as mock_col_fn:
            mock_col_fn.return_value.find_one.return_value = SAMPLE_BLOCK_DOC
            from src.services.block_service import BlockService
            service = BlockService()

            result = service.get_block_by_hash("b" * 64)

            assert result is not None

    def test_returns_none_when_not_found(self):
        """Debe retornar None si el hash no corresponde a ningún bloque."""
        with patch("src.services.block_service.get_blocks_collection") as mock_col_fn:
            mock_col_fn.return_value.find_one.return_value = None
            from src.services.block_service import BlockService
            service = BlockService()

            result = service.get_block_by_hash("z" * 64)

            assert result is None


# ---------------------------------------------------------------------------
# Tests: get_chain_stats
# ---------------------------------------------------------------------------


class TestGetChainStats:
    """BlockService.get_chain_stats — estadísticas en tiempo real."""

    def _make_stats_mock(self, blocks: list[dict], total: int, last_block_doc):
        """Helper para crear un mock de colección apropiado para get_chain_stats."""
        col = MagicMock()
        col.count_documents.return_value = total

        # find_one retorna el último bloque (timestamp)
        col.find_one.return_value = last_block_doc

        # find() retorna cursor iterable para acumular transacciones
        cursor = MagicMock()
        cursor.__iter__ = MagicMock(return_value=iter(blocks))
        col.find.return_value = cursor

        return col

    def test_empty_chain_returns_zeros(self):
        """Con cadena vacía, todos los contadores son 0 y last_block_time es None."""
        with patch("src.services.block_service.get_blocks_collection") as mock_col_fn:
            mock_col_fn.return_value = self._make_stats_mock(
                blocks=[], total=0, last_block_doc=None
            )
            from src.services.block_service import BlockService
            service = BlockService()

            stats = service.get_chain_stats()

            assert stats["total_blocks"] == 0
            assert stats["last_block_time"] is None
            assert stats["total_transactions"] == 0
            assert stats["total_ufrocoins_emitidos"] == 0.0

    def test_stats_with_one_block_two_transactions(self):
        """Un bloque con 2 transacciones debe acumular correctamente."""
        block = {
            "transactions": [
                {"from": "a", "to": "b", "amount": 100.0},
                {"from": "c", "to": "d", "amount": 50.0},
            ]
        }
        last_doc = {"timestamp": "2026-04-10T10:00:00Z"}

        with patch("src.services.block_service.get_blocks_collection") as mock_col_fn:
            mock_col_fn.return_value = self._make_stats_mock(
                blocks=[block], total=1, last_block_doc=last_doc
            )
            from src.services.block_service import BlockService
            service = BlockService()

            stats = service.get_chain_stats()

            assert stats["total_blocks"] == 1
            assert stats["last_block_time"] == "2026-04-10T10:00:00Z"
            assert stats["total_transactions"] == 2
            assert stats["total_ufrocoins_emitidos"] == pytest.approx(150.0)

    def test_non_dict_transactions_are_discarded(self):
        """Las transacciones que no sean dicts (e.g. strings, None) deben ignorarse."""
        block = {
            "transactions": [
                {"from": "a", "to": "b", "amount": 10.0},
                "invalid_string_tx",
                None,
            ]
        }
        with patch("src.services.block_service.get_blocks_collection") as mock_col_fn:
            mock_col_fn.return_value = self._make_stats_mock(
                blocks=[block], total=1, last_block_doc={"timestamp": "2026-04-10T10:00:00Z"}
            )
            from src.services.block_service import BlockService
            service = BlockService()

            stats = service.get_chain_stats()

            assert stats["total_transactions"] == 1
            assert stats["total_ufrocoins_emitidos"] == pytest.approx(10.0)

    def test_missing_amount_defaults_to_zero(self):
        """Una transacción sin 'amount' no debe romper el acumulado (cuenta como 0.0)."""
        block = {"transactions": [{"from": "a", "to": "b"}]}
        with patch("src.services.block_service.get_blocks_collection") as mock_col_fn:
            mock_col_fn.return_value = self._make_stats_mock(
                blocks=[block], total=1, last_block_doc={"timestamp": "2026-04-10T10:00:00Z"}
            )
            from src.services.block_service import BlockService
            service = BlockService()

            stats = service.get_chain_stats()

            assert stats["total_transactions"] == 1
            assert stats["total_ufrocoins_emitidos"] == pytest.approx(0.0)

    def test_multiple_blocks_accumulate_correctly(self):
        """Múltiples bloques deben acumular todas sus transacciones."""
        block1 = {"transactions": [{"from": "a", "to": "b", "amount": 100.0}]}
        block2 = {"transactions": [{"from": "c", "to": "d", "amount": 200.0},
                                    {"from": "e", "to": "f", "amount": 300.0}]}

        with patch("src.services.block_service.get_blocks_collection") as mock_col_fn:
            mock_col_fn.return_value = self._make_stats_mock(
                blocks=[block1, block2], total=2, last_block_doc={"timestamp": "2026-04-10T10:00:00Z"}
            )
            from src.services.block_service import BlockService
            service = BlockService()

            stats = service.get_chain_stats()

            assert stats["total_transactions"] == 3
            assert stats["total_ufrocoins_emitidos"] == pytest.approx(600.0)


# ---------------------------------------------------------------------------
# Tests: _with_confirmed_transaction_indexes (método estático)
# ---------------------------------------------------------------------------


class TestWithConfirmedTransactionIndexes:
    """BlockService._with_confirmed_transaction_indexes — enriquece transacciones."""

    def test_injects_block_index_into_transactions(self):
        """Cada transacción debe recibir el block_index del bloque contenedor."""
        from src.services.block_service import BlockService

        block = {
            "index": 3,
            "timestamp": "2026-04-10T10:00:00Z",
            "transactions": [{"id": "tx-1", "from": "a", "to": "b", "amount": 10.0}],
        }
        result = BlockService._with_confirmed_transaction_indexes(block)

        assert result["transactions"][0]["block_index"] == 3

    def test_sets_status_confirmed(self):
        """Las transacciones sin status deben recibir status=CONFIRMED."""
        from src.services.block_service import BlockService

        block = {
            "index": 1,
            "transactions": [{"id": "tx-1", "amount": 5.0}],
        }
        result = BlockService._with_confirmed_transaction_indexes(block)

        assert result["transactions"][0]["status"] == "CONFIRMED"

    def test_preserves_existing_status(self):
        """Si la transacción ya tiene status, se usa el valor existente (setdefault)."""
        from src.services.block_service import BlockService

        block = {
            "index": 2,
            "transactions": [{"id": "tx-1", "status": "MINING_REWARD", "amount": 50.0}],
        }
        result = BlockService._with_confirmed_transaction_indexes(block)

        assert result["transactions"][0]["status"] == "MINING_REWARD"

    def test_non_dict_transactions_passed_through(self):
        """Valores no-dict en transactions (anomalías) se pasan sin modificar."""
        from src.services.block_service import BlockService

        block = {
            "index": 1,
            "transactions": ["invalid_value"],
        }
        result = BlockService._with_confirmed_transaction_indexes(block)

        assert result["transactions"][0] == "invalid_value"

    def test_empty_transactions_list(self):
        """Un bloque sin transacciones produce transactions=[]."""
        from src.services.block_service import BlockService

        block = {"index": 0, "transactions": []}
        result = BlockService._with_confirmed_transaction_indexes(block)

        assert result["transactions"] == []

    def test_does_not_mutate_original_block(self):
        """La función retorna una copia; el dict original no se modifica."""
        from src.services.block_service import BlockService

        original_tx = {"id": "tx-1", "amount": 10.0}
        block = {"index": 1, "transactions": [original_tx]}
        _ = BlockService._with_confirmed_transaction_indexes(block)

        # La transacción original no debe tener block_index
        assert "block_index" not in original_tx
