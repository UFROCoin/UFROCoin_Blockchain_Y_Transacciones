# TA-03: Tests de Integracion, Mensajeria y Cobertura

## Objetivo

Esta tarea agrupa la comunicacion con agentes externos del modulo Blockchain y Transacciones:

- Publicacion de eventos RabbitMQ desde `src.core.rabbitmq_publisher`.
- Verificacion HTTP de wallets externas desde `src.services.external_wallet_service`.
- Configuracion base para medir cobertura con `pytest-cov`.

El foco es dejar pruebas automatizadas con mocks controlados para no depender de infraestructura real durante CI o desarrollo local.

## Archivos principales cubiertos

- `src/core/rabbitmq_publisher.py`
- `src/services/external_wallet_service.py`
- `requirements.txt`
- `.coveragerc`

## Cambios realizados

### Cobertura

Se agrego `pytest-cov` a `requirements.txt` y se creo `.coveragerc`.

La configuracion mide cobertura sobre `src`, activa branch coverage y excluye archivos de tests, entornos virtuales y `__init__.py`.

Comando recomendado:

```powershell
pytest --cov=src --cov-report=term-missing
```

Reporte HTML opcional:

```powershell
pytest --cov=src --cov-report=html
```

El HTML queda en `htmlcov/`.

### Wallet externa

`ExternalWalletService` dejo de ser un stub local y ahora consulta el modulo Usuarios y Wallets por HTTP usando `httpx`.

Configuracion soportada:

```env
WALLET_SERVICE_BASE_URL=http://modulo1-usuario:8000/api
WALLET_SERVICE_TOKEN=
WALLET_SERVICE_TIMEOUT_SECONDS=3
```

Comportamiento:

- Rechaza localmente direcciones vacias o que no cumplan `^[a-f0-9]{40}$`.
- Consulta `GET {WALLET_SERVICE_BASE_URL}/wallet/{address}`.
- Agrega `Authorization: Bearer <token>` solo si `WALLET_SERVICE_TOKEN` esta configurado.
- Retorna `True` solo si la respuesta HTTP 200 confirma que la wallet consultada coincide con la direccion enviada.
- Retorna `False` para 400, 401, 404, errores de red, JSON invalido o respuestas inesperadas.
- No registra tokens ni informacion sensible en logs.

Importante: el modulo Usuarios y Wallets actual protege `GET /api/wallet/{address}` con JWT y validacion de propietario. Por eso `401` se trata como no verificable y retorna `False`. Si el equipo agrega un endpoint interno de existencia de wallet, este servicio se puede adaptar manteniendo los tests de contrato.

### RabbitMQ

Los tests de `rabbitmq_publisher` mockean `pika` completamente.

Se valida que:

- La conexion usa `RABBITMQ_URL` o el default local.
- La conexion abierta se reutiliza.
- Una conexion cerrada se reemplaza.
- El canal declara el exchange `ufrocoin.blockchain.events` como `topic` y durable.
- `publish_event` serializa JSON deterministico con `sort_keys=True` y `ensure_ascii=True`.
- Los mensajes usan propiedades persistentes: `content_type=application/json` y `delivery_mode=2`.
- `close_rabbitmq_connection` cierra recursos abiertos y limpia estado global.
- `RabbitMQPublisher.publish_transaction` delega con routing key `transaction.created`.

### Integracion ligera TransactionService -> RabbitMQ

Se agrego un test que crea una transferencia valida con DB, wallet y publisher mockeados.

El test verifica:

- Insercion de la transaccion en mempool.
- Validacion de wallet origen y destino.
- Publicacion de evento `transaction.created`.
- Payload con `event_type`, `occurred_at`, `source` y `data` completo.
- Tolerancia a falla del broker: si publicar falla, la transaccion igualmente se crea y se registra warning.

## Tests agregados

- `test/test_rabbitmq_publisher.py`
- `test/test_external_wallet_service.py`
- `test/test_transaction_messaging_integration.py`

## Como correr las pruebas

Instalar dependencias:

```powershell
pip install -r requirements.txt
```

Ejecutar todos los tests:

```powershell
pytest
```

Ejecutar solo TA-03:

```powershell
pytest test/test_rabbitmq_publisher.py test/test_external_wallet_service.py test/test_transaction_messaging_integration.py
```

Ejecutar con cobertura:

```powershell
pytest --cov=src --cov-report=term-missing
```

## Seguridad y estabilidad

- No se necesita RabbitMQ real para los tests.
- No se necesita servicio Usuarios y Wallets real para los tests.
- No se hacen llamadas HTTP reales en pruebas unitarias.
- No se almacenan ni muestran tokens en logs.
- El timeout de wallet externa evita bloqueos largos.
- Errores de red y respuestas inesperadas se manejan retornando `False`.
- La interfaz publica `check_wallet_exist(address)` se mantiene para no romper `TransactionService`.

## Cumplimiento de TA-03

- `src.core.rabbitmq_publisher` cubierto con tests de conexion, canal, publicacion, serializacion y cierre.
- `src.services.external_wallet_service` cubierto con tests de validacion local, HTTP mockeado, errores y configuracion por entorno.
- `requirements.txt` actualizado con `pytest-cov` y `httpx`.
- `.coveragerc` agregado como configuracion base de cobertura.
- Tests de integracion livianos agregados para comunicacion entre transacciones, wallets y mensajeria.
- No requiere servicios externos reales para validar la tarea.

## Verificacion ejecutada

Comandos ejecutados localmente:

```powershell
python -m pip install -r requirements.txt
python -m pytest
python -m pytest --cov=src --cov-report=term-missing
```

Resultado:

- `87 passed`.
- `src.core.rabbitmq_publisher`: 100% cobertura.
- `src.services.external_wallet_service`: 100% cobertura.
- Cobertura total del repo: 59%.

La cobertura total todavia no llega al objetivo general de 70% porque hay modulos fuera del alcance de TA-03 con baja cobertura, principalmente `block_service`, `block_validation_service`, `database`, `hash_utils` y `main`. Esta tarea deja instalada la medicion para que el equipo pueda subir esa metrica en las siguientes tareas.

## Notas para el equipo

El contrato real de wallets todavia tiene una ambiguedad: `GET /api/wallet/{address}` exige JWT y ownership. Si Blockchain necesita verificar wallets de terceros, lo mas seguro es que Usuarios y Wallets exponga un endpoint interno especifico, por ejemplo `GET /api/internal/wallet/{address}/exists`, protegido por token de servicio. Mientras tanto, este modulo queda preparado con token interno opcional y tests que cubren la respuesta `401`.
