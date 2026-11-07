"""Legacy telemetry alias without blocking CPU sampling."""
from ingenuity.core.system_monitor import SystemMonitor

def get_system_status():
    return SystemMonitor.get_status()
