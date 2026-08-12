import os
import time

import psutil


def get_cpu_usage() -> float:
    """
    Restituisce l'utilizzo della CPU in percentuale.
    """
    return psutil.cpu_percent(interval=0.1)


def get_memory_usage() -> dict:
    """
    Restituisce informazioni sull'utilizzo della RAM.
    """
    memory = psutil.virtual_memory()

    return {
        "used_mb": round(memory.used / 1024 / 1024, 1),
        "total_mb": round(memory.total / 1024 / 1024, 1),
        "percent": memory.percent,
    }


def get_temperature() -> float | None:
    """
    Legge la temperatura della CPU del Raspberry Pi.
    """

    thermal_path = "/sys/class/thermal/thermal_zone0/temp"

    try:
        with open(thermal_path, "r") as file:
            temperature = int(file.read().strip())

        return round(temperature / 1000, 1)

    except (FileNotFoundError, ValueError):
        return None


def get_uptime() -> int:
    """
    Restituisce l'uptime del sistema in secondi.
    """

    return int(time.time() - psutil.boot_time())


def format_uptime(seconds: int) -> str:
    """
    Converte i secondi di uptime in una forma leggibile.
    """

    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    if days > 0:
        return f"{days}g {hours}h {minutes}m"

    if hours > 0:
        return f"{hours}h {minutes}m"

    return f"{minutes}m"


def get_system_status() -> dict:
    """
    Restituisce lo stato completo del sistema Ingenuity.
    """

    uptime = get_uptime()
    memory = get_memory_usage()

    return {
        "cpu": get_cpu_usage(),
        "memory": memory,
        "temperature": get_temperature(),
        "uptime": uptime,
        "uptime_formatted": format_uptime(uptime),
    }
