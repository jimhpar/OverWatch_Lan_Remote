import json
import base64
import time

class PacketType:
    # Client -> Server
    AUTH_REQ = "AUTH_REQ"
    FRAME_DATA = "FRAME_DATA"
    HEARTBEAT = "HEARTBEAT"
    SHARE_STREAM_INPUT = "SHARE_STREAM_INPUT"
    PEER_SHARE_REQ = "PEER_SHARE_REQ"
    PEER_PROMPT_RESP = "PEER_PROMPT_RESP"
    
    # Server -> Client
    AUTH_RESP = "AUTH_RESP"
    REMOTE_INPUT = "REMOTE_INPUT"
    QUALITY_UPDATE = "QUALITY_UPDATE"
    DISCONNECT_CMD = "DISCONNECT_CMD"
    ALERT = "ALERT"
    SHARE_STREAM_START = "SHARE_STREAM_START"
    SHARE_STREAM_FRAME = "SHARE_STREAM_FRAME"
    SHARE_STREAM_STOP = "SHARE_STREAM_STOP"
    CLIENT_LIST_UPDATE = "CLIENT_LIST_UPDATE"
    PEER_PROMPT_REQ = "PEER_PROMPT_REQ"
    PEER_REQUEST_DECLINED = "PEER_REQUEST_DECLINED"
    PEER_REQUEST_RESOLVED = "PEER_REQUEST_RESOLVED"
    CURSOR_UPDATE = "CURSOR_UPDATE"

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
    def create_frame_packet(client_id, frame_bytes, fps, width, height, is_static=False, cursor_data=None):
        # Base64 encode image payload for json packet transport
        b64_data = base64.b64encode(frame_bytes).decode('utf-8')
        pkt = {
            "type": PacketType.FRAME_DATA,
            "client_id": client_id,
            "frame": b64_data,
            "fps": round(fps, 1),
            "width": width,
            "height": height,
            "is_static": is_static,
            "timestamp": time.time()
        }
        if cursor_data:
            pkt["cursor"] = cursor_data
        return json.dumps(pkt)

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
    def create_share_frame(session_id, source_id, frame_bytes, fps, width, height, is_static=False, cursor_data=None):
        b64_data = base64.b64encode(frame_bytes).decode('utf-8')
        pkt = {
            "type": PacketType.SHARE_STREAM_FRAME,
            "session_id": session_id,
            "source_id": source_id,
            "frame": b64_data,
            "fps": round(fps, 1),
            "width": width,
            "height": height,
            "is_static": is_static,
            "timestamp": time.time()
        }
        if cursor_data:
            pkt["cursor"] = cursor_data
        return json.dumps(pkt)

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
    def create_client_list_update(clients_list):
        return json.dumps({
            "type": PacketType.CLIENT_LIST_UPDATE,
            "clients": clients_list,
            "timestamp": time.time()
        })

    @staticmethod
    def create_peer_share_request(requester_id, requester_name, target_id, mode="view"):
        return json.dumps({
            "type": PacketType.PEER_SHARE_REQ,
            "requester_id": requester_id,
            "requester_name": requester_name,
            "target_id": target_id,
            "mode": mode,
            "timestamp": time.time()
        })

    @staticmethod
    def create_peer_prompt_request(request_id, requester_id, requester_name, target_id, target_name, mode="view"):
        return json.dumps({
            "type": PacketType.PEER_PROMPT_REQ,
            "request_id": request_id,
            "requester_id": requester_id,
            "requester_name": requester_name,
            "target_id": target_id,
            "target_name": target_name,
            "mode": mode,
            "timestamp": time.time()
        })

    @staticmethod
    def create_peer_prompt_response(request_id, requester_id, target_id, accepted, mode="view"):
        return json.dumps({
            "type": PacketType.PEER_PROMPT_RESP,
            "request_id": request_id,
            "requester_id": requester_id,
            "target_id": target_id,
            "accepted": accepted,
            "mode": mode,
            "timestamp": time.time()
        })

    @staticmethod
    def create_peer_request_declined(target_name, reason="Request was declined."):
        return json.dumps({
            "type": PacketType.PEER_REQUEST_DECLINED,
            "target_name": target_name,
            "reason": reason,
            "timestamp": time.time()
        })

    @staticmethod
    def create_peer_request_resolved(request_id):
        return json.dumps({
            "type": PacketType.PEER_REQUEST_RESOLVED,
            "request_id": request_id,
            "timestamp": time.time()
        })

    @staticmethod
    def create_cursor_update(source_id, cursor_id, hotspot_x, hotspot_y, cursor_png_b64=None):
        pkt = {
            "type": PacketType.CURSOR_UPDATE,
            "source_id": source_id,
            "cursor_id": cursor_id,
            "hotspot": [hotspot_x, hotspot_y],
            "timestamp": time.time()
        }
        if cursor_png_b64 is not None:
            pkt["cursor_png"] = cursor_png_b64
        return json.dumps(pkt)

    @staticmethod
    def parse(raw_data):
        try:
            return json.loads(raw_data)
        except Exception:
            return None
