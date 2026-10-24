import cv2
import math
import threading
import time
from pathlib import Path

from picamera2 import Picamera2
from ultralytics import YOLO


class Camera:

    INFERENCE_INTERVAL = 0.10
    TRACKING_GRACE_PERIOD = 0.35
    TARGET_SMOOTHING = 0.55
    STREAM_FPS = 20.0
    JPEG_QUALITY = 60

    def __init__(self):

        # ==========================
        # Camera Module 3 / IMX708
        # ==========================

        self.frame_width = 640
        self.frame_height = 360

        self.picam2 = Picamera2()

        camera_config = self.picam2.create_preview_configuration(
            main={
                "size": (
                    self.frame_width,
                    self.frame_height
                ),
                "format": "RGB888"
            }
        )

        self.picam2.configure(camera_config)

        self.picam2.start()

        # Diamo tempo alla camera di stabilizzarsi
        time.sleep(1)

        # ==========================
        # Parametri YOLO
        # ==========================

        self.yolo_width = 320
        self.yolo_height = 180
        self.inference_interval = self.INFERENCE_INTERVAL

        # ==========================
        # YOLO
        # ==========================

        project_root = Path(
            __file__
        ).resolve().parents[2]

        model_path = (
            project_root /
            "yolo26n_ncnn_model"
        )

        self.model = YOLO(
            str(model_path),
            task="detect"
        )

        # ==========================
        # Stato
        # ==========================

        self.latest_frame = None
        self.latest_display_frame = None

        self.latest_jpeg = None

        self.frame_id = 0

        self.latest_detections = []
        self._last_target = None

        self._latest_capture_id = 0

        self.camera_fps = 0.0

        self.inference_fps = 0.0

        self._lock = threading.Lock()

        self._running = True

        # ==========================
        # Thread acquisizione
        # ==========================

        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            daemon=True
        )

        # ==========================
        # Thread YOLO
        # ==========================

        self._vision_thread = threading.Thread(
            target=self._vision_loop,
            daemon=True
        )

        # JPEG encoding runs separately so it cannot block camera capture.
        self._stream_thread = threading.Thread(
            target=self._stream_loop,
            daemon=True
        )

        self._capture_thread.start()

        self._vision_thread.start()

        self._stream_thread.start()

    # ======================================
    # ACQUISIZIONE CAMERA
    # ======================================

    def _capture_loop(self):

        previous_time = time.monotonic()

        while self._running:

            try:
                frame = self.picam2.capture_array()
            except Exception:
                time.sleep(0.02)
                continue

            # Picamera2 -> RGB
            # OpenCV -> BGR

            frame = cv2.cvtColor(
                frame,
                cv2.COLOR_RGB2BGR
            )

            current_time = time.monotonic()

            delta = current_time - previous_time

            if delta > 0:
                fps = 1.0 / delta
            else:
                fps = 0.0

            previous_time = current_time

            # --------------------------------
            # Disegna il bersaglio selezionato
            # sul frame ATTUALE. Questo e' solo
            # feedback visivo: non aziona servo.
            # --------------------------------

            with self._lock:

                detections = list(
                    self.latest_detections
                )

                self.camera_fps = fps

            selected_detection = next(
                (
                    detection
                    for detection in detections
                    if detection["selected"]
                ),
                None
            )

            if selected_detection is not None:

                display_frame = frame.copy()

                self._draw_tracking_overlay(
                    display_frame,
                    selected_detection
                )
            else:
                display_frame = frame

            with self._lock:
                self.latest_frame = frame
                self.latest_display_frame = display_frame
                self._latest_capture_id += 1

    def _stream_loop(self):

        frame_interval = 1.0 / self.STREAM_FPS
        last_capture_id = -1
        next_frame_time = time.monotonic()

        while self._running:
            with self._lock:
                frame = self.latest_display_frame
                capture_id = self._latest_capture_id
                if frame is not None:
                    frame = frame.copy()

            if frame is None or capture_id == last_capture_id:
                time.sleep(0.002)
                continue

            now = time.monotonic()
            if now < next_frame_time:
                time.sleep(next_frame_time - now)
                continue

            success, buffer = cv2.imencode(
                ".jpg",
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, self.JPEG_QUALITY],
            )
            last_capture_id = capture_id
            next_frame_time = max(
                next_frame_time + frame_interval,
                time.monotonic(),
            )

            if success:
                with self._lock:
                    self.latest_jpeg = buffer.tobytes()
                    self.frame_id += 1

    # ======================================
    # YOLO
    # ======================================

    def _clamp_x(self, value):

        return max(0, min(self.frame_width - 1, value))

    def _clamp_y(self, value):

        return max(0, min(self.frame_height - 1, value))

    def _select_tracking_target(self, detections):

        now = time.monotonic()
        previous = self._last_target

        if not detections:
            if previous is None:
                return None

            age = now - previous["last_seen"]
            if age > self.TRACKING_GRACE_PERIOD:
                self._last_target = None
                return None

            return {
                "class": previous["class"],
                "confidence": previous["confidence"],
                "box": list(previous["box"]),
                "selected": True,
                "stale": True,
                "tracking_age": round(age, 3),
                "timestamp": previous["timestamp"],
            }

        target = None
        if previous is not None:
            same_class = [
                detection
                for detection in detections
                if detection["class"] == previous["class"]
            ]
            if same_class:
                old_box = previous["box"]
                old_center = (
                    (old_box[0] + old_box[2]) / 2,
                    (old_box[1] + old_box[3]) / 2,
                )
                max_distance = max(
                    48.0,
                    math.hypot(self.frame_width, self.frame_height) * 0.30,
                )

                def association_score(detection):
                    box = detection["box"]
                    center = (
                        (box[0] + box[2]) / 2,
                        (box[1] + box[3]) / 2,
                    )
                    distance = math.hypot(
                        center[0] - old_center[0],
                        center[1] - old_center[1],
                    )
                    intersection_width = max(
                        0,
                        min(old_box[2], box[2]) - max(old_box[0], box[0]),
                    )
                    intersection_height = max(
                        0,
                        min(old_box[3], box[3]) - max(old_box[1], box[1]),
                    )
                    intersection = intersection_width * intersection_height
                    old_area = max(0, old_box[2] - old_box[0]) * max(
                        0, old_box[3] - old_box[1]
                    )
                    new_area = max(0, box[2] - box[0]) * max(
                        0, box[3] - box[1]
                    )
                    union = old_area + new_area - intersection
                    iou = intersection / union if union else 0.0
                    score = (
                        iou * 2
                        - distance / max_distance
                        + detection["confidence"] * 0.15
                    )
                    return score, distance, iou

                scored = [
                    (association_score(detection), detection)
                    for detection in same_class
                ]
                (_, distance, iou), candidate = max(
                    scored,
                    key=lambda item: item[0][0],
                )
                if iou >= 0.02 or distance <= max_distance:
                    target = candidate

        if target is None and previous is not None:
            age = now - previous["last_seen"]
            if age <= self.TRACKING_GRACE_PERIOD:
                return {
                    "class": previous["class"],
                    "confidence": previous["confidence"],
                    "box": list(previous["box"]),
                    "selected": True,
                    "stale": True,
                    "tracking_age": round(age, 3),
                    "timestamp": previous["timestamp"],
                }

        if target is None:
            target = max(
                detections,
                key=lambda detection: (
                    detection["confidence"],
                    (detection["box"][2] - detection["box"][0])
                    * (detection["box"][3] - detection["box"][1]),
                ),
            )
        elif previous is not None:
            target["box"] = [
                self._clamp_x(round(
                    previous["box"][index]
                    + self.TARGET_SMOOTHING
                    * (target["box"][index] - previous["box"][index])
                ))
                if index in (0, 2)
                else self._clamp_y(round(
                    previous["box"][index]
                    + self.TARGET_SMOOTHING
                    * (target["box"][index] - previous["box"][index])
                ))
                for index in range(4)
            ]

        target["selected"] = True
        target["stale"] = False
        target["tracking_age"] = 0.0
        target["timestamp"] = time.time()
        self._last_target = {
            "class": target["class"],
            "confidence": target["confidence"],
            "box": list(target["box"]),
            "last_seen": now,
            "timestamp": target["timestamp"],
        }
        return target

    def _draw_tracking_overlay(self, frame, detection):

        x1, y1, x2, y2 = detection["box"]
        center_x, center_y = detection["center"]
        image_center_x, image_center_y = (
            detection["image_center"]
        )
        error_x, error_y = detection["error"]

        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            (0, 255, 0),
            2
        )

        cv2.circle(
            frame,
            (center_x, center_y),
            5,
            (0, 255, 255),
            -1
        )

        cv2.drawMarker(
            frame,
            (image_center_x, image_center_y),
            (255, 0, 255),
            markerType=cv2.MARKER_CROSS,
            markerSize=18,
            thickness=2
        )

        cv2.line(
            frame,
            (image_center_x, image_center_y),
            (center_x, center_y),
            (255, 255, 0),
            1
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
            2
        )

        cv2.putText(
            frame,
            error_label,
            (x1, max(y1 - 8, 42)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 255),
            2
        )

    def _vision_loop(self):

        while self._running:

            start_time = time.monotonic()

            # --------------------------------
            # Prendiamo SOLO l'ultimo frame
            # --------------------------------

            with self._lock:

                frame = self.latest_frame

                if frame is not None:
                    frame = frame.copy()

            if frame is None:

                time.sleep(0.05)

                continue

            # --------------------------------
            # Riduciamo il frame SOLO per YOLO
            #
            # Il video originale rimane
            # 640x360 @ ~30 FPS
            # --------------------------------

            small_frame = cv2.resize(
                frame,
                (
                    self.yolo_width,
                    self.yolo_height
                ),
                interpolation=cv2.INTER_AREA
            )

            # --------------------------------
            # Inferenza YOLO
            # --------------------------------

            results = self.model(
                small_frame,
                conf=0.40,
                iou=0.30,
                verbose=False
            )

            result = results[0]

            detections = []

            # --------------------------------
            # Fattori di scala
            #
            # 320x180 -> 640x360
            # --------------------------------

            scale_x = self.frame_width / self.yolo_width
            scale_y = self.frame_height / self.yolo_height

            if result.boxes is not None:

                for box in result.boxes:

                    confidence = float(
                        box.conf[0]
                    )

                    class_id = int(
                        box.cls[0]
                    )

                    class_name = (
                        self.model.names[class_id]
                    )

                    x1, y1, x2, y2 = map(
                        int,
                        box.xyxy[0]
                    )

                    # --------------------------------
                    # Riportiamo le coordinate
                    # alla risoluzione originale
                    # --------------------------------

                    x1 = int(x1 * scale_x)
                    y1 = int(y1 * scale_y)
                    x2 = int(x2 * scale_x)
                    y2 = int(y2 * scale_y)

                    detections.append({

                        "class": class_name,

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

                        "selected": False,
                        "stale": False,
                        "tracking_age": 0.0,

                    })

            target = self._select_tracking_target(
                detections
            )

            if target is not None:
                if target not in detections:
                    detections.append(target)

                center_x = (
                    target["box"][0] +
                    target["box"][2]
                ) // 2
                center_y = (
                    target["box"][1] +
                    target["box"][3]
                ) // 2
                image_center_x = self.frame_width // 2
                image_center_y = self.frame_height // 2

                target["selected"] = True
                target["center"] = [
                    center_x,
                    center_y
                ]
                target["image_center"] = [
                    image_center_x,
                    image_center_y
                ]
                # Positive dx/dy means the target is right/down of center.
                target["error"] = [
                    center_x - image_center_x,
                    center_y - image_center_y
                ]
                target["error_normalized"] = [
                    round(target["error"][0] / max(image_center_x, 1), 4),
                    round(target["error"][1] / max(image_center_y, 1), 4),
                ]
                target.setdefault("timestamp", time.time())

            # --------------------------------
            # Calcolo FPS inferenza
            # --------------------------------

            elapsed = (
                time.monotonic() -
                start_time
            )

            if elapsed > 0:

                inference_fps = (
                    1.0 / elapsed
                )

            else:

                inference_fps = 0.0

            # --------------------------------
            # Salviamo il risultato
            # --------------------------------

            with self._lock:

                self.latest_detections = (
                    detections
                )

                self.inference_fps = (
                    inference_fps
                )

            # --------------------------------
            # Aspettiamo fino alla prossima
            # inferenza
            # --------------------------------

            remaining = (
                self.inference_interval -
                elapsed
            )

            if remaining > 0:

                time.sleep(remaining)

    # ======================================
    # STREAM
    # ======================================

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
                + str(len(jpeg)).encode()
                + b"\r\n\r\n"
                + jpeg
                + b"\r\n"
            )

    # ======================================
    # DETECTION
    # ======================================

    def get_detections(self):

        with self._lock:

            return list(
                self.latest_detections
            )

    # ======================================
    # TRACKING TARGET (SOLO TELEMETRIA)
    # ======================================

    def get_tracking_target(self):

        with self._lock:

            target = next(
                (
                    detection
                    for detection in self.latest_detections
                    if detection["selected"]
                ),
                None
            )

            return dict(target) if target is not None else None

    # ======================================
    # CAMERA FPS
    # ======================================

    def get_camera_fps(self):

        with self._lock:

            return round(
                self.camera_fps,
                1
            )

    # ======================================
    # YOLO FPS
    # ======================================

    def get_inference_fps(self):

        with self._lock:

            return round(
                self.inference_fps,
                1
            )

    # ======================================
    # STOP
    # ======================================

    def stop(self):

        self._running = False

        for thread in (
            self._capture_thread,
            self._vision_thread,
            self._stream_thread,
        ):
            if thread.is_alive():
                thread.join(timeout=2.0)

        self.picam2.stop()
