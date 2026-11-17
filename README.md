# 🎯 YOLOv8 Zero-Latency Vision Triggerbot

Sistema de visión artificial en tiempo real de ultra-baja latencia basado en **YOLOv8 Nano**, diseñado para detección de objetivos en pantalla (1920x1080) e inyección instantánea de entrada a nivel de API de Windows (`SendInput` / `ctypes`).

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![YOLOv8](https://img.shields.io/badge/AI-YOLOv8n-purple)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6?logo=windows)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ Características Principales

- **⚡ Captura Asíncrona a 144Hz (`Zero-Latency Frame Buffer`):** Hilo dedicado con `mss` que captura una región de interés (ROI) de `256x256` centrada en la pantalla sin bloquear el hilo de inferencia.
- **🧠 Motor YOLOv8 Optimizado:**
  - Soporte automático para modelos **ONNX** (`yolov8n.onnx`) o **PyTorch** (`yolov8n.pt`) con fusión de capas (`model.fuse()`).
  - Pre-calentamiento (*warmup*) de tensores en RAM y ajuste de hilos (`flush_denormal`) optimizado para arquitecturas AMD Ryzen (Zen 3).
- **🚀 Inyección Instantánea en C (`< 0.05 ms`):** Estructuras `INPUT` de `user32.dll` pre-alojadas en memoria RAM y liberación asíncrona del disparo para no detener el bucle de visión.
- **🔧 Optimización de Kernel en Windows:**
  - Auto-elevación de permisos de Administrador (UAC).
  - Resolución del temporizador del kernel forzada a `1.0 ms` (`timeBeginPeriod(1)`).
  - Prioridad de proceso elevada a `HIGH_PRIORITY_CLASS` y desactivación de escalado DPI.
- **🎯 Recorte Inteligente de Hitbox:** Filtrado proporcional del cuadro delimitador (torso y cabeza) y descarte automático de falsos positivos cercanos (como el modelo del arma propia).

---

## 📂 Estructura del Proyecto

```text
├── blackops.py         # Script principal (captura, inferencia YOLOv8 e inyección Win32)
├── yolov8n.pt          # Modelo base pre-entrenado YOLOv8 Nano
├── best.pt             # Pesos personalizados entrenados
├── requirements.txt    # Dependencias del proyecto
├── .gitignore          # Archivos excluidos de Git
└── README.md           # Documentación del proyecto
```

---

## 🛠️ Requisitos e Instalación

### 1. Clonar el repositorio
```bash
git clone https://github.com/CamiloR28/yolov8-vision-triggerbot.git
cd yolov8-vision-triggerbot
```

### 2. Instalar dependencias
Se recomienda usar Python 3.10 o superior en Windows:
```bash
pip install -r requirements.txt
```

---

## 🎮 Uso y Controles

Ejecuta el script principal desde la terminal (solicitará permisos de Administrador automáticamente para permitir `SendInput`):

```bash
python blackops.py
```

| Tecla | Acción |
| :--- | :--- |
| **`CAPS LOCK`** | Activa / Pausa el disparo automático en tiempo real (con alerta sonora). |
| **`F2`** | Muestra / Oculta la ventana de depuración visual (**Modo Turbo** = mayor FPS y menor latencia). |
| **`Q`** | Cierra la ventana del visor (cuando está activa). |
| **`Ctrl + C`** | Detiene la ejecución de forma segura y restaura el temporizador del kernel. |

---

## ⚙️ Parámetros Configurables (`blackops.py`)

Puedes ajustar el comportamiento directamente en la sección **5. PARÁMETROS DEL TRIGGERBOT**:

- `CONFIDENCE_THRESHOLD = 0.28`: Umbral mínimo de confianza de detección de YOLOv8.
- `SHOT_COOLDOWN = 0.09`: Tiempo mínimo entre disparos (en segundos).
- `ROI_SIZE = 256` / `INFER_SIZE = 224`: Tamaño del recorte de pantalla y resolución interna de inferencia.
- `HORIZONTAL_SHRINK`, `VERTICAL_TOP_SHRINK`, `VERTICAL_BOT_SHRINK`: Ajuste fino del área activa de disparo dentro de la caja detectada.

---

## ⚠️ Aviso Legal (Disclaimer)

Este proyecto fue desarrollado **únicamente con fines educativos y de investigación** sobre visión por computadora en tiempo real, inferencia de redes neuronales de baja latencia e interacción con la API de Windows (`Win32`). El autor no se hace responsable del mal uso de este software ni de posibles sanciones en plataformas de terceros.
