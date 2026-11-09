"""Bounded, proportional control for continuous-rotation servos.

Only fresh observations authorize short movement pulses. All commands, including
selection and STOP, are serialized with the control loop.
"""
from collections import deque
from statistics import median
import logging
import os
import threading
import time
from ingenuity.vision.tracking import TrackingManager

log = logging.getLogger(__name__)


class PanTracker:
    PERIOD = 0.005
    MAX_SPEED = 0.10
    MIN_SPEED = 0.025
    ACCELERATION = 0.5
    ENTER_DEADBAND = 0.06
    EXIT_DEADBAND = 0.09
    MAX_PULSE_SECONDS = 0.035
    MIN_PULSE_SECONDS = 0.020
    SETTLE_SECONDS = 0.060

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
        self._observe_after = float("-inf")
        self._pulse_active = False
        self._last_pan_sign = 0
        self._last_step = self.clock()
        self._centered = [True, True]
        self._speed = [0.0, 0.0]
        self._error = None
        self._pan_samples = deque(maxlen=3)
        self._evidence_sign = 0
        self._evidence_count = 0
        if autostart:
            self._thread = threading.Thread(target=self._loop, name='gimbal-tracking', daemon=True)
            self._thread.start()

    def _halt(self):
        self._speed = [0.0, 0.0]
        self.gimbal.stop()

    def select(self, index, version):
        with self._lock:
            now = self.clock()
            current = self.camera.get_detection_snapshot()
            resolver = getattr(self.camera, 'get_selection_snapshot', None)
            selected = resolver(version) if resolver else current
            # Validate and associate on a temporary tracker; rejected clicks leave
            # the existing target and pulse untouched.
            candidate = TrackingManager(self.tracker.max_distance,
                                        self.tracker.stale_after, self.tracker.reacquire_for)
            candidate.select(selected, index, version, now)
            state = candidate.update(current, now)
            if state['mode'] != 'TRACKING':
                raise ValueError('Bersaglio assente, ambiguo o scaduto: seleziona di nuovo')
            index_now = next(i for i, item in enumerate(current['objects'])
                             if item == state['target'])
            self._halt()
            self.tracker.select(current, index_now, current['version'], now)
            self._pulse_active = False
            self._pulse_until = 0.0
            self._observe_after = now + self.SETTLE_SECONDS
            self._last_version = current['version']
            self._last_pan_sign = 0
            self._centered = [True, True]
            self._reset_pan_filter()
            width = current['size'][0]
            self._stable_pan_error((state['target']['center'][0]-width/2)/(width/2))
            return self.snapshot()

    def stop_tracking(self):
        with self._lock:
            self.tracker.stop()
            self._pulse_until = 0.0
            self._pulse_active = False
            self._reset_pan_filter()
            self._halt()
            return self.snapshot()

    def _reset_pan_filter(self):
        self._pan_samples.clear()
        self._evidence_sign = 0
        self._evidence_count = 0

    def _stable_pan_error(self, raw):
        """Called once per eligible detection batch, never per control tick."""
        if abs(raw) <= self.ENTER_DEADBAND:
            self._centered[0] = True
            self._reset_pan_filter()
            self._pan_samples.append(raw)
            return None
        self._pan_samples.append(raw)
        filtered = median(self._pan_samples)
        threshold = self.EXIT_DEADBAND if self._centered[0] else self.ENTER_DEADBAND
        if abs(raw) <= threshold or abs(filtered) <= threshold or raw*filtered <= 0:
            self._evidence_sign = 0
            self._evidence_count = 0
            return None
        sign = 1 if raw > 0 else -1
        if sign != self._evidence_sign:
            self._evidence_sign, self._evidence_count = sign, 1
        else:
            self._evidence_count += 1
        # Near the centre require three consistent observations; farther away two.
        needed = 3 if abs(filtered) < 0.25 else 2
        return filtered if self._evidence_count >= needed else None

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
        if axis == 0:
            return 0.20 if desired > 0 else -0.40
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
            width, height = batch['size']
            if state['mode'] != 'TRACKING':
                if self._pulse_active:
                    self._observe_after = now + self.SETTLE_SECONDS
                self._pulse_active = False
                self._reset_pan_filter()
                self._halt()
                return
            x, y = state['target']['center']
            error = (x-width/2)/(width/2)
            if self._pulse_active:
                # Never extend a movement because another inference finished.
                crossed = error * self._pulse_error < 0
                if now >= self._pulse_until or abs(error) <= self.ENTER_DEADBAND or crossed:
                    self._halt()
                    self._pulse_active = False
                    self._observe_after = now + self.SETTLE_SECONDS
                    self._reset_pan_filter()
                    if abs(error) <= self.ENTER_DEADBAND or crossed:
                        self._centered[0] = True
                return
            if (batch['version'] == self._last_version or
                    batch['captured_at'] < self._observe_after):
                self._halt()
                return
            self._last_version = batch['version']
            stable_error = self._stable_pan_error(error)
            pan = 0.0 if stable_error is None else self._command(stable_error, 0, dt)
            if stable_error is not None:
                error = stable_error
            tilt = self._command((y-height/2)/(height/2), 1, dt) if self.tilt_enabled else 0.0
            if pan == 0 and tilt == 0:
                self._halt()
                return
            # Effective servo commands with proportional duration instead of a
            # ramp trapped inside the servo's dead zone.
            scale = min(1.0, max(0.0, (abs(error)-self.ENTER_DEADBAND)/0.60))
            duration = self.MIN_PULSE_SECONDS + scale*(self.MAX_PULSE_SECONDS-self.MIN_PULSE_SECONDS)
            sign = 1 if pan > 0 else -1 if pan < 0 else 0
            if sign and self._last_pan_sign and sign != self._last_pan_sign:
                duration = self.MIN_PULSE_SECONDS
            # Clockwise (1550 us) produces more travel on this gimbal.
            # Keep at least one nominal 50 Hz PWM period.
            if pan > 0:
                duration = max(0.020, duration * 0.75)
            if sign:
                self._last_pan_sign = sign
            deadline = batch['captured_at'] + self.tracker.stale_after
            if deadline-now < duration:
                self._halt()
                return
            self._pulse_until = now + duration
            self._pulse_error = error
            self._pulse_active = True
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
