# Documentación Técnica: US-18 Límites de Seguridad en Transacciones

## 1. Contexto y Objetivo
Esta historia de usuario introduce validaciones de seguridad estrictas en el Módulo de Transacciones (Módulo 2). El objetivo es prevenir el envío de transferencias malformadas (ej. montos negativos), evitar el consumo innecesario de recursos por wallets inexistentes y mitigar posibles ataques de spam en el mempool.

## 2. Reglas de Negocio Implementadas

1. **Monto Positivo y Decimales**: 
   - El monto a transferir debe ser estrictamente mayor a `0`.
   - Se restringe la cantidad máxima de decimales a `2` para evitar errores de precisión de punto flotante.
   - *Error arrojado:* `INVALID_AMOUNT` o `"El monto no puede tener más de 2 decimales"`.

2. **Existencia de Wallets (Origen y Destino)**:
   - Se utiliza el `ExternalWalletService` para verificar que **ambas** direcciones (`from` y `to`) estén registradas como válidas en el Módulo 1.
   - *Error arrojado:* `"La wallet de origen/destino es invalida o no existe"`.

3. **Límite Anti-Spam (Mempool)**:
   - Un usuario no puede registrar una nueva transacción si ya posee **10 o más transacciones simultáneas** en estado `PENDING`.
   - *Error arrojado:* `PENDING_LIMIT_EXCEEDED`.

## 3. Arquitectura y Archivos Modificados

- **`src/services/transaction_service.py`**:
  Se interceptó el payload entrante en `create_transfer` para realizar las validaciones estructurales (monto) y de estado (conteo en MongoDB) antes de instanciar el modelo de Pydantic. Se solucionaron además errores tipográficos preventivos.
- **`src/api/transaction_router.py`**:
  Se actualizó el esquema de respuestas del endpoint `POST /transactions/` para mapear las excepciones de tipo `ValueError` a respuestas `HTTP 400 Bad Request`. La documentación de Swagger refleja ahora ejemplos claros de cada escenario de fallo.

## 4. Guía de Pruebas (Swagger UI)

Para verificar el correcto funcionamiento, levanta el entorno con `docker-compose` e interactúa con el endpoint `POST /transactions/`:
1. **Prueba de Monto Negativo**: Envía `amount: -50`. Debe retornar `400 Bad Request` con detalle `INVALID_AMOUNT`.
2. **Prueba de Decimales**: Envía `amount: 10.555`. Debe retornar `400 Bad Request`.
3. **Prueba de Origen Inválido**: Usa un `from` que no exista. Debe retornar `400 Bad Request`.
4. **Prueba de Límite de Mempool**: Con una wallet válida, envía 11 transacciones seguidas sin confirmarlas en un bloque. La transacción número 11 debe ser rechazada con `PENDING_LIMIT_EXCEEDED`.