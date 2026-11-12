"""Benchmark the same letterboxed NCNN inference path used by the camera."""
import os
from pathlib import Path
import time


def main():
    import numpy as np
    from ultralytics import YOLO
    size = int(os.getenv('YOLO_IMGSZ','320'))
    path = Path(os.getenv('YOLO_MODEL_PATH',str(Path(__file__).resolve().parent/'yolo26n_ncnn_model')))
    if not path.is_dir():
        raise FileNotFoundError(f'Modello assente: {path}')
    model = YOLO(str(path),task='detect')
    frame = np.zeros((540,960,3),dtype=np.uint8)
    for _ in range(3):
        model(frame,imgsz=size,verbose=False)
    samples=[]
    for _ in range(10):
        start=time.perf_counter()
        model(frame,imgsz=size,verbose=False)
        samples.append(time.perf_counter()-start)
    mean=sum(samples)/len(samples)
    print(f'Inferenza end-to-end: {mean*1000:.1f} ms; capacità media {1/mean:.2f} FPS')
    print('La frequenza operativa dipende anche da INFERENCE_INTERVAL e dal carico video.')


if __name__ == '__main__':
    main()
