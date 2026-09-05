# SENDA.V0 0.4.2 — Diseño de intercambio fusionable, Gestión y jerarquía visual

## Objetivo
Convertir la exportación de Gestión en un paquete SENDA transportable entre computadoras mediante Excel o JSON, de forma que otra instalación pueda importar el archivo y fusionar movimientos, expedientes, estados de Control/Gestión y auditoría sin borrar datos locales ni duplicar movimientos.

## Flujo aprobado
1. En Gestión se ofrecen `EXPORTAR BASE EXCEL` y `EXPORTAR BASE JSON`.
2. El paquete contiene metadatos de formato/version, movimientos, expedientes y auditoría.
3. Desde `CARGAR DATOS`, un archivo SENDA de intercambio `.xlsx` o `.json` se reconoce antes del importador registral normal.
4. Los movimientos se fusionan usando la firma lógica ya usada para deduplicación, independiente del nombre del archivo.
5. Los expedientes se emparejan por folio; si no hay folio, por plano. Un expediente entrante con `updated_at` posterior o igual actualiza campos administrativos y estado. Nunca se eliminan expedientes locales por ausencia en el archivo importado.
6. La auditoría se fusiona por una firma portable de caso + acción + estados + nota + payload + fecha, evitando duplicados.
7. Tras la fusión, Inicio, Información SENDA, Control y Gestión se refrescan y reflejan el estado actualizado.

## Dashboard
- Mantener KPIs existentes.
- Agregar `TRÁMITES PENDIENTES` como entidades visibles que no están en `EN CONTROL` ni `GESTION` bajo el filtro activo.
- El KPI se recalcula con filtros de Inicio.

## Gestión
- Agregar estadísticas de trámites realizados por mes, basadas en `finalized_at`.
- Mostrar total de trámites realizados y distribución mensual.
- Agregar exportación fusionable Excel/JSON con detalles, fechas y estados.

## Formato JSON fusionable
Objeto raíz:
- `sistema`: `SENDA.V0`
- `formato`: `SENDA_TRANSFER`
- `version_formato`: `1`
- `exported_at`: fecha/hora ISO
- `movimientos`: filas exportables con campos de movimiento y workflow
- `expedientes`: campos completos de `case_files`
- `auditoria`: filas de `case_audit` con clave portable del expediente

## Formato Excel fusionable
Libro con hojas:
- `RESUMEN`: sistema, formato, versión y fecha de exportación.
- `MOVIMIENTOS`: mismos campos de movimiento usados en JSON.
- `EXPEDIENTES`: expediente, folio, plano, distrito, estado, responsable, prioridad, observaciones y fechas.
- `AUDITORIA`: acción, estados, nota, payload y fecha, con folio/plano para resolución portable.

## Seguridad de fusión
- No reemplazar el archivo SQLite completo.
- No borrar movimientos, expedientes ni auditoría local.
- Movimientos repetidos: omitir.
- Caso entrante más antiguo que el local: conservar local.
- Caso entrante más reciente o igual: actualizar campos permitidos y estado.
- Cualquier fusión de estado se registra como evento `SINCRONIZAR DESDE ARCHIVO`.

## Visual
- Aumentar 20% la escala tipográfica: cuerpo 12, panel 14, sección 23, navegación 13, KPI 24, etiqueta KPI 12, pequeño 11.
- Mantener jerarquía visual y aumentar altura de filas/controles para evitar recorte.
- Introducir botones Canvas con esquinas redondeadas para acciones principales y secundarias visibles.
- Información SENDA debe mostrar alarmas con etiqueta `🔴 ROJA`, `🟡 AMARILLA`, `🟢 VERDE` y fondo suave de fila.
- Conservar el botón `↻ ACTUALIZAR DESDE GITHUB` visible y funcional.

## Compatibilidad
- La carga registral continúa soportando XLS, XLSX, CSV, JSON, TXT, ZIP y RAR.
- El formato SENDA fusionable es adicional; no sustituye los importadores existentes.
- Datos persistentes siguen en `%LOCALAPPDATA%\\SENDA.V0`.
