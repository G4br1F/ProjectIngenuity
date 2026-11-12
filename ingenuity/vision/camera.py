"""Single-owner Picamera2 capture, clean inference frames and shared JPEGs."""
from copy import deepcopy
from collections import deque
import logging
import math
import os
from pathlib import Path
import threading
import time

log = logging.getLogger(__name__)


class Camera:
    VIDEO_WIDTH, VIDEO_HEIGHT = 960, 540
    VIDEO_FPS = 20.0
    JPEG_QUALITY = 75
    STALE_AFTER = 1.5

    def __init__(self, *, picam_factory=None, model_factory=None):
        import cv2
        self.cv2 = cv2
        from ingenuity.vision.faces import FaceLocator
        self.faces = FaceLocator(cv2)
        self._condition = threading.Condition()
        self._selection_history = deque(maxlen=32)
        self._stop_event = threading.Event()
        self._threads = []
        self._closed = False
        self._started = False
        self.latest_frame = self.latest_jpeg = None
        self.frame_id = 0
        self.camera_fps = self.inference_fps = 0.0
        self._captured_at = self._previous_inference = None
        self._batch = {'version': 0, 'captured_at': None, 'objects': [],
                       'size': [self.VIDEO_WIDTH, self.VIDEO_HEIGHT]}
        self._camera_error = self._ai_error = None
        self.inference_interval = float(os.getenv('INFERENCE_INTERVAL', '0.25'))
        self.imgsz = int(os.getenv('YOLO_IMGSZ', '320'))
        if (not math.isfinite(self.inference_interval) or not 0.05 <= self.inference_interval <= 10
                or self.imgsz < 32 or self.imgsz % 32):
            raise ValueError('INFERENCE_INTERVAL >= 0.05 e YOLO_IMGSZ multiplo di 32 richiesti')
        if picam_factory is None:
            from picamera2 import Picamera2
            picam_factory = Picamera2
        self.picam2 = picam_factory()
        self.model = None
        try:
            duration = round(1_000_000/self.VIDEO_FPS)
            config = self.picam2.create_preview_configuration(
                main={'size': (self.VIDEO_WIDTH, self.VIDEO_HEIGHT), 'format': 'RGB888'},
                controls={'FrameDurationLimits': (duration, duration)}, buffer_count=4)
            self.picam2.configure(config)
            self.picam2.start()
            self._started = True
            try:
                if model_factory is not None:
                    self.model = model_factory()
                else:
                    self.model = self._load_model()
            except Exception as exc:
                self._ai_error = str(exc)
                log.exception('IA non disponibile; il video rimane utilizzabile')
            for target, name in ((self._capture_loop, 'camera-capture'),
                                 (self._vision_loop, 'camera-inference')):
                if target == self._vision_loop and self.model is None:
                    continue
                thread = threading.Thread(target=target, name=name, daemon=True)
                self._threads.append(thread)
                thread.start()
        except Exception:
            self.stop()
            raise

    def _load_model(self):
        from ultralytics import YOLO
        import yaml
        root = Path(__file__).resolve().parents[2]
        model_path = Path(os.getenv('YOLO_MODEL_PATH', str(root/'yolo26n_ncnn_model')))
        if not model_path.is_dir():
            raise FileNotFoundError(f'Modello NCNN assente: {model_path}; seguire README.md')
        for name in ('model.ncnn.param', 'model.ncnn.bin', 'metadata.yaml'):
            if not (model_path/name).is_file():
                raise FileNotFoundError(f'File modello assente: {model_path/name}')
        metadata = yaml.safe_load((model_path/'metadata.yaml').read_text()) or {}
        shape = metadata.get('imgsz')
        if shape != [self.imgsz, self.imgsz]:
            raise ValueError(f'Modello esportato a {shape}; impostare YOLO_IMGSZ coerente o riesportarlo')
        return YOLO(str(model_path), task='detect')

    def _invalidate(self, *, camera_error=None, ai_error=None):
        with self._condition:
            if camera_error is not None:
                self._camera_error = camera_error
                self.latest_frame = self.latest_jpeg = None
                self._captured_at = None
                self.camera_fps = 0.0
            if ai_error is not None:
                self._ai_error = ai_error
                self.inference_fps = 0.0
            self._batch = {**self._batch, 'version': self._batch['version']+1,
                           'captured_at': None, 'objects': []}
            self._condition.notify_all()

    def _capture_loop(self):
        previous = None
        while not self._stop_event.is_set():
            start = time.monotonic()
            try:
                # RGB888 in Picamera2 is already BGR in a NumPy array.
                frame = self.picam2.capture_array('main')
                captured = time.monotonic()
                with self._condition:
                    self.latest_frame = frame.copy()
                    self._captured_at = captured
                    self._camera_error = None
                    self.camera_fps = 0.0 if previous is None else 1/max(captured-previous, 1e-6)
                    batch = deepcopy(self._batch)
                previous = captured
                stamp = batch['captured_at']
                if stamp is not None and captured-stamp <= self.STALE_AFTER:
                    for detection in batch['objects']:
                        x1, y1, x2, y2 = detection['box']
                        self.cv2.rectangle(frame, (x1,y1), (x2,y2), (0,255,0), 2)
                        if 'face_box' in detection:
                            fx1, fy1, fx2, fy2 = detection['face_box']
                            self.cv2.rectangle(frame, (fx1,fy1), (fx2,fy2), (255,255,0), 2)
                            self.cv2.drawMarker(frame, tuple(detection['aim_center']), (255,255,0))
                        self.cv2.putText(frame, detection['class'], (x1,max(20,y1-8)),
                                         self.cv2.FONT_HERSHEY_SIMPLEX, .5, (0,255,0), 1)
                self.cv2.drawMarker(frame, (frame.shape[1]//2,frame.shape[0]//2), (0,255,255))
                ok, buffer = self.cv2.imencode('.jpg', frame, [self.cv2.IMWRITE_JPEG_QUALITY,self.JPEG_QUALITY])
                if not ok:
                    raise RuntimeError('Codifica JPEG fallita')
                with self._condition:
                    self.latest_jpeg = buffer.tobytes()
                    self.frame_id += 1
                    self._condition.notify_all()
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                log.exception('Errore acquisizione/codifica camera')
                self._invalidate(camera_error=str(exc))
                self._stop_event.wait(0.5)
            self._stop_event.wait(max(0, 1/self.VIDEO_FPS-(time.monotonic()-start)))

    def _vision_loop(self):
        last_capture = None
        while not self._stop_event.is_set():
            start = time.monotonic()
            with self._condition:
                frame = None if self.latest_frame is None else self.latest_frame.copy()
                stamp = self._captured_at
            if frame is None or stamp == last_capture or start-stamp > self.STALE_AFTER:
                self._stop_event.wait(.05)
                continue
            last_capture = stamp
            try:
                # Let Ultralytics letterbox once, preserving the aspect ratio.
                result = self.model(frame, imgsz=self.imgsz, conf=.5, iou=.3, verbose=False)[0]
                height, width = frame.shape[:2]
                detections = []
                if result.boxes is not None:
                    for box in result.boxes:
                        x1,y1,x2,y2 = [round(float(v)) for v in box.xyxy[0]]
                        x1,x2 = [max(0,min(width-1,v)) for v in (x1,x2)]
                        y1,y2 = [max(0,min(height-1,v)) for v in (y1,y2)]
                        if x2 <= x1 or y2 <= y1:
                            continue
                        detections.append({'class': result.names[int(box.cls[0])],
                                           'confidence': round(float(box.conf[0]),3),
                                           'box': [x1,y1,x2,y2], 'center': [(x1+x2)//2,(y1+y2)//2]})
                self.faces.enrich(frame, detections)
                now = time.monotonic()
                if now-stamp > self.STALE_AFTER:
                    self._invalidate(ai_error='Inferenza troppo lenta: risultato scaduto')
                    continue
                with self._condition:
                    if self._stop_event.is_set() or self._camera_error is not None:
                        continue
                    self._batch = {'version': self._batch['version']+1, 'captured_at': stamp,
                                   'objects': detections, 'size': [width,height]}
                    self.inference_fps = (0.0 if self._previous_inference is None else
                                          1/max(now-self._previous_inference,1e-6))
                    self._previous_inference = now
                    self._ai_error = None
            except Exception as exc:
                log.exception('Errore inferenza YOLO')
                self._invalidate(ai_error=str(exc))
                self._stop_event.wait(.5)
            self._stop_event.wait(max(0,self.inference_interval-(time.monotonic()-start)))

    def get_detection_snapshot(self):
        with self._condition:
            batch = deepcopy(self._batch)
            if not self._selection_history or self._selection_history[-1]['version'] != batch['version']:
                self._selection_history.append(deepcopy(batch))
            if batch['captured_at'] is None or time.monotonic()-batch['captured_at'] > self.STALE_AFTER:
                batch['objects'] = []
            return batch

    def get_selection_snapshot(self, version):
        """Resolve an index only against the exact batch shown to the user."""
        with self._condition:
            for batch in reversed(self._selection_history):
                if batch['version'] == version:
                    return deepcopy(batch)
            if self._batch['version'] == version:
                return deepcopy(self._batch)
        raise ValueError('Selezione non piu disponibile: scegli un oggetto aggiornato')

    def get_detections(self):
        return self.get_detection_snapshot()['objects']

    def get_detection_version(self):
        return self.get_detection_snapshot()['version']

    def get_status(self):
        now = time.monotonic()
        with self._condition:
            camera_ok = (not self._stop_event.is_set() and self._captured_at is not None
                         and now-self._captured_at <= self.STALE_AFTER and self._camera_error is None)
            stamp = self._batch['captured_at']
            ai_ok = camera_ok and stamp is not None and now-stamp <= self.STALE_AFTER and self._ai_error is None
            return {'online': camera_ok, 'ai_online': ai_ok,
                    'fps': round(self.camera_fps,1) if camera_ok else 0.0,
                    'inference_fps': round(self.inference_fps,1) if ai_ok else 0.0,
                    'camera_error': self._camera_error, 'ai_error': self._ai_error,
                    'face_enabled': self.faces.enabled, 'face_error': self.faces.error}

    def get_camera_fps(self):
        return self.get_status()['fps']

    def get_inference_fps(self):
        return self.get_status()['inference_fps']

    def next_jpeg(self, after, timeout=.5):
        with self._condition:
            self._condition.wait_for(lambda: self._stop_event.is_set() or
                                     (self.latest_jpeg is not None and self.frame_id != after), timeout)
            if self._stop_event.is_set() or self.frame_id == after:
                return after, None
            return self.frame_id, self.latest_jpeg

    @staticmethod
    def multipart(jpeg):
        return (b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(len(jpeg)).encode()
                +b'\r\n\r\n'+jpeg+b'\r\n')

    def is_running(self):
        return not self._stop_event.is_set()

    def frames(self):
        last = -1
        while not self._stop_event.is_set():
            last, jpeg = self.next_jpeg(last)
            if jpeg is not None:
                yield self.multipart(jpeg)

    def stop(self):
        if self._closed:
            return
        self._stop_event.set()
        with self._condition:
            self._condition.notify_all()
        try:
            if self._started:
                self.picam2.stop()  # Unblocks acquisition before joining the worker.
        finally:
            try:
                for thread in self._threads:
                    if thread.ident is None:
                        continue
                    thread.join(timeout=5)
                    if thread.is_alive():
                        log.error('Thread ancora attivo dopo arresto: %s',thread.name)
            finally:
                self.picam2.close()
                self._closed = True
