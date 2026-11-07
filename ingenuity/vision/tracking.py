"""Versioned target selection and conservative association of detections."""
from copy import deepcopy
import math
import threading
import time


class TrackingManager:
    def __init__(self, max_match_distance=180, stale_after=1.5, reacquire_for=1.0):
        self._lock = threading.RLock()
        self.max_distance = max_match_distance
        self.stale_after = stale_after
        self.reacquire_for = reacquire_for
        self._mode = 'IDLE'
        self._target = None
        self._last_seen = None
        self._version = -1
        self._reason = None

    def _fresh(self, batch, now):
        stamp = batch.get('captured_at')
        return stamp is not None and 0 <= now - stamp <= self.stale_after

    def select(self, batch, index, version, now=None):
        now = time.monotonic() if now is None else now
        with self._lock:
            if version != batch['version'] or not self._fresh(batch, now):
                raise ValueError('Detection scadute: attendi il prossimo aggiornamento e seleziona di nuovo')
            if type(index) is not int or not 0 <= index < len(batch['objects']):
                raise ValueError('Indice target non valido')
            target = batch['objects'][index]
            if 'class' not in target or len(target.get('center', [])) != 2:
                raise ValueError('Detection priva di classe o centro')
            self._target = deepcopy(target)
            self._mode = 'TRACKING'
            self._version = version
            self._last_seen = batch['captured_at']
            self._reason = None
            return self.snapshot()

    def stop(self):
        with self._lock:
            self._mode, self._target, self._last_seen = 'IDLE', None, None
            self._reason = None
            return self.snapshot()

    def update(self, batch, now=None):
        now = time.monotonic() if now is None else now
        with self._lock:
            if self._mode == 'IDLE' or self._target is None:
                return self.snapshot()
            if not self._fresh(batch, now):
                self._mode, self._reason = 'LOST', 'stale_detection'
                return self.snapshot()
            if batch['version'] == self._version:
                return self.snapshot()
            self._version = batch['version']
            if self._mode == 'LOST' and now - self._last_seen > self.reacquire_for:
                self._reason = 'reselect_required'
                return self.snapshot()
            x, y = self._target['center']
            candidates = []
            for item in batch['objects']:
                if item.get('class') != self._target['class']:
                    continue
                cx, cy = item['center']
                distance = math.hypot(cx - x, cy - y)
                # Gate large changes in size as well as position.
                old_box, box = self._target.get('box'), item.get('box')
                if old_box and box:
                    old_area = max(1, (old_box[2]-old_box[0]) * (old_box[3]-old_box[1]))
                    area = max(1, (box[2]-box[0]) * (box[3]-box[1]))
                    if not 0.4 <= area / old_area <= 2.5:
                        continue
                if distance <= self.max_distance:
                    candidates.append((distance, item))
            candidates.sort(key=lambda pair: pair[0])
            # Do not guess between two similarly plausible objects of the same class.
            ambiguous = len(candidates) > 1 and candidates[1][0] - candidates[0][0] < 25
            if not candidates or ambiguous:
                self._mode = 'LOST'
                self._reason = 'ambiguous_target' if ambiguous else 'target_missing'
            else:
                self._target = deepcopy(candidates[0][1])
                self._last_seen = batch['captured_at']
                self._mode, self._reason = 'TRACKING', None
            return self.snapshot()

    def snapshot(self):
        with self._lock:
            return {'mode': self._mode, 'target': deepcopy(self._target),
                    'version': self._version, 'reason': self._reason}
