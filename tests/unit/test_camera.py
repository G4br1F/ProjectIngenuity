import threading
import time
from types import SimpleNamespace
import cv2
import numpy as np
import pytest
from ingenuity.vision.camera import Camera
from ingenuity.vision.capture import Capture


class Picam:
    def __init__(self): self.closed=False;self.stopped=False
    def create_preview_configuration(self,**kw): return kw
    def configure(self,config): self.config=config
    def start(self): pass
    def capture_array(self,*args):
        if self.stopped: raise RuntimeError('stopped')
        frame=np.zeros((60,100,3),dtype=np.uint8);frame[:]=[11,22,33]
        return frame
    def stop(self): self.stopped=True
    def close(self): self.closed=True


def wait_until(predicate):
    deadline=time.monotonic()+3
    while not predicate():
        if time.monotonic()>deadline: raise AssertionError('Timed out')
        time.sleep(.01)


def test_clean_bgr_and_original_coordinates(monkeypatch):
    monkeypatch.setenv('INFERENCE_INTERVAL','0.05')
    picam=Picam();inputs=[]
    def model(frame,**kwargs):
        inputs.append((frame.copy(),kwargs))
        box=SimpleNamespace(xyxy=[[10,10,40,40]],conf=[.9],cls=[0])
        return [SimpleNamespace(boxes=[box],names={0:'person'})]
    camera=Camera(picam_factory=lambda:picam,model_factory=lambda:model)
    try:
        wait_until(lambda:len(inputs)>=3)
        assert all(np.all(frame==[11,22,33]) for frame,kwargs in inputs)
        assert inputs[0][1]['imgsz']==320
        batch=camera.get_detection_snapshot()
        assert batch['objects'][0]['box']==[10,10,40,40]
        assert batch['size']==[100,60]
        assert camera.get_status()['ai_online']
        assert camera.get_inference_fps()>0
        frame_id,jpeg=camera.next_jpeg(-1)
        assert jpeg.startswith(b'\xff\xd8')
    finally: camera.stop()
    camera.stop()
    assert picam.closed and picam.stopped
    assert all(not t.is_alive() for t in camera._threads)
    assert not camera.get_status()['online']


def test_inference_failure_clears_results_and_recovers(monkeypatch):
    monkeypatch.setenv('INFERENCE_INTERVAL','0.05')
    picam=Picam();failed=threading.Event()
    def model(frame,**kwargs):
        if not failed.is_set():
            failed.set();raise RuntimeError('simulated inference error')
        return [SimpleNamespace(boxes=[],names={})]
    camera=Camera(picam_factory=lambda:picam,model_factory=lambda:model)
    try:
        wait_until(failed.is_set)
        wait_until(lambda:camera.get_status()['ai_error'] is not None)
        assert camera.get_detection_snapshot()['objects']==[]
        wait_until(lambda:camera.get_status()['ai_online'])
    finally: camera.stop()


def test_model_load_failure_keeps_video():
    picam=Picam()
    def failed(): raise FileNotFoundError('missing model')
    camera=Camera(picam_factory=lambda:picam,model_factory=failed)
    try:
        wait_until(lambda:camera.get_status()['online'])
        assert not camera.get_status()['ai_online']
        assert camera.next_jpeg(-1)[1] is not None
    finally: camera.stop()


def test_capture_initialization_failure_releases_device():
    picam=Picam()
    def failed(config): raise RuntimeError('bad configuration')
    picam.configure=failed
    with pytest.raises(RuntimeError,match='bad configuration'):
        Camera(picam_factory=lambda:picam,model_factory=lambda:None)
    assert picam.closed


def test_capture_save_unique_and_errors(tmp_path,monkeypatch):
    saver=Capture(tmp_path);frame=np.zeros((5,5,3),dtype=np.uint8)
    a,b=saver.save(frame),saver.save(frame)
    assert a!=b and a.exists() and b.exists()
    monkeypatch.setattr(cv2,'imwrite',lambda *args:False)
    with pytest.raises(OSError):saver.save(frame)
    with pytest.raises(ValueError):saver.save(None)


def test_capture_failure_invalidates_detections(monkeypatch):
    monkeypatch.setenv('INFERENCE_INTERVAL','0.05')
    picam=Picam();fail=threading.Event()
    original=picam.capture_array
    def capture(*args):
        if fail.is_set():raise RuntimeError('camera disconnected')
        return original(*args)
    picam.capture_array=capture
    def model(*args,**kwargs):return [SimpleNamespace(boxes=[],names={})]
    camera=Camera(picam_factory=lambda:picam,model_factory=lambda:model)
    try:
        wait_until(lambda:camera.get_status()['ai_online'])
        fail.set()
        wait_until(lambda:camera.get_status()['camera_error'] is not None)
        assert camera.get_detection_snapshot()['captured_at'] is None
        assert not camera.get_status()['online']
    finally:camera.stop()


def test_selection_history_is_bounded_and_copies_exact_batch():
    from collections import deque
    camera=Camera.__new__(Camera)
    camera._condition=threading.Condition()
    camera._selection_history=deque(maxlen=32)
    for version in range(40):
        camera._batch={'version':version,'captured_at':time.monotonic(),
                       'objects':[{'class':str(version)}],'size':[960,540]}
        camera.get_detection_snapshot()
    assert len(camera._selection_history)==32
    assert camera.get_selection_snapshot(20)['objects'][0]['class']=='20'
    copy=camera.get_selection_snapshot(20);copy['objects'].clear()
    assert camera.get_selection_snapshot(20)['objects']
    with pytest.raises(ValueError):camera.get_selection_snapshot(0)
