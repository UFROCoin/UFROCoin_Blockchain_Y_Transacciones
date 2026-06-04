# Chain Stats Handoff

## 1. Objetivo de este documento

Este archivo resume el contexto completo de la implementacion del endpoint de **estadisticas de la cadena de bloques**. La idea es que cualquier persona o agente que lea este documento entienda rapidamente:

- que se implemento
- que decisiones se tomaron
- que archivos se tocaron
- como verificar el comportamiento manualmente
- que cosas estan fuera de alcance

---

## 2. Contexto funcional y alcance

### User Story implementada

> Como usuario, quiero ver cuantos bloques tiene la cadena y cuando fue el ultimo, para entender la actividad reciente del sistema.

### Criterios de aceptacion cubiertos

- [x] Crear el endpoint `GET /api/chain/stats`.
- [x] Retornar `total_blocks`, `last_block_time`, `total_transactions` y `total_ufrocoins_emitidos`.
- [x] Los totales se calculan en tiempo real recorriendo la cadena completa.
- [x] El endpoint es publico y no requiere JWT.

### Fuera de alcance

No se implemento ni se debe considerar parte de esta sesion:

- cacheo de estadisticas (los valores se calculan en cada peticion)
- filtros por rango de fechas o tipo de transaccion
- autenticacion del endpoint
- paginacion (el endpoint agrega toda la cadena en una unica respuesta)

---

## 3. Resumen de lo implementado

### Archivos modificados

#### `src/models/block.py`

Se agregaron dos modelos Pydantic al final del archivo, antes de `ChainValidateResponse`:

- **`ChainStatsData`**: payload con las estadisticas calculadas. Campos:
  - `total_blocks` (int): cantidad total de bloques en la cadena.
  - `last_block_time` (str | None): timestamp ISO 8601 del ultimo bloque, o `null` si la cadena esta vacia.
  - `total_transactions` (int): suma total de transacciones incluidas en todos los bloques.
  - `total_ufrocoins_emitidos` (float): suma total del campo `amount` de todas las transacciones de todos los bloques.

- **`ChainStatsResponse`**: envelope estandar de respuesta. Campos:
  - `status` (Literal["ok"]): siempre `"ok"` en respuestas exitosas.
  - `data` (ChainStatsData): payload con las estadisticas.

#### `src/services/block_service.py`

Se agrego el metodo `get_chain_stats()` a `BlockService`. El metodo realiza dos consultas separadas a MongoDB para minimizar la memoria utilizada:

1. `count_documents({})` para obtener `total_blocks`.
2. `find_one({}, {"timestamp": 1}, sort=[("index", DESCENDING)])` para obtener `last_block_time` del bloque con el indice mas alto, sin cargar el bloque completo.
3. `find({}, {"transactions": 1})` para recorrer todos los bloques proyectando unicamente el campo `transactions`, acumulando `total_transactions` y `total_ufrocoins_emitidos`.

#### `src/api/block_router.py`

- Se importaron `ChainStatsData` y `ChainStatsResponse`.
- Se agrego el endpoint `GET /chain/stats` con `response_model=ChainStatsResponse`.
- La ruta se declaro **antes** de `GET /chain/validate` para evitar conflictos de matching en FastAPI.
- No se agrego ninguna dependencia de seguridad (endpoint publico por requerimiento).

---

## 4. Contratos de la API

### Endpoint

```
GET /api/chain/stats
```

No requiere cuerpo, parametros de query ni token de autorizacion.

### Respuesta exitosa (200 OK)

```json
{
  "status": "ok",
  "data": {
    "total_blocks": 42,
    "last_block_time": "2026-05-31T20:00:00Z",
    "total_transactions": 138,
    "total_ufrocoins_emitidos": 5000.0
  }
}
```

### Respuesta con cadena vacia

```json
{
  "status": "ok",
  "data": {
    "total_blocks": 0,
    "last_block_time": null,
    "total_transactions": 0,
    "total_ufrocoins_emitidos": 0.0
  }
}
```

---

## 5. Logica de calculo de estadisticas

### total_blocks

Se obtiene directamente con `count_documents({})` sobre la coleccion `blocks`. Es la operacion mas eficiente disponible en MongoDB para contar documentos.

### last_block_time

Se obtiene con `find_one` ordenado por `index` descendente y proyectando solo el campo `timestamp`. Solo se lee un documento y solo el campo necesario.

### total_transactions y total_ufrocoins_emitidos

Se recorre toda la coleccion proyectando unicamente `{"transactions": 1, "_id": 0}`. Por cada bloque se itera la lista de transacciones y se acumula:

```python
for block in cursor:
    for tx in block.get("transactions", []):
        if isinstance(tx, dict):
            total_transactions += 1
            total_ufrocoins_emitidos += float(tx.get("amount", 0.0))
```

La guarda `isinstance(tx, dict)` descarta cualquier valor no estructurado que pudiera estar guardado (por ejemplo, strings o None).

---

## 6. Como verificar que esta bien

### Verificacion de importaciones (sin Docker)

```powershell
.\venv\Scripts\python.exe -c "from src.services.block_service import BlockService; from src.models.block import ChainStatsResponse; print('Imports OK')"
```

### Verificacion funcional con Docker

#### Levantar el stack

```powershell
docker-compose up --build -d
```

#### Caso 1 — Cadena con bloques

```powershell
Invoke-WebRequest -Uri "http://localhost:8000/api/chain/stats" -UseBasicParsing
```

Esperado:
- HTTP 200.
- `total_blocks` mayor a 0.
- `last_block_time` con un timestamp ISO 8601 valido.
- `total_transactions` y `total_ufrocoins_emitidos` con valores acumulados de toda la cadena.

#### Caso 2 — Cadena vacia

1. Levantar la app con MongoDB sin bloques (o vaciar la coleccion temporalmente).
2. Llamar al endpoint.

Esperado:
- HTTP 200.
- `total_blocks` igual a 0.
- `last_block_time` igual a `null`.
- `total_transactions` igual a 0.
- `total_ufrocoins_emitidos` igual a 0.0.

#### Caso 3 — Confirmar que es publico (sin JWT)

```powershell
Invoke-WebRequest -Uri "http://localhost:8000/api/chain/stats" -UseBasicParsing
```

No se debe incluir header `Authorization`. Esperado: HTTP 200 (no 401 ni 403).

---

## 7. Decisiones tecnicas relevantes

### Siempre HTTP 200

El endpoint retorna 200 en todos los casos normales, incluso si la cadena esta vacia. `last_block_time: null` y los contadores en cero son la representacion correcta de una cadena sin bloques, no un error.

### Dos queries en lugar de una

Se podria obtener todo en una sola consulta, pero separar el `count_documents` del cursor de transacciones es mas legible y permite que MongoDB use el contador interno de la coleccion para `total_blocks` sin abrir un cursor completo.

### Proyeccion de campos

El cursor de transacciones proyecta solo `{"transactions": 1}`. No se cargan `index`, `timestamp`, `hash`, `previous_hash` ni `nonce` de cada bloque, lo que reduce el trafico de red entre la app y MongoDB a medida que la cadena crece.

### Ubicacion de la ruta en el router

`/chain/stats` se declaro antes de `/chain/validate` en `block_router.py`. FastAPI evalua las rutas en orden de declaracion: si `/chain/validate` estuviera primero, FastAPI podria intentar matchear `"stats"` como el parametro de path de una ruta dinamica (aunque en este caso no existe tal parametro; es una buena practica mantener las rutas estaticas antes que las dinamicas).

---

## 8. Lo que falta por hacer

- Evaluar si el endpoint debe cachearse (por ejemplo, con un TTL de segundos) si la cadena crece y la cantidad de bloques hace que el recorrido sea lento.
- Definir si `total_ufrocoins_emitidos` debe excluir las transacciones de tipo `GENESIS` o `MINING_REWARD` y contabilizar solo `TRANSFER`, segun la definicion de negocio.
- Agregar tests de integracion especificos para `GET /api/chain/stats` siguiendo el patron de `test/test_chain_endpoint.py`.

---

## 9. Lo que no se debe tocar sin coordinacion

- El calculo de `total_ufrocoins_emitidos` usa el campo `amount` de todas las transacciones sin distincion de tipo. Cambiar este comportamiento (por ejemplo, excluir genesis o recompensas) es una decision de negocio que debe coordinarse con el equipo.
- `ChainStatsResponse` es el contrato publico del endpoint. Cambiar los nombres de los campos o sus tipos sin versionado puede romper clientes que ya consuman la respuesta.

---

## 10. Orden de commits recomendado

1. `feat(models): add ChainStatsData and ChainStatsResponse Pydantic models`
2. `feat(service): add get_chain_stats method to BlockService`
3. `feat(api): add GET /api/chain/stats public endpoint`
4. `docs: add CHAIN_STATS_HANDOFF`
