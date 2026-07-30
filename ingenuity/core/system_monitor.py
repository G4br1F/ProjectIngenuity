import os
import socket
import time

import psutil


class SystemMonitor:

    @staticmethod
    def get_cpu():
        return round(psutil.cpu_percent(interval=0.1), 1)

    @staticmethod
    def get_ram():
        return round(psutil.virtual_memory().percent, 1)

    @staticmethod
    def get_disk():
        return round(psutil.disk_usage("/").percent, 1)

    @staticmethod
    def get_uptime():
        return int(time.time() - psutil.boot_time())

    @staticmethod
    def get_hostname():
        return socket.gethostname()

    @staticmethod
    def get_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "N/D"

    @staticmethod
    def get_temperature():
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                temp = int(f.read()) / 1000
            return round(temp, 1)
        except Exception:
            return None

    @staticmethod
    def camera_connected():
        return os.path.exists("/dev/video0")

    @classmethod
    def get_status(cls):
        return {
            "cpu": cls.get_cpu(),
            "ram": cls.get_ram(),
            "disk": cls.get_disk(),
            "temperature": cls.get_temperature(),
            "uptime": cls.get_uptime(),
            "hostname": cls.get_hostname(),
            "ip": cls.get_ip(),
            "camera": cls.camera_connected()
        }
