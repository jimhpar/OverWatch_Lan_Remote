"""
LAN Screen Monitor - Unified Launcher
Displays a role selection screen on first launch, then starts the selected mode.
"""

import sys
import os
import json
import traceback

from config import Config

# Ensure bundled modules are importable (PyInstaller _MEIPASS / cx_Freeze exe dir)
_bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)))
if _bundle_dir not in sys.path:
    sys.path.insert(0, _bundle_dir)


def get_app_dir():
    """Get the directory where the application is installed/running."""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable (PyInstaller or cx_Freeze)
        return os.path.dirname(sys.executable)
    else:
        # Running as script
        return os.path.dirname(os.path.abspath(__file__))


def get_role_config_path():
    """Path to the role configuration file."""
    return os.path.join(os.path.expanduser("~"), "lan_monitor_role.json")


def load_saved_role():
    """Load previously saved role selection."""
    config_path = get_role_config_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                data = json.load(f)
                return data.get("role")
        except Exception:
            pass
    return None


def save_role(role):
    """Save role selection to config file."""
    config_path = get_role_config_path()
    try:
        with open(config_path, "w") as f:
            json.dump({"role": role}, f, indent=2)
    except Exception as e:
        print(f"[Launcher] Could not save role: {e}")


def show_role_selector():
    """Show a beautiful role selection window and return the chosen role."""
    from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                                 QLabel, QPushButton, QFrame, QGraphicsDropShadowEffect)
    from PyQt6.QtGui import QColor, QIcon
    from PyQt6.QtCore import Qt
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    icon_path = os.path.join(bundle_dir, "app_icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    selected_role = [None]  # mutable container for closure

    # --- Main Window ---
    window = QWidget()
    window.setWindowTitle(f"{Config.APP_NAME} - Setup")
    if os.path.exists(icon_path):
        window.setWindowIcon(QIcon(icon_path))

    window.setFixedSize(700, 480)
    window.setStyleSheet("""
        QWidget {
            background-color: #0F172A;
            font-family: 'Segoe UI', 'Inter', sans-serif;
            color: #F8FAFC;
        }
    """)

    main_layout = QVBoxLayout(window)
    main_layout.setContentsMargins(40, 36, 40, 36)
    main_layout.setSpacing(20)

    # Title
    title = QLabel(f"🛡️ {Config.APP_NAME}", window)
    title.setStyleSheet("font-size: 26px; font-weight: 800; color: #FF9C00;")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    main_layout.addWidget(title)

    subtitle = QLabel("Choose your installation mode", window)
    subtitle.setStyleSheet("font-size: 14px; color: #94A3B8; margin-bottom: 8px;")
    subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
    main_layout.addWidget(subtitle)

    # Publisher
    pub_lbl = QLabel("by Blackbox THC", window)
    pub_lbl.setStyleSheet("font-size: 11px; color: #475569;")
    pub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    main_layout.addWidget(pub_lbl)

    # Cards Row
    cards_row = QHBoxLayout()
    cards_row.setSpacing(24)

    def make_role_card(icon, title_text, desc_text, role_value, accent_color):
        card = QFrame(window)
        card.setFixedSize(280, 240)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(30, 41, 59, 0.85);
                border: 2px solid rgba({accent_color}, 0.3);
                border-radius: 16px;
            }}
            QFrame:hover {{
                border: 2px solid rgba({accent_color}, 0.8);
                background-color: rgba(30, 41, 59, 0.95);
            }}
        """)

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 6)
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(12)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel(icon, card)
        icon_lbl.setStyleSheet("font-size: 40px;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(icon_lbl)

        title_lbl = QLabel(title_text, card)
        title_lbl.setStyleSheet(f"font-size: 18px; font-weight: 700; color: rgb({accent_color});")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title_lbl)

        desc_lbl = QLabel(desc_text, card)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("font-size: 12px; color: #94A3B8;")
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(desc_lbl)

        select_btn = QPushButton(f"Select {title_text}", card)
        select_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba({accent_color}, 0.2);
                border: 1px solid rgb({accent_color});
                border-radius: 10px;
                color: rgb({accent_color});
                padding: 10px;
                font-weight: 700;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: rgba({accent_color}, 0.4);
                color: #FFFFFF;
            }}
        """)
        select_btn.clicked.connect(lambda: (selected_role.__setitem__(0, role_value), save_role(role_value), window.close()))
        card_layout.addWidget(select_btn)

        return card

    # Manager Card
    manager_card = make_role_card(
        "\U0001f441\ufe0f", "Manager Mode",
        "Monitor all employee screens in real-time. View, control, and manage connected PCs.",
        "manager",
        "0, 243, 255"  # Cyan
    )
    cards_row.addWidget(manager_card)

    # Client Card
    client_card = make_role_card(
        "\U0001f4bb", "Client Mode",
        "Stream this PC's screen to the Master Dashboard. Runs silently in system tray.",
        "client",
        "16, 185, 129"  # Green
    )
    cards_row.addWidget(client_card)

    main_layout.addLayout(cards_row)
    main_layout.addStretch()

    # Footer
    footer = QLabel(f"v{Config.VERSION} | This software monitors LAN-connected PC screens", window)
    footer.setStyleSheet("font-size: 11px; color: #475569;")
    footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
    main_layout.addWidget(footer)

    window.show()
    app.exec()

    return selected_role[0]


def launch_manager():
    """Start the Master Dashboard."""
    from master_dashboard import main as master_main
    master_main()


def launch_client():
    """Start the Employee Client."""
    from employee_client import main as client_main
    client_main()


def main():
    try:
        if sys.platform == "win32":
            import ctypes
            myappid = "blackbox.overwatch.lanmonitor.2_105_0"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

        # Check for --switch-role flag to force role selection
        force_select = "--switch-role" in sys.argv

        role = None
        if not force_select:
            role = load_saved_role()

        if not role:
            role = show_role_selector()

        if not role:
            # User closed the selector without choosing
            sys.exit(0)

        if role == "manager":
            launch_manager()
        elif role == "client":
            launch_client()
        else:
            print(f"[Launcher] Unknown role: {role}")
            sys.exit(1)

    except Exception:
        crash_log = os.path.join(get_app_dir(), "crash_log.txt")
        try:
            with open(crash_log, "w", encoding="utf-8") as f:
                traceback.print_exc(file=f)
        except Exception:
            pass
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
