"""
Build script to compile LAN Screen Monitor into a single standalone Windows EXE using PyInstaller.
The launcher provides role selection (Client Mode / Manager Mode) on first run.
"""

import os
import subprocess
import sys

def build_executable():
    print("==================================================")
    print("Building Overwatch (Unified Launcher)")
    print("Publisher: Blackbox THC")
    print("==================================================")
    
    # Ensure PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    # Build single unified launcher EXE
    print("\nPackaging Overwatch.exe...")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconsole",
        "--onefile",
        "--name=Overwatch",
        "--icon=app_icon.ico",
        "--add-data=app_icon.ico;.",
        "--add-data=style.qss;.",
        "--add-data=config.py;.",
        "--add-data=protocol.py;.",
        "--add-data=master_dashboard.py;.",
        "--add-data=employee_client.py;.",
        "--add-data=logo;logo",
        "--hidden-import=websockets",
        "--hidden-import=websockets.exceptions",
        "--hidden-import=mss",
        "--hidden-import=cv2",
        "--hidden-import=numpy",
        "--hidden-import=pynput",
        "--hidden-import=pynput.mouse",
        "--hidden-import=pynput.keyboard",
        "--hidden-import=master_dashboard",
        "--hidden-import=employee_client",
        "launcher.py"
    ]
    subprocess.run(cmd, check=True)
    print("SUCCESS: Overwatch.exe created in 'dist/' folder!")

    print("\n==================================================")
    print("Build complete!")
    print("  dist/Overwatch.exe")
    print("")
    print("Run with --switch-role flag to re-select mode:")
    print("  Overwatch.exe --switch-role")
    print("==================================================")

if __name__ == "__main__":
    build_executable()
