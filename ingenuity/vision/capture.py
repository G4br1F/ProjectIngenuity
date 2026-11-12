from datetime import datetime
from pathlib import Path
from uuid import uuid4
import cv2
from .config import SAVE_FOLDER


class Capture:
    def __init__(self, folder=SAVE_FOLDER):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True,exist_ok=True)

    def save(self, frame):
        if frame is None:
            raise ValueError('Frame assente')
        name = datetime.now().strftime('%Y-%m-%d_%H-%M-%S_%f')+'_'+uuid4().hex[:8]+'.jpg'
        path = self.folder/name
        if not cv2.imwrite(str(path),frame):
            raise OSError(f'Salvataggio immagine fallito: {path}')
        return path
