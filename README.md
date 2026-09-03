# 🛡️ Overwatch - LAN Live Screen Monitoring & Remote Management System

[![Version](https://img.shields.io/badge/version-4.50.1-blue.svg?style=flat-square)](https://github.com/jimhpar/OverWatch_Mac/releases)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-informational.svg?style=flat-square)](https://github.com/jimhpar/OverWatch_Mac/releases)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.14-success.svg?style=flat-square)](https://www.python.org/)
[![GUI Framework](https://img.shields.io/badge/GUI-PyQt6-blueviolet.svg?style=flat-square)](https://www.riverbankcomputing.com/software/pyqt/)
[![Protocol](https://img.shields.io/badge/transport-WebSockets%20%2F%20AsyncIO-orange.svg?style=flat-square)](https://github.com/jimhpar/OverWatch_Mac)
[![Publisher](https://img.shields.io/badge/publisher-Blackbox%20THC-red.svg?style=flat-square)](https://github.com/jimhpar/OverWatch_Mac)

**Overwatch** is an ultra-low latency, real-time LAN live screen monitoring, presentation, and remote management platform engineered for corporate offices, computer labs, educational institutions, and IT administration.

---

## ✨ Key Feature Highlights

### 🎛️ Master Manager Dashboard
- **Live Multi-Screen Grid Monitoring:** Monitor all connected employee screens simultaneously in high resolution with fluid responsive 3-column glassmorphic cards.
- **Interactive Drag & Drop:** Fluidly drag, reorder, and swap stream cards directly on the dashboard layout.
- **Single Screen Expanded View:** Expand any workstation's feed into high-res modal view with aspect-ratio preservation, live FPS counters, and latency diagnostics.
- **Full Bi-directional Remote Control:**
  - Real-time mouse cursor positioning and click dispatch (Left, Right, Middle).
  - High-precision scroll wheel support.
  - Complete keyboard event forwarding (including modifiers and special keys).
- **Client-to-Client Screen Projection:**
  - Project any employee PC's screen live to other employee workstations in a dedicated popup window (`SharedStreamViewer`).
  - Grant optional remote control access to the viewing client.
- **Admin Screen Broadcast:**
  - Broadcast the Manager's own display to selected employee PCs for presentations, training, and demonstrations.
  - Grant target workstations permission to control the Admin's display remotely.
- **Persistent Bandwidth Management:**
  - Choose between **Low**, **Medium**, and **High** quality presets with adaptive JPEG compression and configurable FPS limits (up to 120 FPS).
  - Automatically syncs bandwidth presets across restarts.
- **Emergency Flashing Alerts:** Send a full-screen red neon flashing border alert to notify specific employees or ping all clients at once.
- **Department & Room Grouping:** Organize connected workstations into custom groups (e.g., Office A, Server Room, Remote).
- **Administrative Security:** Built-in password protection overlay with SHA token handshakes.

---

### 💻 Employee Client Application
- **Silent Background Operation:** Runs smoothly in the Windows System Tray / macOS Menu Bar with dynamic connection status indicators:
  - 🟢 **Green:** Connected to Master Dashboard.
  - 🟡 **Orange:** Reconnecting / Authenticating.
  - 🔴 **Red:** Server offline / Connection Error.
- **Interactive Shared Stream Viewer:** Pops up a glassmorphic window whenever the Manager shares another workstation's feed or the Admin screen.
- **Adaptive Screen Throttling:** Automatically reduces transmission frame rates when the desktop is static to save local network bandwidth.
- **Zero-Config Auto-Discovery & Reconnection:** Automatically attempts reconnection in the background if the network connection drops.
- **Automatic System Startup:** Automatically registers to launch on system boot for both Windows (`HKCU Run Registry`) and macOS (`LaunchAgents plist`).

---

## 🏗️ Architecture & Protocol

```
+-------------------------------------------------------------------------+
|                        OVERWATCH UNIFIED LAUNCHER                       |
+------------------------------------+------------------------------------+
                                     |
              +----------------------+----------------------+
              |                                             |
   [ Manager / Master Mode ]                     [ Employee Client Mode ]
              |                                             |
     +--------+--------+                           +--------+--------+
     | WebSocket Server| <=======================> | WebSocket Client|
     | Screen Capturer |       Local LAN (WS)      | Screen Capturer |
     | Input Handler   |                           | Input Handler   |
     | Multi-Cast Relay|                           | Shared Viewer   |
     +-----------------+                           +-----------------+
```

- **Protocol:** High-speed WebSocket packet framing with Base64 compressed JPEG frames.
- **Latency:** Sub-30ms transmission across standard Gigabit LAN & Wi-Fi networks.
- **Static Detection:** Mean Squared Error (MSE) frame differential algorithms to eliminate redundant network traffic.

---

## 📥 Installation & Deployment

### 🪟 Windows Deployment
1. Download the latest installer from the **[Releases Page](https://github.com/jimhpar/OverWatch_Mac/releases)**:
   - 📦 **`Overwatch-4.50.1-win64.msi`** (Installs to `C:\Program Files\Overwatch\` with Desktop & Start Menu shortcuts).
   - ⚡ **`Overwatch.exe`** (Portable standalone single-file executable).
2. Run the application and choose **Manager Mode** for the administrator PC or **Client Mode** for employee PCs.

### 🍏 macOS Deployment
1. Download the latest macOS package from the **[Releases Page](https://github.com/jimhpar/OverWatch_Mac/releases)**:
   - 💿 **`Overwatch-macOS.dmg`** (Drag and drop `Overwatch.app` to your Applications folder).
   - 🗜️ **`Overwatch-macOS.zip`** (Compressed Application bundle).
2. **First-time macOS Permissions:**
   - **Screen Recording:** `System Settings` ➔ `Privacy & Security` ➔ `Screen Recording` ➔ Enable **Overwatch**.
   - **Accessibility:** `System Settings` ➔ `Privacy & Security` ➔ `Accessibility` ➔ Enable **Overwatch** (for remote control).

---

## 🛠️ Building from Source

### Prerequisites
- Python 3.10+ (Supported on Windows 10/11 and macOS Monterey / Ventura / Sonoma / Sequoia).
- Git.

### 1. Clone the Repository
```bash
git clone https://github.com/jimhpar/OverWatch_Mac.git
cd OverWatch_Mac
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Directly
```bash
# Run Unified Launcher (Role Selector)
python launcher.py

# Switch Role on an already configured machine
python launcher.py --switch-role
```

### 4. Compile Binaries

#### 🪟 On Windows:
```bash
# Compile Standalone Portable EXE
python build_exe.py

# Compile Native Machine-Wide MSI Installer
python setup_msi.py bdist_msi
```

#### 🍏 On macOS:
```bash
# Compile macOS .app bundle and .dmg installer
python3 build_mac.py
```

---

## ⚙️ Configuration & Switching Roles

- **Re-select App Role:** Launch the app with `--switch-role` or delete `~/lan_monitor_role.json`.
- **Change Master Server IP (Client):** Right-click the tray icon ➔ `Configure Master Server IP...`.
- **Change Employee Label (Client):** Right-click the tray icon ➔ `Set Employee Name...`.
- **Admin Settings (Manager):** Click `⚙️ App Settings` on the sidebar to configure server port, global quality, target FPS, and admin password.

---

## 🔒 Security & Privacy

- **Firewall Integration:** Automatic Windows Firewall TCP rule verification upon manager startup.
- **Encrypted Local Storage:** All configuration files are maintained in the user's home directory.
- **Passcode Protection:** Clients only establish video transmission after completing passcode verification with the Master server.

---

## 📄 License & Credits

Developed and Published by **Blackbox THC**.  
Copyright © 2026 Blackbox THC. All rights reserved.
