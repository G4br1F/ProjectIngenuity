import threading
import time


class PanTracker:
    IMAGE_WIDTH = 960

    # Zona centrale in cui il PAN resta fermo.
    DEADBAND = 40

    # Velocità massima iniziale, da calibrare.
    MAX_SPEED = 0.10

    # Velocità minima richiesta quando fuori dalla deadband.
    MIN_SPEED = 0.02

    # Errore in pixel necessario per raggiungere MAX_SPEED.
    MAX_ERROR = 300

    # Invertire a -1 se il PAN corregge nella direzione sbagliata.
    PAN_DIRECTION = 1

    def __init__(self, camera, gimbal, tracker):
        self.camera = camera
        self.gimbal = gimbal
        self.tracker = tracker

        self._running = True
        self._last_detection_version = -1

        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
        )
        self._thread.start()

    def _stop_pan(self):
        self.gimbal.stop_pan()

    def _loop(self):
        while self._running:
            try:
                state = self.tracker.snapshot()

                if state["mode"] != "TRACKING":
                    self._stop_pan()
                    time.sleep(0.05)
                    continue

                version = self.camera.get_detection_version()

                if version == self._last_detection_version:
                    time.sleep(0.02)
                    continue

                self._last_detection_version = version

                detections = self.camera.get_detections()
                state = self.tracker.update(detections)

                if state["mode"] != "TRACKING":
                    self._stop_pan()
                    continue

                target = state.get("target")

                if target is None:
                    self._stop_pan()
                    continue

                target_x = target["center"][0]
                image_center_x = self.IMAGE_WIDTH / 2
                error_x = target_x - image_center_x

                if abs(error_x) <= self.DEADBAND:
                    self._stop_pan()
                    print(f"[PAN] TARGET CENTRATO X={target_x}")
                    continue

                magnitude = min(
                    abs(error_x) / self.MAX_ERROR,
                    1.0,
                )

                speed = (
                    self.MIN_SPEED
                    + magnitude * (self.MAX_SPEED - self.MIN_SPEED)
                )

                # Il segno dipende dalla posizione del target.
                # Se la correzione va nel verso sbagliato,
                # impostare PAN_DIRECTION = 1.
                if error_x > 0:
                    speed = -speed
                else:
                    speed = speed

                speed *= self.PAN_DIRECTION

                self.gimbal.pan(speed)

                print(
                    f"[PAN] target_x={target_x} "
                    f"error={error_x:+.0f} "
                    f"speed={speed:+.3f}"
                )

            except Exception as error:
                self._stop_pan()
                print(f"[PAN TRACKER] Errore: {error}")

            time.sleep(0.02)

        self._stop_pan()

    def stop(self):
        self._running = False
        self._stop_pan()

        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
