"""Bounded, proportional control for continuous-rotation servos.

Only fresh observations authorize short movement pulses. All commands, including
selection and STOP, are serialized with the control loop.
"""
import logging
import os
import threading
import time

log = logging.getLogger(__name__)


class PanTracker:
    PERIOD = 0.02
    MAX_SPEED = 0.10
    MIN_SPEED = 0.025
    ACCELERATION = 0.5
    ENTER_DEADBAND = 0.06
    EXIT_DEADBAND = 0.09
    MAX_PULSE_SECONDS = 0.18

    def __init__(self, camera, gimbal, tracker, *, autostart=True, clock=time.monotonic,
                 pan_direction=None, tilt_direction=None, tilt_enabled=None):
        self.camera, self.gimbal, self.tracker = camera, gimbal, tracker
        self.clock = clock
        self.pan_direction = int(os.getenv('PAN_DIRECTION', '-1')) if pan_direction is None else pan_direction
        self.tilt_direction = int(os.getenv('TILT_DIRECTION', '-1')) if tilt_direction is None else tilt_direction
        self.tilt_enabled = os.getenv('TRACK_TILT_ENABLED', '0') == '1' if tilt_enabled is None else tilt_enabled
        if self.pan_direction not in (-1, 1) or self.tilt_direction not in (-1, 1):
            raise ValueError('PAN_DIRECTION e TILT_DIRECTION devono essere -1 o 1')
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread = None
        self._last_version = -1
        self._pulse_until = 0.0
        self._last_step = self.clock()
        self._centered = [True, True]
        self._speed = [0.0, 0.0]
        self._error = None
        if autostart:
            self._thread = threading.Thread(target=self._loop, name='gimbal-tracking', daemon=True)
            self._thread.start()

    def _halt(self):
        self._speed = [0.0, 0.0]
        self.gimbal.stop()

    def select(self, index, version):
        with self._lock:
            # Stop first, including when a stale selection is rejected.
            self._halt()
            self.tracker.stop()
            self._pulse_until = 0.0
            self._last_version = -1
            self._centered = [True, True]
            self.tracker.select(self.camera.get_detection_snapshot(), index, version, self.clock())
            return self.snapshot()

    def stop_tracking(self):
        with self._lock:
            self.tracker.stop()
            self._pulse_until = 0.0
            self._halt()
            return self.snapshot()

    def _command(self, error, axis, dt):
        threshold = self.EXIT_DEADBAND if self._centered[axis] else self.ENTER_DEADBAND
        if abs(error) <= threshold:
            self._centered[axis] = True
            return 0.0
        self._centered[axis] = False
        magnitude = self.MIN_SPEED + (self.MAX_SPEED-self.MIN_SPEED) * min(
            1.0, (abs(error)-self.ENTER_DEADBAND) / (0.65-self.ENTER_DEADBAND))
        direction = self.pan_direction if axis == 0 else self.tilt_direction
        desired = magnitude * (1 if error > 0 else -1) * direction
        previous = self._speed[axis]
        # Cross through neutral rather than abruptly reversing.
        if desired * previous < 0:
            return 0.0
        step = self.ACCELERATION * dt
        return max(previous-step, min(previous+step, desired))

    def step(self, now=None):
        now = self.clock() if now is None else now
        with self._lock:
            if self._stop_event.is_set():
                self._halt()
                return
            dt = max(0.0, min(now-self._last_step, 0.1))
            self._last_step = now
            batch = self.camera.get_detection_snapshot()
            state = self.tracker.update(batch, now)
            if state['mode'] != 'TRACKING':
                self._halt()
                return
            if batch['version'] != self._last_version:
                self._last_version = batch['version']
                # Observation age includes inference time, not only publication time.
                self._pulse_until = min(now+self.MAX_PULSE_SECONDS,
                                        batch['captured_at']+self.tracker.stale_after)
            if now >= self._pulse_until:
                self._halt()
                return
            width, height = batch['size']
            x, y = state['target']['center']
            pan = self._command((x-width/2)/(width/2), 0, dt)
            tilt = self._command((y-height/2)/(height/2), 1, dt) if self.tilt_enabled else 0.0
            self.gimbal.pan(pan)
            self.gimbal.tilt(tilt)
            self._speed = [pan, tilt]
            self._error = None

    def _loop(self):
        try:
            while not self._stop_event.is_set():
                try:
                    self.step()
                except Exception as exc:
                    with self._lock:
                        self._error = str(exc)
                        self.tracker.stop()
                        try:
                            self._halt()
                        except Exception:
                            log.exception('Impossibile inviare il neutro al gimbal')
                    log.exception('Tracking arrestato per errore')
                self._stop_event.wait(self.PERIOD)
        finally:
            try:
                self._halt()
            except Exception:
                log.exception('Arresto finale gimbal fallito')

    def snapshot(self):
        with self._lock:
            return {**self.tracker.snapshot(), 'actuation': 'enabled',
                    'pan_speed': self._speed[0], 'tilt_speed': self._speed[1],
                    'tilt_enabled': self.tilt_enabled, 'error': self._error}

    def stop(self):
        self._stop_event.set()
        try:
            self.stop_tracking()
        finally:
            if self._thread and self._thread is not threading.current_thread():
                self._thread.join(timeout=2)
                if self._thread.is_alive():
                    raise RuntimeError('Il thread gimbal non si è arrestato')
