"""Optional frontal-face detection; association never changes body identity."""
from pathlib import Path
import os


class FaceLocator:
    def __init__(self, cv2):
        self.cv2 = cv2
        self.enabled = os.getenv('TRACK_FACE_ENABLED', '0') == '1'
        self.error = None
        self.detector = None
        if not self.enabled:
            return
        configured = os.getenv('FACE_CASCADE_PATH')
        candidates = [Path(configured)] if configured else [
            Path(getattr(getattr(cv2, 'data', None), 'haarcascades', '/nonexistent')) /
            'haarcascade_frontalface_default.xml',
            Path('/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml'),
        ]
        try:
            path = next((p for p in candidates if p.is_file()), None)
            if path is None:
                raise FileNotFoundError('Cascade volto assente: impostare FACE_CASCADE_PATH')
            self.detector = cv2.CascadeClassifier(str(path))
            if self.detector.empty():
                raise ValueError('Cascade volto non valida')
        except Exception as exc:
            self.error = str(exc)
            self.detector = None

    @staticmethod
    def associate(objects, faces):
        people = [obj for obj in objects if obj['class'] == 'person']
        matches = [[] for _ in people]
        for face in faces:
            x1, y1, x2, y2 = face
            cx, cy = (x1+x2)/2, (y1+y2)/2
            owners = []
            for i, person in enumerate(people):
                left, top, right, bottom = person['box']
                if left <= cx <= right and top <= cy <= bottom:
                    owners.append(i)
            # Reject overlapping owners instead of steering another person's face.
            if len(owners) == 1:
                matches[owners[0]].append(face)
        for person, candidates in zip(people, matches):
            person.pop('face_box', None)
            person.pop('aim_center', None)
            person['aim_kind'] = 'face_missing'
            if len(candidates) == 1:
                x1, y1, x2, y2 = candidates[0]
                person['face_box'] = list(candidates[0])
                person['aim_center'] = [(x1+x2)//2, (y1+y2)//2]
                person['aim_kind'] = 'face'
            elif candidates:
                person['aim_kind'] = 'face_ambiguous'

    def enrich(self, frame, objects):
        if not self.enabled:
            return
        self.associate(objects, [])
        if self.detector is None or not any(o['class'] == 'person' for o in objects):
            return
        try:
            height, width = frame.shape[:2]
            scale = min(1.0, 640/max(width, height))
            small = self.cv2.resize(frame, (round(width*scale), round(height*scale)))
            gray = self.cv2.cvtColor(small, self.cv2.COLOR_BGR2GRAY)
            boxes = self.detector.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
            faces = [[max(0, round(x/scale)), max(0, round(y/scale)),
                      min(width-1, round((x+w)/scale)),
                      min(height-1, round((y+h)/scale))] for x, y, w, h in boxes]
            self.associate(objects, faces)
            self.error = None
        except Exception as exc:
            # Video and YOLO remain available; no face authorizes motion.
            self.error = str(exc)
