"""PCA9685 commands for the calibrated continuous-rotation servos."""
import math
import os
import threading


class Gimbal:
    PCA_FREQUENCY = 50
    PAN_CHANNEL, TILT_CHANNEL = 0, 1
    PAN_NEUTRAL_US, TILT_NEUTRAL_US = 1500, 1500
    MAX_PULSE_OFFSET_US = 250

    def __init__(self):
        import board
        import busio
        from adafruit_pca9685 import PCA9685
        self._lock = threading.RLock()
        self._closed = False
        self.pan_speed = self.tilt_speed = 0.0
        self.pan_neutral = int(os.getenv('PAN_NEUTRAL_US', str(self.PAN_NEUTRAL_US)))
        self.tilt_neutral = int(os.getenv('TILT_NEUTRAL_US', str(self.TILT_NEUTRAL_US)))
        if not all(1000 <= n <= 2000 for n in (self.pan_neutral, self.tilt_neutral)):
            raise ValueError('Neutri servo fuori intervallo 1000..2000 us')
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.pca = None
        try:
            self.pca = PCA9685(self.i2c, reference_clock_speed=27_750_000)
            self.pca.frequency = self.PCA_FREQUENCY
            self.pan_servo = self.pca.channels[self.PAN_CHANNEL]
            self.tilt_servo = self.pca.channels[self.TILT_CHANNEL]
            self.stop()
        except Exception:
            try:
                if self.pca is not None:
                    self.pca.deinit()
            finally:
                self.i2c.deinit()
            raise

    @staticmethod
    def _pulse_to_duty_cycle(pulse_us):
        return round(pulse_us / (1_000_000 / Gimbal.PCA_FREQUENCY) * 65535)

    def _set_speed(self, servo, neutral_us, speed):
        speed = float(speed)
        if not math.isfinite(speed) or not -1 <= speed <= 1:
            raise ValueError('Velocità servo richiesta nell’intervallo [-1, 1], non un angolo')
        if self._closed:
            raise RuntimeError('Gimbal chiuso')
        servo.duty_cycle = (0 if speed == 0 else round(
            (neutral_us + speed*self.MAX_PULSE_OFFSET_US) * self.pca.frequency * 65535 / 1_000_000))
        return speed

    def pan(self, speed):
        with self._lock:
            self.pan_speed = self._set_speed(self.pan_servo, self.pan_neutral, speed)

    def tilt(self, speed):
        with self._lock:
            self.tilt_speed = self._set_speed(self.tilt_servo, self.tilt_neutral, speed)

    def stop_pan(self):
        self.pan(0.0)

    def stop_tilt(self):
        self.tilt(0.0)

    def stop(self):
        with self._lock:
            if self._closed:
                return
            try:
                self.stop_pan()
            finally:
                self.stop_tilt()

    def center(self):
        """Continuous servos cannot command an absolute center; send neutral."""
        self.stop()

    def close(self):
        with self._lock:
            if self._closed:
                return
            try:
                self.stop()
            finally:
                try:
                    self.pca.deinit()
                finally:
                    self._closed = True
                    self.i2c.deinit()
