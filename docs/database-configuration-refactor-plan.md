# Plan de Refactor: Configuracion Centralizada de Base de Datos y Colecciones

## Estado Actual

Implementado con contrato de endpoints existente:

- Base de datos por defecto: `ufrocoin`
- Coleccion de bloques: `blocks`
- Coleccion de transacciones: `transactions`
- Coleccion de metadata de cadena: `chain_metadata`
- Endpoint de pendientes: `GET /api/transactions/pending`
- Endpoint de detalle: `GET /api/transactions/{transaction_id}`

Las referencias historicas a `blockchain_db.transacciones` o `/api/transaction/*` en este documento describen el problema original o alternativas de rollback, no el contrato activo recomendado.

## Objetivo

Centralizar la configuracion de la base de datos MongoDB y los nombres de colecciones en un unico punto del proyecto, usando variables de entorno con valores por defecto seguros.

Configuracion propuesta por defecto:

- Base de datos: `ufrocoin`
- Coleccion de bloques: `blocks`
- Coleccion de transacciones: `transactions`
- Coleccion de metadata de cadena: `chain_metadata`

## Problema Actual

Actualmente el proyecto usa mas de una convencion para acceder a MongoDB.

Por un lado, `src/core/database.py` define:

```python
DEFAULT_DATABASE_NAME = "ufrocoin"

def get_transactions_collection() -> Any:
    return get_database()["transactions"]
```

Esto apunta a:

```text
ufrocoin.transactions
```

o a la base configurada por `MONGO_DB_NAME` / `MONGODB_DB_NAME`.

Pero otros servicios usan nombres hardcodeados:

```python
self.db = db_client.blockchain_db
self.db.transacciones
```

y:

```python
db = client.get_database("blockchain_db")
db.transacciones
```

Esto apunta a:

```text
blockchain_db.transacciones
```

## Por Que Se Deberia Implementar

Esta inconsistencia puede provocar que distintos endpoints lean o escriban en bases/colecciones diferentes.

Ejemplo de riesgo:

1. `POST /api/transactions/` guarda una transaccion en `blockchain_db.transacciones`.
2. `GET /api/transaction/pending` podria leer desde otra coleccion si se usa `get_transactions_collection()`.
3. `GET /history/{address}` podria consultar otra fuente.
4. El calculo de saldo podria descontar pendientes desde una coleccion distinta.
5. El sistema pareceria funcionar parcialmente, pero los datos quedarian desincronizados.

Centralizar esta configuracion reduce ese riesgo y permite que todos los modulos compartan una sola fuente de verdad.

## Beneficios

- Evita nombres de BD hardcodeados en servicios.
- Permite cambiar la base de datos desde `.env`.
- Permite cambiar nombres de colecciones desde `.env`.
- Hace que creacion de transacciones, historial, saldo y mempool usen la misma coleccion.
- Facilita despliegue en distintos entornos: local, testing, staging, produccion.
- Reduce deuda tecnica antes de que existan datos reales.
- Evita migraciones futuras innecesarias.
- Facilita pruebas automatizadas usando bases temporales.
- Mantiene el codigo de negocio desacoplado de detalles de infraestructura.

## Variables de Entorno Propuestas

Agregar al `.env.example`:

```env
MONGO_DB_NAME=ufrocoin
MONGO_BLOCKS_COLLECTION=blocks
MONGO_TRANSACTIONS_COLLECTION=transactions
MONGO_CHAIN_METADATA_COLLECTION=chain_metadata
```

Mantener compatibilidad con `MONGODB_DB_NAME`, que ya existe en el proyecto.

## Convencion Recomendada

Como el proyecto aun no ha sido desplegado y no hay datos productivos, se recomienda usar nombres consistentes en ingles:

```text
ufrocoin.blocks
ufrocoin.transactions
ufrocoin.chain_metadata
```

Esto se alinea con los nombres ya definidos parcialmente en `src/core/database.py`.

## Cambios Propuestos

### 1. Centralizar nombres en `src/core/database.py`

Agregar constantes por defecto:

```python
DEFAULT_DATABASE_NAME = "ufrocoin"
DEFAULT_BLOCKS_COLLECTION_NAME = "blocks"
DEFAULT_TRANSACTIONS_COLLECTION_NAME = "transactions"
DEFAULT_CHAIN_METADATA_COLLECTION_NAME = "chain_metadata"
```

Agregar helpers:

```python
def get_blocks_collection_name() -> str:
    return os.getenv("MONGO_BLOCKS_COLLECTION", DEFAULT_BLOCKS_COLLECTION_NAME)


def get_transactions_collection_name() -> str:
    return os.getenv("MONGO_TRANSACTIONS_COLLECTION", DEFAULT_TRANSACTIONS_COLLECTION_NAME)


def get_chain_metadata_collection_name() -> str:
    return os.getenv("MONGO_CHAIN_METADATA_COLLECTION", DEFAULT_CHAIN_METADATA_COLLECTION_NAME)
```

Actualizar helpers existentes:

```python
def get_blocks_collection() -> Any:
    return get_database()[get_blocks_collection_name()]


def get_transactions_collection() -> Any:
    return get_database()[get_transactions_collection_name()]


def get_chain_metadata_collection() -> Any:
    return get_database()[get_chain_metadata_collection_name()]
```

### 2. Actualizar `TransactionService`

Reemplazar accesos directos:

```python
self.db = db_client.blockchain_db
self.db.blocks
self.db.transacciones
```

por colecciones centralizadas:

```python
from src.core.database import get_blocks_collection, get_transactions_collection
```

y usar:

```python
self.blocks_collection = get_blocks_collection()
self.transactions_collection = get_transactions_collection()
```

Luego reemplazar:

```python
self.db.blocks.find()
self.db.transacciones.find(...)
self.db.transacciones.insert_one(...)
```

por:

```python
self.blocks_collection.find()
self.transactions_collection.find(...)
self.transactions_collection.insert_one(...)
```

### 3. Actualizar `history_service.py`

Reemplazar:

```python
client = get_db_client()
db = client.get_database("blockchain_db")
pending_cursor = db.transacciones.find(query)
blocks_cursor = db.blocks.find(...)
```

por:

```python
from src.core.database import get_blocks_collection, get_transactions_collection

transactions_collection = get_transactions_collection()
blocks_collection = get_blocks_collection()
```

y usar:

```python
pending_cursor = transactions_collection.find(query)
blocks_cursor = blocks_collection.find(...)
```

### 4. Revisar referencias hardcodeadas

Buscar referencias a:

```text
blockchain_db
transacciones
get_database("blockchain_db")
```

La meta es que los servicios no dependan directamente del nombre fisico de la base ni de las colecciones.

### 5. Actualizar `.env.example`

Agregar las nuevas variables:

```env
MONGO_DB_NAME=ufrocoin
MONGO_BLOCKS_COLLECTION=blocks
MONGO_TRANSACTIONS_COLLECTION=transactions
MONGO_CHAIN_METADATA_COLLECTION=chain_metadata
```

No modificar `.env` real sin acuerdo del grupo, ya que puede contener configuracion local o sensible.

## Impacto Esperado en US-15

El endpoint:

```http
GET /api/transaction/pending
```

seguira funcionando igual para el consumidor.

La diferencia es interna:

Antes podria depender de:

```text
blockchain_db.transacciones
```

Despues usara por defecto:

```text
ufrocoin.transactions
```

Si el grupo decide volver a la convencion anterior, no sera necesario tocar codigo. Bastara configurar:

```env
MONGO_DB_NAME=blockchain_db
MONGO_TRANSACTIONS_COLLECTION=transacciones
```

## Impacto en Otros Flujos

### Creacion de transacciones

`POST /api/transactions/` guardara en la coleccion centralizada.

### Historial

`GET /history/{address}` consultara la misma coleccion que usa la creacion de transacciones.

### Saldo

El calculo de saldo descontara pendientes desde la misma coleccion donde se crean las transacciones.

### Blockchain

Los bloques se consultaran desde la coleccion centralizada `blocks`.

## Riesgos

- Si alguien del equipo ya esta usando manualmente `blockchain_db.transacciones`, dejara de ver datos por defecto.
- Si existen scripts externos que esperan `transacciones`, deberan actualizarse o configurar el `.env`.
- Si se cambia solo una parte del codigo, puede aumentar la inconsistencia en vez de resolverla.
- Si se modifica `.env` local sin coordinar, algunos desarrolladores podrian apuntar a bases distintas.

## Mitigaciones

- Implementar el cambio de forma completa en una sola rama.
- No renombrar datos existentes porque el proyecto aun no esta desplegado.
- Mantener variables de entorno para poder volver a nombres anteriores sin tocar codigo.
- Documentar la convencion acordada en este archivo.
- Verificar todos los endpoints afectados despues del cambio.

## Verificaciones Tecnicas

Ejecutar:

```powershell
python -c "from src.main import app; print('ok')"
python -m compileall src
python -c "from src.main import app; print([(sorted(route.methods), route.path) for route in app.routes if 'transaction' in route.path])"
```

Resultado esperado:

```text
ok
POST /api/transactions/
GET /api/transaction/pending
```

Buscar referencias restantes:

```text
blockchain_db
transacciones
get_database("blockchain_db")
```

Resultado esperado:

- No deberian quedar referencias hardcodeadas en servicios.
- Podrian quedar referencias solo en documentacion historica.

## Verificacion Funcional Recomendada

1. Levantar MongoDB y API.
2. Crear una transaccion con `POST /api/transactions/`.
3. Confirmar que se guarda en `ufrocoin.transactions`.
4. Consultar `GET /api/transaction/pending`.
5. Confirmar que la transaccion aparece en `data`.
6. Consultar historial con `GET /history/{address}`.
7. Confirmar que historial lee desde la misma fuente.
8. Cambiar manualmente el estado de una transaccion a `CONFIRMED`.
9. Confirmar que deja de aparecer en `/api/transaction/pending`.

## Decision Solicitada al Grupo

Se propone aprobar la siguiente convencion por defecto:

```text
MONGO_DB_NAME=ufrocoin
MONGO_BLOCKS_COLLECTION=blocks
MONGO_TRANSACTIONS_COLLECTION=transactions
MONGO_CHAIN_METADATA_COLLECTION=chain_metadata
```

Y exigir que todo servicio acceda a MongoDB mediante helpers centralizados en:

```text
src/core/database.py
```

## Recomendacion

Implementar este refactor ahora, antes del despliegue y antes de acumular datos reales. El costo actual es bajo y evita problemas de sincronizacion entre endpoints en futuras historias de usuario.
