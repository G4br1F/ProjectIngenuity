import cv2
import threading
import time
from pathlib import Path

from ultralytics import YOLO


class Camera:
    # YOLO receives only a reduced snapshot. The dashboard video remains full size.
    YOLO_WIDTH = 320
    YOLO_HEIGHT = 180
    INFERENCE_INTERVAL = 1.0

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

        project_root = Path(__file__).resolve().parents[2]
        model_path = project_root / "yolo26n_ncnn_model"
        self.model = YOLO(
            str(model_path),
            task="detect",
        )

        self.latest_frame = None
        self.latest_yolo_frame = None
        self.latest_detections = []

        self.camera_fps = 0.0
        self.inference_fps = 0.0

        self.lock = threading.Lock()

        self.running = False
        self.capture_thread = None
        self.vision_thread = None

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

        self.capture_thread = threading.Thread(
            target=self._capture_loop,
            name="camera-capture",
            daemon=True,
        )
        self.vision_thread = threading.Thread(
            target=self._vision_loop,
            name="camera-yolo",
            daemon=True,
        )

        self.capture_thread.start()
        self.vision_thread.start()

    def _capture_loop(self):
        previous_time = time.monotonic()
        next_yolo_time = previous_time

        while self.running:
            success, frame = self.capture.read()

            if not success:
                time.sleep(0.05)
                continue

            now = time.monotonic()
            delta = now - previous_time
            camera_fps = 1.0 / delta if delta > 0 else 0.0
            previous_time = now

            yolo_frame = None

            if now >= next_yolo_time:
                yolo_frame = frame.copy()
                next_yolo_time = now + self.INFERENCE_INTERVAL

            with self.lock:
                self.camera_fps = camera_fps

                if yolo_frame is not None:
                    self.latest_yolo_frame = yolo_frame

                detections = list(self.latest_detections)

            selected_detection = next(
                (
                    detection
                    for detection in detections
                    if detection["selected"]
                ),
                None,
            )

            if selected_detection is not None:
                self._draw_tracking_overlay(
                    frame,
                    selected_detection,
                )

            with self.lock:
                self.latest_frame = frame

    def _vision_loop(self):
        while self.running:
            start_time = time.monotonic()

            with self.lock:
                frame = self.latest_yolo_frame
                self.latest_yolo_frame = None

            if frame is None:
                time.sleep(0.02)
                continue

            small_frame = cv2.resize(
                frame,
                (
                    self.YOLO_WIDTH,
                    self.YOLO_HEIGHT,
                ),
                interpolation=cv2.INTER_AREA,
            )

            results = self.model(
                small_frame,
                conf=0.50,
                iou=0.30,
                verbose=False,
            )

            detections = self._parse_detections(results[0])
            target = self._select_tracking_target(detections)

            if target is not None:
                center_x = (
                    target["box"][0] + target["box"][2]
                ) // 2
                center_y = (
                    target["box"][1] + target["box"][3]
                ) // 2
                image_center_x = self.width // 2
                image_center_y = self.height // 2

                target["selected"] = True
                target["center"] = [center_x, center_y]
                target["image_center"] = [
                    image_center_x,
                    image_center_y,
                ]
                target["error"] = [
                    center_x - image_center_x,
                    center_y - image_center_y,
                ]

            elapsed = time.monotonic() - start_time
            inference_fps = 1.0 / elapsed if elapsed > 0 else 0.0

            with self.lock:
                self.latest_detections = detections
                self.inference_fps = inference_fps

            remaining = self.INFERENCE_INTERVAL - elapsed

            if remaining > 0:
                time.sleep(remaining)

    def _parse_detections(self, result):
        detections = []
        scale_x = self.width / self.YOLO_WIDTH
        scale_y = self.height / self.YOLO_HEIGHT

        if result.boxes is None:
            return detections

        for box in result.boxes:
            confidence = float(box.conf[0])
            class_id = int(box.cls[0])
            class_name = self.model.names[class_id]
            x1, y1, x2, y2 = map(
                int,
                box.xyxy[0],
            )

            detections.append(
                {
                    "class": class_name,
                    "confidence": round(confidence, 3),
                    "box": [
                        self._clamp_x(int(x1 * scale_x)),
                        self._clamp_y(int(y1 * scale_y)),
                        self._clamp_x(int(x2 * scale_x)),
                        self._clamp_y(int(y2 * scale_y)),
                    ],
                    "selected": False,
                }
            )

        return detections

    def _clamp_x(self, value):
        return max(0, min(self.width - 1, value))

    def _clamp_y(self, value):
        return max(0, min(self.height - 1, value))

    def _select_tracking_target(self, detections):
        if not detections:
            return None

        # Use the most confident detection; prefer the larger box on a tie.
        return max(
            detections,
            key=lambda detection: (
                detection["confidence"],
                (
                    detection["box"][2] - detection["box"][0]
                ) * (
                    detection["box"][3] - detection["box"][1]
                ),
            ),
        )

    def _draw_tracking_overlay(self, frame, detection):
        x1, y1, x2, y2 = detection["box"]
        center_x, center_y = detection["center"]
        image_center_x, image_center_y = detection["image_center"]
        error_x, error_y = detection["error"]

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
            (0, 255, 255),
            -1,
        )
        cv2.drawMarker(
            frame,
            (image_center_x, image_center_y),
            (255, 0, 255),
            markerType=cv2.MARKER_CROSS,
            markerSize=18,
            thickness=2,
        )
        cv2.line(
            frame,
            (image_center_x, image_center_y),
            (center_x, center_y),
            (255, 255, 0),
            1,
        )

        label = (
            f"{detection['class']} "
            f"{detection['confidence']:.0%}"
        )
        error_label = (
            f"dx={error_x:+d}px "
            f"dy={error_y:+d}px"
        )

        cv2.putText(
            frame,
            label,
            (x1, max(y1 - 30, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            error_label,
            (x1, max(y1 - 8, 42)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )

    def get_frame(self):
        with self.lock:
            if self.latest_frame is None:
                return None

            return self.latest_frame.copy()

    def get_detections(self):
        with self.lock:
            return list(self.latest_detections)

    def get_tracking_target(self):
        with self.lock:
            target = next(
                (
                    detection
                    for detection in self.latest_detections
                    if detection["selected"]
                ),
                None,
            )

            return dict(target) if target is not None else None

    def get_camera_fps(self):
        with self.lock:
            return round(self.camera_fps, 1)

    def get_inference_fps(self):
        with self.lock:
            return round(self.inference_fps, 1)

    def stop(self):
        if not self.running:
            return

        self.running = False

        if self.capture_thread is not None:
            self.capture_thread.join(timeout=2.0)

        if self.vision_thread is not None:
            self.vision_thread.join(timeout=2.0)

        if self.capture is not None:
            self.capture.release()

        self.capture = None

    def is_running(self):
        return self.running
