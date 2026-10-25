# ClearCut AI · Removedor de Fondos

Aplicación de escritorio moderna para eliminar fondos y guardar PNG transparente.

## Novedades de diseño
- Tema oscuro con acentos violeta y cian.
- Zona de arrastrar y soltar con anillos pulsantes y borde animado.
- Escáner animado durante el procesamiento.
- Comparador Antes / Después con control deslizante.
- Fondo de vista previa: cuadros, blanco, negro o color.
- Progreso en 3 pasos, avisos animados y fundido de ventana.
- Selector de modelo de IA y opción de bordes suaves.
- Atajos: Ctrl+O abrir, Ctrl+S guardar, Enter procesar.

## Requisitos
- Windows 10/11
- Python 3.11 o 3.12
- Internet en la primera ejecución (dependencias y modelo)

## Inicio rápido
1. Extrae el ZIP.
2. Doble clic en `INICIAR.bat`.
3. Arrastra una imagen o ábrela.
4. Pulsa **Quitar fondo**.
5. Pulsa **Guardar PNG**.

## Manual
```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

## Calidad
- No reduce la resolución antes de procesar.
- Guarda PNG RGBA a resolución original.
- La vista previa se reduce solo para mostrarla.
- Cabello, vidrio y bordes finos pueden requerir retoque.
- `birefnet` da más calidad, pero es más lento y pesado.

## Privacidad
El procesamiento es local tras descargar dependencias y modelo.
