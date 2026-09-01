"""
Helper script to instantly create Desktop shortcuts for MasterDashboard.exe and EmployeeClient.exe
"""
import os
import subprocess

def create_desktop_shortcuts():
    remote_dir = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(remote_dir, "dist")
    desktop_dir = os.path.expanduser("~/Desktop")

    master_exe = os.path.join(dist_dir, "MasterDashboard.exe")
    client_exe = os.path.join(dist_dir, "EmployeeClient.exe")

    master_lnk = os.path.join(desktop_dir, "Master Dashboard.lnk")
    client_lnk = os.path.join(desktop_dir, "Employee Client.lnk")

    ps_script = f"""
    $WshShell = New-Object -ComObject WScript.Shell

    if (Test-Path "{master_exe}") {{
        $Shortcut = $WshShell.CreateShortcut("{master_lnk}")
        $Shortcut.TargetPath = "{master_exe}"
        $Shortcut.WorkingDirectory = "{dist_dir}"
        $Shortcut.Save()
        Write-Host "Created Master Dashboard shortcut on Desktop!"
    }}

    if (Test-Path "{client_exe}") {{
        $Shortcut = $WshShell.CreateShortcut("{client_lnk}")
        $Shortcut.TargetPath = "{client_exe}"
        $Shortcut.WorkingDirectory = "{dist_dir}"
        $Shortcut.Save()
        Write-Host "Created Employee Client shortcut on Desktop!"
    }}
    """

    subprocess.run(["powershell", "-Command", ps_script], check=True)

if __name__ == "__main__":
    create_desktop_shortcuts()
