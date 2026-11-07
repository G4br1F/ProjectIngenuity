from copy import deepcopy
import pytest
from ingenuity.vision.tracking import TrackingManager
from ingenuity.hardware.pan_tracker import PanTracker


def obj(x=800,y=270,label='person'):
    return {'class':label,'confidence':.9,'center':[x,y],'box':[x-40,y-40,x+40,y+40]}


def batch(version=1,stamp=10,objects=None):
    return {'version':version,'captured_at':stamp,'size':[960,540],
            'objects':[obj()] if objects is None else objects}


class Camera:
    def __init__(self): self.batch=batch()
    def get_detection_snapshot(self): return deepcopy(self.batch)


class Gimbal:
    def __init__(self): self.speed=[0,0];self.closed=False
    def pan(self,speed): self.speed[0]=speed
    def tilt(self,speed): self.speed[1]=speed
    def stop(self): self.speed=[0,0]
    def close(self): self.stop();self.closed=True


def setup(**kwargs):
    cam,gimbal,tracker=Camera(),Gimbal(),TrackingManager()
    controller=PanTracker(cam,gimbal,tracker,autostart=False,clock=lambda:10,**kwargs)
    controller.select(0,1)
    return cam,gimbal,tracker,controller


def test_stale_selection_rejected():
    tracker=TrackingManager()
    with pytest.raises(ValueError): tracker.select(batch(),0,0,10)
    with pytest.raises(ValueError): tracker.select(batch(),0,1,12)


def test_reordered_batch_cannot_select_wrong_object():
    tracker=TrackingManager()
    current=batch(2,10,[obj(label='bottle'),obj()])
    with pytest.raises(ValueError): tracker.select(current,0,1,10)
    assert tracker.snapshot()['mode']=='IDLE'


def test_pulse_stops_even_without_new_inference():
    cam,gimbal,tracker,c=setup()
    c.step(10.02)
    assert -.011 <= gimbal.speed[0] < 0
    c.step(10.10)
    assert -.1 <= gimbal.speed[0] < 0
    c.step(10.21)
    assert gimbal.speed==[0,0]
    c.step(20)
    assert gimbal.speed==[0,0]
    assert tracker.snapshot()['mode']=='LOST'


def test_fresh_frame_authorizes_new_bounded_pulse():
    cam,gimbal,tracker,c=setup()
    c.step(10.02);c.step(10.25)
    assert gimbal.speed==[0,0]
    cam.batch=batch(2,10.26)
    c.step(10.28)
    assert gimbal.speed[0]<0


def test_stop_remains_stopped_with_fresh_results():
    cam,gimbal,tracker,c=setup()
    c.step(10.02);c.stop_tracking()
    cam.batch=batch(2,10.04)
    c.step(10.06)
    assert gimbal.speed==[0,0]
    assert tracker.snapshot()['mode']=='IDLE'


def test_center_hysteresis_and_direction():
    cam,gimbal,tracker,c=setup()
    cam.batch=batch(2,10.02,[obj(500)])
    # Move gradually into the association gate rather than teleporting target.
    tracker.select(cam.batch,0,2,10.02)
    c.step(10.04)
    assert gimbal.speed==[0,0]
    cam.batch=batch(3,10.06,[obj(515)]) # 7.3%, within exit threshold
    c.step(10.08)
    assert gimbal.speed==[0,0]
    cam.batch=batch(4,10.10,[obj(540)])
    c.step(10.12)
    assert gimbal.speed[0]<0


def test_tilt_opt_in_and_resolution_independence():
    cam,gimbal,tracker,c=setup(tilt_enabled=True,pan_direction=1,tilt_direction=1)
    cam.batch={'version':2,'captured_at':10.02,'size':[640,360],'objects':[obj(400,250)]}
    tracker.select(cam.batch,0,2,10.02)
    c.step(10.04)
    assert gimbal.speed[0]>0 and gimbal.speed[1]>0


def test_ambiguous_or_missing_target_stops():
    cam,gimbal,tracker,c=setup()
    c.step(10.02)
    cam.batch=batch(2,10.04,[obj(790),obj(810)])
    c.step(10.06)
    assert gimbal.speed==[0,0]
    assert tracker.snapshot()['reason']=='ambiguous_target'


def test_lost_target_reacquired_only_within_grace():
    tracker=TrackingManager()
    tracker.select(batch(),0,1,10)
    assert tracker.update(batch(2,10.1,[]),10.1)['mode']=='LOST'
    assert tracker.update(batch(3,10.2),10.2)['mode']=='TRACKING'
    tracker.update(batch(4,10.3,[]),10.3)
    assert tracker.update(batch(5,12),12)['reason']=='reselect_required'


def test_stale_observation_never_moved_even_when_published_now():
    cam,gimbal,tracker,c=setup()
    cam.batch=batch(2,8)
    c.step(10.02)
    assert gimbal.speed==[0,0]


def test_snapshot_is_deep_copy():
    tracker=TrackingManager();tracker.select(batch(),0,1,10)
    state=tracker.snapshot();state['target']['center'][0]=0
    assert tracker.snapshot()['target']['center'][0]==800


def test_stop_is_serialized_with_inflight_command():
    import threading
    cam,gimbal,tracker,c=setup()
    entered,release=threading.Event(),threading.Event()
    original=gimbal.pan
    def blocking_pan(speed):
        entered.set()
        assert release.wait(1)
        original(speed)
    gimbal.pan=blocking_pan
    worker=threading.Thread(target=lambda:c.step(10.02))
    worker.start();assert entered.wait(1)
    stopper=threading.Thread(target=c.stop_tracking)
    stopper.start();release.set()
    worker.join(1);stopper.join(1)
    assert not worker.is_alive() and not stopper.is_alive()
    assert gimbal.speed==[0,0]
    c.step(10.04)
    assert gimbal.speed==[0,0]
