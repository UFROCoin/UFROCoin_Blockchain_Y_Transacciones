# Confirmed Transaction Block Index

## Objetivo
- Cada transaccion contenida en un bloque se entrega con referencia al indice del bloque que la confirma.
- La referencia se agrega en respuestas de lectura como `block_index`; no se persisten cambios al consultar.

## Decision De Implementacion
- El modulo actual no contiene flujo de mineria/confirmacion que inserte transacciones en bloques.
- Para no tocar responsabilidades externas, `BlockService` enriquece las transacciones al leer bloques desde MongoDB.
- Las transacciones pendientes en `transacciones` no se modifican y no reciben `block_index`.

## Codigo
- `src/services/block_service.py`
  - `_with_confirmed_transaction_indexes(block)` copia el bloque y sus transacciones.
  - Agrega `status = "CONFIRMED"` solo si la transaccion no trae estado.
  - Agrega `block_index = block["index"]` a cada transaccion dict dentro del bloque.
- `src/api/block_router.py`
  - Los endpoints de bloque usan el bloque enriquecido que devuelve `BlockService`.
- `GET /api/chain` tambien usa el mismo enriquecimiento porque consume `BlockService.get_chain()`.

## Contrato Esperado
```json
{
  "index": 1,
  "transactions": [
    {
      "from": "wallet-a",
      "to": "wallet-b",
      "amount": 10,
      "status": "CONFIRMED",
      "block_index": 1
    }
  ]
}
```

## Como Probar
1. Levantar MongoDB: `docker compose -f test/docker-compose.yml up -d`.
2. Ejecutar API: `python -m uvicorn src.main:app --reload`.
3. Consultar cadena: `GET http://127.0.0.1:8000/api/chain`.
4. Confirmar que cada transaccion dentro de `data[].transactions` incluye `block_index` igual al `index` del bloque contenedor.
5. Consultar un bloque: `GET http://127.0.0.1:8000/api/block/0`.
6. Confirmar que las transacciones del bloque incluyen `block_index` y `status`.

## Verificacion Rapida
- `python -m compileall src`
- `python -c "import src.main; print(src.main.app.title)"`
