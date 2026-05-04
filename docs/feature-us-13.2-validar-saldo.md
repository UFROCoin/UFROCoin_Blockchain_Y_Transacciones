# Documentación Técnica: US-13.2 Validación de Saldo en Transferencias

## Contexto
Esta funcionalidad introduce validaciones de reglas de negocio previas a la inserción de una transacción en el mempool. El objetivo es garantizar que el emisor disponga de saldo suficiente y que la wallet receptora sea válida dentro del ecosistema UFROCoin, previniendo el doble gasto o la quema accidental de fondos.

## Arquitectura

1. **API Router (`src/api/transaction_router.py`)**: 
   Expone el endpoint `POST /transactions/`. Implementa el manejo controlado de excepciones, transformando los errores de validación de negocio en respuestas `HTTP 400 Bad Request` con descripciones explícitas (ej. "Saldo insuficiente"). Integra metadatos para la autogeneración de OpenAPI (Swagger).

2. **Capa de Servicios (`src/services/transaction_service.py`)**:
   Incorpora la validación centralizada mediante el método `calculate_balance(address)`. El saldo real se obtiene iterando el historial inmutable de transacciones confirmadas en la colección `blocks` y descontando preventivamente los fondos ya comprometidos en la colección `transacciones` (mempool) con estado `PENDING`.

3. **Integración Externa (`src/services/external_wallet_service.py`)**:
   Abstracción de cliente (Mock) que simula el consumo del endpoint de verificación del Módulo 1 (Usuarios y Wallets). Provee el método `check_wallet_exists`, permitiendo independizar el avance de desarrollo entre equipos.

## Guía de Pruebas (Swagger UI)

**Requisito previo:** Asegurarse de que la infraestructura base (MongoDB y RabbitMQ) esté corriendo localmente mediante `docker-compose up --build -d`.

1. Levantar la API y acceder a la interfaz interactiva en `http://localhost:8000/docs`.
2. Desplegar el endpoint `POST /transactions/` y hacer clic en "Try it out".
3. **Validación de Wallet Inexistente:** - Enviar el payload con un destinatario (`to`) que comience con la palabra "invalid". 
   - *Resultado esperado:* Código `400 Bad Request` indicando que la wallet de destino es inválida.
4. **Validación de Saldo Insuficiente:** - Ejecutar una transferencia con un monto (`amount`) superior al saldo histórico disponible de la wallet `from`. 
   - *Resultado esperado:* Código `400 Bad Request` detallando "Saldo insuficiente. Saldo disponible: X.X".
5. **Ejecución Exitosa:** - Proveer una wallet emisora con fondos confirmados (sin deudas en mempool) y una receptora válida. 
   - *Resultado esperado:* Código `201 Created` retornando el nuevo objeto transacción en estado `PENDING`.