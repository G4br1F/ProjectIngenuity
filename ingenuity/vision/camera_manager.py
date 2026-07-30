import cv2
from .config import *

class CameraManager:

    def __init__(self):
        self.cap = cv2.VideoCapture(CAMERA_ID)

        if not self.cap.isOpened():
            raise RuntimeError("Webcam non trovata.")

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    def read(self):
        ok, frame = self.cap.read()

        if not ok:
            return None

        return frame

    def release(self):
        self.cap.release()
