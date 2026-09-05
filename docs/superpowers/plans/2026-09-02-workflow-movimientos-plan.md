# SENDA.V0 0.3.0 Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar el flujo Inicio → Información SENDA → Control → Gestión con selección múltiple, finalización, edición, paginación y categorías de movimientos sin perder datos existentes.

**Architecture:** Mantener `movements` como fuente registral y agregar migraciones aditivas para `categoria`, metadatos de expedientes y auditoría. Exponer consultas agregadas/paginadas mediante API y construir la UI horizontal de cuatro módulos sobre esas rutas.

**Tech Stack:** Python 3.10+, sqlite3, HTTPServer local, HTML/CSS/JavaScript, xlsxwriter/openpyxl existentes.

**Spec:** `docs/superpowers/specs/2026-09-02-workflow-movimientos-design.md`

## Global Constraints
- Mantener exactamente cuatro módulos: INICIO, INFORMACIÓN SENDA, CONTROL, GESTIÓN.
- No borrar ni recrear la base SQLite existente.
- Movimientos importados no son editables desde expedientes.
- Paginación de Información: 25/50/100, predeterminado 25.
- Orden de movimientos de expediente: más antiguo a más nuevo.
- FINALIZAR existe únicamente en Control y requiere un trámite abierto.
- Actualizaciones conservan todos los datos cargados.

---

### Task 1: Modelo y migración de categorías/workflow
**Files:** Modify `app/repository.py`, `app/importers/engine.py`; Test `tests/test_workflow.py`.
- [ ] Escribir pruebas fallidas para migración aditiva, clasificación y preservación de datos.
- [ ] Ejecutar pruebas y confirmar fallo por API faltante.
- [ ] Implementar `movement_category`, migraciones y campos de expediente/auditoría.
- [ ] Ejecutar pruebas hasta verde.

### Task 2: Información SENDA y paginación
**Files:** Modify `app/repository.py`, `app/server.py`; Test `tests/test_workflow.py`, `tests/test_api_workflow.py`.
- [ ] Escribir pruebas fallidas para bandeja agregada, 25/50/100, filtros y orden ascendente.
- [ ] Implementar consulta agregada por folio/plano y rutas API.
- [ ] Verificar pruebas.

### Task 3: Selección a Control, edición y finalización
**Files:** Modify `app/repository.py`, `app/server.py`; Test `tests/test_workflow.py`, `tests/test_api_workflow.py`.
- [ ] Escribir pruebas fallidas para selección múltiple, edición, detalle por derechos y FINALIZAR.
- [ ] Implementar rutas y auditoría.
- [ ] Verificar que Gestión reciba solo trámites finalizados y que retorno quede auditado.

### Task 4: UI horizontal recuperada y mejorada
**Files:** Modify `ui/index.html`, `ui/app.css`, `ui/app.js`, sincronizar `app/web/*`; Test `tests/test_ui_contract.py`.
- [ ] Escribir contratos fallidos para módulos, barras de movimientos, 25/50/100 y FINALIZAR condicional.
- [ ] Implementar UI horizontal y navegación.
- [ ] Verificar contratos y sintaxis JavaScript.

### Task 5: Exportaciones y KPIs
**Files:** Modify `app/services/exports.py`, `app/repository.py`, `ui/*`; Test `tests/test_workflow.py`, `tests/test_api.py`.
- [ ] Escribir pruebas fallidas para categoría/estado de expediente en exportación y contadores filtrados.
- [ ] Implementar campos y KPIs.
- [ ] Verificar exportaciones JSON/CSV/XLSX.

### Task 6: Regresión, muestras reales y empaquetado
**Files:** Modify version/docs; verify complete tree.
- [ ] Ejecutar suite completa.
- [ ] Ejecutar compilación Python y validación JavaScript.
- [ ] Importar muestras reales entregadas por el usuario en una base temporal.
- [ ] Verificar actualización no destructiva.
- [ ] Empaquetar Windows instalable y repositorio GitHub 0.3.0.
- [ ] Extraer ambos ZIP en carpetas limpias y repetir suite/health/root.
