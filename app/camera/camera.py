import cv2
import threading
import time


class Camera:
    def __init__(
        self,
        device: str = "/dev/video0",
        width: int = 640,
        height: int = 480,
        fps: int = 30,
    ):
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps

        self.capture = None

        self.latest_frame = None
        self.lock = threading.Lock()

        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return

        self.capture = cv2.VideoCapture(
            self.device,
            cv2.CAP_V4L2,
        )

        if not self.capture.isOpened():
            raise RuntimeError(
                f"Impossibile aprire la camera {self.device}"
            )

        self.capture.set(
            cv2.CAP_PROP_FRAME_WIDTH,
            self.width,
        )

        self.capture.set(
            cv2.CAP_PROP_FRAME_HEIGHT,
            self.height,
        )

        self.capture.set(
            cv2.CAP_PROP_FPS,
            self.fps,
        )

        self.running = True

        self.thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
        )

        self.thread.start()

    def _capture_loop(self):
        while self.running:

            success, frame = self.capture.read()

            if not success:
                time.sleep(0.05)
                continue

            with self.lock:
                self.latest_frame = frame

    def get_frame(self):
        with self.lock:
            if self.latest_frame is None:
                return None

            return self.latest_frame.copy()

    def stop(self):
        self.running = False

        if self.thread is not None:
            self.thread.join(timeout=1)

        if self.capture is not None:
            self.capture.release()

        self.capture = None

    def is_running(self):
        return self.running
