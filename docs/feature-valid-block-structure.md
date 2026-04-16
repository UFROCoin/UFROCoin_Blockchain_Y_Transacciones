# Feature: Estructura valida de bloque (Modulo 2)

## Resumen

Esta rama incorpora una API de validacion de bloques y un entorno local con Docker para API + MongoDB.

Objetivos principales:
- Validar la estructura de un bloque y la integridad de su hash.
- Exponer el endpoint de validacion con FastAPI + Swagger.
- Facilitar la ejecucion local con contenedores.

## Funcionalidad implementada

### 1) Endpoint para validacion de bloques

- Ruta: `POST /api/block/validate`
- Tag: `Blockchain`
- Respuesta exitosa (200):
  - `{"status":"ok","data":{"valid":true}}`
- Respuesta de error (400):
  - `{"status":"error","code":"INVALID_BLOCK","message":"Block structure or hash is invalid"}`

Implementado en `src/api/block_router.py`.

### 2) Servicio de validacion de bloques

En `src/services/block_validation_service.py` se implementa la logica de validacion deterministica:

- Verifica campos requeridos del bloque:
  - `index`, `timestamp`, `transactions`, `previous_hash`, `nonce`, `hash`
- Valida tipos:
  - `index` y `nonce` deben ser enteros (no booleanos)
  - `timestamp`, `previous_hash` y `hash` deben ser string
  - `transactions` debe ser una lista
- Valida formato de fecha:
  - Datetime compatible con ISO 8601 (`T` obligatorio, soporta `Z`)
- Valida formato de hashes:
  - `previous_hash` y `hash` deben ser hexadecimales de 64 caracteres
- Recalcula el hash de forma canonica:
  - Excluye el campo `hash`
  - Usa `json.dumps(..., sort_keys=True, separators=(",", ":"))`
  - Compara SHA-256 recalculado con el hash recibido

### 3) Modelos de request/response

En `src/models/block.py` se definen los modelos Pydantic:
- `BlockValidationRequest`
- `BlockValidationSuccessResponse`
- `ApiErrorResponse`

Esto permite validacion automatica y documentacion en Swagger/OpenAPI.

### 4) Integracion en FastAPI

`src/main.py` integra el router bajo `/api` y define metadatos de la API:
- titulo: `UFROCoin Module 2 API`
- descripcion: `Blockchain and transactions service for UFROCoin.`
- version: `1.0.0`

Ademas, cierra la conexion MongoDB al apagar la aplicacion.

### 5) Configuracion de base de datos

`src/core/database.py` incluye:
- Construccion de URI por variables de entorno
- Cliente MongoDB cacheado (`lru_cache`)
- Cierre ordenado del cliente

Variables soportadas:
- `MONGO_HOST`
- `MONGO_PORT`
- `MONGO_DB_NAME`
- `MONGODB_URI`
- `MONGO_INITDB_ROOT_USERNAME`
- `MONGO_INITDB_ROOT_PASSWORD`

### 6) Contenerizacion para desarrollo local

Archivos agregados/actualizados:
- `Dockerfile.api`
- `Dockerfile.mongo`
- `docker-compose.yml`
- `.env.example`
- `requirements.txt`

Servicios en Compose:
- `mongodb` (con healthcheck)
- `api` (depende de MongoDB saludable, puerto `8000`)

## Como ejecutar

Desde la raiz del repositorio:

1. Crear archivo de entorno:
   - copiar `.env.example` a `.env`
2. Levantar servicios:
   - `docker compose up --build -d`
3. Verificar:
   - Swagger: `http://localhost:8000/docs`
   - MongoDB: `localhost:27017`

## Ejemplo de bloque valido

```json
{
  "index": 1,
  "timestamp": "2026-04-13T18:45:00Z",
  "transactions": [
    {
      "amount": 25,
      "from": "a1b2c3d4e5f678901234567890abcdef12345678",
      "to": "b1c2d3e4f5a678901234567890abcdef12345678",
      "type": "TRANSFER"
    }
  ],
  "previous_hash": "0f7a9e3c5e7a1205f8c31f5b8d21ca74095e78eb1ec6dced3d4f8a05d8e6c712",
  "nonce": 48271,
  "hash": "680266db72abe3622b2feb7d1287c028ba3d9625b9c3c7d7763a703c6221ac0f"
}
```

## Notas

- La validacion actual cubre estructura e integridad deterministica del hash.
- La integracion con base de datos queda preparada para validaciones de cadena mas avanzadas.
