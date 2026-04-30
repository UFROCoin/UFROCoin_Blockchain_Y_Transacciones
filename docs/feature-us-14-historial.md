# Documentación Técnica: US-14 Historial de Transacciones

## Contexto
Esta funcionalidad permite obtener una visión consolidada y cronológica de todas las operaciones asociadas a una wallet. El sistema unifica las transacciones que aún residen en el mempool (pendientes) con aquellas ya integradas en la cadena de bloques (confirmadas)[cite: 3].

## Arquitectura

1. **API Router (`src/api/history_router.py`)**: 
   Expone el endpoint `GET /history/{address}`. Utiliza la inyección de dependencias `verify_wallet_owner` para garantizar que solo el dueño de la llave o un administrador con token de desarrollo pueda acceder a los datos[cite: 3]. Define el `response_model=list[dict]` para asegurar una documentación precisa en Swagger.

2. **Capa de Servicios (`src/services/history_service.py`)**:
   Orquesta la recuperación de datos desde MongoDB. Realiza dos consultas paralelas:
   - **Mempool**: Busca en la colección `transacciones` donde el campo `from` o `to` coincida con la dirección[cite: 2, 3].
   - **Blockchain**: Busca en la colección `blocks` transacciones internas que involucren a la dirección[cite: 3].
   Realiza la conversión de `ObjectId` a `string` para evitar errores de serialización JSON y ordena los resultados por `timestamp` de forma descendente.

3. **Base de Datos**:
   Se utiliza la base de datos `blockchain_db`[cite: 2]. Las colecciones involucradas son `transacciones` para el estado actual de envíos y `blocks` para el histórico inmutable[cite: 2, 3].

## Guía de Pruebas (Swagger UI)

1. Acceder a `http://localhost:8000/docs`.
2. Autorizar la sesión usando el botón "Authorize" con el valor `Bearer test-token` (bypass de desarrollo)[cite: 3].
3. **Consulta de Wallet con Actividad**:
   - Introducir una dirección con registros conocidos (ej: `billetera_con_fondos`)[cite: 2].
   - *Resultado esperado*: Código `200 OK` con un arreglo de objetos que incluyen el campo `"status": "PENDING"` o `"status": "CONFIRMED"`.
4. **Consulta de Wallet Nueva**:
   - Introducir una dirección sin transacciones.
   - *Resultado esperado*: Código `200 OK` con un arreglo vacío `[]`.
5. **Validación de Seguridad**:
   - Intentar la consulta sin el header de autorización o con un token inválido.
   - *Resultado esperado*: Código `401 Unauthorized`.

## Estructura de Respuesta (Contrato)
```json
[
  {
    "_id": "69ea6c9d27b89d2fccca7372",
    "from": "billetera_con_fondos",
    "to": "billetera_valida_456",
    "amount": 10,
    "type": "TRANSFER",
    "status": "PENDING",
    "timestamp": "2026-04-23T12:00:00Z",
    "block_index": null
  }
]