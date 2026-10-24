import cv2
import threading
import time
from pathlib import Path

from picamera2 import Picamera2
from ultralytics import YOLO


class Camera:

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
        self.inference_interval = 1.0

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

        self.latest_jpeg = None

        self.frame_id = 0

        self.latest_detections = []

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

        self._capture_thread.start()

        self._vision_thread.start()

    # ======================================
    # ACQUISIZIONE CAMERA
    # ======================================

    def _capture_loop(self):

        target_fps = 15.0
        debug_counter = 0
        frame_interval = 1.0 / target_fps

        previous_time = time.time()

        while self._running:

            loop_start = time.time()

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

            current_time = time.time()

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

                self._draw_tracking_overlay(
                    frame,
                    selected_detection
                )

            # --------------------------------
            # Il video viene aggiornato SEMPRE
            # --------------------------------

            success, buffer = cv2.imencode(
                ".jpg",
                frame,
                [
                    cv2.IMWRITE_JPEG_QUALITY,
                    60
                ]
            )

            '''if success:

              with self._lock:

                    self.latest_frame = frame

                    self.latest_jpeg = (
                        buffer.tobytes()
                    )

                    self.frame_id += 1

                elapsed = time.time() - loop_start

                remaining = frame_interval - elapsed

                if remaining > 0:
                    time.sleep(remaining)'''

            if success:

                with self._lock:

                    self.latest_frame = frame

                    self.latest_jpeg = (
                        buffer.tobytes()
                    )

                    self.frame_id += 1

                    debug_counter += 1

                    if debug_counter % 30 == 0:
                        print(
                            f"[CAMERA DEBUG] frame_id={self.frame_id} "
                            f"jpeg={len(self.latest_jpeg)} bytes"
                        )

    # ======================================
    # YOLO
    # ======================================

    def _select_tracking_target(self, detections):

        if not detections:

            return None

        # Per questa prima fase il bersaglio e' la
        # detection con maggiore confidenza. A parita',
        # preferiamo la box piu' grande.
        return max(
            detections,
            key=lambda detection: (
                detection["confidence"],
                (
                    detection["box"][2] -
                    detection["box"][0]
                ) * (
                    detection["box"][3] -
                    detection["box"][1]
                )
            )
        )

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

            start_time = time.time()

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
                conf=0.50,
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

                        "selected": False

                    })

            target = self._select_tracking_target(
                detections
            )

            if target is not None:

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
                target["error"] = [
                    center_x - image_center_x,
                    center_y - image_center_y
                ]

            # --------------------------------
            # Calcolo FPS inferenza
            # --------------------------------

            elapsed = (
                time.time() -
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

        self.picam2.stop()
