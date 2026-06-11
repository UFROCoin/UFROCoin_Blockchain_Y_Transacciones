# Transaction Detail Handoff

## 1. Objetivo de este documento

Este archivo documenta la implementación de la consulta de detalle de una transacción por ID. La idea es que cualquier persona o agente que lea este documento entienda:

- Qué se implementó
- Qué archivos se tocaron
- Cómo funciona el endpoint
- Cómo probarlo

---

## 2. Contexto funcional y alcance

**Historia de usuario:**
> Como usuario o auditor, quiero consultar los detalles de una transacción por su ID, para verificar que una transferencia se realizó correctamente.

### Alcance implementado

- Endpoint público `GET /api/transactions/{id}` que retorna todos los campos de una transacción.
- Incluye el `block_index` del bloque en que fue confirmada (si aplica).
- Si la transacción no existe, retorna `404` con código `TRANSACTION_NOT_FOUND`.
- Búsqueda en dos fases: primero en el mempool (colección `transactions`), luego en las transacciones embebidas dentro de los bloques confirmados.
- Documentación completa con FastAPI (summary, description, response examples, Path descriptions).

### Fuera de alcance

- Filtros o búsqueda por otros campos (from, to, status, etc.).
- Paginación de transacciones.
- Autenticación o autorización (el endpoint es público por diseño).

---

## 3. Endpoint

`GET /api/transactions/{transaction_id}`

## Respuesta Exitosa

Status: `200`.

```json
{
  "status": "ok",
  "data": {
    "id": "683f1a2b3c4d5e6f7a8b9c0d",
    "from": "a1b2c3d4e5f678901234567890abcdef12345678",
    "to": "b1c2d3e4f5a678901234567890abcdef12345678",
    "amount": 25.0,
    "type": "TRANSFER",
    "status": "CONFIRMED",
    "timestamp": "2026-06-03T22:45:00+00:00",
    "block_index": 3
  }
}
```

Si la transacción está pendiente en el mempool, `status` será `"PENDING"` y `block_index` será `null`.

## Error Si No Existe

Status: `404`.

```json
{
  "status": "error",
  "code": "TRANSACTION_NOT_FOUND",
  "message": "Transaction not found"
}
```

---

## 4. Codigo

- `src/models/transaction.py`
  - `TransactionDetail`: Modelo Pydantic con todos los campos de la transacción (`id`, `from`, `to`, `amount`, `type`, `status`, `timestamp`, `block_index`). Incluye `Field(description=..., examples=...)` para documentación OpenAPI.
  - `TransactionDetailResponse`: Wrapper de respuesta `{"status": "ok", "data": TransactionDetail}`.

- `src/services/transaction_service.py`
  - `get_transaction_by_id(transaction_id)`: Busca primero en la colección `transactions` por `_id` (ObjectId), luego recorre las transacciones dentro de los bloques. Si la encuentra en un bloque, asigna `status="CONFIRMED"` y `block_index` del bloque contenedor. Retorna `None` si no existe.

- `src/api/transaction_router.py`
  - Define `GET /{transaction_id}` en el router con prefijo `/transactions`, resultando en la ruta completa `/api/transactions/{transaction_id}`.
  - Usa `JSONResponse` con `TRANSACTION_NOT_FOUND` cuando el servicio retorna `None`.
  - Documenta la respuesta 404 con el modelo `ApiErrorResponse` (reutilizado de `src/models/block.py`).

---

## 5. Como Probar

1. Levantar MongoDB: `docker compose -f test/docker-compose.yml up -d`.
2. Ejecutar API: `python -m uvicorn src.main:app --reload`.
3. Crear una transacción: `POST http://127.0.0.1:8000/api/transactions/`.
4. Copiar el `_id` de la respuesta.
5. Consultar por ID: `GET http://127.0.0.1:8000/api/transactions/{id}`.
6. Probar ID inexistente: `GET http://127.0.0.1:8000/api/transactions/000000000000000000000000`.
7. Verificar documentación Swagger: `http://127.0.0.1:8000/docs`.

---

## 6. Regresion De Endpoints Existentes

- `GET /health` debe seguir respondiendo `{"status":"ok"}`.
- `POST /api/transactions/` debe conservar el contrato de creación.
- `GET /api/transactions/pending` debe seguir listando transacciones pendientes.
- `GET /api/chain` debe seguir retornando la cadena paginada.

---

## 7. Verificacion Rapida

- `python -m compileall src`
- `python -c "import src.main; print(src.main.app.title)"`

---

## 8. Orden de commits recomendado

1. `feat(transactions): implement GET /api/transactions/{id} for transaction detail lookup`
