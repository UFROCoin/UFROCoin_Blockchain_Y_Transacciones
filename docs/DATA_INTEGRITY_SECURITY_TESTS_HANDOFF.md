# Data Integrity and Security Tests Handoff

## 1. Objetivo de este documento

Este archivo documenta la cobertura de pruebas agregada para la rama enfocada en integridad de datos, acceso seguro y persistencia correcta en base de datos. La idea es que cualquier persona o agente que lea este documento entienda:

- Que se cubrio
- Que archivos se agregaron
- Que casos quedan protegidos
- Como ejecutar la verificacion
- Que advertencias o deuda tecnica quedaron identificadas

---

## 2. Contexto funcional y alcance

**Descripcion de la rama:**

> Enfocada en asegurar la integridad de los datos que entran al sistema, el acceso seguro y la correcta persistencia en la base de datos.

### Archivos objetivo

- `src/core/database.py`
- `src/core/security.py`
- Archivos de modelos Pydantic bajo `src/models/`

### Alcance implementado

- Pruebas unitarias para configuracion y ciclo de vida de MongoDB en `src.core.database`.
- Pruebas unitarias para autenticacion/autorizacion de wallets en `src.core.security`.
- Pruebas de contrato de datos para modelos Pydantic, con inputs validos e invalidos.
- Verificacion de aliases usados por la API, especialmente `from` y `to`.
- Verificacion de restricciones de hashes, literales, montos y campos extra donde corresponda.

### Fuera de alcance

- No se agregaron casos adicionales a transacciones ni a `TransactionService`, por instruccion explicita del equipo.
- No se modifico codigo productivo.
- No se requiere MongoDB real para ejecutar los tests agregados.

---

## 3. Resumen de lo implementado

### Archivos agregados

#### `test/test_database.py`

Cubre el contrato de persistencia y configuracion de `src.core.database`:

- `get_database_name()` respeta la prioridad `MONGO_DB_NAME` sobre `MONGODB_DB_NAME`.
- Si no hay variables de entorno, se usa `DEFAULT_DATABASE_NAME`.
- `_build_mongodb_uri()` usa `MONGODB_URI` directa cuando existe.
- `_build_mongodb_uri()` construye la URI con usuario, password, host, puerto y DB cuando corresponde.
- `_build_mongodb_uri()` construye una URI sin credenciales usando host, puerto y DB.
- `_get_pymongo_module()` entrega un `RuntimeError` claro si falta `pymongo`.
- `get_mongo_client()` reutiliza un unico cliente cacheado.
- `get_database()` selecciona la base de datos configurada.
- Los helpers de nombres de colecciones respetan overrides por variables de entorno.
- `initialize_database()` hace `ping` y crea los indices esperados para `blocks` y `transactions`.
- `close_database()` cierra el cliente y limpia referencias globales/cacheadas.

#### `test/test_security.py`

Cubre los casos comunes de error y exito de `verify_wallet_owner()`:

- Sin credenciales retorna `401`.
- El token especial `test-token` permite acceso y retorna la direccion solicitada.
- Un JWT valido con `wallet_address` igual al parametro `address` permite acceso.
- Un JWT valido para otra wallet retorna `403`.
- Un JWT valido sin `wallet_address` retorna `403`.
- Un token mal formado retorna `401`.
- Un JWT firmado con otra clave retorna `401`.

#### `test/test_pydantic_models.py`

Cubre contratos de datos para los modelos Pydantic principales:

- `Transaction`
- `PendingTransactionData`
- `PendingTransactionsResponse`
- `TransactionDetail`
- `BlockData`
- `ChainSuccessResponse`
- `ChainStatsResponse`
- `ChainValidateResponse`
- `ChainMetadata`
- `TransactionHistoryItem`

Los tests validan:

- Inputs validos.
- Inputs invalidos.
- Uso correcto de aliases `from`, `to` y `_id`.
- Rechazo de montos no positivos en `Transaction`.
- Rechazo de tipos y estados invalidos en `Transaction`.
- Rechazo de campos extra en modelos configurados con `extra="forbid"`.
- Rechazo de `block_index` negativo en `TransactionDetail`.
- Rechazo de hashes que no cumplen el patron SHA-256 hexadecimal de 64 caracteres en `BlockData`.
- Rechazo de numeros negativos en campos `index` y `nonce` de `BlockData`.
- Literales esperados, como `status="ok"`.
- Ignorar campos extra en `ChainMetadata`, segun su configuracion actual.

---

## 4. Detalle por modulo

### `src.core.database`

El modulo mantiene estado global para el cliente MongoDB y la base seleccionada. Por eso los tests usan limpieza automatica entre casos para evitar contaminacion de estado:

```python
database._mongo_client = None
database._database = None
database.get_database_name.cache_clear()
```

La inicializacion de indices se prueba con mocks, sin conectar a MongoDB real. Esto permite validar que se pidan los indices correctos sin depender de infraestructura externa.

### `src.core.security`

La funcion `verify_wallet_owner()` se prueba directamente con objetos `HTTPAuthorizationCredentials`, evitando levantar FastAPI. Esto cubre la decision de autorizacion de manera unitaria:

```python
HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
```

La validacion distingue correctamente entre:

- Falta de token: `401`.
- Token invalido o mal firmado: `401`.
- Token valido pero wallet incorrecta: `403`.

### Modelos Pydantic

Las pruebas son de contrato: no buscan probar internals de Pydantic, sino asegurar que los modelos del proyecto acepten y rechacen los payloads que la API espera.

Esto es especialmente importante para campos con aliases reservados o convencionales en la API, como:

- `from`
- `to`
- `_id`

---

## 5. Como verificar que esta bien

### Suite completa

```powershell
python -m pytest
```

Resultado obtenido en esta rama:

```text
94 passed, 1 warning in 0.46s
```

### Solo tests agregados en esta rama

```powershell
python -m pytest test/test_database.py test/test_security.py test/test_pydantic_models.py
```

---

## 6. Warning conocido

Durante la ejecucion de la suite aparece un warning de Pydantic:

```text
PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead.
Deprecated in Pydantic V2.0 to be removed in V3.0.
```

El origen es `src/models/history.py`, donde `TransactionHistoryItem` usa configuracion estilo Pydantic v1:

```python
class Config:
    populate_by_name = True
```

Recomendacion futura:

```python
from pydantic import ConfigDict

model_config = ConfigDict(populate_by_name=True)
```

Este warning no rompe la suite actual, pero deberia resolverse antes de migrar a Pydantic v3.

---

## 7. Regresion de endpoints existentes

Aunque los tests agregados son principalmente unitarios y de contrato, se ejecuto la suite completa existente para verificar que no hubiera regresiones en:

- `GET /api/chain`
- `GET /api/chain/stats`
- `GET /api/transactions/{transaction_id}`
- `GET /api/transactions/pending`
- Reglas existentes de `TransactionService`
- Tests de regresion existentes

Resultado: todos los tests pasaron.

---

## 8. Orden de commits realizado

1. `test: add data integrity and security coverage`
2. `docs: add data integrity security tests handoff`
