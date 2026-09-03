"""
cx_Freeze setup script to build native MSI installer for Windows deployment.
Installs LAN Screen Monitor to C:\\Program Files\\LAN Screen Monitor.
Publisher: Blackbox THC

Usage:
  python setup_msi.py bdist_msi
"""

import sys
from cx_Freeze import setup, Executable

# Include all required data files and packages
build_exe_options = {
    "packages": [
        "os", "sys", "json", "asyncio", "socket", "threading", "traceback",
        "PyQt6", "websockets", "mss", "cv2", "pynput", "numpy",
    ],
    "include_files": [
        "app_icon.ico",
        "style.qss",
        "config.py",
        "protocol.py",
        "master_dashboard.py",
        "employee_client.py",
        "logo",
    ],
    "excludes": ["tkinter", "unittest"],
}

# Base for Windows GUI application (no console window)
base = "gui" if sys.platform == "win32" else None

# MSI directory definitions
msi_directories = [
    ("ProgramMenuFolder", "TARGETDIR", "."),
    ("DesktopFolder", "TARGETDIR", "."),
    ("StartupFolder", "TARGETDIR", "."),
]

# MSI custom tables for Desktop, Start Menu (Search indexable), and Startup shortcuts
msi_data = {
    "Shortcut": [
        (
            "DesktopShortcut",
            "DesktopFolder",
            "Overwatch",
            "TARGETDIR",
            "[TARGETDIR]Overwatch.exe",
            None,
            "Overwatch LAN Live Screen Monitoring System",
            None,
            "InstallIcon",
            None,
            None,
            "TARGETDIR",
        ),
        (
            "ProgramMenuShortcut",
            "ProgramMenuFolder",
            "Overwatch",
            "TARGETDIR",
            "[TARGETDIR]Overwatch.exe",
            None,
            "Overwatch LAN Live Screen Monitoring System",
            None,
            "InstallIcon",
            None,
            None,
            "TARGETDIR",
        ),
        (
            "StartupShortcut",
            "StartupFolder",
            "Overwatch",
            "TARGETDIR",
            "[TARGETDIR]Overwatch.exe",
            None,
            "Overwatch LAN Live Screen Monitoring System",
            None,
            "InstallIcon",
            None,
            None,
            "TARGETDIR",
        ),
    ]
}

# MSI installer options
bdist_msi_options = {
    "all_users": True,
    "initial_target_dir": r"[ProgramFiles64Folder]\Overwatch",
    "install_icon": "app_icon.ico",
    "directories": msi_directories,
    "data": msi_data,
}

executables = [
    Executable(
        "launcher.py",
        base=base,
        target_name="Overwatch.exe",
        copyright="Copyright 2026 Blackbox THC",
        icon="app_icon.ico",
    ),
]

setup(
    name="Overwatch",
    version="4.50.2",
    description="Overwatch LAN Live Screen Monitoring System v4.50.2",
    author="Blackbox THC",
    author_email="",
    options={
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options,
    },
    executables=executables,
)
