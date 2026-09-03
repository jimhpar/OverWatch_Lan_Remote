import socket
import os

class Config:
    # Application Branding & Metadata
    APP_NAME = "Overwatch"
    APP_TITLE = "Overwatch - LAN Live Screen Monitor"
    VERSION = "4.50.2"

    # Network Server Configuration
    DEFAULT_HOST = "0.0.0.0"
    DEFAULT_PORT = 8765
    AUTH_TOKEN = "LAN_GLASS_SECURE_2026"
    
    # Master Dashboard Admin Access Password
    MASTER_ADMIN_PASSWORD = "admin"
    
    # Settings Persistence Files
    SERVER_SETTINGS_FILE = "server_settings.json"
    CLIENT_SETTINGS_FILE = "client_settings.json"
    
    # Discovery UDP Broadcast
    DISCOVERY_PORT = 8766
    DISCOVERY_MESSAGE = "LAN_MONITOR_DISCOVER_SERVER"
    DISCOVERY_RESPONSE = "LAN_MONITOR_SERVER_HERE"

    # Frame Capture & Compression Settings
    DEFAULT_TARGET_FPS = 10
    MIN_STATIC_FPS = 2
    STATIC_DELTA_THRESHOLD = 1.5  # Mean absolute difference threshold percentage to consider frame static
    
    # Image Quality Presets (JPEG Quality 1-100)
    QUALITY_PRESETS = {
        "Low": {"jpeg_quality": 45, "scale": 0.5},
        "Medium": {"jpeg_quality": 65, "scale": 0.75},
        "High": {"jpeg_quality": 85, "scale": 1.0}
    }
    DEFAULT_QUALITY_PRESET = "Medium"
    
    # Screen Capture Resolution Max Bounds (Width, Height)
    MAX_STREAM_WIDTH = 1920
    MAX_STREAM_HEIGHT = 1080

    @staticmethod
    def get_local_ip():
        """Retrieve local IPv4 address of this machine."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Doesn't need to be reachable
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
