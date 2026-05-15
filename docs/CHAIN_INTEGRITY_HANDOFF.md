# Chain Integrity Validation Handoff

## 1. Objetivo de este documento

Este archivo resume el contexto completo de la implementacion de la **validacion de integridad de la blockchain completa**. La idea es que cualquier persona o agente que lea este documento entienda rapidamente:

- que se implemento
- que decisiones se tomaron
- que archivos se tocaron
- como verificar el comportamiento manualmente
- que falta por hacer
- que cosas estan fuera de alcance

---

## 2. Contexto funcional y alcance

### User Story implementada

> Como sistema, quiero exponer un endpoint de validacion y registrar el punto exacto de falla para facilitar la auditoria de la integridad.

### Criterios de aceptacion cubiertos

- [x] Crear el endpoint `GET /api/chain/validate`.
- [x] Integrar la verificacion de continuidad: el `previous_hash` de cada bloque debe coincidir con el hash del bloque anterior.
- [x] El endpoint retorna el formato `{"valid": true/false, "error_at_block": N}`.
- [x] Si la cadena es invalida, se genera un log en el servidor indicando el indice del primer bloque corrupto detectado.
- [x] Recorrer la blockchain de principio a fin (index ASC).
- [x] Por cada bloque, regenerar el hash actual usando el algoritmo definido y los datos crudos del bloque.
- [x] La funcion de validacion es estrictamente read-only: no modifica ningun documento.

### Fuera de alcance

No se implemento ni se debe considerar parte de esta sesion:

- modificacion de bloques
- reparacion o correccion de hashes
- autenticacion del endpoint
- paginacion de la respuesta de validacion

---

## 3. Resumen de lo implementado

### Archivos modificados

#### `src/models/block.py`

Se agregaron cuatro modelos Pydantic al final del archivo:

- `BlockIntegrityResult`: resultado de integridad para un bloque individual. Campos:
  - `index` (int): posicion del bloque en la cadena.
  - `stored_hash` (str): hash SHA-256 almacenado en MongoDB.
  - `computed_hash` (str): hash SHA-256 recalculado en tiempo real.
  - `valid` (bool): `True` si el hash individual es correcto Y el `previous_hash` enlaza correctamente con el bloque anterior.

- `ChainValidationData`: payload de la respuesta detallada. Campos:
  - `chain_valid` (bool): `True` si todos los bloques son integros.
  - `total_blocks` (int): cantidad total de bloques evaluados.
  - `blocks` (list[BlockIntegrityResult]): detalle por bloque en orden cronologico.

- `ChainValidationSuccessResponse`: envelope estandar de respuesta detallada (conservado para compatibilidad interna).

- **`ChainValidateResponse`** *(nuevo — contrato publico del ticket)*: respuesta minima exigida. Campos:
  - `valid` (bool): `True` si la cadena es integra.
  - `error_at_block` (int | None): indice del primer bloque corrupto, o `null` si la cadena es valida.

#### `src/services/block_validation_service.py`

Se agrego `import logging` y el logger de modulo:

```python
logger = logging.getLogger(__name__)
```

Se actualizo el metodo `validate_chain_integrity()` con dos verificaciones por bloque:

1. **Integridad individual del hash** (`hash_valid`): `stored_hash == computed_hash`.
2. **Continuidad de la cadena** (`link_valid`): `block.previous_hash == hash_almacenado_del_bloque_anterior`. Aplica desde el bloque con index >= 1.

Un bloque falla si cualquiera de las dos verificaciones falla. Solo se loguea y se registra `error_at_block` para el **primer** bloque corrupto encontrado.

El metodo ahora retorna un dict con `chain_valid`, `error_at_block`, `total_blocks` y `blocks`.

#### `src/api/block_router.py`

- Se importo `ChainValidateResponse`.
- El endpoint `GET /api/chain/validate` ahora usa `response_model=ChainValidateResponse`.
- La descripcion del endpoint se actualizo para documentar ambas verificaciones y el logging.
- La respuesta se simplifica a `{"valid": ..., "error_at_block": ...}`.

---

## 4. Contratos de la API

### Endpoint

```
GET /api/chain/validate
```

No requiere cuerpo ni parametros.

### Respuesta — cadena integra

```json
{"valid": true, "error_at_block": null}
```

### Respuesta — cadena comprometida

```json
{"valid": false, "error_at_block": 3}
```

`error_at_block` contiene el indice del **primer** bloque donde se detecto la falla (puede ser por hash incorrecto o por `previous_hash` que no enlaza con el bloque anterior).

### Respuesta — cadena vacia

```json
{"valid": true, "error_at_block": null}
```

---

## 5. Logica de validacion por tipo de verificacion

### Verificacion 1 — Integridad individual del hash

El metodo `_calculate_block_hash_from_dict` define dos caminos segun el tipo de bloque:

#### Bloque genesis (`index == 0` y `previous_hash == "0" * 64`)

Se usa `calculate_concatenated_block_hash` de `src/utils/hash_utils.py`:

```
SHA-256( str(index) + str(previous_hash) + str(timestamp) + JSON(transactions) + str(nonce) )
```

#### Bloques normales

Se usa serializacion JSON deterministica:

```python
payload = {
    "index": ...,
    "timestamp": ...,
    "transactions": ...,
    "previous_hash": ...,
    "nonce": ...,
}
SHA-256( json.dumps(payload, sort_keys=True, separators=(",", ":")) )
```

El campo `hash` nunca se incluye en el payload de recalculo.

### Verificacion 2 — Continuidad del previous_hash

Para cada bloque con `index >= 1`, se comprueba:

```python
block["previous_hash"].lower() == hash_almacenado_del_bloque_anterior.lower()
```

Esta verificacion detecta bloques reordenados o con `previous_hash` adulterado aunque el hash individual sea correcto.

### Logging del primer bloque corrupto

Cuando se detecta el primer fallo (ya sea de hash o de continuidad), se emite:

```
ERROR src.services.block_validation_service — Chain integrity failure detected at block N — hash_valid=True/False, link_valid=True/False
```

Los bloques subsiguientes aun se evaluan (para tener el detalle completo), pero `error_at_block` ya no se sobreescribe.

---

## 6. Como verificar que esta bien

### Verificacion de importaciones (sin Docker)

```powershell
.venv\Scripts\python.exe -c "from src.services.block_validation_service import BlockValidationService; from src.models.block import ChainValidateResponse; print('Imports OK')"
```

### Verificacion funcional con Docker

#### Levantar el stack

```powershell
docker-compose up --build -d
```

#### Caso 1 — Cadena integra

```powershell
Invoke-WebRequest -Uri "http://localhost:8000/api/chain/validate" -UseBasicParsing
```

Esperado:
- HTTP 200.
- `{"valid": true, "error_at_block": null}`.

#### Caso 2 — Hash de bloque adulterado

1. Desde mongosh o MongoDB Compass, modificar el campo `hash` de cualquier bloque:

```js
use blockchain_db
db.blocks.updateOne(
  { index: 1 },
  { $set: { hash: "0000000000000000000000000000000000000000000000000000000000000000" } }
)
```

2. Llamar al endpoint.

Esperado:
- `{"valid": false, "error_at_block": 1}`.
- Log en el servidor: `Chain integrity failure detected at block 1 — hash_valid=False, link_valid=True`.

#### Caso 3 — previous_hash roto (enlace de cadena adulterado)

1. Modificar el campo `previous_hash` de un bloque para que no coincida con el hash del bloque anterior:

```js
db.blocks.updateOne(
  { index: 2 },
  { $set: { previous_hash: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" } }
)
```

2. Llamar al endpoint.

Esperado:
- `{"valid": false, "error_at_block": 2}`.
- Log: `Chain integrity failure detected at block 2 — hash_valid=True, link_valid=False`.

#### Caso 4 — Cadena vacia

1. Levantar la app con MongoDB sin bloques.
2. Llamar al endpoint.

Esperado:
- `{"valid": true, "error_at_block": null}`.

#### Ver logs del servidor

```powershell
docker logs ufrocoin_api
```

Buscar lineas con: `Chain integrity failure detected at block`.

---

## 7. Decisiones tecnicas relevantes

### Siempre HTTP 200

El endpoint devuelve 200 independientemente de si la cadena esta integra o no. El resultado real esta en `valid`. Esto es intencional: la operacion de validacion en si fue exitosa; el estado de la cadena es informacion de negocio, no un error de servidor.

### Solo se registra el primer bloque corrupto

`error_at_block` captura unicamente el primer fallo. Los bloques siguientes aun se evaluan para tener visibilidad completa via logs, pero no sobreescriben el indice inicial de corrupcion.

### Read-only garantizado

El metodo solo usa `.find()` con proyeccion `{"_id": 0}`. No existe ninguna llamada a `.insert_one()`, `.update_one()`, `.delete_one()` ni similar dentro de `validate_chain_integrity`.

### Reutilizacion del algoritmo existente

Se reutiliza `_calculate_block_hash_from_dict`, que ya era el corazon de `validate_block_integrity`. Esto asegura que el recalculo de hashes en la validacion de cadena usa exactamente el mismo algoritmo que la validacion individual de bloque. No hay logica de hash duplicada.

### Dependencia de DB obligatoria

Si `BlockValidationService` se instancia sin `db_client`, `validate_chain_integrity` lanza `RuntimeError` con un mensaje descriptivo. El endpoint ya inyecta la DB correctamente via `get_block_validation_service`.

---

## 8. Lo que falta por hacer

- Agregar paginacion a la respuesta si la cadena crece y la respuesta se vuelve grande.
- Definir con el equipo si un resultado `valid: false` debe devolver un codigo HTTP diferente (por ejemplo, 409 o 422).
- Definir rol o autenticacion necesaria para acceder al endpoint si se considera sensible.
- Considerar exponer el detalle por bloque (`stored_hash`, `computed_hash`) en un endpoint separado o como query param opcional.

---

## 9. Lo que no se debe tocar sin coordinacion

- La logica de `_calculate_block_hash_from_dict` y `_is_genesis_block` en `BlockValidationService`: cualquier cambio rompe tanto la validacion individual como la de cadena.
- La regla de concatenacion para el genesis en `hash_utils.py`: esta directamente ligada al hash almacenado del bloque genesis real en produccion.
- El modelo `ChainValidateResponse`: es el contrato publico del endpoint definido en el ticket; cambiar `valid` o `error_at_block` sin versionado puede romper clientes que ya consuman la respuesta.

---

## 10. Orden de commits recomendado

1. `feat: add ChainValidateResponse model with {valid, error_at_block} shape`
2. `feat: add previous_hash continuity check and server logging to validate_chain_integrity`
3. `feat: update GET /api/chain/validate to return simplified audit response`
4. `docs: update CHAIN_INTEGRITY_HANDOFF with ticket changes`
