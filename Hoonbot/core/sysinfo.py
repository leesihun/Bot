"""System information via psutil.

Returns a compact status string (CPU, RAM, disk, battery) suitable for
injection into the LLM context. Used by the heartbeat to enable proactive
alerts (e.g. low disk space, high CPU, low battery).

psutil is optional — returns empty string if not installed.
"""
import logging

logger = logging.getLogger(__name__)


def get_system_info() -> str:
    """Return a compact system status block, or empty string if psutil unavailable."""
    try:
        import psutil
    except ImportError:
        return ""

    try:
        cpu = psutil.cpu_percent(interval=0.1)

        vm = psutil.virtual_memory()
        ram_used = vm.used // (1024 ** 3)
        ram_total = vm.total // (1024 ** 3)

        # Use the root disk on Windows (C:\) or / on Unix
        import os
        disk_path = os.path.splitdrive(os.getcwd())[0] + "\\" if os.name == "nt" else "/"
        disk = psutil.disk_usage(disk_path)
        disk_used = disk.used // (1024 ** 3)
        disk_total = disk.total // (1024 ** 3)

        lines = [
            "## System Status",
            f"- CPU: {cpu:.0f}%",
            f"- RAM: {ram_used}GB / {ram_total}GB ({vm.percent:.0f}%)",
            f"- Disk: {disk_used}GB / {disk_total}GB ({disk.percent:.0f}%)",
        ]

        # Battery — not present on all machines
        try:
            battery = psutil.sensors_battery()
            if battery is not None:
                status = "charging" if battery.power_plugged else "discharging"
                lines.append(f"- Battery: {battery.percent:.0f}% ({status})")
        except Exception:
            pass

        return "\n".join(lines)

    except Exception as e:
        logger.debug(f"[SysInfo] Failed: {e}")
        return ""
