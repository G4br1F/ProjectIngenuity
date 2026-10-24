"""Explicit, vision-only target selection.

This module intentionally contains no gimbal, GPIO, servo, or PCA9685 code.
"""

from __future__ import annotations

import threading
import time
from typing import Any


class TrackingManager:
    """Keeps the user-selected YOLO target stable between detections."""

    def __init__(self, max_match_distance: int = 180) -> None:
        self._lock = threading.Lock()
        self._max_match_distance_sq = max_match_distance**2
        self._mode = "IDLE"
        self._target: dict[str, Any] | None = None
        self._last_seen: float | None = None

    def select(self, detections: list[dict[str, Any]], index: int) -> dict[str, Any]:
        """Select one currently visible detection and enter TRACKING mode."""
        if index < 0 or index >= len(detections):
            raise ValueError("Indice target non valido")

        candidate = detections[index]
        if "class" not in candidate or "center" not in candidate:
            raise ValueError("Detection priva di classe o centro")

        with self._lock:
            self._target = dict(candidate)
            self._mode = "TRACKING"
            self._last_seen = time.monotonic()
            return self._snapshot_locked()

    def stop(self) -> dict[str, Any]:
        """Immediately clear the selected target.  No hardware action occurs."""
        with self._lock:
            self._mode = "IDLE"
            self._target = None
            self._last_seen = None
            return self._snapshot_locked()

    def update(self, detections: list[dict[str, Any]]) -> dict[str, Any]:
        """Associate the target with the closest detection of the same class."""
        with self._lock:
            if self._mode == "IDLE" or self._target is None:
                return self._snapshot_locked()

            previous_x, previous_y = self._target["center"]
            same_class = [
                detection
                for detection in detections
                if detection.get("class") == self._target.get("class")
                and isinstance(detection.get("center"), list)
                and len(detection["center"]) == 2
            ]

            if same_class:
                nearest = min(
                    same_class,
                    key=lambda detection: (
                        (detection["center"][0] - previous_x) ** 2
                        + (detection["center"][1] - previous_y) ** 2
                    ),
                )
                distance_sq = (
                    (nearest["center"][0] - previous_x) ** 2
                    + (nearest["center"][1] - previous_y) ** 2
                )
                if distance_sq <= self._max_match_distance_sq:
                    self._target = dict(nearest)
                    self._mode = "TRACKING"
                    self._last_seen = time.monotonic()
                    return self._snapshot_locked()

            # A missing target is only reported.  Nothing is moved or inferred.
            self._mode = "LOST"
            return self._snapshot_locked()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> dict[str, Any]:
        return {
            "mode": self._mode,
            "target": None if self._target is None else dict(self._target),
            "actuation": "disabled",
        }
