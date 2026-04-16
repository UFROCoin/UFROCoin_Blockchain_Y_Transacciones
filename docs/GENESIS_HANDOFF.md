# Genesis Block Handoff

## 1. Objetivo de este documento

Este archivo resume el contexto completo de la sesion de trabajo sobre el modulo 2 de UFROCoin, especificamente la parte de **US-7: bloque genesis**. La idea es que cualquier persona o agente que lea este documento entienda rapidamente:

- que se implemento
- que decisiones se tomaron
- que archivos se tocaron
- como levantar el proyecto
- como verificar el comportamiento
- que falta por hacer
- que cosas estan fuera de alcance

---

## 2. Contexto funcional y alcance

Se trabajo solo en la parte correspondiente a la creacion del **bloque genesis** del modulo **Blockchain Core** usando:

- Python
- FastAPI
- MongoDB
- RabbitMQ

### Alcance implementado

- Crear el bloque genesis al arrancar el sistema por primera vez.
- Usar `index = 0`.
- Usar `previous_hash = "0" * 64`.
- Calcular el hash con SHA-256.
- Evitar recrear el genesis si ya existen bloques.
- Crear una transaccion genesis de emision inicial del sistema.
- Persistir metadata minima de la cadena.
- Publicar el evento `genesis.created`.

### Fuera de alcance

No se implemento ni se debe considerar parte de esta sesion:

- `models/block.py`
- clase `Block`
- `POST /api/transaction`
- validacion de transacciones de usuario
- mempool
- mineria / PoW
- US-8
- US-13.1 salvo integracion minima
- consumo de eventos RabbitMQ

---

## 3. Resumen de lo implementado

Se creo una base funcional del modulo para soportar el bloque genesis. La implementacion esta desacoplada del futuro modelo `Block`; los bloques se manejan como `dict` con un contrato minimo esperado.

### Archivos creados o modificados

#### Infraestructura de paquetes

- `src/__init__.py`
- `src/api/__init__.py`
- `src/core/__init__.py`
- `src/models/__init__.py`
- `src/services/__init__.py`
- `src/utils/__init__.py`

Estos archivos se agregaron para que las carpetas sean paquetes Python importables y los imports tipo `from src.services...` funcionen de forma consistente.

#### Constantes

- `src/core/constants.py`

Contiene constantes de dominio y de integracion:

- `SYSTEM_REWARD`
- `REWARD_POOL`
- `SYSTEM_ADDRESS`
- `GENESIS_BLOCK_INDEX`
- `GENESIS_PREVIOUS_HASH`
- `GENESIS_TRANSACTION_TYPE`
- `CHAIN_METADATA_ID`
- `BLOCKCHAIN_EVENTS_EXCHANGE`
- `GENESIS_EVENT_ROUTING_KEY`

#### Modelo de metadata

- `src/models/chain_metadata.py`

Define `ChainMetadata` con:

- `genesis_created`
- `last_block_index`
- `last_block_hash`
- `total_blocks`

#### Utilidades de hash

- `src/utils/hash_utils.py`

Funciones:

- `serialize_block_for_hash(block_data)`
- `calculate_block_hash(block_data)`

Puntos importantes:

- serializacion deterministica
- `sort_keys=True`
- `separators=(",", ":")`
- excluye `_id` y `hash`
- normaliza `datetime` a formato ISO UTC

#### Base de datos

- `src/core/database.py`

Responsabilidades:

- conectar a MongoDB
- exponer colecciones `blocks`, `transactions`, `chain_metadata`
- inicializar indices en `blocks`
- cerrar conexion al apagar la app

Indices creados:

- unico para `blocks.index`
- unico para `blocks.hash`
- indice descendente para `blocks.index`

#### RabbitMQ

- `src/core/rabbitmq.py`

Responsabilidades:

- conectar a RabbitMQ
- declarar exchange `ufrocoin.blockchain.events`
- publicar payloads JSON
- cerrar conexion al apagar la app

Actualmente solo se usa para publicar `genesis.created`.

#### Servicio de bloques

- `src/services/block_service.py`

Metodos:

- `get_last_block()`
- `create_genesis_block(block)`
- `save_block(block)`

Este servicio encapsula la persistencia minima en `blocks`.

#### Servicio de genesis

- `src/services/genesis_service.py`

Metodos principales:

- `create_genesis_if_needed()`
- `build_genesis_transaction()`
- `build_genesis_block(genesis_transaction)`

Que hace:

1. revisa si `chain_metadata` ya marca `genesis_created`
2. si no, revisa si ya existen bloques
3. si existen bloques, sincroniza metadata y termina
4. si no existen bloques, construye transaccion genesis
5. construye el bloque genesis
6. calcula el hash
7. guarda el bloque
8. actualiza metadata
9. publica `genesis.created`

#### Startup de FastAPI

- `src/api/startup.py`
- `src/main.py`

Se uso `lifespan` para ejecutar la inicializacion del genesis al arrancar la aplicacion.

#### Configuracion local

- `requirements.txt`
- `.env.example`

---

## 4. Contratos minimos usados

### Contrato minimo del bloque

No existe aun `models/block.py`, asi que esta implementacion trabaja con `dict` y espera al menos:

```json
{
  "index": 0,
  "previous_hash": "0000000000000000000000000000000000000000000000000000000000000000",
  "timestamp": "2026-04-09T12:00:00Z",
  "transactions": [],
  "hash": "..."
}
```

### Contrato minimo de la transaccion genesis

```json
{
  "tx_id": "genesis-...",
  "type": "GENESIS_ISSUANCE",
  "from_address": "SYSTEM",
  "to_address": "REWARD_POOL",
  "amount": 1000000,
  "timestamp": "2026-04-09T12:00:00Z",
  "metadata": {
    "reason": "initial_system_issuance"
  }
}
```

### Contrato de metadata

```json
{
  "_id": "chain_state",
  "genesis_created": true,
  "last_block_index": 0,
  "last_block_hash": "...",
  "total_blocks": 1
}
```

### Contrato del evento RabbitMQ

Exchange:

- `ufrocoin.blockchain.events`

Routing key:

- `genesis.created`

Payload esperado:

```json
{
  "event_type": "genesis.created",
  "occurred_at": "2026-04-09T12:00:00Z",
  "source": "blockchain-core",
  "data": {
    "block_index": 0,
    "block_hash": "...",
    "previous_hash": "0000000000000000000000000000000000000000000000000000000000000000",
    "transaction_count": 1,
    "genesis_created": true
  }
}
```

---

## 5. Flujo de arranque actual

Cuando se ejecuta la app:

1. FastAPI inicia desde `src/main.py`.
2. `lifespan` de `src/api/startup.py` corre al startup.
3. `initialize_database()` intenta conectar a MongoDB y crear indices.
4. Se instancia `GenesisService`.
5. `create_genesis_if_needed()` revisa metadata y bloques existentes.
6. Si no hay bloques:
   - crea transaccion genesis
   - construye bloque genesis con `index = 0`
   - usa `previous_hash = "0" * 64`
   - calcula hash SHA-256 deterministico
   - guarda el bloque en MongoDB
   - actualiza `chain_metadata`
   - intenta publicar `genesis.created`
7. Si ya hay bloques, no crea otro genesis.
8. Al apagar la app, se cierran conexiones de MongoDB y RabbitMQ.

---

## 6. Como inicializar el proyecto localmente

### 6.1 Crear y activar entorno virtual

En PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea la activacion:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 6.2 Instalar dependencias

```powershell
pip install -r requirements.txt
```

### 6.3 Configurar variables de entorno

Usar `.env.example` como referencia:

```env
MONGODB_URI=mongodb://localhost:27017/
MONGODB_DB_NAME=ufrocoin
RABBITMQ_URL=amqp://guest:guest@localhost:5672/%2F
```

### 6.4 Levantar MongoDB

El repo tiene un compose en `test/docker-compose.yml`.

Desde la raiz del repo:

```powershell
docker compose -f test/docker-compose.yml up -d
```

Verificar:

```powershell
docker ps
```

### 6.5 Levantar RabbitMQ

Todavia no hay `docker-compose` para RabbitMQ en el repo. Si se quiere probar la publicacion real del evento, falta levantar RabbitMQ aparte.

Si RabbitMQ no esta activo, la app puede registrar warning al publicar eventos, pero la persistencia del bloque genesis sigue siendo la fuente de verdad.

### 6.6 Ejecutar la app

```powershell
python -m uvicorn src.main:app --reload
```

Rutas utiles:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

---

## 7. Como verificar que esta bien

### Verificacion tecnica basica

Se ejecuto durante la sesion:

```powershell
python -m compileall src
python -c "import src.main; print(src.main.app.title)"
```

Ademas se verifico el hash deterministico con un bloque de prueba.

### Verificacion funcional manual recomendada

#### Caso 1: primer arranque

Esperado:

- la app inicia con MongoDB disponible
- se crea 1 bloque en `blocks`
- ese bloque tiene `index = 0`
- `previous_hash` es 64 ceros
- se crea `chain_metadata`
- `genesis_created = true`
- `total_blocks = 1`

#### Caso 2: segundo arranque

Esperado:

- no se crea otro bloque genesis
- sigue existiendo solo 1 bloque genesis si no se agregaron otros bloques

#### Caso 3: metadata ausente pero bloques existentes

Esperado:

- no se recrea genesis
- se sincroniza `chain_metadata` desde el ultimo bloque existente

---

## 8. Problemas encontrados durante la sesion

### `uvicorn` no se reconocia

Se resolvio recomendando:

```powershell
python -m uvicorn src.main:app --reload
```

en lugar de depender del ejecutable directo `uvicorn`.

### La app no arrancaba por MongoDB

Error observado:

- `ServerSelectionTimeoutError`
- `localhost:27017` rechazando conexion

Causa:

- MongoDB no estaba levantado localmente.

Solucion:

```powershell
docker compose -f test/docker-compose.yml up -d
```

---

## 9. Validaciones que si cubre esta implementacion

- evitar recrear genesis si ya hay bloques
- asegurar `index = 0`
- asegurar `previous_hash = "0" * 64`
- calcular hash SHA-256 de forma deterministica
- excluir campos variables del hash
- persistir correctamente metadata
- mantener alineado `last_block_hash` y `last_block_index` con el bloque guardado
- intentar publicar `genesis.created` despues de persistir

---

## 10. Lo que falta por hacer

### Pendientes tecnicos razonables

- agregar pruebas unitarias para `hash_utils`
- agregar pruebas para `GenesisService`
- agregar logging mas explicito en arranque y errores
- agregar soporte formal para cargar variables desde `.env`
- agregar compose o setup local para RabbitMQ
- definir junto al equipo el contrato final de `Block`
- definir junto al equipo el contrato final de transacciones y eventos

### Pendientes de integracion con otros miembros

- implementacion futura de `models/block.py`
- integracion con endpoints de lectura si el modulo los expone despues
- integracion con modulo de mineria
- integracion con US-8 y US-13.1 fuera de esta parte

---

## 11. Lo que no se debe tocar sin coordinacion

Para mantener el alcance limpio, otro agente o desarrollador no deberia mezclar en esta parte:

- mempool
- validacion de saldos
- endpoints de transferencia
- mineria
- PoW
- validacion de transacciones de usuario
- clase `Block` si pertenece a otro integrante

Si se implementa `Block` en el futuro, lo ideal es adaptar `GenesisService` y `BlockService` a ese contrato sin romper el flujo ya creado.

---

## 12. Orden de commits recomendado

Separacion sugerida:

1. `feat: add blockchain core constants and chain metadata model`
2. `feat: add deterministic block hashing utilities`
3. `feat: add MongoDB connection helpers and block indexes`
4. `feat: add minimal block persistence service`
5. `feat: add RabbitMQ base publisher for blockchain events`
6. `feat: implement genesis block creation service`
7. `feat: trigger genesis initialization on FastAPI startup`
8. `chore: add local environment and dependency setup`

---

## 13. Estado actual de la sesion

Estado general:

- implementacion base terminada para tu parte de US-7
- falta validacion completa con MongoDB real levantado y, opcionalmente, RabbitMQ real
- no hay tests automaticos aun

En otras palabras: la base esta hecha y la pieza central del bloque genesis ya esta implementada, pero todavia conviene cerrar pruebas y coordinacion de contratos con el equipo.
