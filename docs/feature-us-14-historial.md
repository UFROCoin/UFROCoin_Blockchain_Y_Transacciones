# Documentación Técnica: Historial de Transacciones (US-14)

## 1. Resumen de la Funcionalidad
Esta feature permite a los usuarios obtener un listado cronológico de todas sus transacciones. El sistema consulta dos fuentes de datos para asegurar integridad:
- **Confirmadas:** Transacciones persistidas en la colección `blocks`.
- **Pendientes:** Transacciones en el mempool (colección `transacciones`).

## 2. Especificación del API
- **Ruta:** `GET /history/{address}`
- **Método:** `GET`
- **Seguridad:** `HTTPBearer` (JWT)

### Parámetros de Ruta
- `address`: La dirección pública de la wallet cuyo historial se desea consultar.

## 3. Lógica de Transformación de Datos
Para facilitar la lectura en el Frontend, el servicio transforma el tipo genérico `TRANSFER` en etiquetas dinámicas:
- **SEND:** Se asigna si la wallet consultada es la emisora (`from`).
- **RECEIVE:** Se asigna si la wallet consultada es la receptora (`to`).
- **Estados:** Los registros se marcan como `CONFIRMED` o `PENDING` según su origen.

## 4. Pruebas en Entorno de Desarrollo (Swagger Bypass)
Para facilitar las pruebas sin necesidad de un JWT real generado por el Módulo 1, se ha implementado un bypass de seguridad:

### Pasos para probar en Swagger:
1. Accede a `http://localhost:8000/docs`.
2. Haz clic en el botón **"Authorize"** (el candado arriba a la derecha).
3. En el campo "Value", escribe exactamente: `test-token`
4. Haz clic en **"Authorize"** y luego en **"Close"**.
5. Ve al endpoint `GET /history/{address}`, presiona **"Try it out"**.
6. Ingresa la dirección de la wallet que desees consultar y presiona **"Execute"**.

> **Nota:** El sistema detectará el `test-token` y te permitirá ver los datos de la wallet ingresada como si fueras el dueño legítimo.

## 5. Modelos de Respuesta (JSON)
El endpoint devuelve una lista de objetos con la siguiente estructura:
```json
[
  {
    "_id": "string",
    "type": "SEND | RECEIVE",
    "from": "string",
    "to": "string",
    "amount": 0.0,
    "timestamp": "ISO-8601 String",
    "status": "CONFIRMED | PENDING"
  }
]