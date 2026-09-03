import sys
import os
import time
import json
import base64
import asyncio
import socket
import threading
import traceback
import subprocess
import numpy as np
import cv2
import websockets
import websockets.exceptions

if sys.platform == "win32":
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
    def capture_active_cursor(cursor_size=32):
        return None, 0, 0, None

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QGridLayout, QLabel, QPushButton,
                             QScrollArea, QFrame, QDialog, QSlider, QComboBox,
                             QGraphicsDropShadowEffect, QSpinBox, QFormLayout,
                             QFileDialog, QMessageBox, QLineEdit, QStackedWidget,
                             QSizePolicy, QCheckBox)
from PyQt6.QtGui import QPixmap, QImage, QColor, QIcon, QPainter, QCursor, QDrag
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QEvent, QMimeData, QTimer
import mss

from config import Config
from protocol import Protocol, PacketType

# Optional pynput for admin remote input execution
try:
    from pynput.mouse import Button, Controller as MouseController
    from pynput.keyboard import Key, Controller as KeyboardController
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False


def get_server_settings_path():
    return os.path.join(os.path.expanduser("~"), Config.SERVER_SETTINGS_FILE)

def load_server_settings():
    path = get_server_settings_path()
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
                if data.get("admin_password"):
                    Config.MASTER_ADMIN_PASSWORD = data.get("admin_password")
                if data.get("quality_preset") in Config.QUALITY_PRESETS:
                    Config.DEFAULT_QUALITY_PRESET = data.get("quality_preset")
                if data.get("target_fps"):
                    Config.DEFAULT_TARGET_FPS = int(data.get("target_fps"))
                if data.get("server_port"):
                    Config.DEFAULT_PORT = int(data.get("server_port"))
        except Exception as e:
            print(f"[Settings Error] {e}")

def save_server_settings():
    path = get_server_settings_path()
    try:
        with open(path, "w") as f:
            json.dump({
                "admin_password": Config.MASTER_ADMIN_PASSWORD,
                "quality_preset": Config.DEFAULT_QUALITY_PRESET,
                "target_fps": Config.DEFAULT_TARGET_FPS,
                "server_port": Config.DEFAULT_PORT
            }, f, indent=2)
    except Exception as e:
        print(f"[Save Settings Error] {e}")


class RemoteInputHandler:
    """Executes remote mouse and keyboard events on Admin PC when Admin screen is shared."""
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
            print(f"[Admin InputHandler Error] {e}")

    def _parse_key(self, key_str):
        if len(key_str) == 1:
            return key_str
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


class AdminScreenCapturer(threading.Thread):
    """Captures and compresses the Admin/Master PC screen when Admin sharing is active."""
    def __init__(self, server_thread):
        super().__init__(daemon=True)
        self.server_thread = server_thread
        self.running = True
        self.sct = mss.mss()
        self.monitor = self.sct.monitors[1]
        self.last_cursor_id = None

    def stop(self):
        self.running = False

    def run(self):
        fps_counter = 0
        last_time = time.time()
        current_fps = 10.0

        while self.running:
            start_t = time.time()
            if not self.server_thread.has_active_admin_share():
                time.sleep(0.2)
                continue

            try:
                sct_img = self.sct.grab(self.monitor)
                frame_bgra = np.array(sct_img)
                frame_bgr = cv2.cvtColor(frame_bgra, cv2.COLOR_BGRA2BGR)
                h, w = frame_bgr.shape[:2]

                quality_preset = Config.DEFAULT_QUALITY_PRESET
                jpeg_quality = Config.QUALITY_PRESETS[quality_preset]["jpeg_quality"]
                scale = Config.QUALITY_PRESETS[quality_preset]["scale"]

                if scale != 1.0:
                    tw, th = int(w * scale), int(h * scale)
                    frame_to_encode = cv2.resize(frame_bgr, (tw, th), interpolation=cv2.INTER_AREA)
                else:
                    frame_to_encode = frame_bgr

                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]
                success, encoded_img = cv2.imencode('.jpg', frame_to_encode, encode_param)
                if success:
                    frame_bytes = encoded_img.tobytes()
                    cursor_data = None
                    cid, hx, hy, b64_png = capture_active_cursor()
                    if cid:
                        if cid != self.last_cursor_id:
                            self.last_cursor_id = cid
                            cursor_data = {"id": cid, "hx": hx, "hy": hy, "png": b64_png}
                        else:
                            cursor_data = {"id": cid, "hx": hx, "hy": hy}
                    self.server_thread.broadcast_admin_frame(frame_bytes, current_fps, w, h, cursor_data=cursor_data)

                fps_counter += 1
                now = time.time()
                if now - last_time >= 1.0:
                    current_fps = fps_counter / (now - last_time)
                    fps_counter = 0
                    last_time = now

                target_fps = Config.DEFAULT_TARGET_FPS
                delay = max(0.001, (1.0 / target_fps) - (time.time() - start_t))
                time.sleep(delay)
            except Exception:
                time.sleep(0.1)


# --- WEBSOCKET SERVER THREAD ---

class MasterWebSocketServer(QThread):
    client_connected = pyqtSignal(str, dict)       # client_id, client_info
    client_disconnected = pyqtSignal(str)          # client_id
    frame_received = pyqtSignal(str, bytes, dict)  # client_id, image_bytes, metadata
    log_emitted = pyqtSignal(str)
    share_state_changed = pyqtSignal()
    peer_requests_updated = pyqtSignal()

    def __init__(self, host=Config.DEFAULT_HOST, port=Config.DEFAULT_PORT):
        super().__init__()
        self.host = host
        self.port = port
        self.running = True
        self.active_clients = {} # client_id -> websocket
        self.client_info = {}    # client_id -> {"name": str, "hostname": str, "ip": str}
        self.share_sessions = {} # session_id -> { "source_id": str, "source_name": str, "targets": set([client_id, ...]), "allow_remote": bool }
        self.pending_peer_requests = {} # req_id -> dict
        self.admin_input_handler = RemoteInputHandler()
        self.loop = None

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._start_server())

    async def _start_server(self):
        self.log_emitted.emit(f"Starting WebSocket server on {self.host}:{self.port}...")
        async with websockets.serve(self._handle_client, self.host, self.port, max_size=10_000_000):
            self.log_emitted.emit(f"Master Dashboard Server listening at ws://{Config.get_local_ip()}:{self.port}")
            while self.running:
                await asyncio.sleep(1)

    async def _handle_client(self, websocket):
        client_id = None
        try:
            # 1. Read Auth Handshake
            raw_msg = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            pkt = Protocol.parse(raw_msg)
            if not pkt or pkt.get("type") != PacketType.AUTH_REQ:
                await websocket.send(Protocol.create_auth_response(False, "Invalid initial packet"))
                await websocket.close()
                return

            passcode = pkt.get("passcode")
            if passcode != Config.AUTH_TOKEN:
                await websocket.send(Protocol.create_auth_response(False, "Unauthorized Passcode"))
                await websocket.close()
                return

            client_name = pkt.get("client_name", "Unknown PC")
            hostname = pkt.get("hostname", "Host")
            ip_address = pkt.get("ip_address", "0.0.0.0")
            client_id = f"{hostname}_{ip_address}"

            # Accept auth
            await websocket.send(Protocol.create_auth_response(True, "Authenticated Successfully"))

            # Send current server quality and fps settings so client immediately syncs with master's configured bandwidth settings
            quality_pkt = Protocol.create_quality_update(preset_name=Config.DEFAULT_QUALITY_PRESET, target_fps=Config.DEFAULT_TARGET_FPS)
            await websocket.send(quality_pkt)

            self.active_clients[client_id] = websocket
            self.client_info[client_id] = {
                "name": client_name,
                "hostname": hostname,
                "ip": ip_address
            }
            self.client_connected.emit(client_id, self.client_info[client_id])
            self.log_emitted.emit(f"Client connected: {client_id} ({ip_address})")

            # Broadcast updated client list to all peers
            self.broadcast_client_list()

            # 2. Main Receive Loop
            async for message in websocket:
                data = Protocol.parse(message)
                if not data:
                    continue

                pkt_type = data.get("type")
                if pkt_type == PacketType.FRAME_DATA:
                    b64_frame = data.get("frame")
                    if b64_frame:
                        frame_bytes = base64.b64decode(b64_frame)
                        cursor_data = data.get("cursor")
                        metadata = {
                            "fps": data.get("fps", 0),
                            "width": data.get("width", 1920),
                            "height": data.get("height", 1080),
                            "is_static": data.get("is_static", False),
                            "cursor": cursor_data,
                            "timestamp": data.get("timestamp", time.time())
                        }
                        self.frame_received.emit(client_id, frame_bytes, metadata)

                        # Relay frame if this client is being shared
                        for sess_id, sess_data in list(self.share_sessions.items()):
                            if sess_data.get("source_id") == client_id:
                                share_pkt = Protocol.create_share_frame(
                                    session_id=sess_id,
                                    source_id=client_id,
                                    frame_bytes=frame_bytes,
                                    fps=metadata.get("fps", 0),
                                    width=metadata.get("width", 1920),
                                    height=metadata.get("height", 1080),
                                    is_static=metadata.get("is_static", False),
                                    cursor_data=cursor_data
                                )
                                for tid in list(sess_data.get("targets", [])):
                                    self.send_to_client(tid, share_pkt)

                elif pkt_type == PacketType.PEER_SHARE_REQ:
                    req_id = f"req_{int(time.time()*1000)}"
                    req_src = data.get("requester_id", client_id)
                    req_name = data.get("requester_name", self.client_info.get(client_id, {}).get("name", "User"))
                    target_id = data.get("target_id")
                    action_type = data.get("action_type", data.get("mode", "access_screen"))
                    target_name = self.client_info.get(target_id, {}).get("name", target_id)

                    if target_id and target_id in self.active_clients:
                        self.pending_peer_requests[req_id] = {
                            "request_id": req_id,
                            "requester_id": req_src,
                            "requester_name": req_name,
                            "target_id": target_id,
                            "target_name": target_name,
                            "action_type": action_type,
                            "mode": action_type,
                            "timestamp": time.time()
                        }
                        self.peer_requests_updated.emit()
                        prompt_pkt = Protocol.create_peer_prompt_request(
                            request_id=req_id,
                            requester_id=req_src,
                            requester_name=req_name,
                            target_id=target_id,
                            target_name=target_name,
                            action_type=action_type
                        )
                        self.send_to_client(target_id, prompt_pkt)

                elif pkt_type == PacketType.PEER_PROMPT_RESP:
                    req_id = data.get("request_id")
                    req_src = data.get("requester_id")
                    target_id = data.get("target_id", client_id)
                    accepted = data.get("accepted", False)
                    action_type = data.get("action_type", data.get("mode", "access_screen"))
                    target_name = self.client_info.get(target_id, {}).get("name", "Target PC")
                    req_name = self.client_info.get(req_src, {}).get("name", "Requester PC")

                    if req_id in self.pending_peer_requests:
                        del self.pending_peer_requests[req_id]
                        self.peer_requests_updated.emit()

                    if accepted:
                        if action_type == "share_my_screen":
                            self.start_share_session(
                                source_id=req_src,
                                source_name=f"{req_name}'s Screen",
                                target_ids=[target_id],
                                allow_remote=True
                            )
                        else:
                            self.start_share_session(
                                source_id=target_id,
                                source_name=target_name,
                                target_ids=[req_src],
                                allow_remote=True
                            )
                    else:
                        dec_pkt = Protocol.create_peer_request_declined(target_name, "User declined the request.")
                        self.send_to_client(req_src, dec_pkt)

                elif pkt_type == PacketType.SHARE_STREAM_INPUT:
                    sess_id = data.get("session_id")
                    source_id = data.get("source_id")
                    event_type = data.get("event_type")
                    params = data.get("params", {})

                    sess_data = self.share_sessions.get(sess_id)
                    if sess_data and sess_data.get("allow_remote"):
                        if source_id == "ADMIN_PC":
                            self.admin_input_handler.handle_event(event_type, params)
                        else:
                            input_pkt = Protocol.create_remote_input_packet(event_type, params)
                            self.send_to_client(source_id, input_pkt)

        except (websockets.exceptions.ConnectionClosed, asyncio.TimeoutError):
            pass
        except Exception as e:
            self.log_emitted.emit(f"Client connection error ({client_id}): {e}")
        finally:
            if client_id and client_id in self.active_clients:
                del self.active_clients[client_id]
            if client_id and client_id in self.client_info:
                del self.client_info[client_id]

            # Clear pending requests related to this client
            for r_id, r in list(self.pending_peer_requests.items()):
                if r.get("requester_id") == client_id or r.get("target_id") == client_id:
                    del self.pending_peer_requests[r_id]

            self.peer_requests_updated.emit()
            if client_id:
                self.stop_all_shares_for_client(client_id)
                self.client_disconnected.emit(client_id)
                self.log_emitted.emit(f"Client disconnected: {client_id}")
            self.broadcast_client_list()

    def broadcast_client_list(self):
        """Dispatch list of all active online clients to all connected peers."""
        c_list = []
        for cid, info in self.client_info.items():
            if cid in self.active_clients:
                c_list.append({
                    "client_id": cid,
                    "name": info.get("name", "Employee PC"),
                    "hostname": info.get("hostname", "Host"),
                    "ip": info.get("ip", "0.0.0.0")
                })
        pkt = Protocol.create_client_list_update(c_list)
        self.broadcast(pkt)

    def send_to_client(self, client_id, packet_str):
        """Thread-safe call to dispatch message to client."""
        if self.loop and client_id in self.active_clients:
            ws = self.active_clients[client_id]
            asyncio.run_coroutine_threadsafe(ws.send(packet_str), self.loop)

    def broadcast(self, packet_str):
        if self.loop:
            for ws in list(self.active_clients.values()):
                asyncio.run_coroutine_threadsafe(ws.send(packet_str), self.loop)

    def start_share_session(self, source_id, source_name, target_ids, allow_remote=True):
        session_id = f"share_{source_id}_{int(time.time()*1000)}"
        self.share_sessions[session_id] = {
            "source_id": source_id,
            "source_name": source_name,
            "targets": set(target_ids),
            "allow_remote": allow_remote
        }
        start_pkt = Protocol.create_share_start(session_id, source_id, source_name, allow_remote)
        for tid in target_ids:
            self.send_to_client(tid, start_pkt)
        self.share_state_changed.emit()
        return session_id

    def stop_share_session(self, session_id):
        if session_id in self.share_sessions:
            sess_data = self.share_sessions.pop(session_id)
            stop_pkt = Protocol.create_share_stop(session_id, sess_data.get("source_id"))
            for tid in sess_data.get("targets", []):
                self.send_to_client(tid, stop_pkt)
            self.share_state_changed.emit()

    def stop_all_shares_for_source(self, source_id):
        for sess_id, sess in list(self.share_sessions.items()):
            if sess.get("source_id") == source_id:
                self.stop_share_session(sess_id)

    def stop_all_shares_for_client(self, client_id):
        # Stop shares where this client is the source or one of the targets
        for sess_id, sess in list(self.share_sessions.items()):
            if sess.get("source_id") == client_id:
                self.stop_share_session(sess_id)
            elif client_id in sess.get("targets", set()):
                sess.get("targets", set()).discard(client_id)
                if not sess.get("targets"):
                    self.stop_share_session(sess_id)
                else:
                    self.share_state_changed.emit()

    def get_active_share_for_source(self, source_id):
        for sess_id, sess in self.share_sessions.items():
            if sess.get("source_id") == source_id:
                return sess_id, sess
        return None, None

    def has_active_admin_share(self):
        return any(s.get("source_id") == "ADMIN_PC" for s in self.share_sessions.values())

    def broadcast_admin_frame(self, frame_bytes, fps, width, height, cursor_data=None):
        for sess_id, sess in list(self.share_sessions.items()):
            if sess.get("source_id") == "ADMIN_PC":
                pkt = Protocol.create_share_frame(sess_id, "ADMIN_PC", frame_bytes, fps, width, height, cursor_data=cursor_data)
                for tid in list(sess.get("targets", [])):
                    self.send_to_client(tid, pkt)

    def admin_approve_peer_request(self, req_id):
        if req_id in self.pending_peer_requests:
            req = self.pending_peer_requests.pop(req_id)
            self.peer_requests_updated.emit()
            target_id = req.get("target_id")
            requester_id = req.get("requester_id")
            target_name = req.get("target_name")
            requester_name = req.get("requester_name", "Requester PC")
            action_type = req.get("action_type", req.get("mode", "access_screen"))

            # Close popup on target client
            resolved_pkt = Protocol.create_peer_request_resolved(req_id)
            self.send_to_client(target_id, resolved_pkt)

            # Start share session based on action_type
            if action_type == "share_my_screen":
                self.start_share_session(
                    source_id=requester_id,
                    source_name=f"{requester_name}'s Screen",
                    target_ids=[target_id],
                    allow_remote=True
                )
            else:
                self.start_share_session(
                    source_id=target_id,
                    source_name=target_name,
                    target_ids=[requester_id],
                    allow_remote=True
                )

    def admin_reject_peer_request(self, req_id):
        if req_id in self.pending_peer_requests:
            req = self.pending_peer_requests.pop(req_id)
            self.peer_requests_updated.emit()
            target_id = req.get("target_id")
            requester_id = req.get("requester_id")
            target_name = req.get("target_name")

            # Close popup on target client
            resolved_pkt = Protocol.create_peer_request_resolved(req_id)
            self.send_to_client(target_id, resolved_pkt)

            # Send decline to requester
            dec_pkt = Protocol.create_peer_request_declined(target_name, "Admin declined the request.")
            self.send_to_client(requester_id, dec_pkt)

    def stop(self):
        self.running = False


# --- STREAM CARD WIDGET ---

class StreamCard(QFrame):
    expand_requested = pyqtSignal(str)        # client_id
    share_requested = pyqtSignal(str)         # client_id
    remote_control_toggled = pyqtSignal(str)  # client_id
    swap_requested = pyqtSignal(str, str)     # source_id, target_id

    def __init__(self, client_id, info, parent=None):
        super().__init__(parent)
        self.client_id = client_id
        self.info = info
        self.last_frame_bytes = None
        self.last_metadata = {}
        self.status = "active"
        self.is_sharing = False

        self.setObjectName("StreamCard")
        self.setMinimumSize(320, 240)

        # Soft Glow Drop Shadow Effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 140))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
        
        self.setAcceptDrops(True)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Header Bar
        header = QFrame(self)
        header.setObjectName("CardHeader")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 8, 12, 8)

        # Status Neon Dot
        self.status_dot = QWidget(self)
        self.status_dot.setObjectName("StatusDot")
        self.status_dot.setProperty("status", "active")
        h_layout.addWidget(self.status_dot)

        # Name & Host info
        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(1)
        self.name_label = QLineEdit(self.info.get("name", "Employee PC"), self)
        self.name_label.setObjectName("ClientNameLabel")
        self.name_label.setStyleSheet("background: transparent; border: none; color: #F8FAFC; font-weight: bold;")
        self.ip_label = QLabel(f"{self.info.get('hostname')} • {self.info.get('ip')}", self)
        self.ip_label.setObjectName("ClientIPLabel")
        title_vbox.addWidget(self.name_label)
        title_vbox.addWidget(self.ip_label)

        h_layout.addLayout(title_vbox)
        h_layout.addStretch()

        # Share Action Button
        self.share_btn = QPushButton("↗ Share", self)
        self.share_btn.setObjectName("ShareButton")
        self.share_btn.setProperty("class", "GlassButton")
        self.share_btn.setStyleSheet("background-color: rgba(0, 243, 255, 0.15); border: 1px solid rgba(0, 243, 255, 0.4); color: #00F3FF; font-weight: 600; padding: 4px 8px; border-radius: 6px;")
        self.share_btn.clicked.connect(lambda: self.share_requested.emit(self.client_id))
        h_layout.addWidget(self.share_btn)

        # Expand Action Button
        self.expand_btn = QPushButton("Expand", self)
        self.expand_btn.setObjectName("ExpandButton")
        self.expand_btn.setProperty("class", "GlassButton")
        self.expand_btn.clicked.connect(lambda: self.expand_requested.emit(self.client_id))
        h_layout.addWidget(self.expand_btn)

        layout.addWidget(header)

        # 2. Live Video Viewport Container
        self.viewport = QLabel(self)
        self.viewport.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewport.setStyleSheet("background-color: rgba(15, 23, 42, 0.5); border-bottom-left-radius: 15px; border-bottom-right-radius: 15px;")
        self.viewport.setText("Awaiting stream feed...")
        layout.addWidget(self.viewport, stretch=1)

        # Overlay Stats Badge (FPS & Latency)
        self.stats_badge = QLabel("0 FPS | static", self.viewport)
        self.stats_badge.setObjectName("StatsOverlay")
        self.stats_badge.move(12, 12)
        self.stats_badge.show()

    def set_share_active(self, active):
        self.is_sharing = active
        if active:
            self.share_btn.setText("↗ Sharing")
            self.share_btn.setStyleSheet("background-color: rgba(16, 185, 129, 0.3); border: 1px solid #10B981; color: #10B981; font-weight: 700; padding: 4px 8px; border-radius: 6px;")
        else:
            self.share_btn.setText("↗ Share")
            self.share_btn.setStyleSheet("background-color: rgba(0, 243, 255, 0.15); border: 1px solid rgba(0, 243, 255, 0.4); color: #00F3FF; font-weight: 600; padding: 4px 8px; border-radius: 6px;")

    def update_frame(self, image_bytes, metadata):
        self.last_frame_bytes = image_bytes
        self.last_metadata = metadata

        w = metadata.get("width", 1920)
        h = metadata.get("height", 1080)
        if h > w:
            self.setMinimumSize(240, 360)
        else:
            self.setMinimumSize(320, 240)

        # Convert JPEG bytes to QPixmap
        image = QImage()
        if image.loadFromData(image_bytes):
            pixmap = QPixmap.fromImage(image)
            scaled = pixmap.scaled(
                self.viewport.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.viewport.setPixmap(scaled)

        fps = metadata.get("fps", 0)
        is_static = metadata.get("is_static", False)
        status_text = "Idle" if is_static else "Active"
        
        self.stats_badge.setText(f"{fps:.1f} FPS | {status_text}")
        self.stats_badge.adjustSize()

        # Update status dot styling
        new_status = "idle" if is_static else "active"
        if self.status != new_status:
            self.status = new_status
            self.status_dot.setProperty("status", new_status)
            self.status_dot.style().unpolish(self.status_dot)
            self.status_dot.style().polish(self.status_dot)

    def set_offline(self):
        self.status = "offline"
        self.status_dot.setProperty("status", "offline")
        self.status_dot.style().unpolish(self.status_dot)
        self.status_dot.style().polish(self.status_dot)
        self.viewport.setText("CLIENT OFFLINE")
        self.stats_badge.setText("0 FPS | Offline")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.last_frame_bytes:
            self.update_frame(self.last_frame_bytes, self.last_metadata)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_position = event.position()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not hasattr(self, 'drag_start_position'):
            return
        distance = (event.position() - self.drag_start_position).manhattanLength()
        if distance < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(self.client_id)
        drag.setMimeData(mime_data)
        
        pixmap = self.grab()
        drag.setPixmap(pixmap.scaled(pixmap.width() // 2, pixmap.height() // 2, Qt.AspectRatioMode.KeepAspectRatio))
        drag.setHotSpot(event.position().toPoint() // 2)
        
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text() != self.client_id:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text() != self.client_id:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        source_id = event.mimeData().text()
        if source_id != self.client_id:
            self.swap_requested.emit(source_id, self.client_id)
            event.acceptProposedAction()


# --- SINGLE VIEW FULLSCREEN MODAL WITH REMOTE CONTROL ---

class SingleStreamModal(QDialog):
    def __init__(self, client_id, info, server_thread, parent=None):
        super().__init__(parent)
        self.client_id = client_id
        self.info = info
        self.server_thread = server_thread
        self.remote_control_enabled = False
        self.last_frame_size = (1920, 1080)
        self.last_frame_bytes = None
        self.last_metadata = {}
        self.normal_geometry = None
        self.cursor_cache = {}
        self.current_remote_cursor = None

        self.setWindowTitle(f"Live Stream - {self.info.get('name')} ({self.info.get('ip')})")
        
        # Calculate clean default scale (1280x720 or 85% of available screen)
        screen = QApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            def_w = min(1280, int(screen_geo.width() * 0.85))
            def_h = min(720, int(screen_geo.height() * 0.85))
            self.resize(def_w, def_h)
        else:
            self.resize(1280, 720)

        self.setStyleSheet("background-color: #0F172A;")

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

        # Main Stream Viewport
        self.viewport = QLabel(self)
        self.viewport.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewport.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.viewport.setMinimumSize(320, 180)
        self.viewport.setText("Loading high-res stream...")
        self.viewport.setMouseTracking(True)
        self.viewport.installEventFilter(self)
        main_layout.addWidget(self.viewport, stretch=1)

        # Floating Glass Action Bar
        self.action_bar = QFrame(self)
        self.action_bar.setObjectName("FloatingActionBar")
        bar_layout = QHBoxLayout(self.action_bar)
        bar_layout.setContentsMargins(16, 6, 16, 6)
        bar_layout.setSpacing(14)

        # Client info label
        self.title_lbl = QLabel(f"🖥️ {self.info.get('name')} ({self.info.get('ip')})", self)
        self.title_lbl.setStyleSheet("font-weight: 700; color: #FFFFFF; font-size: 14px;")
        bar_layout.addWidget(self.title_lbl)

        # Stats readout
        self.stats_lbl = QLabel("0 FPS | Latency: 12ms", self)
        self.stats_lbl.setStyleSheet("color: #00F3FF; font-weight: 600;")
        bar_layout.addWidget(self.stats_lbl)

        bar_layout.addStretch()

        # Quality quick toggle
        bar_layout.addWidget(QLabel("Quality:", self))
        self.combo_quality = QComboBox(self)
        self.combo_quality.addItems(["Low", "Medium", "High"])
        self.combo_quality.setCurrentText(Config.DEFAULT_QUALITY_PRESET)
        self.combo_quality.currentTextChanged.connect(self.on_quality_changed)
        bar_layout.addWidget(self.combo_quality)

        # Remote Control Toggle Button
        self.rc_btn = QPushButton("🎮 Remote Control: OFF", self)
        self.rc_btn.setProperty("class", "GlassButton")
        self.rc_btn.setCheckable(True)
        self.rc_btn.clicked.connect(self.toggle_remote_control)
        bar_layout.addWidget(self.rc_btn)

        # Share Screen Button
        self.share_btn = QPushButton("↗ Share Screen", self)
        self.share_btn.setProperty("class", "GlassButton")
        self.share_btn.setStyleSheet("background-color: rgba(0, 243, 255, 0.2); border: 1px solid #00F3FF; color: #00F3FF; font-weight: 600;")
        self.share_btn.clicked.connect(self.open_share_dialog)
        bar_layout.addWidget(self.share_btn)

        # Ping Alert Button
        self.alert_btn = QPushButton("🚨 Ping Alert", self)
        self.alert_btn.setProperty("class", "GlassButton")
        self.alert_btn.clicked.connect(self.ping_alert)
        bar_layout.addWidget(self.alert_btn)

        # Screenshot Button
        self.shot_btn = QPushButton("📸 Screenshot", self)
        self.shot_btn.setProperty("class", "GlassButton")
        self.shot_btn.clicked.connect(self.take_screenshot)
        bar_layout.addWidget(self.shot_btn)

        # Fullscreen Toggle Button
        self.fs_btn = QPushButton("🖵 Fullscreen", self)
        self.fs_btn.setProperty("class", "GlassButton")
        self.fs_btn.setCheckable(True)
        self.fs_btn.clicked.connect(self.toggle_fullscreen)
        bar_layout.addWidget(self.fs_btn)

        # Close Modal Button
        self.close_btn = QPushButton("❌ Close", self)
        self.close_btn.setProperty("class", "GlassButtonPrimary")
        self.close_btn.clicked.connect(self.close)
        bar_layout.addWidget(self.close_btn)

        # Position Floating Bar over bottom of viewport
        main_layout.addWidget(self.action_bar, alignment=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)

    def open_share_dialog(self):
        if self.parent() and hasattr(self.parent(), 'open_share_client_dialog'):
            self.parent().open_share_client_dialog(self.client_id)

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

        # Update remote cursor for Photoshop / design tools
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

    def on_quality_changed(self, preset):
        fps = 60 if preset == "High" else (30 if preset == "Medium" else 15)
        pkt = Protocol.create_quality_update(preset_name=preset, target_fps=fps)
        self.server_thread.send_to_client(self.client_id, pkt)

    def toggle_remote_control(self, checked):
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

    def ping_alert(self):
        pkt = Protocol.create_alert_packet()
        self.server_thread.send_to_client(self.client_id, pkt)
        QMessageBox.information(self, "Ping Alert", f"Alert sent to {self.info.get('name')}.")

    def take_screenshot(self):
        if not self.viewport.pixmap():
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Screenshot", f"Screenshot_{self.client_id}.png", "Images (*.png *.jpg)"
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
                pkt = Protocol.create_remote_input_packet("mouse_scroll", {
                    "x": norm_x,
                    "y": norm_y,
                    "screen_w": self.last_frame_size[0],
                    "screen_h": self.last_frame_size[1],
                    "dx": dx,
                    "dy": dy
                })
                self.server_thread.send_to_client(self.client_id, pkt)

    def _dispatch_mouse_event(self, event):
        pixmap = self.viewport.pixmap()
        if not pixmap:
            return

        vp_rect = self.viewport.rect()
        pm_size = pixmap.size()
        
        # Calculate image offsets inside QLabel
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

            pkt = Protocol.create_remote_input_packet(event_name, {
                "x": norm_x,
                "y": norm_y,
                "screen_w": self.last_frame_size[0],
                "screen_h": self.last_frame_size[1],
                "button": button_str,
                "pressed": (event.type() == QEvent.Type.MouseButtonPress)
            })
            self.server_thread.send_to_client(self.client_id, pkt)

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
        pkt = Protocol.create_remote_input_packet(event_name, {"key": key_str})
        self.server_thread.send_to_client(self.client_id, pkt)


# --- SHARE SCREEN DIALOG ---

class ShareScreenDialog(QDialog):
    def __init__(self, source_id, source_name, server_thread, cards, parent=None):
        super().__init__(parent)
        self.source_id = source_id
        self.source_name = source_name
        self.server_thread = server_thread
        self.cards = cards # client_id -> StreamCard

        self.setWindowTitle(f"Share Screen - {self.source_name}")
        self.setFixedSize(500, 520)
        self.setStyleSheet("background-color: #0F172A; color: #F8FAFC;")

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        title = QLabel("↗ Project & Share Screen", self)
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #00F3FF;")
        layout.addWidget(title)

        desc = QLabel(f"Project <b>{self.source_name}</b> live directly to other employee PC screens as a pop-up window.", self)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #94A3B8; font-size: 13px;")
        layout.addWidget(desc)

        # Check existing active share for this source
        active_sess_id, active_sess = self.server_thread.get_active_share_for_source(self.source_id)

        # Targets Box
        targets_label = QLabel("Select Target Employee PCs:", self)
        targets_label.setStyleSheet("font-weight: 600; color: #F8FAFC; margin-top: 4px;")
        layout.addWidget(targets_label)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background-color: #1E293B; border: 1px solid #334155; border-radius: 8px; }")
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(12, 12, 12, 12)
        scroll_layout.setSpacing(8)

        self.target_checkboxes = {} # client_id -> QCheckBox
        available_clients = [c for c in self.cards.values() if c.client_id != self.source_id and c.status != "offline"]

        if available_clients:
            # Select All checkbox
            self.select_all_cb = QCheckBox("Select All Connected PCs", scroll_content)
            self.select_all_cb.setStyleSheet("color: #00F3FF; font-weight: bold; margin-bottom: 6px;")
            def on_select_all(state):
                checked = (state == Qt.CheckState.Checked.value or state == 2)
                for cb in self.target_checkboxes.values():
                    cb.setChecked(checked)
            self.select_all_cb.stateChanged.connect(on_select_all)
            scroll_layout.addWidget(self.select_all_cb)

            active_targets = active_sess.get("targets", set()) if active_sess else set()

            for card in available_clients:
                cid = card.client_id
                cname = card.info.get('name', 'Employee PC')
                cip = card.info.get('ip', '')
                cb = QCheckBox(f"🖥️ {cname} ({cip})", scroll_content)
                cb.setStyleSheet("color: #F8FAFC; font-size: 13px; padding: 2px;")
                if cid in active_targets:
                    cb.setChecked(True)
                self.target_checkboxes[cid] = cb
                scroll_layout.addWidget(cb)
        else:
            empty_lbl = QLabel("No other active employee PCs connected.\nConnect employee PCs to project this screen.", scroll_content)
            empty_lbl.setStyleSheet("color: #64748B; font-style: italic; padding: 16px;")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            scroll_layout.addWidget(empty_lbl)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, stretch=1)

        # Allow Remote Control toggle
        self.control_cb = QCheckBox("🎮 Allow Target PCs to Remote Control this Screen", self)
        self.control_cb.setStyleSheet("color: #10B981; font-weight: 600; font-size: 13px;")
        if active_sess:
            self.control_cb.setChecked(active_sess.get("allow_remote", True))
        else:
            self.control_cb.setChecked(True)
        layout.addWidget(self.control_cb)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        if active_sess_id:
            status_lbl = QLabel(f"● Sharing active ({len(active_sess.get('targets', []))} targets)", self)
            status_lbl.setStyleSheet("color: #10B981; font-weight: bold;")
            layout.addWidget(status_lbl)

            stop_btn = QPushButton("⏹ Stop Sharing", self)
            stop_btn.setStyleSheet("background-color: rgba(239, 68, 68, 0.25); border: 1px solid #EF4444; border-radius: 8px; color: #EF4444; padding: 10px; font-weight: 700;")
            def on_stop():
                self.server_thread.stop_share_session(active_sess_id)
                QMessageBox.information(self, "Stopped", f"Stopped sharing {self.source_name}.")
                self.accept()
            stop_btn.clicked.connect(on_stop)
            btn_layout.addWidget(stop_btn)

        apply_btn = QPushButton("Update / Start Sharing" if active_sess_id else "Start Sharing Screen", self)
        apply_btn.setStyleSheet("background-color: rgba(0, 243, 255, 0.25); border: 1px solid #00F3FF; border-radius: 8px; color: #00F3FF; padding: 10px; font-weight: 700;")
        
        def on_start():
            selected = [cid for cid, cb in self.target_checkboxes.items() if cb.isChecked()]
            if not selected:
                QMessageBox.warning(self, "No Target Selected", "Please select at least one employee PC to share screen with.")
                return

            if active_sess_id:
                self.server_thread.stop_share_session(active_sess_id)

            allow_control = self.control_cb.isChecked()
            self.server_thread.start_share_session(self.source_id, self.source_name, selected, allow_remote=allow_control)
            QMessageBox.information(self, "Sharing Started", f"Now projecting {self.source_name} to {len(selected)} client PC(s).")
            self.accept()

        apply_btn.clicked.connect(on_start)
        btn_layout.addWidget(apply_btn)

        layout.addLayout(btn_layout)


# --- SETTINGS DIALOG ---

class SettingsDialog(QDialog):
    def __init__(self, current_port, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Application Configuration")
        self.setFixedSize(400, 300)
        self.setStyleSheet("background-color: #0F172A; color: #F8FAFC;")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.port_spin = QSpinBox(self)
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(current_port)
        form.addRow("Server Port:", self.port_spin)

        self.preset_combo = QComboBox(self)
        self.preset_combo.addItems(["Low", "Medium", "High"])
        self.preset_combo.setCurrentText(Config.DEFAULT_QUALITY_PRESET)
        form.addRow("Global Frame Quality:", self.preset_combo)

        self.fps_spin = QSpinBox(self)
        self.fps_spin.setRange(1, 120)
        self.fps_spin.setValue(Config.DEFAULT_TARGET_FPS)
        form.addRow("Global Target FPS Cap:", self.fps_spin)

        self.pass_edit = QLineEdit(self)
        self.pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_edit.setText(Config.MASTER_ADMIN_PASSWORD)
        form.addRow("Admin Password:", self.pass_edit)

        layout.addLayout(form)
        layout.addStretch()

        btn_box = QHBoxLayout()
        save_btn = QPushButton("Save & Apply", self)
        save_btn.setProperty("class", "GlassButtonPrimary")
        save_btn.clicked.connect(self.on_save)
        btn_box.addWidget(save_btn)

        layout.addLayout(btn_box)

    def on_save(self):
        new_pass = self.pass_edit.text().strip()
        if new_pass:
            Config.MASTER_ADMIN_PASSWORD = new_pass
        Config.DEFAULT_QUALITY_PRESET = self.preset_combo.currentText()
        Config.DEFAULT_TARGET_FPS = self.fps_spin.value()
        Config.DEFAULT_PORT = self.port_spin.value()
        save_server_settings()
        self.accept()


class PeerRequestNotificationPopup(QFrame):
    """Dropdown overlay panel attached beneath the bell icon showing active pending peer requests."""
    def __init__(self, server_thread, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.server_thread = server_thread
        self.setObjectName("NotificationPopup")
        self.setFixedWidth(360)
        self.setStyleSheet("""
            QFrame#NotificationPopup {
                background-color: rgba(15, 23, 42, 0.98);
                border: 2px solid rgba(0, 243, 255, 0.6);
                border-radius: 12px;
            }
            QLabel {
                color: #F8FAFC;
                font-family: 'Segoe UI', 'Inter', sans-serif;
            }
        """)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.layout.setSpacing(12)
        self.refresh_ui()

    def refresh_ui(self):
        # Clear layout
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Header
        hdr_box = QHBoxLayout()
        title_lbl = QLabel("🔔 Screen Access Requests", self)
        title_lbl.setStyleSheet("font-weight: 800; font-size: 14px; color: #00F3FF;")
        hdr_box.addWidget(title_lbl)
        hdr_box.addStretch()

        count = len(self.server_thread.pending_peer_requests)
        cnt_lbl = QLabel(f"{count} pending", self)
        cnt_lbl.setStyleSheet("color: #94A3B8; font-size: 11px;")
        hdr_box.addWidget(cnt_lbl)
        self.layout.addLayout(hdr_box)

        if not self.server_thread.pending_peer_requests:
            empty_lbl = QLabel("No pending screen access requests.", self)
            empty_lbl.setStyleSheet("color: #64748B; font-style: italic; padding: 12px 0;")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout.addWidget(empty_lbl)
        else:
            for req_id, req in list(self.server_thread.pending_peer_requests.items()):
                req_card = QFrame(self)
                req_card.setStyleSheet("""
                    QFrame {
                        background-color: rgba(30, 41, 59, 0.85);
                        border: 1px solid #334155;
                        border-radius: 8px;
                    }
                """)
                card_vbox = QVBoxLayout(req_card)
                card_vbox.setContentsMargins(10, 10, 10, 10)
                card_vbox.setSpacing(8)

                act_type = req.get("action_type", req.get("mode", "access_screen"))
                if act_type == "share_my_screen":
                    act_str = "↗️ Share My Screen"
                    act_color = "#10B981"
                else:
                    act_str = "👁️ Access Screen"
                    act_color = "#00F3FF"

                info_lbl = QLabel(
                    f"<b>{req.get('requester_name')}</b> ➔ <b>{req.get('target_name')}</b><br>"
                    f"<span style='color: {act_color}; font-size: 11px;'>Requesting {act_str}</span>",
                    req_card
                )
                info_lbl.setWordWrap(True)
                card_vbox.addWidget(info_lbl)

                btn_row = QHBoxLayout()
                btn_row.setSpacing(8)

                reject_btn = QPushButton("❌ Reject", req_card)
                reject_btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(239, 68, 68, 0.2);
                        border: 1px solid #EF4444;
                        border-radius: 6px;
                        color: #EF4444;
                        font-weight: 700;
                        padding: 5px 10px;
                        font-size: 11px;
                    }
                    QPushButton:hover {
                        background-color: rgba(239, 68, 68, 0.45);
                        color: #FFFFFF;
                    }
                """)
                reject_btn.clicked.connect(lambda checked, rid=req_id: self.reject_request(rid))
                btn_row.addWidget(reject_btn)

                approve_btn = QPushButton("✅ Approve", req_card)
                approve_btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(16, 185, 129, 0.25);
                        border: 1px solid #10B981;
                        border-radius: 6px;
                        color: #10B981;
                        font-weight: 700;
                        padding: 5px 10px;
                        font-size: 11px;
                    }
                    QPushButton:hover {
                        background-color: rgba(16, 185, 129, 0.5);
                        color: #FFFFFF;
                    }
                """)
                approve_btn.clicked.connect(lambda checked, rid=req_id: self.approve_request(rid))
                btn_row.addWidget(approve_btn)

                card_vbox.addLayout(btn_row)
                self.layout.addWidget(req_card)

        self.adjustSize()

    def approve_request(self, req_id):
        self.server_thread.admin_approve_peer_request(req_id)
        self.refresh_ui()
        if not self.server_thread.pending_peer_requests:
            self.hide()

    def reject_request(self, req_id):
        self.server_thread.admin_reject_peer_request(req_id)
        self.refresh_ui()
        if not self.server_thread.pending_peer_requests:
            self.hide()


# --- MASTER DASHBOARD WINDOW WITH EMBEDDED LOGIN OVERLAY ---

class MasterDashboardWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{Config.APP_NAME} - LAN Live Screen Monitor Master v{Config.VERSION}")
        self.resize(1366, 768)

        # Set App Icon
        bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(bundle_dir, "app_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.cards = {} # client_id -> StreamCard
        self.active_modal = None
        self.notif_popup = None

        # Stacked Widget to handle Login Overlay -> Main Dashboard Transition
        self.stacked_widget = QStackedWidget(self)
        self.stacked_widget.setStyleSheet("background-color: #0F172A;")
        self.setCentralWidget(self.stacked_widget)

        # 1. Login Page
        self.login_page = self.create_login_page()
        self.stacked_widget.addWidget(self.login_page)

        # 2. Dashboard Page
        self.dashboard_page = QWidget(self)
        self.init_dashboard_ui(self.dashboard_page)
        self.stacked_widget.addWidget(self.dashboard_page)

        # Show Login Page First
        self.stacked_widget.setCurrentWidget(self.login_page)

        # Load QSS Glassmorphism Stylesheet
        self.load_stylesheet()

        # Start WebSocket Server Thread
        self.server_thread = MasterWebSocketServer(host=Config.DEFAULT_HOST, port=Config.DEFAULT_PORT)
        self.server_thread.client_connected.connect(self.on_client_connected)
        self.server_thread.client_disconnected.connect(self.on_client_disconnected)
        self.server_thread.frame_received.connect(self.on_frame_received)
        self.server_thread.share_state_changed.connect(self.update_share_indicators)
        self.server_thread.peer_requests_updated.connect(self.update_bell_indicator)
        self.server_thread.log_emitted.connect(print)
        self.server_thread.start()

        # Start Admin Screen Capturer
        self.admin_capturer = AdminScreenCapturer(self.server_thread)
        self.admin_capturer.start()

    def load_stylesheet(self):
        # Try multiple locations: PyInstaller bundle, cx_Freeze exe dir, script dir
        candidates = [
            getattr(sys, '_MEIPASS', ''),
            os.path.dirname(sys.executable),
            os.path.dirname(os.path.abspath(__file__)),
        ]
        for base_dir in candidates:
            if not base_dir:
                continue
            qss_path = os.path.join(base_dir, "style.qss")
            if os.path.exists(qss_path):
                with open(qss_path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())
                return

    def create_login_page(self):
        login_container = QWidget()
        login_container.setStyleSheet("background-color: #0F172A;")
        
        outer_layout = QVBoxLayout(login_container)
        outer_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame(login_container)
        card.setFixedSize(400, 320)
        card.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 41, 59, 0.85);
                border: 1px solid rgba(0, 243, 255, 0.4);
                border-radius: 16px;
            }
            QLabel {
                color: #F8FAFC;
            }
            QLineEdit {
                background-color: rgba(15, 23, 42, 0.9);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 10px;
                padding: 12px;
                color: #FFFFFF;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #00F3FF;
            }
            QPushButton {
                background-color: rgba(0, 243, 255, 0.25);
                border: 1px solid #00F3FF;
                border-radius: 10px;
                color: #00F3FF;
                padding: 12px;
                font-weight: 700;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(0, 243, 255, 0.45);
                color: #FFFFFF;
            }
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 30, 30, 30)
        card_layout.setSpacing(16)

        title = QLabel("🔐 MASTER MONITOR LOGIN", card)
        title.setStyleSheet("font-size: 18px; font-weight: 800; color: #00F3FF;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        subtitle = QLabel("Enter Admin Access Password to unlock:", card)
        subtitle.setStyleSheet("color: #94A3B8; font-size: 12px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(subtitle)

        self.login_pass_input = QLineEdit(card)
        self.login_pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.login_pass_input.setPlaceholderText("Password (Default: admin)")
        self.login_pass_input.returnPressed.connect(self.verify_login_password)
        card_layout.addWidget(self.login_pass_input)

        self.login_err_msg = QLabel("", card)
        self.login_err_msg.setStyleSheet("color: #EF4444; font-size: 12px; font-weight: 600;")
        self.login_err_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.login_err_msg)

        unlock_btn = QPushButton("Unlock Dashboard", card)
        unlock_btn.clicked.connect(self.verify_login_password)
        card_layout.addWidget(unlock_btn)

        outer_layout.addWidget(card)
        return login_container

    def verify_login_password(self):
        entered = self.login_pass_input.text().strip()
        if entered.lower() == Config.MASTER_ADMIN_PASSWORD.lower():
            self.stacked_widget.setCurrentIndex(1)
        else:
            self.login_err_msg.setText("❌ Incorrect Password. Access Denied.")
            self.login_pass_input.selectAll()

    def init_dashboard_ui(self, page_widget):
        root_layout = QHBoxLayout(page_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Glassmorphism Sidebar Navigation
        sidebar = QFrame(page_widget)
        sidebar.setObjectName("SidebarFrame")
        sidebar.setFixedWidth(220)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(16, 24, 16, 24)
        sb_layout.setSpacing(12)

        # Header / Branding (Overwatch Logo + Name + Version)
        logo_layout = QHBoxLayout()
        logo_layout.setSpacing(10)
        logo_layout.setContentsMargins(0, 0, 0, 10)

        bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        logo_pix = None
        for path_opt in [
            os.path.join(bundle_dir, "logo", "overwatch_transparent.png"),
            os.path.join(bundle_dir, "logo", "overwatch.jpg"),
            os.path.join(bundle_dir, "app_icon.ico"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo", "overwatch_transparent.png"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo", "overwatch.jpg")
        ]:
            if os.path.exists(path_opt):
                logo_pix = QPixmap(path_opt)
                if not logo_pix.isNull():
                    break

        if logo_pix and not logo_pix.isNull():
            logo_img_lbl = QLabel(sidebar)
            logo_img_lbl.setPixmap(logo_pix.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            logo_layout.addWidget(logo_img_lbl)

        logo_text_layout = QVBoxLayout()
        logo_text_layout.setSpacing(1)
        logo_title = QLabel("OVERWATCH", sidebar)
        logo_title.setStyleSheet("font-size: 16px; font-weight: 900; color: #FF9C00; letter-spacing: 1px;")
        logo_ver = QLabel(f"LAN Monitor v{Config.VERSION}", sidebar)
        logo_ver.setStyleSheet("font-size: 10px; color: #94A3B8; font-weight: 500;")
        logo_text_layout.addWidget(logo_title)
        logo_text_layout.addWidget(logo_ver)

        logo_layout.addLayout(logo_text_layout)
        logo_layout.addStretch()
        sb_layout.addLayout(logo_layout)

        self.sidebar_buttons = []

        btn_grid = QPushButton("  📊 Grid View", sidebar)
        btn_grid.setObjectName("SidebarButton")
        btn_grid.setProperty("active", "true")
        btn_grid.clicked.connect(lambda: self._set_active_sidebar(btn_grid))
        sb_layout.addWidget(btn_grid)
        self.sidebar_buttons.append(btn_grid)

        btn_rooms = QPushButton("  🏢 Group / Rooms", sidebar)
        btn_rooms.setObjectName("SidebarButton")
        btn_rooms.clicked.connect(lambda: (self._set_active_sidebar(btn_rooms), self.open_group_rooms()))
        sb_layout.addWidget(btn_rooms)
        self.sidebar_buttons.append(btn_rooms)

        btn_bandwidth = QPushButton("  ⚡ Bandwidth Control", sidebar)
        btn_bandwidth.setObjectName("SidebarButton")
        btn_bandwidth.clicked.connect(lambda: (self._set_active_sidebar(btn_bandwidth), self.open_bandwidth_control()))
        sb_layout.addWidget(btn_bandwidth)
        self.sidebar_buttons.append(btn_bandwidth)

        btn_alert = QPushButton("  🚨 Ping All Clients", sidebar)
        btn_alert.setObjectName("SidebarButton")
        btn_alert.clicked.connect(lambda: (self._set_active_sidebar(btn_alert), self.ping_all_clients()))
        sb_layout.addWidget(btn_alert)
        self.sidebar_buttons.append(btn_alert)

        btn_settings = QPushButton("  ⚙️ App Settings", sidebar)
        btn_settings.setObjectName("SidebarButton")
        btn_settings.clicked.connect(lambda: (self._set_active_sidebar(btn_settings), self.open_settings()))
        sb_layout.addWidget(btn_settings)
        self.sidebar_buttons.append(btn_settings)

        sb_layout.addStretch()

        server_info_lbl = QLabel(f"Server IP:\n{Config.get_local_ip()}:{Config.DEFAULT_PORT}", sidebar)
        server_info_lbl.setStyleSheet("color: #64748B; font-size: 11px; padding: 8px;")
        sb_layout.addWidget(server_info_lbl)

        root_layout.addWidget(sidebar)

        # 2. Main Dashboard Area
        main_area = QWidget(page_widget)
        ma_layout = QVBoxLayout(main_area)
        ma_layout.setContentsMargins(0, 0, 0, 0)
        ma_layout.setSpacing(0)

        # Top Header Bar: [ Title ] -> stretch -> [ Share Admin Screen ] -> [ Connected: X ] -> [ Global Net ] -> [ Bell ]
        header = QFrame(main_area)
        header.setObjectName("HeaderFrame")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 10, 20, 10)
        h_layout.setSpacing(12)

        title = QLabel("Live Employee Screen Monitor", header)
        title.setObjectName("HeaderTitle")
        h_layout.addWidget(title)

        h_layout.addStretch()

        # 1. Share Admin Screen Button (Moved from sidebar to top-right header)
        self.top_share_admin_btn = QPushButton("🖥️ Share Admin Screen", header)
        self.top_share_admin_btn.setObjectName("TopShareAdminButton")
        self.top_share_admin_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 243, 255, 0.15);
                border: 1px solid rgba(0, 243, 255, 0.5);
                border-radius: 8px;
                color: #00F3FF;
                padding: 6px 14px;
                font-weight: 700;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(0, 243, 255, 0.35);
                color: #FFFFFF;
            }
        """)
        self.top_share_admin_btn.clicked.connect(self.open_share_admin_screen)
        h_layout.addWidget(self.top_share_admin_btn)

        # 2. Connected PCs Badge
        self.badge_connected = QLabel("Connected: 0 PCs", header)
        self.badge_connected.setObjectName("HeaderBadge")
        h_layout.addWidget(self.badge_connected)

        # 3. Global Network Badge
        self.badge_fps = QLabel("Global Network: 0.0 MB/s", header)
        self.badge_fps.setObjectName("HeaderBadge")
        h_layout.addWidget(self.badge_fps)

        # 4. Far-Right Notification Bell Button
        self.bell_btn = QPushButton("🔔", header)
        self.bell_btn.setObjectName("NotificationBellButton")
        self.bell_btn.setFixedSize(38, 32)
        self.bell_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bell_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(30, 41, 59, 0.9);
                border: 1px solid #334155;
                border-radius: 8px;
                font-size: 15px;
                color: #94A3B8;
            }
            QPushButton:hover {
                border-color: #00F3FF;
                color: #00F3FF;
                background-color: rgba(51, 65, 85, 0.9);
            }
        """)
        self.bell_btn.clicked.connect(self.toggle_notification_popup)
        h_layout.addWidget(self.bell_btn)

        ma_layout.addWidget(header)

        # Responsive Grid Scroll Area
        scroll_area = QScrollArea(main_area)
        scroll_area.setWidgetResizable(True)

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(24, 24, 24, 24)
        self.grid_layout.setSpacing(20)

        scroll_area.setWidget(self.grid_container)
        ma_layout.addWidget(scroll_area)

        root_layout.addWidget(main_area)

    def update_bell_indicator(self):
        count = len(self.server_thread.pending_peer_requests)
        if count > 0:
            self.bell_btn.setText(f"🔔 {count}")
            self.bell_btn.setFixedWidth(54)
            self.bell_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(245, 158, 11, 0.25);
                    border: 1px solid #F59E0B;
                    border-radius: 8px;
                    font-size: 13px;
                    font-weight: 800;
                    color: #F59E0B;
                }
                QPushButton:hover {
                    background-color: rgba(245, 158, 11, 0.45);
                    color: #FFFFFF;
                }
            """)
        else:
            self.bell_btn.setText("🔔")
            self.bell_btn.setFixedSize(38, 32)
            self.bell_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(30, 41, 59, 0.9);
                    border: 1px solid #334155;
                    border-radius: 8px;
                    font-size: 15px;
                    color: #94A3B8;
                }
                QPushButton:hover {
                    border-color: #00F3FF;
                    color: #00F3FF;
                    background-color: rgba(51, 65, 85, 0.9);
                }
            """)

        if self.notif_popup and self.notif_popup.isVisible():
            self.notif_popup.refresh_ui()

    def toggle_notification_popup(self):
        if self.notif_popup is None:
            self.notif_popup = PeerRequestNotificationPopup(self.server_thread, self)

        if self.notif_popup.isVisible():
            self.notif_popup.hide()
        else:
            self.notif_popup.refresh_ui()
            # Position right under bell button
            bell_pos = self.bell_btn.mapToGlobal(self.bell_btn.rect().bottomRight())
            popup_w = self.notif_popup.sizeHint().width()
            self.notif_popup.move(bell_pos.x() - popup_w, bell_pos.y() + 6)
            self.notif_popup.show()
            self.notif_popup.raise_()

    def rearrange_grid(self):
        """Rearrange cards into a fluid responsive 3-column grid."""
        # Clear layout first
        for i in reversed(range(self.grid_layout.count())):
            item = self.grid_layout.itemAt(i)
            if item.widget():
                self.grid_layout.removeWidget(item.widget())

        for i, card in enumerate(self.cards.values()):
            row = i // 3
            col = i % 3
            self.grid_layout.addWidget(card, row, col)

    def on_client_connected(self, client_id, info):
        if client_id in self.cards:
            card = self.cards[client_id]
        else:
            card = StreamCard(client_id=client_id, info=info, parent=self.grid_container)
            card.expand_requested.connect(self.open_single_view_modal)
            card.share_requested.connect(self.open_share_client_dialog)
            card.swap_requested.connect(self.swap_cards)
            self.cards[client_id] = card
            self.rearrange_grid()

    def swap_cards(self, source_id, target_id):
        items = list(self.cards.items())
        try:
            source_idx = next(i for i, (k, v) in enumerate(items) if k == source_id)
            target_idx = next(i for i, (k, v) in enumerate(items) if k == target_id)
            items[source_idx], items[target_idx] = items[target_idx], items[source_idx]
            self.cards = dict(items)
            self.rearrange_grid()
        except StopIteration:
            pass

        self.update_header_stats()

    def on_client_disconnected(self, client_id):
        if client_id in self.cards:
            self.cards[client_id].set_offline()
        self.update_header_stats()
        self.update_share_indicators()

    def on_frame_received(self, client_id, frame_bytes, metadata):
        if client_id in self.cards:
            self.cards[client_id].update_frame(frame_bytes, metadata)

        # Update modal stream if active
        if self.active_modal and self.active_modal.client_id == client_id:
            self.active_modal.update_frame(frame_bytes, metadata)

    def update_header_stats(self):
        active_count = sum(1 for c in self.cards.values() if c.status != "offline")
        self.badge_connected.setText(f"Connected: {active_count} PCs")

    def open_single_view_modal(self, client_id):
        if client_id not in self.cards:
            return

        card = self.cards[client_id]
        modal = SingleStreamModal(
            client_id=client_id,
            info=card.info,
            server_thread=self.server_thread,
            parent=self
        )
        self.active_modal = modal
        modal.exec()
        self.active_modal = None

    def open_share_client_dialog(self, client_id):
        if client_id not in self.cards:
            return
        card = self.cards[client_id]
        dlg = ShareScreenDialog(
            source_id=client_id,
            source_name=card.info.get('name', client_id),
            server_thread=self.server_thread,
            cards=self.cards,
            parent=self
        )
        dlg.exec()
        self.update_share_indicators()

    def open_share_admin_screen(self):
        dlg = ShareScreenDialog(
            source_id="ADMIN_PC",
            source_name="Admin / Master Screen",
            server_thread=self.server_thread,
            cards=self.cards,
            parent=self
        )
        dlg.exec()
        self.update_share_indicators()

    def update_share_indicators(self):
        active_source_ids = set(s.get("source_id") for s in self.server_thread.share_sessions.values())
        for cid, card in self.cards.items():
            card.set_share_active(cid in active_source_ids)

    def _set_active_sidebar(self, active_btn):
        """Toggle active visual state across sidebar buttons."""
        for btn in self.sidebar_buttons:
            btn.setProperty("active", "true" if btn is active_btn else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def open_group_rooms(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Group / Rooms Management")
        dlg.setFixedSize(500, 400)
        dlg.setStyleSheet("background-color: #0F172A; color: #F8FAFC;")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("🏢 Group / Room Assignments", dlg)
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #00F3FF;")
        layout.addWidget(title)

        desc = QLabel("Assign connected PCs to rooms or departments for organized monitoring.", dlg)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #94A3B8; font-size: 13px;")
        layout.addWidget(desc)

        # List currently connected clients
        if self.cards:
            for cid, card in self.cards.items():
                row = QFrame(dlg)
                row.setStyleSheet("background-color: rgba(30, 41, 59, 0.8); border-radius: 8px; padding: 8px;")
                row_layout = QHBoxLayout(row)
                name_lbl = QLabel(f"🖥️ {card.info.get('name', cid)}", row)
                name_lbl.setStyleSheet("color: #F8FAFC; font-weight: 600;")
                row_layout.addWidget(name_lbl)
                ip_lbl = QLabel(f"{card.info.get('ip', '')}", row)
                ip_lbl.setStyleSheet("color: #64748B;")
                row_layout.addWidget(ip_lbl)
                row_layout.addStretch()
                group_combo = QComboBox(row)
                group_combo.addItems(["Default", "Office A", "Office B", "Server Room", "Remote"])
                group_combo.setStyleSheet("background-color: #1E293B; color: #F8FAFC; border: 1px solid #334155; border-radius: 6px; padding: 4px 8px;")
                row_layout.addWidget(group_combo)
                layout.addWidget(row)
        else:
            empty = QLabel("No clients connected yet. Connect employee PCs to assign them to rooms.", dlg)
            empty.setStyleSheet("color: #475569; font-style: italic; padding: 20px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(empty)

        layout.addStretch()

        close_btn = QPushButton("Close", dlg)
        close_btn.setStyleSheet("background-color: rgba(0, 243, 255, 0.2); border: 1px solid #00F3FF; border-radius: 8px; color: #00F3FF; padding: 10px; font-weight: 600;")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)

        dlg.exec()

    def open_bandwidth_control(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Bandwidth Control")
        dlg.setFixedSize(450, 380)
        dlg.setStyleSheet("background-color: #0F172A; color: #F8FAFC;")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("⚡ Bandwidth Control Panel", dlg)
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #00F3FF;")
        layout.addWidget(title)

        desc = QLabel("Adjust global streaming quality and FPS to optimize network bandwidth usage.", dlg)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #94A3B8; font-size: 13px;")
        layout.addWidget(desc)

        form = QFormLayout()
        form.setSpacing(12)

        quality_combo = QComboBox(dlg)
        quality_combo.addItems(["Low (45% JPEG, 50% Scale)", "Medium (65% JPEG, 75% Scale)", "High (85% JPEG, 100% Scale)"])
        preset_idx_map = {"Low": 0, "Medium": 1, "High": 2}
        quality_combo.setCurrentIndex(preset_idx_map.get(Config.DEFAULT_QUALITY_PRESET, 1))
        quality_combo.setStyleSheet("background-color: #1E293B; color: #F8FAFC; border: 1px solid #334155; border-radius: 6px; padding: 6px;")
        form.addRow("Streaming Quality:", quality_combo)

        fps_slider = QSlider(Qt.Orientation.Horizontal, dlg)
        fps_slider.setRange(5, 60)
        fps_slider.setValue(Config.DEFAULT_TARGET_FPS)
        fps_lbl = QLabel(f"{Config.DEFAULT_TARGET_FPS} FPS", dlg)
        fps_slider.valueChanged.connect(lambda v: fps_lbl.setText(f"{v} FPS"))

        fps_box = QHBoxLayout()
        fps_box.addWidget(fps_slider)
        fps_box.addWidget(fps_lbl)
        form.addRow("Max Target FPS:", fps_box)

        layout.addLayout(form)
        layout.addStretch()

        btn_box = QHBoxLayout()
        apply_btn = QPushButton("Apply to All Clients", dlg)
        apply_btn.setProperty("class", "GlassButtonPrimary")
        def on_apply():
            preset_map = {0: "Low", 1: "Medium", 2: "High"}
            chosen_preset = preset_map[quality_combo.currentIndex()]
            chosen_fps = fps_slider.value()
            Config.DEFAULT_QUALITY_PRESET = chosen_preset
            Config.DEFAULT_TARGET_FPS = chosen_fps
            save_server_settings()
            pkt = Protocol.create_quality_update(preset_name=chosen_preset, target_fps=chosen_fps)
            self.server_thread.broadcast(pkt)
            QMessageBox.information(dlg, "Settings Applied", f"Bandwidth configuration saved & dispatched to all clients.\nQuality: {chosen_preset} | FPS: {chosen_fps}")
            dlg.accept()
        apply_btn.clicked.connect(on_apply)
        btn_box.addWidget(apply_btn)

        layout.addLayout(btn_box)
        dlg.exec()

    def open_settings(self):
        dlg = SettingsDialog(current_port=self.server_thread.port, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            save_server_settings()
            QMessageBox.information(
                self, 
                "Settings Saved", 
                "Application settings saved.\n\nNote: If you changed the server port, please restart Overwatch Master Dashboard for the new port to take effect."
            )

    def ping_all_clients(self):
        pkt = Protocol.create_alert_packet()
        self.server_thread.broadcast(pkt)
        QMessageBox.information(self, "Ping Alert Sent", "Flashing screen border alert sent to all connected client screens!")

    def closeEvent(self, event):
        if hasattr(self, 'admin_capturer') and self.admin_capturer:
            self.admin_capturer.stop()
        if hasattr(self, 'server_thread') and self.server_thread:
            self.server_thread.stop()
        super().closeEvent(event)


def ensure_firewall_rule():
    """Ensure Windows Firewall allows incoming connections on the server port.
    Creates the rule via an elevated subprocess (UAC prompt) if it doesn't exist."""
    if sys.platform != "win32":
        return

    rule_name = "LAN Screen Monitor Server"
    port = str(Config.DEFAULT_PORT)

    try:
        # Check if rule already exists
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", f"name={rule_name}"],
            capture_output=True, text=True, timeout=10
        )
        if rule_name in result.stdout:
            return  # Rule already exists
    except Exception:
        pass

    try:
        # Inform the user before UAC prompt appears
        QMessageBox.information(
            None, 
            "Firewall Setup Required", 
            "LAN Screen Monitor needs to add a Windows Firewall rule to allow employee PCs to connect to this dashboard.\n\n"
            "Please click 'Yes' on the administrator prompt that appears next."
        )

        # Build the netsh command arguments
        cmd_args = (
            f'advfirewall firewall add rule '
            f'name="{rule_name}" dir=in action=allow protocol=TCP '
            f'localport={port} profile=any'
        )

        # Use ShellExecuteW with 'runas' verb for UAC elevation
        # 1 = SW_SHOWNORMAL (Avoids silent failures on some Windows versions)
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "netsh", cmd_args, None, 1  
        )
        
        # ShellExecuteW returns > 32 on success
        if ret > 32:
            print(f"[Firewall] Rule '{rule_name}' created for port {port}.")
        else:
            print(f"[Firewall] Could not create rule (user may have declined UAC).")
            QMessageBox.warning(
                None,
                "Firewall Setup Failed",
                "The firewall rule was not created because the administrator prompt was declined or failed. "
                "Employee PCs may not be able to connect."
            )
    except Exception as e:
        print(f"[Firewall] Error creating rule: {e}")


def main():
    try:
        if sys.platform == "win32":
            import ctypes
            myappid = "blackbox.overwatch.lanmonitor.4_50_2"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

        load_server_settings()
        app = QApplication(sys.argv)

        bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(bundle_dir, "app_icon.ico")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))

        ensure_firewall_rule()
        window = MasterDashboardWindow()
        window.show()
        sys.exit(app.exec())
    except Exception:
        # Log crash to file next to the executable for debugging
        crash_log = os.path.join(os.path.dirname(sys.executable), "crash_log.txt")
        with open(crash_log, "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        raise


if __name__ == "__main__":
    main()
