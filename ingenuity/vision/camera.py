import cv2
import threading
import time
from pathlib import Path

from ultralytics import YOLO


class Camera:

    DEVICE = "/dev/video0"

    def __init__(self):

        self.cap = cv2.VideoCapture(
            self.DEVICE,
            cv2.CAP_V4L2
        )

        if not self.cap.isOpened():
            raise RuntimeError(
                f"Impossibile aprire la webcam {self.DEVICE}"
            )

        self.cap.set(
            cv2.CAP_PROP_FOURCC,
            cv2.VideoWriter_fourcc(*"MJPG")
        )

        self.cap.set(
            cv2.CAP_PROP_FRAME_WIDTH,
            640
        )

        self.cap.set(
            cv2.CAP_PROP_FRAME_HEIGHT,
            360
        )

        self.cap.set(
            cv2.CAP_PROP_FPS,
            30
        )

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
    # ACQUISIZIONE WEBCAM
    # ======================================

    def _capture_loop(self):

        previous_time = time.time()

        while self._running:

            success, frame = self.cap.read()

            if not success:

                time.sleep(0.02)

                continue

            current_time = time.time()

            delta = current_time - previous_time

            if delta > 0:

                fps = 1.0 / delta

            else:

                fps = 0.0

            previous_time = current_time

            # --------------------------------
            # Disegna le ultime detection
            # sul frame ATTUALE
            # --------------------------------

            with self._lock:

                detections = list(
                    self.latest_detections
                )

                self.camera_fps = fps

            for detection in detections:

                x1, y1, x2, y2 = (
                    detection["box"]
                )

                class_name = (
                    detection["class"]
                )

                confidence = (
                    detection["confidence"]
                )

                cv2.rectangle(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    (0, 255, 0),
                    2
                )

                label = (
                    f"{class_name} "
                    f"{confidence:.0%}"
                )

                cv2.putText(
                    frame,
                    label,
                    (
                        x1,
                        max(y1 - 10, 20)
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2
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

            if success:
                with self._lock:
                    self.latest_frame = frame
                    self.latest_jpeg = buffer.tobytes()
                    self.frame_id += 1

    # ======================================
    # YOLO
    # ======================================

    def _vision_loop(self):

        inference_interval = 0.33

        while self._running:

            start_time = time.time()

            # Prendiamo SOLO l'ultimo frame
            with self._lock:

                frame = self.latest_frame

                if frame is not None:
                    frame = frame.copy()

            if frame is None:

                time.sleep(0.05)

                continue

            # --------------------------------
            # Inferenza
            # --------------------------------

            results = self.model(
                frame,
                conf=0.50,
                iou=0.30,
                verbose=False
            )

            result = results[0]

            detections = []

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
                        ]

                    })

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
            # Salviamo SOLO il risultato YOLO
            # --------------------------------

            with self._lock:

                self.latest_detections = (
                    detections
                )

                self.inference_fps = (
                    inference_fps
                )

            remaining = (
                inference_interval -
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
                current_frame_id = self.frame_id

            if jpeg is None or current_frame_id == last_frame_id:
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

        self.cap.release()