# Documentación Técnica: US-14 Historial de Transacciones

## 1. Objetivo de este documento
Este archivo resume la implementación de la **US-14: Historial de Transacciones**, la cual permite a los usuarios obtener una visión cronológica y paginada de sus movimientos, consolidando datos del mempool y la cadena de bloques.

---

## 2. Contexto Funcional y Alcance
Se implementó un servicio unificado que recupera transacciones asociadas a una wallet (ya sea como emisor o receptor) desde el Módulo 2 de UFROCoin.

### Alcance Implementado
- **Consulta Unificada**: Recuperación de transacciones desde la colección `transacciones` (pendientes) y `blocks` (confirmadas).
- **Paginación**: Soporte para parámetros `page` y `limit` para optimizar el consumo del cliente.
- **Seguridad**: Validación de propiedad de la wallet mediante JWT con bypass de desarrollo (`test-token`).
- **Ordenamiento**: Entrega cronológica descendente (más reciente primero).
- **Integración MongoDB**: Conexión directa a la base de datos `blockchain_db`.

### Fuera de Alcance
- Filtros avanzados por fecha o tipo de transacción (se considerarán para futuras versiones).
- Exportación a formatos externos (PDF/CSV).

---

## 3. Arquitectura y Archivos Tocados

- `src/core/security.py`: Se añadió el bypass para `test-token` en `verify_wallet_owner`.
- `src/services/history_service.py`: Lógica central de filtrado, ordenamiento y paginación.
- `src/api/history_router.py`: Definición del endpoint y documentación OpenAPI.
- `src/main.py`: Registro del nuevo enrutador en la aplicación FastAPI.

---

## 4. Especificaciones Técnicas

### Endpoint: `GET /history/{address}`
- **Parámetros de Query**:
    - `page` (int, default=1): Número de página.
    - `limit` (int, default=10, max=100): Cantidad de registros.
- **Respuesta Exitosa (200 OK)**:
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
    ```

### Lógica de Paginación
La paginación se aplica sobre el conjunto total de resultados (Mempool + Blockchain) después de realizar el ordenamiento:
`resultado = lista_total[skip : skip + limit]` donde `skip = (page - 1) * limit`.

---

## 5. Guía de Verificación (Swagger)
1. Abrir `http://localhost:8000/docs`.
2. Autorizar con `test-token`.
3. Ejecutar `GET /history/billetera_con_fondos?page=1&limit=5`.
4. Verificar que se retornan los registros de la base de datos `blockchain_db`.
