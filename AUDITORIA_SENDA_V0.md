# AUDITORÍA FINAL · SENDA.V0 0.4.4

Fecha de cierre de código: 2026-09-04

## Dictamen

**Repositorio fuente: CONFORME para subir a GitHub y ejecutar el workflow Windows.**

La 0.4.4 corrige las regresiones encontradas en 0.4.3 y usa una sola interfaz visual `ui/` para GitHub y para el ejecutable Windows. El EXE definitivo debe construirse en `windows-latest` mediante `.github/workflows/build-windows-desktop.yml`; el entorno local de esta auditoría no es Windows y por ello no se declara un EXE local como sustituto del artefacto de GitHub.

## 1. Interfaz GitHub = Windows

- `index.html` de la raíz redirige a `./ui/`.
- `SENDA_V0_DESKTOP.pyw` importa `app.desktop_webview`.
- PyInstaller incluye `--add-data "ui;ui"`.
- El workflow compara SHA-256 de `ui/index.html`, `ui/app.css`, `ui/app.js`, icono y PNG contra `_internal/ui` después del build.
- Después de crear el ZIP de Release, el workflow lo extrae y vuelve a comparar los mismos archivos UI por SHA-256.
- El EXE se prueba con `SENDA.V0.exe --check` antes de publicar.

Resultado: la versión instalada no mantiene una segunda UI Tk/ttk diferente.

## 2. Funciones de UI auditadas

Presencia y contrato automatizado verificados para:

- selección/copiar texto con mouse;
- `COPIAR EXPEDIENTE` en Información, Control y Gestión;
- selección múltiple de movimientos mediante casillas en Control;
- seleccionar página y limpiar selección;
- prohibición de finalizar si no hay movimientos seleccionados;
- Gestión recibe solamente los movimientos seleccionados;
- estados PENDIENTE / NOTIFICADO / REGISTRADO;
- regreso de Gestión a Información SENDA;
- filtro Año trámite;
- búsqueda por cédula y cédula jurídica;
- paginación 25/50/100;
- estadísticas de Inicio y Gestión;
- panel derecho de pendientes, alarmas, leyenda y códigos;
- enlaces de movimiento: ELIMINADOS en 0.4.5 por solicitud del usuario; no existe URL de respaldo.

## 3. Regla NUMERO = FINCA/FOLIO

Regla implementada:

1. `NUMERO` es autoritativo cuando existe.
2. `DERECHO=0`, vacío o inexistente no elimina la finca.
3. Si hay derecho real, se conserva como subdivisión de la misma finca.
4. Si `FOLIO` discrepa con `NUMERO`, prevalece `NUMERO`.

Prueba real sobre `Fincas_SARAPIQUI_01.06.2026(3).xls`:

- 1.511 movimientos insertados;
- 0 duplicados;
- 0 omitidos;
- 0 errores.

Casos reportados por el usuario, comprobados en una base fresca:

| NUMERO | Entidad encontrada | Movimientos vinculados en conjunto T1+T2 | Trámite conservado |
|---|---:|---:|---|
| 281400 | sí | 2 | 20260039683601 |
| 281407 | sí | 10 | 20260042421401 |
| 281408 | sí | 2 | 20260024716101 |
| 281413 | sí | 2 | 20260037530701 |
| 281414 | sí | 2 | 20250095408101 |

El caso 281414 demuestra además que el año del trámite se conserva independientemente del año del corte/movimiento.

Prueba real sobre `Fincas_SARAPIQUI_02.03.2026(1).xls`:

- 1.547 movimientos insertados;
- 0 duplicados;
- 0 omitidos;
- 0 errores.

## 4. Carga real T1/T2

Carga secuencial sobre una SQLite fresca usando los XLS y catálogos reales proporcionados:

### T1 · 02.03.2026

- nuevos: 8.397
- duplicados evitados: 2.032
- omitidos: 0
- errores: 0
- metadatos: 8.782
- catálogos procesados: 646

### T2 · 01.06.2026, añadida sobre la misma base

- nuevos: 8.666
- duplicados evitados: 1.726
- omitidos: 0
- errores: 0
- metadatos: 8.814
- catálogos procesados: 646

Total de movimientos lógicos en esa prueba combinada: **17.063**.

Este total corresponde específicamente a los archivos reales seleccionados en esta auditoría; no se fuerza para coincidir con conteos históricos de lotes diferentes.

## 5. ZIP real

`Anotaciones_SARAPIQUI_01.06.2026(1).zip` se procesó en una base fresca:

- nuevos: 8.735
- duplicados internos evitados: 1.657
- omitidos: 0
- errores: 0
- metadatos: 8.814

El ZIP contenía los archivos registrales de junio y sus catálogos.

## 6. RAR real

`SARAPIQUI(4).rar` fue extraído con la ruta real de `extract_rar` y procesado en una SQLite fresca.

Resultado:

- movimientos insertados: **0**;
- errores: **0**;
- referencias registrales/catastrales: **3.131**.

Distribución de metadatos:

- FINCAS de referencia: 499
- FINCAS GENERADAS: 342
- ÍNDICES PLANOS: 1.539
- PLANOS HIJO: 342
- PLANOS PADRE: 409

Por tanto, esos CSV auxiliares del RAR ya no inflan el contador de movimientos. Se conservan en `registry_references` y 2.050 registros tienen vínculo directo de finca en la prueba real.

## 7. STATUS y catálogos

La normalización conserva el valor fuente de STATUS antes de limpiar texto, permitiendo distinguir el NULL registral de un valor explícitamente omitible. Los catálogos se almacenan como catálogos, no como movimientos. Cédulas jurídicas y representantes se almacenan como metadatos de referencia.

## 8. Base SENDA fusionable

JSON/XLSX incluyen y fusionan sin borrar la base local:

- movimientos;
- expedientes;
- selecciones de movimientos;
- auditoría;
- estados de Gestión;
- referencias registrales;
- cédulas jurídicas;
- representantes.

## 9. Dependencias recurrentes

El workflow rechaza copias conflictivas en raíz/vendor de:

- openpyxl
- xlsxwriter
- et_xmlfile

También ejecuta `import openpyxl.compat` y `pip check` antes de las pruebas. En el repositorio final no existen esas carpetas sombreadoras.

## 10. Verificaciones de código

Última ejecución antes del empaquetado:

- `python -m pytest -q` → **120 passed**.
- `python SENDA_V0_DESKTOP.pyw --check ...` → **SENDA.V0 Desktop WebView OK 0.4.4**.
- `node --check ui/app.js` → sin errores de sintaxis.
- YAML del workflow → parseo correcto.
- dependencias sombreadoras prohibidas → ninguna.
- entrada GitHub Pages → `./ui/` verificada.

## 11. Límite de esta auditoría

El binario Windows final no se fabrica en el contenedor Linux de auditoría. Se fabrica y se vuelve a probar en `windows-latest` dentro del workflow entregado. Ese workflow tiene barreras de fallo antes de publicar el Artifact/Release si las pruebas, el EXE, la UI empaquetada o el ZIP final no coinciden con el contrato.
