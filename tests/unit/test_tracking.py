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






def test_stop_remains_stopped_with_fresh_results():
    cam,gimbal,tracker,c=setup()
    c.step(10.02);c.stop_tracking()
    cam.batch=batch(2,10.04)
    c.step(10.06)
    assert gimbal.speed==[0,0]
    assert tracker.snapshot()['mode']=='IDLE'






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
    assert tracker.update(batch(5,14),14)['reason']=='reselect_required'


def test_stale_observation_never_moved_even_when_published_now():
    cam,gimbal,tracker,c=setup()
    cam.batch=batch(2,8)
    c.step(10.02)
    assert gimbal.speed==[0,0]


def test_snapshot_is_deep_copy():
    tracker=TrackingManager();tracker.select(batch(),0,1,10)
    state=tracker.snapshot();state['target']['center'][0]=0
    assert tracker.snapshot()['target']['center'][0]==800




def start_pulse(x=800):
    cam,gimbal,tracker,c=setup()
    cam.batch=batch(2,10.07,[obj(x)])
    tracker.select(cam.batch,0,2,10.07)
    c.step(10.08)
    return cam,gimbal,tracker,c


def test_pulse_not_extended_and_waits_for_post_stop_capture():
    cam,gimbal,tracker,c=start_pulse()
    assert gimbal.speed[0]==-.4
    deadline=c._pulse_until
    cam.batch=batch(3,10.09)
    c.step(10.10)
    assert c._pulse_until==deadline
    c.step(deadline+.001)
    assert gimbal.speed==[0,0]
    cam.batch=batch(4,deadline-.01)  # inference completed after stop, old capture
    c.step(deadline+.10)
    assert gimbal.speed==[0,0]
    cam.batch=batch(5,deadline+.08)
    c.step(deadline+.11)
    assert gimbal.speed[0]==-.4


def test_shorter_correction_near_center_and_after_crossing():
    _,g,_,near=start_pulse(540)
    assert g.speed[0]==-.4
    _,_,_,far=start_pulse(900)
    assert near._pulse_until < far._pulse_until
    assert near._pulse_until-10.08 >= near.MIN_PULSE_SECONDS-1e-9
    assert far._pulse_until-10.08 <= far.MAX_PULSE_SECONDS+1e-9


def test_effective_commands_center_and_inversion():
    _,_,_,c=setup()
    assert c._command(0,0,.005)==0
    assert c._command(.5,0,.005)==-.4
    assert c._command(-.5,0,.005)==.2
    c._speed[0]=.2
    assert c._command(.5,0,.005)==0


def test_stop_and_expiry_during_active_pulse():
    cam,g,t,c=start_pulse()
    c.stop_tracking()
    cam.batch=batch(3,10.2)
    c.step(10.21)
    assert g.speed==[0,0] and t.snapshot()['mode']=='IDLE'
    cam,g,t,c=start_pulse()
    c.step(12)
    assert g.speed==[0,0] and t.snapshot()['mode']=='LOST'


def test_rejected_selection_preserves_active_target():
    cam,g,t,c=start_pulse()
    before=t.snapshot()
    with pytest.raises(ValueError): c.select(0,999)
    assert t.snapshot()==before
    assert g.speed[0]==-.4


def test_old_displayed_batch_resolves_reordered_target():
    cam,g,t,c=setup()
    old=batch(1,9.9,[obj(800),obj(200,label='bottle')])
    cam.get_selection_snapshot=lambda version: deepcopy(old)
    cam.batch=batch(2,10,[obj(200,label='bottle'),obj(810)])
    c.select(0,1)
    assert t.snapshot()['target']['class']=='person'
    assert t.snapshot()['target']['center'][0]==810
    assert g.speed==[0,0]


def test_old_selection_rejects_stale_and_ambiguous():
    cam,g,t,c=setup()
    cam.get_selection_snapshot=lambda version: batch(1,8)
    with pytest.raises(ValueError):c.select(0,1)
    cam.get_selection_snapshot=lambda version: batch(1,9.9)
    cam.batch=batch(2,10,[obj(790),obj(810)])
    with pytest.raises(ValueError):c.select(0,1)


def test_stop_is_serialized_with_inflight_command():
    import threading
    cam,g,t,c=setup()
    cam.batch=batch(2,10.07)
    entered,release=threading.Event(),threading.Event()
    original=g.pan
    def blocking_pan(speed):
        entered.set()
        assert release.wait(1)
        original(speed)
    g.pan=blocking_pan
    worker=threading.Thread(target=lambda:c.step(10.08))
    worker.start();assert entered.wait(1)
    stopper=threading.Thread(target=c.stop_tracking)
    stopper.start();release.set()
    worker.join(1);stopper.join(1)
    assert not worker.is_alive() and not stopper.is_alive()
    assert g.speed==[0,0]


def test_reacquisition_grace_starts_when_target_is_lost():
    t=TrackingManager()
    t.select(batch(1,9),0,1,9.1)
    assert t.update(batch(2,10.1,[]),10.2)['mode']=='LOST'
    assert t.update(batch(3,10.3),10.4)['mode']=='TRACKING'


def detection(box, label='person'):
    x1,y1,x2,y2=box
    return {'class':label,'confidence':.8,'box':box,'center':[(x1+x2)//2,(y1+y2)//2]}


@pytest.mark.parametrize('before,after',[
    ([206,155,759,537],[410,145,957,534]),
    ([438,143,958,536],[114,153,675,531]),
])
def test_user_large_overlapping_person_boxes_remain_associated(before,after):
    t=TrackingManager()
    t.select(batch(1,10,[detection(before)]),0,1,10)
    state=t.update(batch(2,10.2,[detection(after)]),10.2)
    assert state['mode']=='TRACKING'
    assert state['target']['box']==after


def test_overlap_does_not_select_distant_small_target_or_change_class():
    for target in (obj(100),detection([760,200,900,400],'laptop')):
        t=TrackingManager()
        t.select(batch(),0,1,10)
        assert t.update(batch(2,10.1,[target]),10.1)['mode']=='LOST'


def test_extended_match_rejects_multiple_plausible_people():
    t=TrackingManager()
    t.select(batch(1,10,[detection([438,143,958,536])]),0,1,10)
    state=t.update(batch(2,10.2,[detection([114,153,675,531]),
                                detection([420,143,940,536])]),10.2)
    assert state['reason']=='ambiguous_target'


def test_dropout_reacquires_after_one_second_but_not_after_three():
    t=TrackingManager()
    t.select(batch(),0,1,10)
    t.update(batch(2,10.1,[]),10.1)
    assert t.update(batch(3,11.8),11.8)['mode']=='TRACKING'
    t.update(batch(4,12,[]),12)
    assert t.update(batch(5,15.2),15.2)['reason']=='reselect_required'


def test_servo_stays_stopped_through_detection_dropout():
    cam,g,t,c=start_pulse()
    cam.batch=batch(3,10.10,[])
    c.step(10.11)
    assert g.speed==[0,0]
    cam.batch=batch(4,11.0,[])
    c.step(11.01)
    assert g.speed==[0,0] and t.snapshot()['mode']=='LOST'


@pytest.mark.parametrize('offset',[60,180,420])
def test_clockwise_duration_reduced_without_changing_anticlockwise(offset):
    _,g_cw,_,cw=start_pulse(480-offset)
    _,g_ccw,_,ccw=start_pulse(480+offset)
    assert g_cw.speed[0]==.2 and g_ccw.speed[0]==-.4
    ccw_duration=ccw._pulse_until-10.08
    cw_duration=cw._pulse_until-10.08
    assert cw_duration==pytest.approx(max(.020,.75*ccw_duration))
    scale=min(1,max(0,(offset/480-.06)/.60))
    assert ccw_duration==pytest.approx(.025+scale*(.060-.025))
