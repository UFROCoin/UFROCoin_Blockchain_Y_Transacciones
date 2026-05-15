# US-15: Transacciones pendientes visibles

## Objetivo

Implementar el endpoint publico `GET /api/transaction/pending` para consultar las transacciones del mempool que aun tienen estado `PENDING`.

## Contexto revisado antes de crear codigo

- El proyecto usa FastAPI en `src/main.py`.
- El router de transacciones actual se registra con prefijo global `/api`.
- El endpoint existente de creacion de transacciones es `POST /api/transactions/`.
- Las transacciones se persisten en MongoDB en `blockchain_db.transacciones`.
- El modelo `Transaction` ya guarda `status` con valor por defecto `PENDING`.
- La confirmacion automatica `PENDING -> CONFIRMED` corresponde al flujo de mineria y queda fuera del alcance directo de US-15.

## Pasos antes de implementar codigo

1. Revisar `src/api/transaction_router.py` para no romper `POST /api/transactions/`.
2. Revisar `src/services/transaction_service.py` para reutilizar la conexion y coleccion existentes.
3. Revisar `src/models/transaction.py` para definir una respuesta tipada del endpoint.
4. Confirmar que el endpoint solicitado debe ser exactamente `GET /api/transaction/pending`.
5. Confirmar que el endpoint es publico y no debe usar JWT ni validacion de propiedad de wallet.
6. Confirmar que la respuesta debe usar wrapper segun la documentacion:

```json
{
  "status": "ok",
  "data": []
}
```

## Cambios de codigo previstos

1. Agregar modelos de respuesta en `src/models/transaction.py`:
   - `PendingTransactionData`
   - `PendingTransactionsResponse`
2. Agregar `TransactionService.get_pending_transactions()` para consultar solo documentos con `status: "PENDING"`.
3. Mapear cada documento Mongo a los campos publicos requeridos:
   - `id`
   - `from`
   - `to`
   - `amount`
   - `timestamp`
4. Agregar un router adicional con prefijo `/transaction` para no modificar el endpoint existente `/transactions`.
5. Registrar el nuevo router en `src/main.py` con prefijo global `/api`.

## Pasos despues de implementar codigo

1. Verificar que la app FastAPI importe correctamente.
2. Verificar que exista la ruta `GET /api/transaction/pending`.
3. Verificar que siga existiendo `POST /api/transactions/`.
4. Verificar que el endpoint publico no tenga dependencias de autenticacion.
5. Verificar que la respuesta tenga wrapper `status: "ok"` y `data` como lista.
6. Verificar que cada entrada en `data` incluya solo `id`, `from`, `to`, `amount` y `timestamp`.
7. Verificar que una transaccion con `status: "CONFIRMED"` no aparezca en el resultado.

## Resultado esperado

Solicitud:

```http
GET /api/transaction/pending
```

Respuesta exitosa:

```json
{
  "status": "ok",
  "data": [
    {
      "id": "665f1c2e8f5a8f2a9c4d0001",
      "from": "wallet_origen",
      "to": "wallet_destino",
      "amount": 10.0,
      "timestamp": "2026-05-13T12:00:00Z"
    }
  ]
}
```

## Criterios de aceptacion cubiertos

- `GET /api/transaction/pending` retorna todas las transacciones en estado `PENDING`.
- Cada entrada del mempool incluye `id`, `from`, `to`, `amount`, `timestamp`.
- El endpoint es publico.
- Una transaccion deja de aparecer cuando su estado cambia a `CONFIRMED` por el flujo de mineria.

## Dependencia con US-16

US-15 solo consulta el mempool. La actualizacion del estado a `CONFIRMED` al incluir una transaccion en un bloque minado debe implementarse en US-16 o en el modulo de mineria correspondiente.

## Comandos de verificacion

```powershell
python -c "from src.main import app; print('ok')"
python -c "from src.main import app; print([route.path for route in app.routes if 'transaction' in route.path])"
```
