# GBSturio - Video Studio

Software de producción de video en vivo desarrollado por **Ing. Gabrielli Gabriel**.

## Descripción

GBSturio es un mezclador de video en vivo con funcionalidades profesionales para streaming, producción de contenido y transmisiones en iglesias/eventos.

## Características principales

### Video
- **Pre-escucha A y B**: dos canales de preview independientes
- **Salida en Vivo (Master)**: pantalla de salida configurable a monitor/proyector externo
- **Captura de pantalla**: captura cualquier monitor y envía al pre o directo al vivo
- **PiP (Picture in Picture)**: cámara superpuesta en círculo o cuadrado
- **Transiciones**: Corte, Fundido, Deslizar, Zoom, Disolver, Borrado pizarrón, Burbujas, Quemar imagen, Pixelar, Cortinas
- **Zócalos/Overlays**: texto sobre video con fuente, color, posición y duración configurables
- **Alertas**: mensajes urgentes con parpadeo sobre el vivo

### Audio
- **3 canales independientes**: Pre A, Pre B, Master
- **Cada canal con**: volumen, mute, selector de dispositivo de salida
- **Samples**: 8 pads de efectos de sonido (auto-carga desde carpeta)
- **Reproducción de audio/video** con línea de tiempo por canal

### Biblia (requiere internet)
- **Búsqueda por referencia**: Juan 3:16, Salmos 23:1, etc.
- **Búsqueda inteligente por tema**: "jesús sana leproso", "amor de Dios"
- **Versiones**: Reina Valera 1960, NVI, NTV, DHH
- **API utilizada**: `bible-api.deno.dev` (gratuita, sin API key)
- **Idioma**: Español
- **Envío directo** al pre-escucha o al vivo como zócalo

> ⚠️ La Biblia requiere conexión a internet. Los versículos se obtienen en tiempo real desde la API.

### Streaming
- Configuración de RTMP para YouTube, Facebook Live, Twitch
- URL personalizada para cualquier servidor RTMP

### Programación
- Playlist con reproducción ordenada o random
- Guardado/carga de listas en formato `.gbs`

## Requisitos

```
Python 3.10+
PySide6 >= 6.6.0
opencv-python >= 4.9.0
numpy >= 1.26.0
Pillow >= 10.2.0
requests >= 2.31.0
```

## Instalación

```bash
pip install -r requirements.txt
```

## Ejecución

```bash
python main.py
```

## Estructura de carpetas

```
├── main.py                    # Punto de entrada
├── icono.png                  # Icono de la aplicación
├── requirements.txt           # Dependencias
├── README.md                  # Este archivo
├── src/
│   ├── core/
│   │   ├── camera.py          # Captura de cámara (OpenCV)
│   │   ├── audio_player.py    # Mezclador de audio (QMediaPlayer)
│   │   └── screen_capture.py  # Captura de pantalla
│   ├── ui/
│   │   ├── main_window.py     # Ventana principal
│   │   ├── samples/           # Carpeta de samples (auto-carga)
│   │   └── icons/
│   │       ├── png_botones/   # Iconos generales de botones
│   │       ├── tabs/          # Iconos de pestañas
│   │       ├── pre/           # Iconos de Pre A, Pre B, Vivo
│   │       ├── config/        # Icono de configuración
│   │       ├── mixer_btns/    # Iconos del mixer de audio
│   │       └── panel_derecho/ # Iconos del panel derecho
│   └── streaming/
│       └── __init__.py
```

## Samples

Poné archivos de audio (.mp3, .wav, .ogg, .flac) en `src/ui/samples/` y se cargan automáticamente en los 8 pads al iniciar la app.

## Temas

- **Tema oscuro** (por defecto): estilo profesional de producción
- **Tema claro**: interfaz limpia con fondos blancos

## Contacto

- 📧 gabgabrielligabriel@gmail.com
- 📧 virtualgaby361@gmail.com
- 📱 WhatsApp: 1121674227

## Donaciones

Este software fue desarrollado sin fines de lucro. Si te resulta útil, podés enviar una donación:

💰 **Mercado Pago - Alias: gaby28894178**

Se apreciará cualquier monto. ¡Gracias!

## Licencia

© 2026 GBSturio - Todos los derechos reservados.
Ing. Gabrielli Gabriel.
"# GbEstudio" 
