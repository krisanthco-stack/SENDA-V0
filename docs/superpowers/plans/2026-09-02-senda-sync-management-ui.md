# SENDA.V0 0.4.2 Sync + Gestión + UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Añadir intercambio Excel/JSON fusionable entre computadoras, KPI de trámites pendientes, estadísticas/exportación de Gestión y mejoras visuales aprobadas sin romper importadores ni datos existentes.

**Architecture:** Crear un servicio aislado `app/services/sync_transfer.py` que serializa/deserializa un formato SENDA portable y delega la fusión transaccional al repositorio. `desktop_model.import_files` detectará paquetes SENDA directos antes del importador registral. La UI reutilizará los métodos del repositorio y nuevos helpers visuales sin migraciones destructivas.

**Tech Stack:** Python 3.12, SQLite, Tkinter/ttk, XlsxWriter/OpenPyXL, pytest, GitHub Actions/PyInstaller.

**Spec:** `docs/superpowers/specs/2026-09-02-senda-sync-management-ui-design.md`

## Global Constraints
- Mantener módulos: INICIO, INFORMACIÓN SENDA, CONTROL, GESTIÓN.
- No borrar ni reemplazar `%LOCALAPPDATA%\\SENDA.V0`.
- Mantener XLS/XLSX/CSV/JSON/TXT/ZIP/RAR.
- Deduplicar movimientos y archivos repetidos.
- Conservar botón `ACTUALIZAR DESDE GITHUB`.
- Versión de entrega: 0.4.2.

---

### Task 1: Alarmas visibles y escala tipográfica

**Files:**
- Modify: `app/desktop_model.py`
- Modify: `app/desktop.py`
- Test: `tests/test_alarm_visuals.py`
- Test: `tests/test_visual_hierarchy.py`

**Interfaces:**
- Produces: `alarm_visual(level: str) -> dict`, `information_alarm_row(row: dict, checked: bool) -> tuple[tuple, str]`.

- [x] **Step 1:** Añadir prueba que exige etiquetas/badges de alarma, tags de Treeview y tamaños tipográficos 20% mayores.
- [x] **Step 2:** Ejecutar las pruebas y confirmar fallo por helpers/tamaños ausentes.
- [x] **Step 3:** Implementar helpers, tags de Treeview y constantes 12/14/23/13/24/12/11.
- [x] **Step 4:** Ejecutar pruebas y confirmar PASS.

### Task 2: KPI de trámites pendientes

**Files:**
- Modify: `app/repository.py`
- Modify: `app/desktop.py`
- Test: `tests/test_pending_dashboard.py`

**Interfaces:**
- Produces: `Repository.dashboard(...)["tramites_pendientes"]`.

- [x] **Step 1:** Probar que pendientes cuenta entidades del filtro no asociadas a casos EN CONTROL/GESTION.
- [x] **Step 2:** Confirmar fallo por clave ausente.
- [x] **Step 3:** Añadir consulta SQL de pendientes y tarjeta KPI.
- [x] **Step 4:** Ejecutar pruebas y confirmar PASS.

### Task 3: Exportación/importación SENDA fusionable

**Files:**
- Create: `app/services/sync_transfer.py`
- Modify: `app/repository.py`
- Modify: `app/desktop_model.py`
- Test: `tests/test_sync_transfer.py`

**Interfaces:**
- Produces: `export_sync_json(repo, target)`, `export_sync_xlsx(repo, target)`, `detect_sync_file(path)`, `import_sync_file(repo, path) -> dict`.
- Produces: `Repository.export_case_rows()`, `Repository.export_audit_rows()`, `Repository.merge_sync_payload(payload) -> dict`.

- [x] **Step 1:** Escribir pruebas de round-trip JSON y XLSX entre dos bases, incluyendo estados Control/Gestión y deduplicación de movimientos.
- [x] **Step 2:** Confirmar fallo por servicio ausente.
- [x] **Step 3:** Implementar exportación portable, lectura de Excel/JSON y fusión transaccional no destructiva.
- [x] **Step 4:** Integrar detección en `desktop_model.import_files` para archivos directos SENDA.
- [x] **Step 5:** Ejecutar pruebas y confirmar PASS.

### Task 4: Gestión con estadísticas y exportación fusionable

**Files:**
- Modify: `app/repository.py`
- Modify: `app/desktop_model.py`
- Modify: `app/desktop.py`
- Test: `tests/test_management_statistics.py`
- Test: `tests/test_desktop_management_contract.py`

**Interfaces:**
- Produces: `Repository.management_statistics(filters=None) -> dict` con `total`, `por_mes`, `por_distrito`.
- Produces: `export_sync_database(ctx, fmt, target)`.

- [x] **Step 1:** Escribir prueba de estadísticas por `finalized_at` y contrato visual/exportación.
- [x] **Step 2:** Confirmar fallo.
- [x] **Step 3:** Implementar estadísticas y panel gráfico en Gestión.
- [x] **Step 4:** Añadir botones `EXPORTAR BASE EXCEL` / `EXPORTAR BASE JSON` y usar servicio sync.
- [x] **Step 5:** Ejecutar pruebas y confirmar PASS.

### Task 5: Botones redondeados y actualización GitHub preservada

**Files:**
- Modify: `app/desktop.py`
- Test: `tests/test_rounded_buttons_and_update.py`

**Interfaces:**
- Produces: `RoundedButton` compatible con `pack/grid`, `command` y `state`.

- [x] **Step 1:** Escribir contrato que exige clase RoundedButton y uso en acciones principales, incluyendo actualización GitHub.
- [x] **Step 2:** Confirmar fallo.
- [x] **Step 3:** Implementar Canvas redondeado y migrar acciones principales/flujo.
- [x] **Step 4:** Ejecutar pruebas y confirmar PASS.

### Task 6: Versionado, workflow y regresión completa

**Files:**
- Modify: `pyproject.toml`
- Modify: `app/desktop.py`
- Modify: `.github/workflows/build-windows-desktop.yml`
- Modify: `README.md`
- Test: `tests/test_release_042.py`

**Interfaces:**
- Produces: Release `v0.4.2`, asset `SENDA.V0_0.4.2_WINDOWS_DESKTOP.zip`.

- [x] **Step 1:** Escribir prueba de contrato 0.4.2 y contenido del workflow.
- [x] **Step 2:** Confirmar fallo.
- [x] **Step 3:** Actualizar versión/workflow/documentación.
- [x] **Step 4:** Ejecutar `python -m pytest -q`, `python -m app.desktop --check` y compilación Python.
- [x] **Step 5:** Empaquetar parche y repositorio completo, comprobar ZIP y SHA-256.
