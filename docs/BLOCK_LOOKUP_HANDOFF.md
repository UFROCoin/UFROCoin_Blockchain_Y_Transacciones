# Block Lookup Handoff

## Objetivo
- Permitir que desarrolladores o auditores consulten un bloque especifico para inspeccionar sus transacciones.
- Se agregan busquedas por indice y por hash sobre la coleccion `blocks`.

## Endpoints
- `GET /api/block/{index}` retorna el bloque con ese indice.
- `GET /api/block/hash/{hash}` retorna el bloque con ese hash.

## Respuesta Exitosa
```json
{
  "index": 0,
  "timestamp": "2026-04-13T18:45:00Z",
  "transactions": [],
  "previous_hash": "0000000000000000000000000000000000000000000000000000000000000000",
  "nonce": 0,
  "hash": "..."
}
```

## Error Si No Existe
- Status: `404`.
- Body:
```json
{
  "status": "error",
  "code": "BLOCK_NOT_FOUND",
  "message": "Block not found"
}
```

## Codigo
- `src/services/block_service.py`
  - `get_block_by_index(index)` consulta `blocks` por `index` y excluye `_id`.
  - `get_block_by_hash(block_hash)` consulta `blocks` por `hash` y excluye `_id`.
  - Ambos devuelven transacciones enriquecidas con `block_index`.
- `src/api/block_router.py`
  - Define `/block/hash/{block_hash}` antes de `/block/{index}` para evitar colision de rutas.
  - Retorna `BLOCK_NOT_FOUND` cuando `BlockService` no encuentra bloque.

## Como Probar
1. Levantar MongoDB: `docker compose -f test/docker-compose.yml up -d`.
2. Ejecutar API: `python -m uvicorn src.main:app --reload`.
3. Obtener genesis por indice: `GET http://127.0.0.1:8000/api/block/0`.
4. Copiar el valor `hash` de la respuesta.
5. Obtener el mismo bloque por hash: `GET http://127.0.0.1:8000/api/block/hash/{hash}`.
6. Probar bloque inexistente: `GET http://127.0.0.1:8000/api/block/999999`.
7. Probar hash inexistente: `GET http://127.0.0.1:8000/api/block/hash/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`.

## Regresion De Endpoints Existentes
- `GET /health` debe seguir respondiendo `{"status":"ok"}`.
- `POST /api/block/validate` debe conservar el contrato `INVALID_BLOCK` para bloques invalidos.
- `GET /api/chain` debe seguir retornando la cadena paginada.
- `GET /api/chain/validate` debe seguir siendo read-only.

## Verificacion Rapida
- `python -m compileall src`
- `python -c "import src.main; print(src.main.app.title)"`
