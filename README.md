# SENDA.V0 0.4.6 · Registro Inmobiliario

SENDA.V0 0.4.6 consolida una sola interfaz oficial para GitHub y Windows. La vista publicada por GitHub Pages abre `ui/index.html`, y el ejecutable Windows empaqueta **exactamente los mismos** `ui/index.html`, `ui/app.css`, `ui/app.js` y recursos. El escritorio se ejecuta en una ventana propia mediante PyWebView y un servidor local interno; no abre Chrome/Edge como navegador externo.

## Módulos

**INICIO // INFORMACIÓN SENDA // CONTROL // GESTIÓN**

- **Inicio:** carga de XLS/XLSX/CSV/JSON/TXT/ZIP/RAR, resumen de importación, estadísticas, contadores y Base SENDA fusionable.
- **Información SENDA:** fincas/folios y planos, filtros, cédula/cédula jurídica, año del trámite, paginación 25/50/100, selección de expedientes hacia Control y detalle seleccionable/copIABLE con mouse.
- **Control:** selección múltiple de movimientos mediante casillas. Un expediente no puede finalizar sin al menos un movimiento seleccionado. Solo los movimientos elegidos pasan a Gestión.
- **Gestión:** movimientos finalizados, estados PENDIENTE/NOTIFICADO/REGISTRADO, estadísticas, retorno a Información SENDA y exportación de la Base SENDA.

## Regla registral obligatoria: NUMERO = FINCA/FOLIO

Cuando un archivo registral contiene la columna `NUMERO`, SENDA la trata como identidad autoritativa de la finca.

- `PROVINCIA=4`, `NUMERO=281407`, `DERECHO=0` → finca `4-281407`.
- `PROVINCIA=4`, `NUMERO=281407`, `DERECHO=1` → finca base `4-281407`, derecho `001`, folio registral `4-281407-001`.
- `DERECHO=0`, vacío o ausente **nunca elimina NUMERO**.
- Si `FOLIO` y `NUMERO` discrepan, prevalece `NUMERO`.

Los ejemplos reportados `281400`, `281407`, `281408`, `281413` y `281414` forman parte de la regresión automatizada de 0.4.6.

## Estados y catálogos

SENDA distingue el `STATUS` registral sin convertir automáticamente un NULL de exportación en un valor omitible. Los catálogos, cédulas jurídicas y referencias catastrales/registrales auxiliares se almacenan como metadatos y **no se cuentan como movimientos**.

Los archivos RAR de referencia como `Indices_Planos.csv`, `Planos_Hijo.csv`, `Planos_Padre.csv`, `Fincas_Generadas.csv` y el `Fincas.csv` de relación plano→finca se guardan en `registry_references` y se enlazan con la finca/plano cuando es posible.

## Deduplicación

- El nombre de archivo no forma parte de la identidad lógica del movimiento.
- Una copia renombrada o el mismo contenido dentro de ZIP/RAR no debe crear otro movimiento.
- La firma lógica usa campos registrales normalizados.
- El resumen separa nuevos, duplicados, omitidos, errores, ignorados y metadatos.

## Base SENDA fusionable

La exportación/importación JSON y Excel fusiona datos sin borrar la base local. Incluye movimientos, expedientes, selección de movimientos, estados de Gestión, auditoría, referencias registrales RAR, cédulas jurídicas y representantes.

## Persistencia

Programa:

`%LOCALAPPDATA%\Programs\SENDA.V0`

Datos:

`%LOCALAPPDATA%\SENDA.V0`

Base principal:

`%LOCALAPPDATA%\SENDA.V0\database\senda_v0.sqlite`

Actualizar reemplaza solamente los archivos del programa; la carpeta de datos permanece separada.

## Interfaz única GitHub = Windows

La raíz de GitHub Pages (`index.html`) redirige a `./ui/`. Esa carpeta es la fuente única de la interfaz. El workflow de Windows:

1. ejecuta la suite de pruebas;
2. comprueba que el entrypoint usa `app.desktop_webview`;
3. empaqueta `ui/` con PyInstaller;
4. compara por SHA-256 cada archivo UI fuente contra la copia interna del ejecutable;
5. ejecuta `SENDA.V0.exe --check`;
6. extrae el ZIP de Release y vuelve a comparar por SHA-256 la UI final;
7. solo después publica el Artifact/Release.

Por diseño, un cambio visual en `ui/` es el mismo que se empaqueta en el instalable.

## Dependencias y regla anti-sombreado

El workflow instala versiones fijadas de PyInstaller, PyWebView, openpyxl, XlsxWriter, xlrd y pytest. Antes de probar/compilar falla si encuentra copias conflictivas en la raíz o `vendor/` de:

- `openpyxl`
- `xlsxwriter`
- `et_xmlfile`

También importa explícitamente `openpyxl.compat` antes del build para impedir la regresión recurrente de dependencias sombreadas.

## Generar el instalable en GitHub

1. Suba **el contenido** del ZIP del repositorio a la raíz de un repositorio con nombre compatible con Windows, por ejemplo `SENDA-V0` (sin punto final).
2. Abra **Actions → Build SENDA.V0 Windows Desktop → Run workflow**.
3. El workflow genera el Artifact `SENDA.V0-0.4.6-Windows-Desktop`.
4. La Release crea `SENDA.V0_0.4.6_WINDOWS_DESKTOP.zip`.
5. Extraiga el ZIP y ejecute `INSTALAR_SENDA_V0.bat`.

El Artifact se entrega directamente como carpeta instalable; la Release se entrega como ZIP de distribución.

## Verificación local

```bash
python -m pytest -q
python SENDA_V0_DESKTOP.pyw --check --data-dir <carpeta-temporal>
```

`--check` crea/migra SQLite, resuelve la UI oficial y valida el servidor local sin abrir la ventana.

## Cambio 0.4.6 · enlaces eliminados

Los enlaces web provenientes de Excel no se importan, no se muestran, no se copian ni se exportan. También se eliminó cualquier URL de respaldo para expedientes.


## Cambio 0.4.6 · arranque Windows reforzado

El escritorio fuerza Edge Chromium (WebView2), habilita selección de texto con mouse, elimina Mark-of-the-Web de DLL/PYD/EXE antes de cargar pythonnet, y el workflow ejecuta una prueba real de inicialización de la GUI además de `--check`. El stack Windows queda fijado a PyWebView 6.2.1, pythonnet 3.1.0 y clr-loader 0.3.1.
