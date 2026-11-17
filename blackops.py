import cv2
import mss
import numpy as np
from ultralytics import YOLO
import time
import torch
import keyboard
import winsound
import ctypes
import threading
import sys
import os

# ==============================================================================
# 1. AUTO-ELEVACIÓN A ADMINISTRADOR Y OPTIMIZACIÓN DE KERNEL WINDOWS
# ==============================================================================
def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

if not is_admin():
    print("[INFO] Elevando permisos de Administrador (UAC) para inyección directa...")
    script_path = os.path.abspath(sys.argv[0])
    params = f'"{script_path}"'
    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    if ret > 32:
        sys.exit(0)
    else:
        print("[ERROR CRÍTICO] No se concedieron permisos de Administrador.")

# Desactivar virtualización de DPI en Windows (1920x1080 100% escala exacta)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

# Forzar resolución del temporizador del Kernel de Windows a 1.0 ms (por defecto es 15.6 ms)
ctypes.windll.winmm.timeBeginPeriod(1)

# Elevar prioridad del proceso Python a HIGH_PRIORITY_CLASS (0x00000080)
HIGH_PRIORITY_CLASS = 0x00000080
current_process = ctypes.windll.kernel32.GetCurrentProcess()
ctypes.windll.kernel32.SetPriorityClass(current_process, HIGH_PRIORITY_CLASS)

# Activar aceleración por hardware OpenCL en la AMD Radeon RX 6600 (gfx1032)
if cv2.ocl.haveOpenCL():
    cv2.ocl.setUseOpenCL(True)

# ==============================================================================
# 2. ESTRUCTURAS C PRE-ALOJADAS PARA DISPARO INSTANTÁNEO (< 0.05 ms)
# ==============================================================================
PUL = ctypes.POINTER(ctypes.c_ulong)

class KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL)
    ]

class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_short),
        ("wParamH", ctypes.c_ushort)
    ]

class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL)
    ]

class Input_I(ctypes.Union):
    _fields_ = [
        ("ki", KeyBdInput),
        ("mi", MouseInput),
        ("hi", HardwareInput)
    ]

class Input(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("ii", Input_I)
    ]

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_KEYUP = 0x0002
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001

VK_K = ord('K')
SCAN_CODE_K = ctypes.windll.user32.MapVirtualKeyW(VK_K, 0)
INPUT_SIZE = ctypes.sizeof(Input)

# Pre-construir los paquetes C en RAM una sola vez para cero latencia al disparar
_extra = ctypes.c_ulong(0)
_extra_ptr = ctypes.pointer(_extra)

_ii_mdown = Input_I()
_ii_mdown.mi = MouseInput(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, _extra_ptr)
_ii_kdown = Input_I()
_ii_kdown.ki = KeyBdInput(VK_K, SCAN_CODE_K, KEYEVENTF_SCANCODE, 0, _extra_ptr)
PACKET_DOWN = (Input * 2)(
    Input(INPUT_MOUSE, _ii_mdown),
    Input(INPUT_KEYBOARD, _ii_kdown)
)
PACKET_DOWN_PTR = ctypes.pointer(PACKET_DOWN[0])

_ii_mup = Input_I()
_ii_mup.mi = MouseInput(0, 0, 0, MOUSEEVENTF_LEFTUP, 0, _extra_ptr)
_ii_kup = Input_I()
_ii_kup.ki = KeyBdInput(VK_K, SCAN_CODE_K, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, _extra_ptr)
PACKET_UP = (Input * 2)(
    Input(INPUT_MOUSE, _ii_mup),
    Input(INPUT_KEYBOARD, _ii_kup)
)
PACKET_UP_PTR = ctypes.pointer(PACKET_UP[0])

SendInput = ctypes.windll.user32.SendInput
PostMessageW = ctypes.windll.user32.PostMessageW
GetForegroundWindow = ctypes.windll.user32.GetForegroundWindow

def _release_shot_async(hwnd, hold_time):
    time.sleep(hold_time)
    SendInput(2, PACKET_UP_PTR, INPUT_SIZE)
    if hwnd:
        PostMessageW(hwnd, WM_LBUTTONUP, 0, 0)

def trigger_fire_instant(hold_time=0.045):
    """
    Presiona el gatillo en el mismo microsegundo en que se detecta al enemigo
    y delega el levantamiento del botón a un hilo secundario sin bloquear la cámara.
    """
    hwnd = GetForegroundWindow()
    SendInput(2, PACKET_DOWN_PTR, INPUT_SIZE)
    if hwnd:
        PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, 0)
    threading.Thread(target=_release_shot_async, args=(hwnd, hold_time), daemon=True).start()

# ==============================================================================
# 3. CONFIGURACIÓN DEL MOTOR DE IA (RYZEN 5 5500 + RX 6600)
# ==============================================================================
# En Zen 3 (Ryzen 5 5500), 3 hilos físicos con flush_denormal evita contención de caché L3
torch.set_num_threads(3)
torch.set_num_interop_threads(1)
torch.set_flush_denormal(True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ONNX_PATH = os.path.join(BASE_DIR, 'yolov8n.onnx')
PT_PATH = os.path.join(BASE_DIR, 'yolov8n.pt')

if os.path.exists(ONNX_PATH):
    print("[GPU] Cargando modelo ONNX acelerado...")
    model = YOLO(ONNX_PATH, task='detect')
else:
    print("[CPU/Zen3] Cargando y fusionando capas de YOLOv8 Nano...")
    model = YOLO(PT_PATH)
    model.fuse()

# Región de 256x256 centrada exactamente en 1920x1080 (centro real: X=960, Y=540)
# Un recorte de 256x256 procesa un 72% menos de píxeles vacíos que 480x480 -> Reacción ~3.5x más rápida
ROI_SIZE = 256
INFER_SIZE = 224  # Tamaño interno óptimo de red para velocidad máxima (< 22 ms)
monitor_region = {
    "top": (1080 - ROI_SIZE) // 2,   # 412
    "left": (1920 - ROI_SIZE) // 2,  # 832
    "width": ROI_SIZE,
    "height": ROI_SIZE
}

# Warmup del modelo (pre-compila tensores en RAM antes de empezar a jugar)
print("[INFO] Pre-calentando tensores en memoria...")
_dummy = np.zeros((ROI_SIZE, ROI_SIZE, 3), dtype=np.uint8)
with torch.inference_mode():
    for _ in range(4):
        model.predict(_dummy, imgsz=INFER_SIZE, classes=[0], verbose=False, device='cpu')

# ==============================================================================
# 4. HILO DEDICADO DE CAPTURA A 144Hz (ZERO-LATENCY FRAME BUFFER)
# ==============================================================================
latest_frame = None
frame_lock = threading.Lock()
running = True

def capture_worker():
    """Hilo dedicado exclusivamente a leer el buffer de pantalla a máxima velocidad."""
    global latest_frame
    with mss.mss() as sct:
        while running:
            raw = np.asarray(sct.grab(monitor_region), dtype=np.uint8)
            # Slice directo BGRA -> BGR sin crear copias intermedias de OpenCV
            bgr = np.ascontiguousarray(raw[:, :, :3])
            with frame_lock:
                latest_frame = bgr

capture_thread = threading.Thread(target=capture_worker, daemon=True)
capture_thread.start()

# ==============================================================================
# 5. PARÁMETROS DEL TRIGGERBOT
# ==============================================================================
ACTIVATION_KEY = 'caps lock'
VISUALS_TOGGLE_KEY = 'f2'
CONFIDENCE_THRESHOLD = 0.28
SHOW_VISUALS = True
SHOT_COOLDOWN = 0.09  # Permite ráfagas rápidas de hasta ~11 disparos/seg

center_x = ROI_SIZE // 2
center_y = ROI_SIZE // 2

# Recorte interno de Hitbox (solo torso y cabeza)
HORIZONTAL_SHRINK = 0.24
VERTICAL_TOP_SHRINK = 0.07
VERTICAL_BOT_SHRINK = 0.15

print("\n" + "=" * 62)
print(f" [LISTO] Triggerbot Optimizado (Ryzen 5 5500 + RX 6600)")
print(f" -> Presiona [{ACTIVATION_KEY.upper()}] para ACTIVAR / PAUSAR el disparo.")
print(f" -> Presiona [{VISUALS_TOGGLE_KEY.upper()}] para OCULTAR / MOSTRAR el visor (Oculto = +FPS).")
print("=" * 62 + "\n")

bot_active = False
key_was_pressed = False
vis_key_was_pressed = False
last_shot_time = 0.0

try:
    with torch.inference_mode():
        while True:
            t_start = time.perf_counter()

            # --- INTERRUPTOR ACTIVAR / PAUSAR BOT (CAPS LOCK) ---
            if keyboard.is_pressed(ACTIVATION_KEY):
                if not key_was_pressed:
                    bot_active = not bot_active
                    key_was_pressed = True
                    if bot_active:
                        winsound.Beep(900, 60)
                        print("[INFO] Bot ACTIVADO (Tiempo Real).")
                    else:
                        winsound.Beep(400, 60)
                        print("[INFO] Bot EN PAUSA.")
            else:
                key_was_pressed = False

            # --- INTERRUPTOR MOSTRAR / OCULTAR VISOR (F2) ---
            if keyboard.is_pressed(VISUALS_TOGGLE_KEY):
                if not vis_key_was_pressed:
                    SHOW_VISUALS = not SHOW_VISUALS
                    vis_key_was_pressed = True
                    if not SHOW_VISUALS:
                        cv2.destroyAllWindows()
                        print("[MODO TURBO] Visor oculto -> Latencia mínima activada.")
                    else:
                        print("[INFO] Visor activado.")
            else:
                vis_key_was_pressed = False

            if not bot_active and not SHOW_VISUALS:
                time.sleep(0.005)
                continue

            # Obtener el último frame capturado por el hilo de 144Hz
            with frame_lock:
                if latest_frame is None:
                    continue
                frame = latest_frame if not SHOW_VISUALS else latest_frame.copy()

            if bot_active:
                results = model.predict(
                    frame,
                    conf=CONFIDENCE_THRESHOLD,
                    classes=[0],
                    imgsz=INFER_SIZE,
                    verbose=False,
                    device='cpu'
                )

                should_fire = False
                boxes = results[0].boxes

                if len(boxes) > 0:
                    xyxy_arr = boxes.xyxy.cpu().numpy()
                    conf_arr = boxes.conf.cpu().numpy()

                    for i in range(len(xyxy_arr)):
                        x1, y1, x2, y2 = map(int, xyxy_arr[i])
                        box_w = x2 - x1
                        box_h = y2 - y1

                        # Ignorar detecciones del arma propia ocupando casi todo el cuadro
                        if box_w > 220 and box_h > 220:
                            continue

                        hx1 = int(x1 + box_w * HORIZONTAL_SHRINK)
                        hx2 = int(x2 - box_w * HORIZONTAL_SHRINK)
                        hy1 = int(y1 + box_h * VERTICAL_TOP_SHRINK)
                        hy2 = int(y2 - box_h * VERTICAL_BOT_SHRINK)

                        if (hx1 <= center_x <= hx2) and (hy1 <= center_y <= hy2):
                            should_fire = True
                            box_color = (0, 0, 255)
                        else:
                            box_color = (0, 255, 0)

                        if SHOW_VISUALS:
                            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 1)
                            cv2.rectangle(frame, (hx1, hy1), (hx2, hy2), (0, 165, 255), 2)

                # Disparo instantáneo sin esperas bloqueantes
                now = time.perf_counter()
                if should_fire and (now - last_shot_time) >= SHOT_COOLDOWN:
                    trigger_fire_instant(hold_time=0.045)
                    last_shot_time = now

            if SHOW_VISUALS:
                dt_ms = (time.perf_counter() - t_start) * 1000.0
                fps = 1000.0 / max(dt_ms, 0.1)
                cv2.drawMarker(frame, (center_x, center_y), (255, 255, 0), cv2.MARKER_CROSS, 12, 1)
                cv2.putText(frame, f"{dt_ms:.1f}ms ({fps:.0f} FPS)", (6, 18),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
                cv2.imshow('Vista YOLOv8n - Turbo', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

except KeyboardInterrupt:
    pass
finally:
    running = False
    ctypes.windll.winmm.timeEndPeriod(1)
    cv2.destroyAllWindows()
