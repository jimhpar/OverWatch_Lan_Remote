import sys
import os
import time
import json
import base64
import asyncio
import socket
import threading
import numpy as np
import cv2
import mss
import websockets
if sys.platform == "win32":
    import winreg
    import ctypes
    import ctypes.wintypes as wintypes

    class POINT(ctypes.Structure):
        _fields_ = [('x', wintypes.LONG), ('y', wintypes.LONG)]

    class CURSORINFO(ctypes.Structure):
        _fields_ = [
            ('cbSize', wintypes.DWORD),
            ('flags', wintypes.DWORD),
            ('hCursor', wintypes.HANDLE),
            ('ptScreenPos', POINT)
        ]

    class ICONINFO(ctypes.Structure):
        _fields_ = [
            ('fIcon', wintypes.BOOL),
            ('xHotspot', wintypes.DWORD),
            ('yHotspot', wintypes.DWORD),
            ('hbmMask', wintypes.HBITMAP),
            ('hbmColor', wintypes.HBITMAP)
        ]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ('biSize', wintypes.DWORD),
            ('biWidth', wintypes.LONG),
            ('biHeight', wintypes.LONG),
            ('biPlanes', wintypes.WORD),
            ('biBitCount', wintypes.WORD),
            ('biCompression', wintypes.DWORD),
            ('biSizeImage', wintypes.DWORD),
            ('biXPelsPerMeter', wintypes.LONG),
            ('biYPelsPerMeter', wintypes.LONG),
            ('biClrUsed', wintypes.DWORD),
            ('biClrImportant', wintypes.DWORD)
        ]

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    user32.GetCursorInfo.argtypes = [ctypes.POINTER(CURSORINFO)]
    user32.GetCursorInfo.restype = wintypes.BOOL
    user32.GetIconInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(ICONINFO)]
    user32.GetIconInfo.restype = wintypes.BOOL
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteObject.restype = wintypes.BOOL

    def capture_active_cursor(cursor_size=32):
        """Captures active Windows cursor bitmap (Photoshop, Illustrator, CAD tools) & hotspot."""
        try:
            hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)

            ci = CURSORINFO()
            ci.cbSize = ctypes.sizeof(CURSORINFO)
            if not user32.GetCursorInfo(ctypes.byref(ci)) or not ci.hCursor or not (ci.flags & 1):
                return None, 0, 0, None

            cursor_handle_id = str(ci.hCursor)

            ii = ICONINFO()
            if not user32.GetIconInfo(ci.hCursor, ctypes.byref(ii)):
                return cursor_handle_id, 0, 0, None

            hx, hy = int(ii.xHotspot), int(ii.yHotspot)

            hdc_screen = user32.GetDC(0)
            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)

            bih = BITMAPINFOHEADER()
            bih.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bih.biWidth = cursor_size
            bih.biHeight = -cursor_size
            bih.biPlanes = 1
            bih.biBitCount = 32
            bih.biCompression = 0

            p_bits = ctypes.c_void_p()
            hbmp = gdi32.CreateDIBSection(hdc_screen, ctypes.byref(bih), 0, ctypes.byref(p_bits), 0, 0)
            old_bmp = gdi32.SelectObject(hdc_mem, hbmp)

            user32.DrawIconEx(hdc_mem, 0, 0, ci.hCursor, cursor_size, cursor_size, 0, 0, 0x0003)

            buf = (ctypes.c_ubyte * (cursor_size * cursor_size * 4)).from_address(p_bits.value)
            arr = np.frombuffer(buf, dtype=np.uint8).reshape((cursor_size, cursor_size, 4)).copy()

            # If alpha channel is all zeros (monochrome / standard inverted cursor), create alpha from RGB presence
            if not np.any(arr[:, :, 3] > 0):
                rgb_sum = np.sum(arr[:, :, :3], axis=2)
                arr[:, :, 3] = np.where(rgb_sum > 0, 255, 0).astype(np.uint8)

            gdi32.SelectObject(hdc_mem, old_bmp)
            gdi32.DeleteObject(hbmp)
            gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(0, hdc_screen)
            if ii.hbmColor:
                gdi32.DeleteObject(ii.hbmColor)
            if ii.hbmMask:
                gdi32.DeleteObject(ii.hbmMask)

            success, png_bytes = cv2.imencode('.png', arr)
            if success:
                b64_png = base64.b64encode(png_bytes.tobytes()).decode('utf-8')
                return cursor_handle_id, hx, hy, b64_png
            return cursor_handle_id, hx, hy, None
        except Exception:
            return None, 0, 0, None
else:
    winreg = None
    def capture_active_cursor(cursor_size=32):
        return None, 0, 0, None

from PyQt6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QMessageBox,
                             QInputDialog, QWidget, QDialog, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QFrame,
                             QComboBox, QFileDialog, QSizePolicy, QProgressBar)
from PyQt6.QtGui import QIcon, QPixmap, QImage, QPainter, QColor, QCursor
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, Qt, QEvent, QSize

from config import Config
from protocol import Protocol, PacketType

# Optional pynput for remote input execution
try:
    from pynput.mouse import Button, Controller as MouseController
    from pynput.keyboard import Key, Controller as KeyboardController
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False


class RemoteInputHandler:
    """Executes remote mouse and keyboard events sent from Master Manager."""
    def __init__(self):
        if PYNPUT_AVAILABLE:
            self.mouse = MouseController()
            self.keyboard = KeyboardController()
        else:
            self.mouse = None
            self.keyboard = None

    def handle_event(self, event_type, params):
        if not PYNPUT_AVAILABLE or not self.mouse or not self.keyboard:
            return

        try:
            if event_type == "mouse_move":
                # Normalized coordinates (0.0 - 1.0)
                norm_x = params.get("x", 0)
                norm_y = params.get("y", 0)
                screen_w = params.get("screen_w", 1920)
                screen_h = params.get("screen_h", 1080)
                self.mouse.position = (int(norm_x * screen_w), int(norm_y * screen_h))

            elif event_type == "mouse_click":
                norm_x = params.get("x", 0)
                norm_y = params.get("y", 0)
                screen_w = params.get("screen_w", 1920)
                screen_h = params.get("screen_h", 1080)
                button_name = params.get("button", "left")
                pressed = params.get("pressed", True)

                btn = Button.left
                if button_name == "right":
                    btn = Button.right
                elif button_name == "middle":
                    btn = Button.middle

                self.mouse.position = (int(norm_x * screen_w), int(norm_y * screen_h))
                if pressed:
                    self.mouse.press(btn)
                else:
                    self.mouse.release(btn)

            elif event_type == "mouse_scroll":
                norm_x = params.get("x")
                norm_y = params.get("y")
                if norm_x is not None and norm_y is not None:
                    screen_w = params.get("screen_w", 1920)
                    screen_h = params.get("screen_h", 1080)
                    self.mouse.position = (int(norm_x * screen_w), int(norm_y * screen_h))

                dx = params.get("dx", 0)
                dy = params.get("dy", 0)

                if self.mouse:
                    self.mouse.scroll(dx, dy)
                elif sys.platform == "win32":
                    import ctypes
                    if dy:
                        ctypes.windll.user32.mouse_event(0x0800, 0, 0, int(dy * 120), 0)
                    if dx:
                        ctypes.windll.user32.mouse_event(0x01000, 0, 0, int(dx * 120), 0)

            elif event_type in ("key_press", "key_release"):
                key_str = params.get("key", "")
                key_obj = self._parse_key(key_str)
                if key_obj:
                    if event_type == "key_press":
                        self.keyboard.press(key_obj)
                    else:
                        self.keyboard.release(key_obj)
        except Exception as e:
            print(f"[InputHandler Error] {e}")

    def _parse_key(self, key_str):
        if len(key_str) == 1:
            return key_str
        # Special key mapping
        special_keys = {
            "space": Key.space,
            "enter": Key.enter,
            "backspace": Key.backspace,
            "tab": Key.tab,
            "esc": Key.esc,
            "shift": Key.shift,
            "ctrl": Key.ctrl,
            "alt": Key.alt,
            "cmd": Key.cmd,
            "delete": Key.delete,
            "up": Key.up,
            "down": Key.down,
            "left": Key.left,
            "right": Key.right
        }
        return special_keys.get(key_str.lower(), None)


class ScreenCapturer:
    """High performance screen capture & compression using MSS and OpenCV."""
    def __init__(self):
        self.sct = mss.mss()
        self.monitor = self.sct.monitors[1]  # Primary monitor
        self.prev_frame_gray = None
        self.quality_preset = Config.DEFAULT_QUALITY_PRESET
        self.jpeg_quality = Config.QUALITY_PRESETS[self.quality_preset]["jpeg_quality"]
        self.scale = Config.QUALITY_PRESETS[self.quality_preset]["scale"]
        self.last_cursor_id = None

    def set_preset(self, preset_name):
        if preset_name in Config.QUALITY_PRESETS:
            self.quality_preset = preset_name
            self.jpeg_quality = Config.QUALITY_PRESETS[preset_name]["jpeg_quality"]
            self.scale = Config.QUALITY_PRESETS[preset_name]["scale"]

    def capture_and_compress(self):
        # Capture raw frame
        sct_img = self.sct.grab(self.monitor)
        frame_bgra = np.array(sct_img)
        frame_bgr = cv2.cvtColor(frame_bgra, cv2.COLOR_BGRA2BGR)

        h, w = frame_bgr.shape[:2]

        # Calculate static screen delta
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        is_static = False
        if self.prev_frame_gray is not None:
            # Resize for fast delta calculation
            small_curr = cv2.resize(gray, (160, 90))
            small_prev = cv2.resize(self.prev_frame_gray, (160, 90))
            delta = np.mean(cv2.absdiff(small_curr, small_prev))
            if delta < Config.STATIC_DELTA_THRESHOLD:
                is_static = True

        self.prev_frame_gray = gray

        # Optional Downscaling for bandwidth efficiency
        if self.scale != 1.0:
            target_w = int(w * self.scale)
            target_h = int(h * self.scale)
            frame_to_encode = cv2.resize(frame_bgr, (target_w, target_h), interpolation=cv2.INTER_AREA)
        else:
            frame_to_encode = frame_bgr
            target_w, target_h = w, h

        # JPEG Encoding
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
        success, encoded_img = cv2.imencode('.jpg', frame_to_encode, encode_param)
        if not success:
            return None, w, h, False, None

        # Capture active cursor for Photoshop / design tools
        cursor_data = None
        cid, hx, hy, b64_png = capture_active_cursor()
        if cid:
            if cid != self.last_cursor_id:
                self.last_cursor_id = cid
                cursor_data = {"id": cid, "hx": hx, "hy": hy, "png": b64_png}
            else:
                cursor_data = {"id": cid, "hx": hx, "hy": hy}

        return encoded_img.tobytes(), w, h, is_static, cursor_data


class ClientWorker(QObject):
    status_changed = pyqtSignal(str, str) # status_type ('connected', 'disconnected', 'error'), message
    alert_received = pyqtSignal()
    quality_updated = pyqtSignal(str, int)
    share_started = pyqtSignal(str, str, str, bool) # session_id, source_id, source_name, allow_remote
    share_frame_received = pyqtSignal(str, bytes, dict) # session_id, frame_bytes, metadata
    share_stopped = pyqtSignal(str) # session_id
    client_list_updated = pyqtSignal(list) # clients list
    peer_prompt_received = pyqtSignal(str, str, str, str, str) # req_id, req_id_str, req_name, target_id, mode
    peer_request_declined = pyqtSignal(str, str) # target_name, reason
    peer_request_resolved = pyqtSignal(str) # req_id

    def __init__(self, server_ip, server_port, client_name, passcode):
        super().__init__()
        self.server_ip = server_ip
        self.server_port = server_port
        self.client_name = client_name
        self.passcode = passcode
        self.running = True
        self.target_fps = Config.DEFAULT_TARGET_FPS
        self.capturer = ScreenCapturer()
        self.input_handler = RemoteInputHandler()
        self.hostname = socket.gethostname()
        self.local_ip = Config.get_local_ip()
        self.loop = None
        self.ws = None

    def stop(self):
        self.running = False

    def run(self):
        asyncio.run(self._main_loop())

    async def _main_loop(self):
        self.loop = asyncio.get_running_loop()
        uri = f"ws://{self.server_ip}:{self.server_port}"
        
        while self.running:
            try:
                self.status_changed.emit("connecting", f"Connecting to {uri}...")
                async with websockets.connect(uri, max_size=10_000_000, ping_interval=10) as ws:
                    self.ws = ws
                    self.status_changed.emit("connected", f"Connected to Master at {self.server_ip}")
                    
                    # 1. Handshake Auth
                    auth_pkt = Protocol.create_auth_request(
                        client_name=self.client_name,
                        hostname=self.hostname,
                        ip_address=self.local_ip,
                        passcode=self.passcode
                    )
                    await ws.send(auth_pkt)

                    resp_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    resp = Protocol.parse(resp_raw)
                    if not resp or not resp.get("success"):
                        err_msg = resp.get("message", "Authentication Failed") if resp else "Auth Timeout"
                        self.status_changed.emit("error", f"Auth Error: {err_msg}")
                        await asyncio.sleep(5)
                        continue

                    # 2. Parallel tasks: Sending frame stream & Listening for remote commands
                    send_task = asyncio.create_task(self._send_stream(ws))
                    recv_task = asyncio.create_task(self._listen_commands(ws))

                    done, pending = await asyncio.wait(
                        [send_task, recv_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in pending:
                        task.cancel()

            except (websockets.exceptions.ConnectionClosed, OSError, asyncio.TimeoutError) as e:
                self.ws = None
                self.status_changed.emit("disconnected", f"Disconnected. Retrying in 3s... ({e})")
                await asyncio.sleep(3)
            except Exception as e:
                self.ws = None
                self.status_changed.emit("error", f"Unexpected error: {e}")
                await asyncio.sleep(3)

    async def _send_stream(self, ws):
        last_time = time.time()
        fps_counter = 0
        current_fps = 10.0

        while self.running:
            start_t = time.time()

            frame_bytes, orig_w, orig_h, is_static, cursor_data = self.capturer.capture_and_compress()
            if frame_bytes:
                pkt = Protocol.create_frame_packet(
                    client_id=f"{self.hostname}_{self.local_ip}",
                    frame_bytes=frame_bytes,
                    fps=current_fps,
                    width=orig_w,
                    height=orig_h,
                    is_static=is_static,
                    cursor_data=cursor_data
                )
                await ws.send(pkt)

            fps_counter += 1
            now = time.time()
            if now - last_time >= 1.0:
                current_fps = fps_counter / (now - last_time)
                fps_counter = 0
                last_time = now

            # Adaptive throttling based on screen static state
            effective_target_fps = Config.MIN_STATIC_FPS if is_static else self.target_fps
            delay = max(0.001, (1.0 / effective_target_fps) - (time.time() - start_t))
            await asyncio.sleep(delay)

    async def _listen_commands(self, ws):
        async for message in ws:
            pkt = Protocol.parse(message)
            if not pkt:
                continue

            pkt_type = pkt.get("type")
            if pkt_type == PacketType.REMOTE_INPUT:
                event_type = pkt.get("event_type")
                params = pkt.get("params", {})
                self.input_handler.handle_event(event_type, params)

            elif pkt_type == PacketType.QUALITY_UPDATE:
                preset = pkt.get("preset")
                target_fps = pkt.get("target_fps")
                if preset:
                    self.capturer.set_preset(preset)
                if target_fps:
                    self.target_fps = max(1, min(120, int(target_fps)))
                self.quality_updated.emit(self.capturer.quality_preset, self.target_fps)

            elif pkt_type == PacketType.ALERT:
                self.alert_received.emit()

            elif pkt_type == PacketType.CLIENT_LIST_UPDATE:
                clients = pkt.get("clients", [])
                self.client_list_updated.emit(clients)

            elif pkt_type == PacketType.PEER_PROMPT_REQ:
                req_id = pkt.get("request_id")
                req_id_str = pkt.get("requester_id")
                req_name = pkt.get("requester_name", "A colleague")
                target_id = pkt.get("target_id")
                mode = pkt.get("mode", "view")
                self.peer_prompt_received.emit(req_id, req_id_str, req_name, target_id, mode)

            elif pkt_type == PacketType.PEER_REQUEST_DECLINED:
                target_name = pkt.get("target_name", "Target PC")
                reason = pkt.get("reason", "Request was declined.")
                self.peer_request_declined.emit(target_name, reason)

            elif pkt_type == PacketType.PEER_REQUEST_RESOLVED:
                req_id = pkt.get("request_id")
                self.peer_request_resolved.emit(req_id)

            elif pkt_type == PacketType.SHARE_STREAM_START:
                session_id = pkt.get("session_id")
                source_id = pkt.get("source_id")
                source_name = pkt.get("source_name", "Shared Screen")
                allow_remote = pkt.get("allow_remote_control", False)
                self.share_started.emit(session_id, source_id, source_name, allow_remote)

            elif pkt_type == PacketType.SHARE_STREAM_FRAME:
                session_id = pkt.get("session_id")
                b64_frame = pkt.get("frame")
                if b64_frame:
                    frame_bytes = base64.b64decode(b64_frame)
                    metadata = {
                        "fps": pkt.get("fps", 0),
                        "width": pkt.get("width", 1920),
                        "height": pkt.get("height", 1080),
                        "is_static": pkt.get("is_static", False),
                        "cursor": pkt.get("cursor")
                    }
                    self.share_frame_received.emit(session_id, frame_bytes, metadata)

            elif pkt_type == PacketType.SHARE_STREAM_STOP:
                session_id = pkt.get("session_id")
                self.share_stopped.emit(session_id)

    def send_share_input(self, session_id, source_id, event_type, params):
        if self.loop and self.ws:
            pkt = Protocol.create_share_input(session_id, source_id, event_type, params)
            asyncio.run_coroutine_threadsafe(self.ws.send(pkt), self.loop)

    def send_peer_share_request(self, target_id, mode="view"):
        if self.loop and self.ws:
            pkt = Protocol.create_peer_share_request(
                requester_id=f"{self.hostname}_{self.local_ip}",
                requester_name=self.client_name,
                target_id=target_id,
                mode=mode
            )
            asyncio.run_coroutine_threadsafe(self.ws.send(pkt), self.loop)

    def send_peer_prompt_response(self, request_id, requester_id, target_id, accepted, mode="view"):
        if self.loop and self.ws:
            pkt = Protocol.create_peer_prompt_response(
                request_id=request_id,
                requester_id=requester_id,
                target_id=target_id,
                accepted=accepted,
                mode=mode
            )
            asyncio.run_coroutine_threadsafe(self.ws.send(pkt), self.loop)


class SharedStreamViewer(QDialog):
    def __init__(self, session_id, source_id, source_name, allow_remote_control, worker, parent=None):
        super().__init__(parent)
        self.session_id = session_id
        self.source_id = source_id
        self.source_name = source_name
        self.allow_remote_control = allow_remote_control
        self.worker = worker
        self.remote_control_enabled = False
        self.last_frame_size = (1920, 1080)
        self.last_frame_bytes = None
        self.last_metadata = {}
        self.normal_geometry = None
        self.cursor_cache = {}
        self.current_remote_cursor = None

        self.setWindowTitle(f"Shared Screen - {self.source_name} (Overwatch)")

        # Default responsive scale (1280x720 or 85% available screen)
        screen = QApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            def_w = min(1280, int(screen_geo.width() * 0.85))
            def_h = min(720, int(screen_geo.height() * 0.85))
            self.resize(def_w, def_h)
        else:
            self.resize(1280, 720)

        self.setStyleSheet("background-color: #0F172A; color: #F8FAFC;")

        bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(bundle_dir, "app_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.init_ui()
        self.installEventFilter(self)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Stream Viewport
        self.viewport = QLabel(self)
        self.viewport.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewport.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.viewport.setMinimumSize(320, 180)
        self.viewport.setText("Receiving shared stream feed...")
        self.viewport.setStyleSheet("background-color: #0B1120; color: #64748B; font-size: 14px;")
        self.viewport.setMouseTracking(True)
        self.viewport.installEventFilter(self)
        main_layout.addWidget(self.viewport, stretch=1)

        # Floating Action Bar
        self.action_bar = QFrame(self)
        self.action_bar.setStyleSheet("""
            QFrame {
                background-color: rgba(15, 23, 42, 0.9);
                border: 1px solid rgba(0, 243, 255, 0.3);
                border-radius: 12px;
                margin: 8px;
            }
            QLabel {
                color: #F8FAFC;
                font-family: 'Segoe UI', 'Inter', sans-serif;
            }
            QPushButton {
                background-color: rgba(30, 41, 59, 0.8);
                border: 1px solid #334155;
                border-radius: 6px;
                color: #F8FAFC;
                padding: 6px 12px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(51, 65, 85, 0.9);
                border-color: #00F3FF;
                color: #00F3FF;
            }
        """)
        bar_layout = QHBoxLayout(self.action_bar)
        bar_layout.setContentsMargins(14, 6, 14, 6)
        bar_layout.setSpacing(12)

        # Title Label
        self.title_lbl = QLabel(f"🖥️ {self.source_name}", self.action_bar)
        self.title_lbl.setStyleSheet("font-weight: 700; color: #00F3FF; font-size: 13px;")
        bar_layout.addWidget(self.title_lbl)

        # Stats readout
        self.stats_lbl = QLabel("0 FPS | Res: 1920x1080", self.action_bar)
        self.stats_lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
        bar_layout.addWidget(self.stats_lbl)

        bar_layout.addStretch()

        # Remote Control Button (if allowed)
        if self.allow_remote_control:
            self.rc_btn = QPushButton("🎮 Remote Control: OFF", self.action_bar)
            self.rc_btn.setCheckable(True)
            self.rc_btn.clicked.connect(self.toggle_remote_control)
            bar_layout.addWidget(self.rc_btn)
        else:
            self.rc_btn = QLabel("🔒 View Only", self.action_bar)
            self.rc_btn.setStyleSheet("color: #64748B; font-style: italic; font-size: 12px; padding: 4px 8px;")
            bar_layout.addWidget(self.rc_btn)

        # Screenshot Button
        self.shot_btn = QPushButton("📸 Screenshot", self.action_bar)
        self.shot_btn.clicked.connect(self.take_screenshot)
        bar_layout.addWidget(self.shot_btn)

        # Fullscreen Toggle Button
        self.fs_btn = QPushButton("🖵 Fullscreen", self.action_bar)
        self.fs_btn.setCheckable(True)
        self.fs_btn.clicked.connect(self.toggle_fullscreen)
        bar_layout.addWidget(self.fs_btn)

        # Close Button
        self.close_btn = QPushButton("❌ Close", self.action_bar)
        self.close_btn.setStyleSheet("background-color: rgba(239, 68, 68, 0.2); border: 1px solid #EF4444; color: #EF4444; font-weight: 700;")
        self.close_btn.clicked.connect(self.close)
        bar_layout.addWidget(self.close_btn)

        main_layout.addWidget(self.action_bar, alignment=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)

    def render_frame(self):
        if not self.last_frame_bytes:
            return
        image = QImage()
        if image.loadFromData(self.last_frame_bytes):
            pixmap = QPixmap.fromImage(image)
            vp_size = self.viewport.size()
            if vp_size.width() > 10 and vp_size.height() > 10:
                scaled = pixmap.scaled(
                    vp_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.viewport.setPixmap(scaled)

    def update_frame(self, image_bytes, metadata):
        self.last_frame_bytes = image_bytes
        self.last_metadata = metadata
        self.last_frame_size = (metadata.get("width", 1920), metadata.get("height", 1080))
        self.render_frame()

        fps = metadata.get("fps", 0)
        self.stats_lbl.setText(f"{fps:.1f} FPS | Res: {self.last_frame_size[0]}x{self.last_frame_size[1]}")

        # Update cursor for Photoshop / design tools
        cursor_info = metadata.get("cursor")
        if cursor_info:
            cid = cursor_info.get("id")
            hx = cursor_info.get("hx", 0)
            hy = cursor_info.get("hy", 0)
            png_b64 = cursor_info.get("png")
            if png_b64:
                try:
                    png_data = base64.b64decode(png_b64)
                    qimg = QImage.fromData(png_data)
                    qpix = QPixmap.fromImage(qimg)
                    qcur = QCursor(qpix, hx, hy)
                    self.cursor_cache[cid] = qcur
                    self.current_remote_cursor = qcur
                except Exception:
                    pass
            elif cid in self.cursor_cache:
                self.current_remote_cursor = self.cursor_cache[cid]

            if self.remote_control_enabled and self.current_remote_cursor:
                self.viewport.setCursor(self.current_remote_cursor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.render_frame()

    def toggle_remote_control(self, checked):
        if not self.allow_remote_control:
            return
        self.remote_control_enabled = checked
        if checked:
            self.rc_btn.setText("🎮 Remote Control: ON")
            self.rc_btn.setStyleSheet("background-color: rgba(16, 185, 129, 0.3); border: 1px solid #10B981; color: #10B981;")
            self.viewport.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.viewport.setFocus()
            if self.current_remote_cursor:
                self.viewport.setCursor(self.current_remote_cursor)
        else:
            self.rc_btn.setText("🎮 Remote Control: OFF")
            self.rc_btn.setStyleSheet("")
            self.viewport.setCursor(Qt.CursorShape.ArrowCursor)
            self.viewport.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def take_screenshot(self):
        if not self.viewport.pixmap():
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Screenshot", f"SharedScreenshot_{self.source_name}.png", "Images (*.png *.jpg)"
        )
        if file_path:
            self.viewport.pixmap().save(file_path)
            QMessageBox.information(self, "Saved", f"Screenshot saved to:\n{file_path}")

    def toggle_fullscreen(self, checked):
        if checked:
            self.normal_geometry = self.geometry()
            self.showFullScreen()
            self.fs_btn.setText("🗗 Exit Fullscreen")
            self.fs_btn.setChecked(True)
        else:
            self.showNormal()
            if self.normal_geometry and not self.normal_geometry.isEmpty():
                self.setGeometry(self.normal_geometry)
            else:
                screen = QApplication.primaryScreen()
                if screen:
                    screen_geo = screen.availableGeometry()
                    w = min(1280, int(screen_geo.width() * 0.85))
                    h = min(720, int(screen_geo.height() * 0.85))
                    x = screen_geo.x() + (screen_geo.width() - w) // 2
                    y = screen_geo.y() + (screen_geo.height() - h) // 2
                    self.setGeometry(x, y, w, h)
                else:
                    self.resize(1280, 720)
            self.fs_btn.setText("🖵 Fullscreen")
            self.fs_btn.setChecked(False)
            QTimer.singleShot(50, self.render_frame)

    def eventFilter(self, obj, event):
        # Handle Escape key to exit fullscreen when remote control is inactive
        if not self.remote_control_enabled and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
                self.toggle_fullscreen(False)
                return True

        if self.remote_control_enabled:
            if obj == self.viewport and event.type() in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
                self._dispatch_mouse_event(event)
                return True
            elif obj == self.viewport and event.type() == QEvent.Type.Wheel:
                self._dispatch_wheel_event(event)
                return True
            elif event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                if not event.isAutoRepeat():
                    self._dispatch_key_event(event)
                return True
        return super().eventFilter(obj, event)

    def _dispatch_wheel_event(self, event):
        pixmap = self.viewport.pixmap()
        if not pixmap:
            return

        vp_rect = self.viewport.rect()
        pm_size = pixmap.size()
        offset_x = (vp_rect.width() - pm_size.width()) / 2
        offset_y = (vp_rect.height() - pm_size.height()) / 2

        pos = event.position()
        rel_x = pos.x() - offset_x
        rel_y = pos.y() - offset_y

        if 0 <= rel_x <= pm_size.width() and 0 <= rel_y <= pm_size.height():
            norm_x = rel_x / pm_size.width()
            norm_y = rel_y / pm_size.height()

            angle_delta = event.angleDelta()
            dx = angle_delta.x() / 120.0
            dy = angle_delta.y() / 120.0
            if dx == 0 and dy == 0:
                pixel_delta = event.pixelDelta()
                dx = pixel_delta.x() / 20.0
                dy = pixel_delta.y() / 20.0

            if dx != 0 or dy != 0:
                self.worker.send_share_input(self.session_id, self.source_id, "mouse_scroll", {
                    "x": norm_x,
                    "y": norm_y,
                    "screen_w": self.last_frame_size[0],
                    "screen_h": self.last_frame_size[1],
                    "dx": dx,
                    "dy": dy
                })

    def _dispatch_mouse_event(self, event):
        pixmap = self.viewport.pixmap()
        if not pixmap:
            return

        vp_rect = self.viewport.rect()
        pm_size = pixmap.size()
        offset_x = (vp_rect.width() - pm_size.width()) / 2
        offset_y = (vp_rect.height() - pm_size.height()) / 2

        pos = event.position()
        rel_x = pos.x() - offset_x
        rel_y = pos.y() - offset_y

        if 0 <= rel_x <= pm_size.width() and 0 <= rel_y <= pm_size.height():
            norm_x = rel_x / pm_size.width()
            norm_y = rel_y / pm_size.height()

            event_name = "mouse_move"
            button_str = "left"
            if event.type() == QEvent.Type.MouseButtonPress or event.type() == QEvent.Type.MouseButtonRelease:
                event_name = "mouse_click"
                if event.button() == Qt.MouseButton.LeftButton:
                    button_str = "left"
                elif event.button() == Qt.MouseButton.RightButton:
                    button_str = "right"
                elif event.button() == Qt.MouseButton.MiddleButton:
                    button_str = "middle"

            self.worker.send_share_input(self.session_id, self.source_id, event_name, {
                "x": norm_x,
                "y": norm_y,
                "screen_w": self.last_frame_size[0],
                "screen_h": self.last_frame_size[1],
                "button": button_str,
                "pressed": (event.type() == QEvent.Type.MouseButtonPress)
            })

    def _dispatch_key_event(self, event):
        qt_key = event.key()
        key_str = ""
        special_keys = {
            Qt.Key.Key_Space: "space",
            Qt.Key.Key_Return: "enter",
            Qt.Key.Key_Enter: "enter",
            Qt.Key.Key_Backspace: "backspace",
            Qt.Key.Key_Tab: "tab",
            Qt.Key.Key_Escape: "esc",
            Qt.Key.Key_Shift: "shift",
            Qt.Key.Key_Control: "ctrl",
            Qt.Key.Key_Alt: "alt",
            Qt.Key.Key_Meta: "cmd",
            Qt.Key.Key_Up: "up",
            Qt.Key.Key_Down: "down",
            Qt.Key.Key_Left: "left",
            Qt.Key.Key_Right: "right",
            Qt.Key.Key_Delete: "delete"
        }
        if qt_key in special_keys:
            key_str = special_keys[qt_key]
        elif 0x20 <= qt_key <= 0x7E:
            key_str = chr(qt_key).lower()
        else:
            key_str = event.text()

        if not key_str:
            return

        event_name = "key_press" if event.type() == QEvent.Type.KeyPress else "key_release"
        self.worker.send_share_input(self.session_id, self.source_id, event_name, {"key": key_str})


class RequestPromptDialog(QDialog):
    """Modern Glassmorphic confirmation dialog when another user requests screen access."""
    accepted_signal = pyqtSignal(str, str, str, str) # req_id, req_id_str, target_id, mode
    declined_signal = pyqtSignal(str, str, str, str)

    def __init__(self, request_id, requester_id, requester_name, target_id, mode="view", parent=None):
        super().__init__(parent)
        self.request_id = request_id
        self.requester_id = requester_id
        self.requester_name = requester_name
        self.target_id = target_id
        self.mode = mode
        self.countdown = 30

        self.setWindowTitle("Overwatch - Screen Access Request")
        self.setFixedSize(460, 270)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.init_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(1000)

    def init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)

        card = QFrame(self)
        card.setStyleSheet("""
            QFrame {
                background-color: rgba(15, 23, 42, 0.96);
                border: 2px solid #00F3FF;
                border-radius: 14px;
            }
            QLabel {
                color: #F8FAFC;
                font-family: 'Segoe UI', 'Inter', sans-serif;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(12)

        # Title row
        title_box = QHBoxLayout()
        icon_str = "🎮" if self.mode == "control" else "👁️"
        action_title = "Remote Control Request" if self.mode == "control" else "Screen View Request"
        title_lbl = QLabel(f"{icon_str} {action_title}", card)
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 800; color: #00F3FF; border: none;")
        title_box.addWidget(title_lbl)
        title_box.addStretch()

        self.time_lbl = QLabel(f"⏱ {self.countdown}s", card)
        self.time_lbl.setStyleSheet("color: #F59E0B; font-weight: bold; font-size: 13px; border: none;")
        title_box.addWidget(self.time_lbl)
        card_layout.addLayout(title_box)

        # Body message
        perm_text = "<b>REMOTELY CONTROL</b> your workstation" if self.mode == "control" else "<b>VIEW</b> your live display"
        body_lbl = QLabel(
            f"<b>{self.requester_name}</b> is requesting permission to {perm_text}.<br><br>"
            "Do you want to grant access?",
            card
        )
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet("color: #E2E8F0; font-size: 13px; line-height: 1.4; border: none;")
        card_layout.addWidget(body_lbl)

        card_layout.addStretch()

        # Action Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(14)

        decline_btn = QPushButton("❌ Decline", card)
        decline_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(239, 68, 68, 0.2);
                border: 1px solid #EF4444;
                border-radius: 8px;
                color: #EF4444;
                font-weight: 700;
                padding: 8px 18px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: rgba(239, 68, 68, 0.45);
                color: #FFFFFF;
            }
        """)
        decline_btn.clicked.connect(self.on_decline)
        btn_box.addWidget(decline_btn)

        accept_btn = QPushButton("✅ Accept & Share", card)
        accept_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(16, 185, 129, 0.25);
                border: 1px solid #10B981;
                border-radius: 8px;
                color: #10B981;
                font-weight: 700;
                padding: 8px 18px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: rgba(16, 185, 129, 0.5);
                color: #FFFFFF;
            }
        """)
        accept_btn.clicked.connect(self.on_accept)
        btn_box.addWidget(accept_btn)

        card_layout.addLayout(btn_box)
        root_layout.addWidget(card)

    def _on_tick(self):
        self.countdown -= 1
        if self.countdown <= 0:
            self.timer.stop()
            self.on_decline()
        else:
            self.time_lbl.setText(f"⏱ {self.countdown}s")

    def on_accept(self):
        self.timer.stop()
        self.accepted_signal.emit(self.request_id, self.requester_id, self.target_id, self.mode)
        self.accept()

    def on_decline(self):
        self.timer.stop()
        self.declined_signal.emit(self.request_id, self.requester_id, self.target_id, self.mode)
        self.reject()


class FlashAlertWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        self.setStyleSheet("background-color: transparent; border: 15px solid rgba(255, 0, 0, 0.8);")
        
        # Flash counter
        self.flash_count = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.toggle_flash)
        self.timer.start(250)

    def toggle_flash(self):
        self.flash_count += 1
        if self.flash_count > 12:  # 12 toggles * 250ms = 3 seconds
            self.timer.stop()
            self.close()
            self.deleteLater()
            return
            
        if self.isVisible():
            self.hide()
        else:
            self.showFullScreen()
            self.raise_()
            self.activateWindow()
            self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)


def create_tray_icon_pixmap(color_hex="#00F3FF"):
    """Generate a clean glass icon for system tray."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color_hex))
    painter.setPen(QColor("#FFFFFF"))
    painter.drawEllipse(4, 4, 24, 24)
    painter.end()
    return pixmap


class EmployeeClientTrayApp(QWidget):
    def __init__(self):
        super().__init__()
        self.settings_file = os.path.join(os.path.expanduser("~"), Config.CLIENT_SETTINGS_FILE)
        self.server_ip = Config.get_local_ip()
        self.server_port = Config.DEFAULT_PORT
        self.client_name = socket.gethostname()
        self.passcode = Config.AUTH_TOKEN

        self.worker = None
        self.worker_thread = None
        self.is_first_launch = False
        self.active_shared_viewers = {}  # session_id -> SharedStreamViewer
        self.connected_users = []
        self.current_prompt_dialog = None

        self.enable_auto_startup()

        self.load_settings()
        self.init_tray()

        # On first launch, require both employee name and server IP
        if not self.has_custom_name:
            self.is_first_launch = True
            self.prompt_employee_name(first_time=True)

        if not self.has_configured_server:
            self.is_first_launch = True
            self.prompt_server_ip(first_time=True)

        self.start_worker()

    def load_settings(self):
        self.has_custom_name = False
        self.has_configured_server = False
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r") as f:
                    data = json.load(f)
                    if data.get("server_ip"):
                        self.server_ip = data.get("server_ip")
                        self.has_configured_server = True
                    if data.get("employee_name"):
                        self.client_name = data.get("employee_name")
                        self.has_custom_name = True
                    if data.get("quality_preset") in Config.QUALITY_PRESETS:
                        Config.DEFAULT_QUALITY_PRESET = data.get("quality_preset")
                    if data.get("target_fps"):
                        Config.DEFAULT_TARGET_FPS = int(data.get("target_fps"))
            except Exception as e:
                print(f"[Settings Error] {e}")

    def save_settings(self):
        try:
            cur_preset = getattr(self.worker.capturer, 'quality_preset', Config.DEFAULT_QUALITY_PRESET) if self.worker else Config.DEFAULT_QUALITY_PRESET
            cur_fps = getattr(self.worker, 'target_fps', Config.DEFAULT_TARGET_FPS) if self.worker else Config.DEFAULT_TARGET_FPS
            with open(self.settings_file, "w") as f:
                json.dump({
                    "server_ip": self.server_ip,
                    "employee_name": self.client_name,
                    "quality_preset": cur_preset,
                    "target_fps": cur_fps
                }, f, indent=2)
        except Exception as e:
            print(f"[Save Settings Error] {e}")

    def init_tray(self):
        self.tray = QSystemTrayIcon(self)
        bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(bundle_dir, "app_icon.ico")
        if os.path.exists(icon_path):
            self.tray.setIcon(QIcon(icon_path))
        else:
            self.tray.setIcon(QIcon(create_tray_icon_pixmap("#00F3FF")))
        self.tray.setToolTip(f"{Config.APP_NAME} - {self.client_name}")

        menu = QMenu()
        
        self.name_action = menu.addAction(f"👤 Employee: {self.client_name}")
        self.name_action.setEnabled(False)

        self.status_action = menu.addAction("Status: Initializing...")
        self.status_action.setEnabled(False)
        
        menu.addSeparator()

        self.users_menu = menu.addMenu("👥 Connected Users (0)")
        self.rebuild_users_menu()

        menu.addSeparator()

        change_name_action = menu.addAction("Set Employee Name...")
        change_name_action.triggered.connect(self.prompt_employee_name)

        change_server_action = menu.addAction("Configure Master Server IP...")
        change_server_action.triggered.connect(self.prompt_server_ip)

        menu.addSeparator()

        quit_action = menu.addAction("Exit Client")
        quit_action.triggered.connect(self.quit_app)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def rebuild_users_menu(self):
        self.users_menu.clear()
        my_id = f"{socket.gethostname()}_{self.local_ip}"

        filtered_peers = []
        seen = set()
        for p in self.connected_users:
            cid = p.get("client_id", "")
            if cid == my_id or p.get("name") == self.client_name:
                continue
            if cid not in seen:
                seen.add(cid)
                filtered_peers.append(p)

        self.users_menu.setTitle(f"👥 Connected Users ({len(filtered_peers)})")

        if not filtered_peers:
            empty_act = self.users_menu.addAction("(No other users connected)")
            empty_act.setEnabled(False)
            return

        for p in filtered_peers:
            p_id = p.get("client_id")
            p_name = p.get("name", "User PC")
            p_ip = p.get("ip", "")
            sub = self.users_menu.addMenu(f"🖥️ {p_name} ({p_ip})")
            
            view_act = sub.addAction("👁️ Request Screen View")
            view_act.triggered.connect(lambda checked, tid=p_id, tname=p_name: self.request_peer_share(tid, tname, "view"))
            
            ctrl_act = sub.addAction("🎮 Request Remote Control")
            ctrl_act.triggered.connect(lambda checked, tid=p_id, tname=p_name: self.request_peer_share(tid, tname, "control"))

    def request_peer_share(self, target_id, target_name, mode):
        if not self.worker or not self.worker.ws:
            QMessageBox.warning(self, "Not Connected", "You are not currently connected to the Master Server.")
            return
        self.worker.send_peer_share_request(target_id, mode)
        perm_title = "Remote Control" if mode == "control" else "Screen View"
        self.tray.showMessage(
            "Request Sent",
            f"Sent {perm_title} request to {target_name}. Waiting for approval...",
            QSystemTrayIcon.MessageIcon.Information,
            4000
        )

    def on_client_list_updated(self, clients):
        self.connected_users = clients
        self.rebuild_users_menu()

    def on_peer_prompt_received(self, req_id, req_id_str, req_name, target_id, mode):
        if self.current_prompt_dialog:
            try:
                self.current_prompt_dialog.close()
                self.current_prompt_dialog.deleteLater()
            except Exception:
                pass

        dlg = RequestPromptDialog(req_id, req_id_str, req_name, target_id, mode, parent=self)
        self.current_prompt_dialog = dlg
        dlg.accepted_signal.connect(lambda r_id, r_id_s, t_id, m: self.worker.send_peer_prompt_response(r_id, r_id_s, t_id, True, m))
        dlg.declined_signal.connect(lambda r_id, r_id_s, t_id, m: self.worker.send_peer_prompt_response(r_id, r_id_s, t_id, False, m))
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def on_peer_request_resolved(self, req_id):
        if self.current_prompt_dialog and self.current_prompt_dialog.request_id == req_id:
            try:
                self.current_prompt_dialog.close()
                self.current_prompt_dialog.deleteLater()
            except Exception:
                pass
            self.current_prompt_dialog = None

    def on_peer_request_declined(self, target_name, reason):
        self.tray.showMessage(
            "Request Declined",
            f"{target_name} declined your screen request ({reason}).",
            QSystemTrayIcon.MessageIcon.Warning,
            5000
        )

    def start_worker(self):
        if self.worker:
            self.worker.stop()

        self.worker = ClientWorker(
            server_ip=self.server_ip,
            server_port=self.server_port,
            client_name=self.client_name,
            passcode=self.passcode
        )
        self.worker.status_changed.connect(self.on_status_changed)
        self.worker.alert_received.connect(self.show_flashing_alert)
        self.worker.quality_updated.connect(lambda p, f: self.save_settings())
        self.worker.share_started.connect(self.on_share_started)
        self.worker.share_frame_received.connect(self.on_share_frame_received)
        self.worker.share_stopped.connect(self.on_share_stopped)
        self.worker.client_list_updated.connect(self.on_client_list_updated)
        self.worker.peer_prompt_received.connect(self.on_peer_prompt_received)
        self.worker.peer_request_declined.connect(self.on_peer_request_declined)
        self.worker.peer_request_resolved.connect(self.on_peer_request_resolved)

        self.worker_thread = threading.Thread(target=self.worker.run, daemon=True)
        self.worker_thread.start()

    def on_share_started(self, session_id, source_id, source_name, allow_remote):
        if session_id in self.active_shared_viewers:
            try:
                viewer = self.active_shared_viewers[session_id]
                viewer.close()
                viewer.deleteLater()
            except Exception:
                pass

        viewer = SharedStreamViewer(session_id, source_id, source_name, allow_remote, self.worker)
        self.active_shared_viewers[session_id] = viewer
        viewer.show()
        viewer.raise_()
        viewer.activateWindow()

    def on_share_frame_received(self, session_id, frame_bytes, metadata):
        if session_id in self.active_shared_viewers:
            self.active_shared_viewers[session_id].update_frame(frame_bytes, metadata)

    def on_share_stopped(self, session_id):
        if session_id in self.active_shared_viewers:
            viewer = self.active_shared_viewers.pop(session_id)
            viewer.close()
            viewer.deleteLater()

    def on_status_changed(self, status_type, message):
        self.status_action.setText(f"Status: {message}")
        if status_type == "connected":
            self.tray.setIcon(QIcon(create_tray_icon_pixmap("#10B981"))) # Green
        elif status_type == "connecting":
            self.tray.setIcon(QIcon(create_tray_icon_pixmap("#F59E0B"))) # Orange
        else:
            self.tray.setIcon(QIcon(create_tray_icon_pixmap("#EF4444"))) # Red

    def show_flashing_alert(self):
        self.flash_window = FlashAlertWindow()
        self.flash_window.showFullScreen()
        self.flash_window.raise_()
        self.flash_window.activateWindow()
        self.flash_window.setWindowState(self.flash_window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)

    def prompt_employee_name(self, first_time=False):
        title = "Setup Employee Name" if first_time else "Change Employee Name"
        name, ok = QInputDialog.getText(
            self, title,
            "Enter Employee Full Name / Computer Label:",
            text=self.client_name
        )
        if ok and name.strip():
            self.client_name = name.strip()
            self.has_custom_name = True
            self.name_action.setText(f"👤 Employee: {self.client_name}")
            self.tray.setToolTip(f"{Config.APP_NAME} - {self.client_name}")
            self.save_settings()
            if not first_time and self.worker:
                self.start_worker()

    def prompt_server_ip(self, first_time=False):
        title = "Setup Master Server IP" if first_time else "Configure Master Server IP"
        msg = ("Enter the Master Dashboard Server IP Address.\n"
               "You can find this on the Manager's sidebar (Server IP).") if first_time else "Enter Master Manager IP Address:"
        ip, ok = QInputDialog.getText(
            self, title,
            msg,
            text=self.server_ip
        )
        if ok and ip.strip():
            self.server_ip = ip.strip()
            self.has_configured_server = True
            self.save_settings()
            if not first_time and self.worker:
                self.start_worker()

    def quit_app(self):
        if self.worker:
            self.worker.stop()
        self.tray.hide()
        QApplication.quit()

    def enable_auto_startup(self):
        try:
            exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(sys.argv[0])
            if sys.platform == "win32" and winreg:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, 
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 
                    0, 
                    winreg.KEY_SET_VALUE
                )
                cmd = f'"{exe_path}"'
                winreg.SetValueEx(key, "Overwatch", 0, winreg.REG_SZ, cmd)
                # Remove old legacy key name if it exists
                try:
                    winreg.DeleteValue(key, "LANScreenMonitor")
                except Exception:
                    pass
                winreg.CloseKey(key)
            elif sys.platform == "darwin":
                # macOS LaunchAgent plist auto startup
                plist_dir = os.path.expanduser("~/Library/LaunchAgents")
                os.makedirs(plist_dir, exist_ok=True)
                plist_path = os.path.join(plist_dir, "com.blackbox.overwatch.plist")
                plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.blackbox.overwatch</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exe_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
"""
                with open(plist_path, "w", encoding="utf-8") as f:
                    f.write(plist_content)
        except Exception as e:
            print(f"[Auto-Startup Error] {e}")


def main():
    if sys.platform == "win32":
        import ctypes
        myappid = "blackbox.overwatch.lanmonitor.4_50_1"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    app = QApplication(sys.argv)
    
    bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    icon_path = os.path.join(bundle_dir, "app_icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    app.setQuitOnLastWindowClosed(False)
    client_app = EmployeeClientTrayApp()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

