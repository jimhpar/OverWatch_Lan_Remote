import json
import base64
import time

class PacketType:
    # Client -> Server
    AUTH_REQ = "AUTH_REQ"
    FRAME_DATA = "FRAME_DATA"
    HEARTBEAT = "HEARTBEAT"
    SHARE_STREAM_INPUT = "SHARE_STREAM_INPUT"
    
    # Server -> Client
    AUTH_RESP = "AUTH_RESP"
    REMOTE_INPUT = "REMOTE_INPUT"
    QUALITY_UPDATE = "QUALITY_UPDATE"
    DISCONNECT_CMD = "DISCONNECT_CMD"
    ALERT = "ALERT"
    SHARE_STREAM_START = "SHARE_STREAM_START"
    SHARE_STREAM_FRAME = "SHARE_STREAM_FRAME"
    SHARE_STREAM_STOP = "SHARE_STREAM_STOP"

class Protocol:
    @staticmethod
    def create_auth_request(client_name, hostname, ip_address, passcode):
        return json.dumps({
            "type": PacketType.AUTH_REQ,
            "client_name": client_name,
            "hostname": hostname,
            "ip_address": ip_address,
            "passcode": passcode,
            "timestamp": time.time()
        })

    @staticmethod
    def create_auth_response(success, message=""):
        return json.dumps({
            "type": PacketType.AUTH_RESP,
            "success": success,
            "message": message
        })

    @staticmethod
    def create_frame_packet(client_id, frame_bytes, fps, width, height, is_static=False):
        # Base64 encode image payload for json packet transport
        b64_data = base64.b64encode(frame_bytes).decode('utf-8')
        return json.dumps({
            "type": PacketType.FRAME_DATA,
            "client_id": client_id,
            "frame": b64_data,
            "fps": round(fps, 1),
            "width": width,
            "height": height,
            "is_static": is_static,
            "timestamp": time.time()
        })

    @staticmethod
    def create_remote_input_packet(event_type, params):
        """
        event_type: 'mouse_move', 'mouse_click', 'mouse_scroll', 'key_press', 'key_release'
        params: dict of event data (e.g. x, y, button, key)
        """
        return json.dumps({
            "type": PacketType.REMOTE_INPUT,
            "event_type": event_type,
            "params": params,
            "timestamp": time.time()
        })

    @staticmethod
    def create_quality_update(preset_name, target_fps):
        return json.dumps({
            "type": PacketType.QUALITY_UPDATE,
            "preset": preset_name,
            "target_fps": target_fps
        })

    @staticmethod
    def create_alert_packet():
        return json.dumps({
            "type": PacketType.ALERT,
            "timestamp": time.time()
        })

    @staticmethod
    def create_share_start(session_id, source_id, source_name, allow_remote_control=True):
        return json.dumps({
            "type": PacketType.SHARE_STREAM_START,
            "session_id": session_id,
            "source_id": source_id,
            "source_name": source_name,
            "allow_remote_control": allow_remote_control,
            "timestamp": time.time()
        })

    @staticmethod
    def create_share_frame(session_id, source_id, frame_bytes, fps, width, height, is_static=False):
        b64_data = base64.b64encode(frame_bytes).decode('utf-8')
        return json.dumps({
            "type": PacketType.SHARE_STREAM_FRAME,
            "session_id": session_id,
            "source_id": source_id,
            "frame": b64_data,
            "fps": round(fps, 1),
            "width": width,
            "height": height,
            "is_static": is_static,
            "timestamp": time.time()
        })

    @staticmethod
    def create_share_stop(session_id, source_id):
        return json.dumps({
            "type": PacketType.SHARE_STREAM_STOP,
            "session_id": session_id,
            "source_id": source_id,
            "timestamp": time.time()
        })

    @staticmethod
    def create_share_input(session_id, source_id, event_type, params):
        return json.dumps({
            "type": PacketType.SHARE_STREAM_INPUT,
            "session_id": session_id,
            "source_id": source_id,
            "event_type": event_type,
            "params": params,
            "timestamp": time.time()
        })

    @staticmethod
    def parse(raw_data):
        try:
            return json.loads(raw_data)
        except Exception:
            return None
