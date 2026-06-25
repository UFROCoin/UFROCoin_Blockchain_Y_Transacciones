"""
CheckpointService — generación y consulta de checkpoints de la blockchain.

Un checkpoint resume un rango contiguo de bloques [from_block, to_block] con:
  - merkle_root: raíz del árbol de Merkle calculada sobre los hashes del rango.
  - last_block_hash: hash del último bloque del rango.
  - created_at: timestamp ISO 8601 UTC de la generación.
  - status: CREATED si la generación fue correcta.

Política ante errores en el cálculo del Merkle root:
  El checkpoint NO se persiste. El rango con error se incluye en el resultado
  de la llamada a generate_checkpoints() con status=ERROR para trazabilidad,
  pero no queda ningún documento en la colección checkpoints.

Política de duplicados:
  Si ya existe un checkpoint para el rango [from_block, to_block], ese rango
  se omite (no se sobreescribe, no se genera uno nuevo).
"""

import logging
import os
from datetime import datetime, timezone
from importlib import import_module
from typing import Any

from src.core.constants import DEFAULT_CHECKPOINT_FREQUENCY
from src.utils.merkle_utils import compute_merkle_root

LOGGER = logging.getLogger(__name__)


class CheckpointService:
    """
    Servicio responsable de generar y consultar checkpoints de la blockchain.

    Parámetros del constructor:
        blocks_collection: Colección MongoDB que contiene los bloques.
        checkpoints_collection: Colección MongoDB donde se persisten los checkpoints.
    """

    def __init__(self, blocks_collection: Any, checkpoints_collection: Any) -> None:
        self.blocks_collection = blocks_collection
        self.checkpoints_collection = checkpoints_collection

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------

    @staticmethod
    def get_checkpoint_frequency() -> int:
        """
        Lee la frecuencia de checkpoints desde la variable de entorno
        CHECKPOINT_FREQUENCY.

        Si la variable no está definida, no es un entero positivo o es menor
        que 1, se usa DEFAULT_CHECKPOINT_FREQUENCY (100).

        Retorna:
            Entero >= 1 que representa cada cuántos bloques se genera un checkpoint.
        """
        raw = os.getenv("CHECKPOINT_FREQUENCY", "")
        try:
            value = int(raw)
            if value >= 1:
                return value
        except (ValueError, TypeError):
            pass
        return DEFAULT_CHECKPOINT_FREQUENCY

    # ------------------------------------------------------------------
    # Generación
    # ------------------------------------------------------------------

    def generate_checkpoints(
        self, frequency: int | None = None
    ) -> dict[str, Any]:
        """
        Genera checkpoints para todos los rangos de bloques que aún no tienen uno.

        Parámetros:
            frequency: Frecuencia de bloques por checkpoint. Si es None, se usa
                       la variable de entorno CHECKPOINT_FREQUENCY (o el default).

        Retorna:
            Diccionario con:
                - generated (int): checkpoints nuevos persistidos.
                - skipped (int): rangos omitidos por duplicado.
                - errors (int): rangos donde el cálculo falló (no persistidos).
                - data (list[dict]): detalle de los checkpoints generados.
        """
        try:
            pymongo = import_module("pymongo")
        except ImportError as exc:
            raise RuntimeError("pymongo is required to generate checkpoints") from exc

        effective_frequency = frequency if (frequency and frequency >= 1) else self.get_checkpoint_frequency()

        # Obtener todos los bloques ordenados por índice ASC.
        # Solo se proyectan los campos necesarios (hash e index).
        blocks_cursor = (
            self.blocks_collection
            .find({}, {"_id": 0, "index": 1, "hash": 1})
            .sort("index", pymongo.ASCENDING)
        )
        all_blocks: list[dict[str, Any]] = list(blocks_cursor)

        total_blocks = len(all_blocks)

        # Si no hay suficientes bloques para cubrir un rango completo, no hay nada que hacer.
        if total_blocks < effective_frequency:
            LOGGER.debug(
                "generate_checkpoints: %d bloques disponibles, frecuencia %d — sin rangos completos.",
                total_blocks,
                effective_frequency,
            )
            return {"generated": 0, "skipped": 0, "errors": 0, "data": []}

        # Calcular los rangos completos (solo rangos cerrados).
        ranges = self._build_ranges(all_blocks, effective_frequency)

        generated = 0
        skipped = 0
        errors = 0
        created_checkpoints: list[dict[str, Any]] = []

        for block_range in ranges:
            from_block: int = block_range["from_block"]
            to_block: int = block_range["to_block"]
            hashes: list[str] = block_range["hashes"]
            last_hash: str = block_range["last_hash"]

            # Verificar si ya existe un checkpoint para este rango exacto.
            existing = self.checkpoints_collection.find_one(
                {"from_block": from_block, "to_block": to_block},
                {"_id": 0},
            )
            if existing is not None:
                LOGGER.debug(
                    "generate_checkpoints: rango [%d, %d] ya tiene checkpoint — omitido.",
                    from_block,
                    to_block,
                )
                skipped += 1
                continue

            # Calcular el Merkle root. Si falla, registrar error y NO persistir.
            try:
                merkle_root = compute_merkle_root(hashes)
            except Exception as exc:  # noqa: BLE001
                LOGGER.error(
                    "generate_checkpoints: error al calcular Merkle root para [%d, %d]: %s",
                    from_block,
                    to_block,
                    exc,
                )
                errors += 1
                continue

            checkpoint_doc = self._build_checkpoint_document(
                from_block=from_block,
                to_block=to_block,
                merkle_root=merkle_root,
                last_block_hash=last_hash,
            )

            try:
                self.checkpoints_collection.insert_one(checkpoint_doc)
            except Exception as exc:  # noqa: BLE001
                # Si la inserción falla (p. ej. por race condition en el índice único),
                # se trata como un skip para no generar duplicados.
                LOGGER.warning(
                    "generate_checkpoints: no se pudo persistir checkpoint [%d, %d]: %s",
                    from_block,
                    to_block,
                    exc,
                )
                skipped += 1
                continue

            # Excluir _id de la respuesta (MongoDB agrega _id tras insert_one).
            public_doc = {k: v for k, v in checkpoint_doc.items() if k != "_id"}
            generated += 1
            created_checkpoints.append(public_doc)
            LOGGER.info(
                "generate_checkpoints: checkpoint creado para rango [%d, %d] — merkle_root=%s…",
                from_block,
                to_block,
                merkle_root[:16],
            )

        return {
            "generated": generated,
            "skipped": skipped,
            "errors": errors,
            "data": created_checkpoints,
        }

    # ------------------------------------------------------------------
    # Consulta
    # ------------------------------------------------------------------

    def list_checkpoints(self) -> list[dict[str, Any]]:
        """
        Retorna todos los checkpoints persistidos ordenados por from_block ASC.

        Retorna:
            Lista de documentos de checkpoint sin el campo _id de MongoDB.
        """
        try:
            pymongo = import_module("pymongo")
        except ImportError as exc:
            raise RuntimeError("pymongo is required to list checkpoints") from exc

        cursor = self.checkpoints_collection.find(
            {}, {"_id": 0}
        ).sort("from_block", pymongo.ASCENDING)
        return list(cursor)

    def get_checkpoint_by_range(self, from_block: int, to_block: int) -> dict[str, Any] | None:
        """
        Retorna el checkpoint del rango [from_block, to_block], o None si no existe.

        Parámetros:
            from_block: Índice del primer bloque del rango.
            to_block: Índice del último bloque del rango.

        Retorna:
            Documento de checkpoint sin _id, o None.
        """
        return self.checkpoints_collection.find_one(
            {"from_block": from_block, "to_block": to_block},
            {"_id": 0},
        )

    def validate_fast(self) -> dict[str, Any]:
        """
        Valida la integridad de la blockchain comparando los Merkle roots actuales
        contra los checkpoints registrados, sin recorrer toda la cadena bloque a bloque.

        Algoritmo:
          1. Consulta todos los checkpoints (ordenados por from_block ASC).
          2. Si no hay checkpoints, retorna valid=False con reason=CHECKPOINTS_NOT_FOUND.
          3. Para cada checkpoint, obtiene los hashes actuales de los bloques del rango
             y recalcula el Merkle root.
          4. Si el Merkle root recalculado difiere del almacenado, busca el primer bloque
             alterado dentro del rango usando _find_first_corrupted_block().
          5. Si todos los checkpoints son íntegros, retorna valid=True.

        Esta operación es estrictamente read-only: no modifica ningún documento.

        Retorna:
            Diccionario con los campos definidos en FastValidationResponse.
        """
        try:
            pymongo = import_module("pymongo")
        except ImportError as exc:
            raise RuntimeError("pymongo is required to validate the chain") from exc

        # Obtener todos los checkpoints ordenados por from_block ASC.
        checkpoints = list(
            self.checkpoints_collection
            .find({}, {"_id": 0})
            .sort("from_block", pymongo.ASCENDING)
        )

        if not checkpoints:
            LOGGER.warning("validate_fast: no hay checkpoints registrados.")
            return {
                "valid": False,
                "message": None,
                "reason": "CHECKPOINTS_NOT_FOUND",
                "corrupted_range": None,
                "first_corrupted_block": None,
                "expected_root": None,
                "actual_root": None,
            }

        for checkpoint in checkpoints:
            from_block: int = checkpoint["from_block"]
            to_block: int = checkpoint["to_block"]
            expected_root: str = checkpoint["merkle_root"]

            # Obtener los hashes actuales de los bloques del rango.
            blocks_in_range = list(
                self.blocks_collection
                .find(
                    {"index": {"$gte": from_block, "$lte": to_block}},
                    {"_id": 0, "index": 1, "hash": 1},
                )
                .sort("index", pymongo.ASCENDING)
            )

            current_hashes = [b["hash"] for b in blocks_in_range]
            actual_root = compute_merkle_root(current_hashes)

            if actual_root.lower() != expected_root.lower():
                LOGGER.error(
                    "validate_fast: discrepancia de Merkle root en rango [%d, %d] — "
                    "expected=%s…, actual=%s…",
                    from_block,
                    to_block,
                    expected_root[:16],
                    actual_root[:16],
                )
                # Localizar el primer bloque alterado dentro del rango.
                first_corrupted = self._find_first_corrupted_block(
                    from_block=from_block,
                    to_block=to_block,
                    pymongo_module=pymongo,
                )
                return {
                    "valid": False,
                    "message": None,
                    "reason": "MERKLE_ROOT_MISMATCH",
                    "corrupted_range": {
                        "from_block": from_block,
                        "to_block": to_block,
                    },
                    "first_corrupted_block": first_corrupted,
                    "expected_root": expected_root,
                    "actual_root": actual_root,
                }

        LOGGER.info(
            "validate_fast: %d checkpoint(s) verificados — cadena íntegra.",
            len(checkpoints),
        )
        return {
            "valid": True,
            "message": "Blockchain integrity verified using checkpoints and hash tree",
            "reason": None,
            "corrupted_range": None,
            "first_corrupted_block": None,
            "expected_root": None,
            "actual_root": None,
        }

    def _find_first_corrupted_block(
        self,
        from_block: int,
        to_block: int,
        pymongo_module: Any,
    ) -> int | None:
        """
        Localiza el primer bloque alterado dentro de un rango [from_block, to_block].

        Estrategia de árbol de hashes (bisección):
          - Obtiene todos los bloques completos del rango (con contenido).
          - Divide el rango en mitades sucesivas.
          - En cada mitad, recalcula los hashes de contenido y construye el Merkle.
          - Si el Merkle de una mitad difiere del esperado (calculado desde los hashes
            almacenados), la corrupción está en esa mitad.
          - Continúa bisectando hasta llegar a un único bloque.
          - Ese bloque individual donde hash_almacenado ≠ hash_recalculado es el
            primer bloque corrupto.

        Si la bisección no encuentra diferencias individuales (caso degenerado donde
        el hash del bloque coincide pero el Merkle no, lo que no debería ocurrir en
        un escenario real), retorna None.

        Parámetros:
            from_block: Índice del primer bloque del rango corrupto.
            to_block: Índice del último bloque del rango corrupto.
            pymongo_module: Módulo pymongo importado dinámicamente.

        Retorna:
            Índice del primer bloque corrupto, o None si no se pudo identificar.
        """
        # Cargamos los bloques completos del rango para poder recalcular hashes.
        blocks_full = list(
            self.blocks_collection
            .find(
                {"index": {"$gte": from_block, "$lte": to_block}},
                {"_id": 0},
            )
            .sort("index", pymongo_module.ASCENDING)
        )

        if not blocks_full:
            return None

        # Bisección sobre la lista de bloques del rango usando Merkle.
        # candidate_blocks es la sublista donde sabemos que está la corrupción.
        candidate_blocks = blocks_full

        while len(candidate_blocks) > 1:
            mid = len(candidate_blocks) // 2
            left_half = candidate_blocks[:mid]
            right_half = candidate_blocks[mid:]

            # Merkle de la mitad izquierda calculado desde hashes almacenados.
            left_stored_root = compute_merkle_root([b["hash"] for b in left_half])
            # Merkle de la mitad izquierda calculado desde contenido real.
            left_computed_root = compute_merkle_root(
                [self._recompute_block_hash(b) for b in left_half]
            )

            if left_stored_root.lower() != left_computed_root.lower():
                # La corrupción está en la mitad izquierda.
                candidate_blocks = left_half
            else:
                # La corrupción está en la mitad derecha.
                candidate_blocks = right_half

        # Quedó un único candidato: verificamos que efectivamente está corrupto.
        if len(candidate_blocks) == 1:
            block = candidate_blocks[0]
            stored_hash = block.get("hash", "")
            computed_hash = self._recompute_block_hash(block)
            if stored_hash.lower() != computed_hash.lower():
                return block["index"]

        # Si el candidato no muestra diferencia individual (caso degenerado),
        # hacemos escaneo lineal como respaldo.
        return self._linear_scan_first_corrupted(blocks_full)

    @staticmethod
    def _recompute_block_hash(block: dict[str, Any]) -> str:
        """
        Recalcula el hash SHA-256 de un bloque desde su contenido almacenado,
        reutilizando la misma lógica que BlockValidationService.

        Parámetros:
            block: Documento de bloque con todos los campos.

        Retorna:
            Hash SHA-256 hexadecimal recalculado.
        """
        # Importación diferida para evitar dependencias circulares.
        from src.services.block_validation_service import BlockValidationService
        return BlockValidationService._calculate_block_hash_from_dict(block)

    @staticmethod
    def _linear_scan_first_corrupted(blocks: list[dict[str, Any]]) -> int | None:
        """
        Escaneo lineal de respaldo para encontrar el primer bloque donde
        el hash almacenado difiere del hash recalculado desde el contenido.

        Parámetros:
            blocks: Lista de bloques completos ordenados por index ASC.

        Retorna:
            Índice del primer bloque corrupto, o None si no se detecta ninguno.
        """
        from src.services.block_validation_service import BlockValidationService
        for block in blocks:
            stored = block.get("hash", "")
            computed = BlockValidationService._calculate_block_hash_from_dict(block)
            if stored.lower() != computed.lower():
                return block["index"]
        return None


    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    @staticmethod
    def _build_ranges(
        all_blocks: list[dict[str, Any]], frequency: int
    ) -> list[dict[str, Any]]:
        """
        Construye la lista de rangos completos de bloques dado el intervalo de frecuencia.

        Solo se generan rangos donde hay exactamente ``frequency`` bloques.
        El último grupo se descarta si está incompleto (< frequency bloques).

        Parámetros:
            all_blocks: Lista de dicts con al menos los campos ``index`` y ``hash``,
                        ordenada de forma ascendente por ``index``.
            frequency: Cantidad de bloques por rango.

        Retorna:
            Lista de dicts con:
                - from_block (int): índice del primer bloque del rango.
                - to_block (int): índice del último bloque del rango.
                - hashes (list[str]): hashes de los bloques del rango.
                - last_hash (str): hash del último bloque del rango.
        """
        ranges: list[dict[str, Any]] = []
        total = len(all_blocks)
        complete_groups = total // frequency

        for group in range(complete_groups):
            start = group * frequency
            end = start + frequency  # end es exclusivo (slice)
            group_blocks = all_blocks[start:end]

            from_block = group_blocks[0]["index"]
            to_block = group_blocks[-1]["index"]
            hashes = [b["hash"] for b in group_blocks]
            last_hash = group_blocks[-1]["hash"]

            ranges.append({
                "from_block": from_block,
                "to_block": to_block,
                "hashes": hashes,
                "last_hash": last_hash,
            })

        return ranges

    @staticmethod
    def _build_checkpoint_document(
        from_block: int,
        to_block: int,
        merkle_root: str,
        last_block_hash: str,
    ) -> dict[str, Any]:
        """
        Construye el documento de checkpoint listo para insertar en MongoDB.

        Parámetros:
            from_block: Índice del primer bloque del rango.
            to_block: Índice del último bloque del rango.
            merkle_root: Merkle root calculado para el rango.
            last_block_hash: Hash del último bloque del rango.

        Retorna:
            Diccionario con todos los campos del checkpoint.
        """
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return {
            "from_block": from_block,
            "to_block": to_block,
            "merkle_root": merkle_root,
            "last_block_hash": last_block_hash,
            "created_at": created_at,
            "status": "CREATED",
        }
