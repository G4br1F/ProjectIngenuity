"""Nonblocking telemetry, sampled at most once per second across clients."""
import socket
import threading
import time
import psutil


class SystemMonitor:
    _lock = threading.Lock()
    _cached = {}
    _sampled = -1.0

    @staticmethod
    def get_ip():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(('8.8.8.8',80))
                return sock.getsockname()[0]
        except OSError:
            return 'N/D'

    @staticmethod
    def get_temperature():
        try:
            with open('/sys/class/thermal/thermal_zone0/temp') as file:
                return round(int(file.read())/1000,1)
        except (OSError, ValueError):
            return None

    @classmethod
    def get_status(cls):
        with cls._lock:
            now = time.monotonic()
            if now-cls._sampled >= 1:
                cls._cached = {'cpu': round(psutil.cpu_percent(interval=None),1),
                               'ram': round(psutil.virtual_memory().percent,1),
                               'disk': round(psutil.disk_usage('/').percent,1),
                               'temperature': cls.get_temperature(),
                               'uptime': int(time.time()-psutil.boot_time()),
                               'hostname': socket.gethostname(), 'ip': cls.get_ip()}
                cls._sampled = now
            return dict(cls._cached)
