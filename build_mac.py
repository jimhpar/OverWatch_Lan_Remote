"""
Build script to compile Overwatch for macOS into a standalone .app bundle and .dmg installer using PyInstaller.
Publisher: Blackbox THC
"""

import os
import subprocess
import sys


def build_mac():
    print("==================================================")
    print("Building Overwatch for macOS")
    print("Publisher: Blackbox THC")
    print("==================================================")

    if sys.platform != "darwin":
        print("[Notice] This script is designed to run natively on macOS (or a macOS GitHub Actions runner).")

    # Ensure PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    # Icon handling (.icns preferred on macOS, fallback without --icon flag to avoid format error)
    icon_args = []
    if os.path.exists("app_icon.icns"):
        icon_args = ["--icon=app_icon.icns"]

    # PyInstaller data delimiter on macOS/Linux is ':'
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconsole",
        "--windowed",
        "--onedir",
        "--name=Overwatch",
        *icon_args,
        "--add-data=style.qss:.",
        "--add-data=config.py:.",
        "--add-data=protocol.py:.",
        "--add-data=master_dashboard.py:.",
        "--add-data=employee_client.py:.",
        "--add-data=logo:logo",
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
        "--osx-bundle-identifier=com.blackbox.overwatch",
        "launcher.py"
    ]

    if os.path.exists("app_icon.ico"):
        cmd.insert(cmd.index("launcher.py"), "--add-data=app_icon.ico:.")

    print("\nPackaging Overwatch.app bundle...")
    subprocess.run(cmd, check=True)

    app_path = os.path.join("dist", "Overwatch.app")
    print(f"\nSUCCESS: macOS Application bundle created at '{app_path}'!")

    # Create .dmg and .zip on macOS
    if sys.platform == "darwin":
        dmg_path = os.path.join("dist", "Overwatch-macOS.dmg")
        zip_path = os.path.join("dist", "Overwatch-macOS.zip")
        print("\nPackaging .dmg disk image and .zip archive...")
        try:
            if os.path.exists(dmg_path):
                os.remove(dmg_path)
            subprocess.run([
                "hdiutil", "create",
                "-volname", "Overwatch",
                "-srcfolder", app_path,
                "-ov",
                "-format", "UDZO",
                dmg_path
            ], check=True)
            print(f"SUCCESS: Installer created at '{dmg_path}'!")
        except Exception as e:
            print(f"Notice: .dmg creation skipped ({e}).")

        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
            subprocess.run([
                "ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                app_path, zip_path
            ], check=True)
            print(f"SUCCESS: Zip archive created at '{zip_path}'!")
        except Exception as e:
            print(f"Notice: .zip creation skipped ({e}).")

    print("\n==================================================")
    print("Build complete!")
    print("  dist/Overwatch.app")
    print("==================================================")


if __name__ == "__main__":
    build_mac()
