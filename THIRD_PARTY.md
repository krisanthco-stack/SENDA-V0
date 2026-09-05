# Componentes de terceros

El build oficial de SENDA.V0 0.4.6 utiliza componentes de terceros:

- Python 3.12 (PSF License), incorporado por PyInstaller en la distribución.
- PyInstaller 6.22.2.
- PyWebView 6.2.1 para la ventana HTML local del escritorio.
- pythonnet 3.1.0 y clr-loader 0.3.1 para la integración .NET/WinForms requerida por PyWebView en Windows.
- Microsoft Edge WebView2 Runtime como motor Chromium embebido de Windows.
- openpyxl 3.1.5 y et_xmlfile para XLSX.
- XlsxWriter 3.2.9 para exportaciones XLSX.
- xlrd 2.0.2 (BSD) para Excel binario `.xls`.
- `rarfile.py` para detección/gestión RAR.
- 7-Zip, copiado desde el runner oficial de GitHub Actions al paquete para extracción RAR en Windows.

Las dependencias Python se instalan durante el build; no deben copiarse manualmente a la raíz ni a `vendor/` si pueden sombrear las versiones instaladas por pip. El workflow limpia y verifica expresamente copias conflictivas de `openpyxl`, `xlsxwriter`, `et_xmlfile`, `webview`, `pythonnet`, `clr_loader` y `clr.py`.

Windows fuerza `edgechromium`, por lo que la misma interfaz HTML/CSS/JS publicada en GitHub Pages se renderiza mediante Edge WebView2 dentro de la ventana propia de SENDA; no se abre Chrome/Edge como navegador externo.
