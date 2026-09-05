# SENDA.V0 0.3.0 — Flujo de Información SENDA, Control y Gestión

## Objetivo
Recuperar las funciones operativas útiles de SENDA 02 anterior y adaptarlas a la arquitectura SQLite/API de SENDA.V0 0.2.0 sin reintroducir sus fallos de conexión, almacenamiento en HTML o instalación.

## Estructura horizontal definitiva
1. INICIO
2. INFORMACIÓN SENDA
3. CONTROL
4. GESTIÓN

No se crean módulos adicionales. Las utilidades de exportación/mantenimiento permanecen en Inicio/contexto.

## Inicio
- Carga XLS/XLSX/CSV/JSON/TXT/ZIP/RAR.
- KPIs filtrables por año, trimestre, mes, distrito y alarma.
- Contadores: movimientos totales, folios/fincas, movimientos en Control/Gestión, alarmas.
- Estadísticas por distrito y categoría de movimiento.
- Exportación JSON/CSV/Excel de la base consolidada de movimientos.

## Información SENDA
- Bandeja de folios/fincas pendientes y en Control, excluyendo los que ya fueron finalizados hacia Gestión.
- Selección múltiple por checkbox; solo los seleccionados pasan a Control.
- Creación manual de expediente por folio y/o plano.
- Paginación predeterminada de 25; opciones 25/50/100.
- Orden predeterminado por primer movimiento del más antiguo al más nuevo.
- Filtros por año, trimestre, mes, distrito, alarma, estado y categoría de movimiento.
- Barra horizontal: TODOS, FINCAS, HIPOTECAS, GRAVÁMENES, SEGREGACIONES, ANOTACIONES, HISTÓRICOS, CERRADAS, OTROS.
- Cada fila muestra folio, plano, derechos, cantidad de movimientos, fechas, estado y alarmas.

## Control
- Contiene únicamente expedientes seleccionados desde Información SENDA.
- Puede contener varios trámites simultáneamente.
- Al abrir un trámite se muestran resumen, derechos subdivididos y todos los movimientos ligados por folio/plano.
- Movimientos paginados, 25 por defecto, ordenados del más antiguo al más nuevo.
- Permite editar metadatos administrativos del expediente sin alterar los movimientos importados.
- El botón FINALIZAR solo se habilita cuando existe un trámite abierto.
- FINALIZAR cambia el estado a GESTIÓN, registra auditoría y hace que el expediente deje de aparecer en Información SENDA y Control.

## Gestión
- Lista únicamente expedientes finalizados desde Control.
- Conserva historial, derechos y movimientos.
- Recupera la función anterior “Regresar a Información SENDA”, registrando la acción en auditoría.

## Modelo de datos
Los movimientos importados son fuente protegida. Se añade `categoria` a movimientos, sin modificar el contenido original. Los expedientes contienen estado administrativo, plano, responsable, prioridad, notas y fechas de flujo. Una tabla de auditoría registra cambios de estado y edición.

Estados operativos: INFORMACION, EN CONTROL, GESTION.

## Categorías de movimientos
Clasificación compatible con la lógica útil anterior:
- HIPOTECAS: operación/fuente contiene HIPOTECA.
- SEGREGACIONES: contiene SEGREG.
- ANOTACIONES: contiene ANOT.
- GRAVÁMENES: contiene GRAVAM, SERVIDUM, EMBARGO, LIMITACION o DEMANDA.
- CERRADAS: contiene CIERRE/CERRAD o fuente CERRADAS.
- FINCAS: fuente FINCAS/FINCAS GENERADAS.
- HISTÓRICOS: fuente HISTORICOS cuando no clasificó antes.
- OTROS: resto.

## Compatibilidad y datos existentes
- No se elimina ni recrea SQLite.
- Las migraciones solo agregan columnas/tablas/índices.
- Estados antiguos PENDIENTE/EN REVISION/FINALIZADO/REGRESADO se mapean a los estados nuevos.
- Actualizar SENDA conserva `%LOCALAPPDATA%\\SENDA.V0` y la base ya cargada.
