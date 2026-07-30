import os
from datetime import datetime
import cv2

from .config import SAVE_FOLDER


class Capture:

    def __init__(self):
        os.makedirs(SAVE_FOLDER, exist_ok=True)

    def save(self, frame):

        filename = datetime.now().strftime("%Y-%m-%d_%H-%M-%S.jpg")

        path = os.path.join(SAVE_FOLDER, filename)

        cv2.imwrite(path, frame)

        print(f"Foto salvata: {path}")