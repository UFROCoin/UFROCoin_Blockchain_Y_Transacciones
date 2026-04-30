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

> Como sistema, quiero recalcular los hashes de cada bloque comparandolos con los almacenados para asegurar que el contenido de la cadena es veridico.

### Criterios de aceptacion cubiertos

- Recorrer la blockchain de principio a fin (index ASC).
- Por cada bloque, regenerar el hash actual usando el algoritmo definido y los datos crudos del bloque.
- Confirmar que el hash almacenado coincide con el hash generado en tiempo real.
- La funcion de validacion es estrictamente read-only: no modifica ningun documento.

### Fuera de alcance

No se implemento ni se debe considerar parte de esta sesion:

- modificacion de bloques
- reparacion o correccion de hashes
- validacion de la cadena de `previous_hash` entre bloques consecutivos
- autenticacion del endpoint
- paginacion de la respuesta de validacion

---

## 3. Resumen de lo implementado

### Archivos modificados

#### `src/models/block.py`

Se agregaron tres modelos Pydantic al final del archivo:

- `BlockIntegrityResult`: resultado de integridad para un bloque individual. Campos:
  - `index` (int): posicion del bloque en la cadena.
  - `stored_hash` (str): hash SHA-256 almacenado en MongoDB.
  - `computed_hash` (str): hash SHA-256 recalculado en tiempo real.
  - `valid` (bool): `True` si `stored_hash == computed_hash`.

- `ChainValidationData`: payload de la respuesta de validacion. Campos:
  - `chain_valid` (bool): `True` si todos los bloques son integros.
  - `total_blocks` (int): cantidad total de bloques evaluados.
  - `blocks` (list[BlockIntegrityResult]): detalle por bloque en orden cronologico.

- `ChainValidationSuccessResponse`: envelope estandar de respuesta del endpoint. Campos:
  - `success` (bool)
  - `message` (str)
  - `data` (ChainValidationData)
  - `error` (ApiErrorDetail | None)

#### `src/services/block_validation_service.py`

Se agrego el metodo `validate_chain_integrity()` a `BlockValidationService`.

Comportamiento:

1. Verifica que la instancia tenga conexion a DB; si no, lanza `RuntimeError`.
2. Consulta la coleccion `blocks` con `.find({}, {"_id": 0}).sort("index", ASCENDING)` — sin escrituras.
3. Para cada bloque del cursor:
   - Obtiene `stored_hash = raw_block["hash"]`.
   - Recalcula `computed_hash` usando `_calculate_block_hash_from_dict`, que ya diferencia correctamente entre bloque genesis (concatenacion de campos) y bloques normales (JSON serializado + SHA-256).
   - Compara ambos hashes en minusculas.
   - Si no coinciden, marca `chain_valid = False`.
4. Retorna un dict con `chain_valid`, `total_blocks` y `blocks` (detalle por bloque).

Se agrego tambien el import `from importlib import import_module` necesario para cargar `pymongo` dentro del metodo.

#### `src/api/block_router.py`

Se agrego el endpoint `GET /api/chain/validate` y los imports de los nuevos modelos.

Comportamiento del endpoint:

- Usa la misma dependencia `get_block_validation_service` que ya existia para `POST /api/block/validate`.
- Llama a `validation_service.validate_chain_integrity()`.
- Construye y retorna `ChainValidationSuccessResponse`.
- El campo `message` refleja el resultado:
  - cadena integra: `"Chain integrity verified successfully"`
  - cadena comprometida: `"Chain integrity compromised"`
- Siempre devuelve HTTP 200; `chain_valid` dentro de `data` indica el resultado real.

---

## 4. Contratos de la API

### Endpoint

```
GET /api/chain/validate
```

No requiere cuerpo ni parametros.

### Respuesta exitosa — cadena integra

```json
{
  "success": true,
  "message": "Chain integrity verified successfully",
  "data": {
    "chain_valid": true,
    "total_blocks": 3,
    "blocks": [
      {
        "index": 0,
        "stored_hash": "a1b2c3...",
        "computed_hash": "a1b2c3...",
        "valid": true
      },
      {
        "index": 1,
        "stored_hash": "d4e5f6...",
        "computed_hash": "d4e5f6...",
        "valid": true
      },
      {
        "index": 2,
        "stored_hash": "789abc...",
        "computed_hash": "789abc...",
        "valid": true
      }
    ]
  },
  "error": null
}
```

### Respuesta exitosa — cadena comprometida

```json
{
  "success": true,
  "message": "Chain integrity compromised",
  "data": {
    "chain_valid": false,
    "total_blocks": 2,
    "blocks": [
      {
        "index": 0,
        "stored_hash": "aaaa...",
        "computed_hash": "a1b2c3...",
        "valid": false
      },
      {
        "index": 1,
        "stored_hash": "d4e5f6...",
        "computed_hash": "d4e5f6...",
        "valid": true
      }
    ]
  },
  "error": null
}
```

### Respuesta — cadena vacia

```json
{
  "success": true,
  "message": "Chain integrity verified successfully",
  "data": {
    "chain_valid": true,
    "total_blocks": 0,
    "blocks": []
  },
  "error": null
}
```

---

## 5. Regla de recalculo de hash por tipo de bloque

El metodo `_calculate_block_hash_from_dict` ya existia en `BlockValidationService` y define dos caminos:

### Bloque genesis (`index == 0` y `previous_hash == "0" * 64`)

Se usa `calculate_concatenated_block_hash` de `src/utils/hash_utils.py`:

```
SHA-256( str(index) + str(previous_hash) + str(timestamp) + JSON(transactions) + str(nonce) )
```

### Bloques normales

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

---

## 6. Como verificar que esta bien

### Verificacion tecnica basica

```powershell
python -m compileall src
python -c "import src.main; print(src.main.app.title)"
```

### Verificacion funcional manual recomendada

#### Caso 1: cadena integra

Pasos:

1. Levantar la app con MongoDB disponible y al menos el bloque genesis creado.
2. Llamar a `GET /api/chain/validate`.

Esperado:

- HTTP 200.
- `data.chain_valid = true`.
- `data.total_blocks >= 1`.
- Todos los bloques en `data.blocks` tienen `valid = true`.
- `stored_hash == computed_hash` en cada bloque.

#### Caso 2: bloque adulterado

Pasos:

1. Con MongoDB disponible, modificar manualmente el campo `hash` de cualquier bloque (por ejemplo, desde Mongo Compass o mongosh).
2. Llamar a `GET /api/chain/validate`.

Esperado:

- HTTP 200.
- `data.chain_valid = false`.
- El bloque adulterado aparece con `valid = false`.
- `stored_hash` muestra el valor adulterado.
- `computed_hash` muestra el hash real recalculado.

#### Caso 3: cadena vacia

Pasos:

1. Levantar la app con MongoDB vacio (sin bloques).
2. Llamar a `GET /api/chain/validate`.

Esperado:

- HTTP 200.
- `data.chain_valid = true`.
- `data.total_blocks = 0`.
- `data.blocks = []`.

---

## 7. Decisiones tecnicas relevantes

### Siempre HTTP 200

El endpoint devuelve 200 independientemente de si la cadena esta integra o no. El resultado real esta en `data.chain_valid`. Esto es intencional: la operacion de validacion en si fue exitosa; el estado de la cadena es informacion de negocio, no un error de servidor.

### Read-only garantizado

El metodo solo usa `.find()` con proyeccion `{"_id": 0}`. No existe ninguna llamada a `.insert_one()`, `.update_one()`, `.delete_one()` ni similar dentro de `validate_chain_integrity`.

### Reutilizacion del algoritmo existente

Se reutiliza `_calculate_block_hash_from_dict`, que ya era el corazon de `validate_block_integrity`. Esto asegura que el recalculo de hashes en la validacion de cadena usa exactamente el mismo algoritmo que la validacion individual de bloque. No hay logica de hash duplicada.

### Dependencia de DB obligatoria

Si `BlockValidationService` se instancia sin `db_client`, `validate_chain_integrity` lanza `RuntimeError` con un mensaje descriptivo. El endpoint ya inyecta la DB correctamente via `get_block_validation_service`.

---

## 8. Lo que falta por hacer

- Validar que el `previous_hash` de cada bloque coincida con el `hash` del bloque anterior (encadenamiento).
- Agregar paginacion a la respuesta si la cadena crece y la respuesta se vuelve grande.
- Definir con el equipo si un resultado `chain_valid = false` debe devolver un codigo HTTP diferente (por ejemplo, 409 o 422).
- Definir rol o autenticacion necesaria para acceder al endpoint si se considera sensible.

---

## 9. Lo que no se debe tocar sin coordinacion

- La logica de `_calculate_block_hash_from_dict` y `_is_genesis_block` en `BlockValidationService`: cualquier cambio rompe tanto la validacion individual como la de cadena.
- La regla de concatenacion para el genesis en `hash_utils.py`: esta directamente ligada al hash almacenado del bloque genesis real en produccion.
- Los modelos `BlockIntegrityResult`, `ChainValidationData` y `ChainValidationSuccessResponse`: son el contrato publico del endpoint; cambiarlos sin versionado puede romper clientes que ya consuman la respuesta.

---

## 10. Orden de commits recomendado

1. `feat: add chain integrity validation response models`
2. `feat: implement validate_chain_integrity in BlockValidationService`
3. `feat: add GET /api/chain/validate endpoint`
