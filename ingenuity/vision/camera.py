import cv2
import threading
import time
from pathlib import Path

from picamera2 import Picamera2
from ultralytics import YOLO


class Camera:
    """Camera stream and YOLO detection overlay.

    This class is deliberately vision-only. It does not import or call any
    PAN/TILT or PCA9685 code.
    """

    VIDEO_WIDTH = 960
    VIDEO_HEIGHT = 540
    VIDEO_FPS = 20.0
    JPEG_QUALITY = 80

    YOLO_WIDTH = 320
    YOLO_HEIGHT = 180
    INFERENCE_INTERVAL = 1.0

    def __init__(self):
        self.picam2 = Picamera2()

        # Incrementato ad ogni nuova inferenza YOLO.
        # Serve al tracking per distinguere una nuova detection
        # dalla stessa detection già elaborata.
        self._detection_version = 0

        frame_duration_us = int(
            1_000_000 / self.VIDEO_FPS
        )

        camera_config = self.picam2.create_preview_configuration(
            main={
                "size": (
                    self.VIDEO_WIDTH,
                    self.VIDEO_HEIGHT
                ),
                "format": "RGB888",
            },
            controls={
                "FrameDurationLimits": (
                    frame_duration_us,
                    frame_duration_us
                ),
            },
            buffer_count=4,
        )

        self.picam2.configure(camera_config)
        self.picam2.start()

        time.sleep(1)

        project_root = Path(__file__).resolve().parents[2]
        model_path = project_root / "yolo26n_ncnn_model"

        self.model = YOLO(
            str(model_path),
            task="detect"
        )

        # latest_frame è un frame BGR pulito per YOLO.
        # Il JPEG viene annotato separatamente.
        self.latest_frame = None
        self.latest_jpeg = None
        self.latest_detections = []

        self.frame_id = 0
        self.camera_fps = 0.0
        self.inference_fps = 0.0

        self._lock = threading.Lock()
        self._running = True

        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            daemon=True
        )

        self._vision_thread = threading.Thread(
            target=self._vision_loop,
            daemon=True
        )

        self._capture_thread.start()
        self._vision_thread.start()

    def _capture_loop(self):

        frame_interval = 1.0 / self.VIDEO_FPS
        previous_time = time.time()

        while self._running:

            loop_start = time.time()

            try:
                frame = self.picam2.capture_array()

            except Exception:
                time.sleep(0.02)
                continue

            frame = cv2.cvtColor(
                frame,
                cv2.COLOR_RGB2BGR
            )

            now = time.time()

            delta = now - previous_time

            fps = (
                1.0 / delta
                if delta > 0
                else 0.0
            )

            previous_time = now

            with self._lock:

                # Frame pulito per YOLO.
                self.latest_frame = frame.copy()

                # Copia delle ultime detection per
                # disegnarle sul video.
                detections = list(
                    self.latest_detections
                )

                self.camera_fps = fps

            image_height, image_width = frame.shape[:2]

            image_center_x = image_width // 2
            image_center_y = image_height // 2

            # ==================================================
            # CENTRO IMMAGINE
            # ==================================================

            cross_half_size = 14

            cv2.line(
                frame,
                (
                    image_center_x - cross_half_size,
                    image_center_y
                ),
                (
                    image_center_x + cross_half_size,
                    image_center_y
                ),
                (0, 255, 255),
                2,
            )

            cv2.line(
                frame,
                (
                    image_center_x,
                    image_center_y - cross_half_size
                ),
                (
                    image_center_x,
                    image_center_y + cross_half_size
                ),
                (0, 255, 255),
                2,
            )

            # ==================================================
            # DETECTION OVERLAY
            # ==================================================

            for detection in detections:

                x1, y1, x2, y2 = detection["box"]

                center_x, center_y = detection["center"]

                error_x = (
                    center_x -
                    image_center_x
                )

                error_y = (
                    center_y -
                    image_center_y
                )

                cv2.rectangle(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    (0, 255, 0),
                    2,
                )

                cv2.circle(
                    frame,
                    (center_x, center_y),
                    5,
                    (0, 0, 255),
                    -1,
                )

                cv2.line(
                    frame,
                    (
                        image_center_x,
                        image_center_y
                    ),
                    (
                        center_x,
                        center_y
                    ),
                    (255, 128, 0),
                    1,
                )

                label = (
                    f'{detection["class"]} '
                    f'{detection["confidence"]:.0%} '
                    f"X:{error_x:+d} "
                    f"Y:{error_y:+d}"
                )

                cv2.putText(
                    frame,
                    label,
                    (
                        x1,
                        max(y1 - 10, 20)
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 255, 0),
                    2,
                )

            # ==================================================
            # JPEG
            # ==================================================

            success, buffer = cv2.imencode(
                ".jpg",
                frame,
                [
                    cv2.IMWRITE_JPEG_QUALITY,
                    self.JPEG_QUALITY
                ],
            )

            if success:

                with self._lock:

                    self.latest_jpeg = (
                        buffer.tobytes()
                    )

                    self.frame_id += 1

            remaining = (
                frame_interval -
                (time.time() - loop_start)
            )

            if remaining > 0:
                time.sleep(remaining)

    def _vision_loop(self):

        while self._running:

            start_time = time.time()

            with self._lock:

                frame = (
                    None
                    if self.latest_frame is None
                    else self.latest_frame.copy()
                )

            if frame is None:

                time.sleep(0.05)
                continue

            frame_height, frame_width = (
                frame.shape[:2]
            )

            small_frame = cv2.resize(
                frame,
                (
                    self.YOLO_WIDTH,
                    self.YOLO_HEIGHT
                ),
                interpolation=cv2.INTER_AREA,
            )

            results = self.model(
                small_frame,
                conf=0.50,
                iou=0.30,
                verbose=False
            )

            result = results[0]

            detections = []

            scale_x = (
                frame_width /
                self.YOLO_WIDTH
            )

            scale_y = (
                frame_height /
                self.YOLO_HEIGHT
            )

            if result.boxes is not None:

                for box in result.boxes:

                    confidence = float(
                        box.conf[0]
                    )

                    class_id = int(
                        box.cls[0]
                    )

                    x1, y1, x2, y2 = map(
                        int,
                        box.xyxy[0]
                    )

                    x1 = int(
                        x1 * scale_x
                    )

                    y1 = int(
                        y1 * scale_y
                    )

                    x2 = int(
                        x2 * scale_x
                    )

                    y2 = int(
                        y2 * scale_y
                    )

                    center_x = (
                        x1 + x2
                    ) // 2

                    center_y = (
                        y1 + y2
                    ) // 2

                    detections.append(
                        {
                            "class": self.model.names[
                                class_id
                            ],
                            "confidence": round(
                                confidence,
                                3
                            ),
                            "box": [
                                x1,
                                y1,
                                x2,
                                y2
                            ],
                            "center": [
                                center_x,
                                center_y
                            ],
                        }
                    )

            elapsed = (
                time.time() -
                start_time
            )

            inference_fps = (
                1.0 / elapsed
                if elapsed > 0
                else 0.0
            )

            with self._lock:

                # Pubblica la nuova detection.
                self.latest_detections = detections

                # Segnala che è arrivato un nuovo
                # risultato YOLO.
                self._detection_version += 1

                self.inference_fps = inference_fps

            remaining = (
                self.INFERENCE_INTERVAL -
                elapsed
            )

            if remaining > 0:
                time.sleep(remaining)

    def frames(self):

        last_frame_id = -1

        while self._running:

            with self._lock:

                jpeg = self.latest_jpeg

                current_frame_id = (
                    self.frame_id
                )

            if (
                jpeg is None
                or current_frame_id == last_frame_id
            ):

                time.sleep(0.001)
                continue

            last_frame_id = current_frame_id

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: "
                + str(
                    len(jpeg)
                ).encode()
                + b"\r\n\r\n"
                + jpeg
                + b"\r\n"
            )

    def get_detections(self):

        with self._lock:
            return list(
                self.latest_detections
            )

    def get_detection_version(self):

        with self._lock:
            return self._detection_version

    def get_camera_fps(self):

        with self._lock:
            return round(
                self.camera_fps,
                1
            )

    def get_inference_fps(self):

        with self._lock:
            return round(
                self.inference_fps,
                1
            )

    def stop(self):

        self._running = False

        self.picam2.stop()