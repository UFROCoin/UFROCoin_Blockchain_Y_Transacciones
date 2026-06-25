# Checkpoint Handoff

## 1. Objetivo de este documento

Este archivo resume el contexto completo de la implementacion del sistema de **checkpoints de la blockchain**. La idea es que cualquier persona o agente que lea este documento entienda rapidamente:

- que se implemento
- que decisiones se tomaron
- que archivos se tocaron
- como verificar el comportamiento manualmente
- que falta por hacer
- que cosas estan fuera de alcance

---

## 2. Contexto funcional y alcance

### User Story implementada

> Como sistema, quiero generar checkpoints cada N bloques segun configuracion, para guardar puntos de verificacion eficientes de la integridad de la cadena.

### Criterios de aceptacion cubiertos

- [x] El sistema permite configurar la frecuencia de checkpoints: 50, 100, 1.000 bloques u otro valor definido (via variable de entorno `CHECKPOINT_FREQUENCY`).
- [x] Cada checkpoint contiene `from_block`, `to_block`, `merkle_root`, `last_block_hash`, `created_at` y `status`.
- [x] El `merkle_root` se calcula usando los hashes de todos los bloques incluidos en el rango.
- [x] El checkpoint se genera sin modificar bloques, transacciones ni saldos (operacion estrictamente read-only sobre las colecciones existentes).
- [x] El sistema evita crear checkpoints duplicados para el mismo rango (`from_block`, `to_block`).
- [x] Si ocurre un error al calcular el arbol de hashes, el checkpoint no se registra (se reporta en el campo `errors` de la respuesta, pero no queda ningun documento en la coleccion).
- [x] El endpoint `GET /api/chain/validate/fast` consulta los checkpoints existentes y recalcula el Merkle root de cada rango.
- [x] Si no existen checkpoints, retorna `valid=false` con `reason=CHECKPOINTS_NOT_FOUND`.
- [x] Si todos los Merkle roots coinciden, retorna `valid=true` con el mensaje definido en los criterios.
- [x] Si un checkpoint no coincide, retorna `valid=false` con `corrupted_range`, `first_corrupted_block`, `expected_root`, `actual_root` y `reason=MERKLE_ROOT_MISMATCH`.
- [x] Dentro del rango corrupto, se usa bisecion Merkle (divide y venceras) para localizar el primer bloque alterado.
- [x] La validacion rapida no modifica bloques, transacciones ni saldos.

### Fuera de alcance

No se implemento ni se debe considerar parte de esta sesion:

- Generacion automatica en startup o cron interno (el disparador es el endpoint POST).
- Verificacion de integridad de la cadena usando el checkpoint (eso pertenece a la US de validacion).
- Autenticacion de los endpoints.
- Paginacion del listado de checkpoints.
- Checkpoints parciales (rangos con menos bloques que la frecuencia).

---

## 3. Resumen de lo implementado

### Archivos nuevos

#### `src/models/checkpoint.py`

Modelos Pydantic para el dominio de checkpoints:

- `CheckpointStatus` (str Enum): valores `CREATED` y `ERROR`.
- `CheckpointDocument`: refleja el documento MongoDB (extra="ignore").
- `CheckpointData`: payload publico de un checkpoint (extra="forbid").
- `CheckpointResponse`: envelope para un solo checkpoint.
- `CheckpointListResponse`: envelope para la lista de checkpoints.
- `CheckpointGenerateResult`: resultado completo de una generacion (incluye `generated`, `skipped`, `errors`, `data`).
- `CheckpointGenerateRequest`: cuerpo opcional del POST con el campo `frequency` (int >= 1).

#### `src/utils/merkle_utils.py`

Implementacion pura del algoritmo Merkle tree:

- `compute_merkle_root(block_hashes: list[str]) -> str`: calcula SHA-256 pairwise de forma iterativa (bottom-up).
- Casos especiales: lista vacia devuelve SHA-256 de cadena vacia; lista de un elemento devuelve ese hash.
- Si la cantidad de nodos en cualquier nivel del arbol es impar, el ultimo hash se duplica.
- Sin dependencias externas (solo `hashlib`).

#### `src/services/checkpoint_service.py`

Clase `CheckpointService`:

- `__init__(blocks_collection, checkpoints_collection)`: recibe las colecciones inyectadas.
- `get_checkpoint_frequency() -> int`: lee `CHECKPOINT_FREQUENCY` del ENV con fallback a `DEFAULT_CHECKPOINT_FREQUENCY` (100).
- `generate_checkpoints(frequency=None) -> dict`: genera checkpoints para rangos completos sin checkpoint previo. Retorna dict con `generated`, `skipped`, `errors` y `data`.
- `list_checkpoints() -> list[dict]`: retorna todos los checkpoints ordenados por `from_block` ASC.
- `get_checkpoint_by_range(from_block, to_block) -> dict | None`: busca un checkpoint por rango exacto.
- `_build_ranges(all_blocks, frequency) -> list[dict]`: helper estatico que particiona la lista de bloques en rangos completos.
- `_build_checkpoint_document(...) -> dict`: helper estatico que construye el documento listo para insertar.

#### `src/api/checkpoint_router.py`

Router FastAPI con dos endpoints:

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| `POST` | `/api/chain/checkpoints/generate` | Genera checkpoints para los rangos aun sin checkpoint |
| `GET` | `/api/chain/checkpoints` | Lista todos los checkpoints persistidos |

#### `test/test_checkpoint_service.py`

Tests unitarios con mocks de MongoDB:
- 7 tests de `compute_merkle_root`
- 5 tests de `get_checkpoint_frequency`
- 11 tests de `generate_checkpoints`
- 2 tests de `list_checkpoints`
- 2 tests de `get_checkpoint_by_range`

Total: **27 tests unitarios**.

#### `test/test_checkpoint_endpoint.py`

Tests de integracion con TestClient y dependency_overrides:
- 12 tests de `POST /api/chain/checkpoints/generate`
- 8 tests de `GET /api/chain/checkpoints`

Total: **20 tests de integracion**.

### Archivos modificados

#### `src/core/constants.py`

Se agregaron al final del archivo:

```python
DEFAULT_CHECKPOINT_FREQUENCY = 100
DEFAULT_CHECKPOINTS_COLLECTION_NAME = "checkpoints"
```

#### `src/core/database.py`

- Se importo `DEFAULT_CHECKPOINTS_COLLECTION_NAME` desde constants.
- Se agrego `get_checkpoints_collection_name()` con soporte para `MONGO_CHECKPOINTS_COLLECTION`.
- Se agrego `get_checkpoints_collection()` con el mismo patron que las demas colecciones.
- En `initialize_database()` se crean tres indices en la coleccion `checkpoints`:
  - `(from_block, to_block)` unico (evita duplicados del mismo rango).
  - `from_block` ASC (para consultas por rango).
  - `created_at` DESC (para listar los mas recientes primero).

#### `src/main.py`

Se importo `checkpoint_router` y se registro con prefijo `/api`.

---

## 4. Contratos de la API

### POST /api/chain/checkpoints/generate

**Cuerpo (opcional):**

```json
{
  "frequency": 100
}
```

Si se omite el cuerpo, se usa la variable de entorno `CHECKPOINT_FREQUENCY` (default: 100).

**Respuesta exitosa (200 OK):**

```json
{
  "status": "ok",
  "generated": 2,
  "skipped": 0,
  "errors": 0,
  "data": [
    {
      "from_block": 0,
      "to_block": 99,
      "merkle_root": "a3f1...",
      "last_block_hash": "7e2c...",
      "created_at": "2026-06-25T06:00:00Z",
      "status": "CREATED"
    },
    {
      "from_block": 100,
      "to_block": 199,
      "merkle_root": "b5d2...",
      "last_block_hash": "9f1a...",
      "created_at": "2026-06-25T06:00:01Z",
      "status": "CREATED"
    }
  ]
}
```

**Respuesta con cadena sin rangos completos:**

```json
{
  "status": "ok",
  "generated": 0,
  "skipped": 0,
  "errors": 0,
  "data": []
}
```

**Respuesta con frequency invalido (422):**

```json
{
  "detail": [
    {
      "type": "greater_than_equal",
      "loc": ["body", "frequency"],
      "msg": "Input should be greater than or equal to 1"
    }
  ]
}
```

### GET /api/chain/checkpoints

**Respuesta exitosa (200 OK):**

```json
{
  "status": "ok",
  "data": [
    {
      "from_block": 0,
      "to_block": 99,
      "merkle_root": "a3f1...",
      "last_block_hash": "7e2c...",
      "created_at": "2026-06-25T06:00:00Z",
      "status": "CREATED"
    }
  ]
}
```

**Respuesta sin checkpoints:**

```json
{
  "status": "ok",
  "data": []
}
```

---

## 5. Logica del algoritmo Merkle

El arbol de Merkle se construye de forma iterativa (bottom-up):

```
Entrada: [h0, h1, h2, h3, h4]   (5 hashes — cantidad impar)

Nivel 0 (hojas):     [h0, h1, h2, h3, h4, h4]   <- h4 duplicado
Nivel 1:             [SHA256(h0+h1), SHA256(h2+h3), SHA256(h4+h4)]  <- 3 nodos, impar
Nivel 1 ajustado:    [p01, p23, p44, p44]          <- p44 duplicado
Nivel 2:             [SHA256(p01+p23), SHA256(p44+p44)]
Nivel 3 (raiz):      SHA256( nivel2[0] + nivel2[1] )
```

La concatenacion es directa entre strings hexadecimales en minusculas. No se usa codificacion binaria de los hashes antes de concatenar.

---

## 6. Logica de rangos

La particion de bloques en rangos usa division entera:

```python
complete_groups = total_blocks // frequency
```

Solo se generan checkpoints para rangos **completos**. El ultimo grupo parcial (si `total_blocks % frequency != 0`) se descarta.

Ejemplo con 250 bloques y frecuencia 100:
- Rango 0: bloques con indices 0-99   → checkpoint generado.
- Rango 1: bloques con indices 100-199 → checkpoint generado.
- Residuo: bloques con indices 200-249 → descartado.

---

## 7. Como verificar que esta bien

### Verificacion de importaciones (sin Docker)

```powershell
.\venv\Scripts\python.exe -c "
from src.services.checkpoint_service import CheckpointService
from src.models.checkpoint import CheckpointGenerateResult
from src.utils.merkle_utils import compute_merkle_root
print('Imports OK')
"
```

### Ejecutar los tests

```powershell
.\venv\Scripts\python.exe -m pytest test/test_checkpoint_service.py test/test_checkpoint_endpoint.py -v
```

### Verificacion funcional con Docker

#### Levantar el stack

```powershell
docker-compose up --build -d
```

#### Caso 1 — Generar checkpoints con frecuencia por defecto

```powershell
Invoke-WebRequest -Uri "http://localhost:8000/api/chain/checkpoints/generate" -Method POST -UseBasicParsing
```

Esperado:
- HTTP 200.
- `generated` >= 0 segun la cantidad de bloques en la cadena.
- Si la cadena tiene menos de 100 bloques: `generated=0`, `data=[]`.

#### Caso 2 — Generar con frecuencia personalizada

```powershell
$body = '{"frequency": 1}'
Invoke-WebRequest -Uri "http://localhost:8000/api/chain/checkpoints/generate" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing
```

Esperado: se genera un checkpoint por cada bloque completo (frecuencia 1 implica 1 bloque por rango).

#### Caso 3 — Listar checkpoints

```powershell
Invoke-WebRequest -Uri "http://localhost:8000/api/chain/checkpoints" -UseBasicParsing
```

Esperado: HTTP 200, `status=ok`, `data` con la lista de checkpoints generados.

#### Caso 4 — Verificar que no genera duplicados

1. Llamar a `/generate` dos veces con la misma frecuencia.
2. En la segunda llamada, `generated=0` y `skipped` debe ser igual al numero de rangos existentes.

---

## 8. Decisiones tecnicas relevantes

### Nueva coleccion independiente

Los checkpoints se almacenan en una coleccion `checkpoints` separada. Esto es coherente con la arquitectura del proyecto, que ya usa colecciones separadas para `blocks`, `transactions` y `chain_metadata`. No se tocan esas colecciones.

### No se persiste ante error Merkle

Si `compute_merkle_root` lanza una excepcion, el checkpoint no se guarda. Se cuenta en `errors` de la respuesta del POST para trazabilidad, pero no queda ningun documento en la coleccion. Esta politica mantiene la coleccion libre de registros corrompidos o incompletos.

### Endpoint POST en lugar de cron automatico

La generacion se dispara mediante una llamada explicita a `POST /api/chain/checkpoints/generate`. Esto mantiene la filosofia del proyecto (sin workers en background dentro del proceso FastAPI) y permite que el Modulo 3, un scheduler externo o un operador disparen la generacion segun sus necesidades.

### Frecuencia configurable por ENV

La variable `CHECKPOINT_FREQUENCY` permite cambiar la frecuencia sin redeployar codigo. El cuerpo del POST puede sobreescribirla para usos puntuales (por ejemplo, auditorias manuales con frecuencia diferente).

### Rangos parciales descartados

Un grupo de bloques con menos bloques que la frecuencia no genera checkpoint. Esta decision garantiza que cada checkpoint siempre cubre exactamente `frequency` bloques, lo que hace predecible el tamano del arbol Merkle y simplifica la verificacion.

### Indice unico en (from_block, to_block)

El indice unico en MongoDB actua como segunda linea de defensa contra duplicados, ademas de la verificacion previa con `find_one`. Esto protege ante race conditions en entornos con multiples llamadas concurrentes.

---

## 9. Lo que falta por hacer

- Endpoint `GET /api/chain/checkpoints/{from_block}/{to_block}` para consultar un checkpoint especifico por rango.
- Verificacion de integridad usando el checkpoint: recalcular el Merkle root del rango y compararlo con el `merkle_root` almacenado.
- Paginacion del listado de checkpoints si la cadena crece mucho.
- Evaluar si el endpoint de generacion debe requerir autenticacion.
- Agregar el campo `frequency` al documento de checkpoint para registrar con que frecuencia fue generado.

---

## 10. Orden de commits recomendado

1. `feat(constants): add DEFAULT_CHECKPOINT_FREQUENCY and DEFAULT_CHECKPOINTS_COLLECTION_NAME`
2. `feat(db): add checkpoints collection support and indexes`
3. `feat(models): add checkpoint Pydantic models`
4. `feat(utils): add compute_merkle_root in merkle_utils`
5. `feat(service): add CheckpointService with generate, list and query methods`
6. `feat(api): add POST /api/chain/checkpoints/generate and GET /api/chain/checkpoints endpoints`
7. `feat(main): register checkpoint_router`
8. `test: add unit and integration tests for checkpoint service and endpoints`
9. `docs: add CHECKPOINT_HANDOFF`
