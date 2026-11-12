from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import cv2
from ingenuity.vision.faces import FaceLocator
from ingenuity.vision.tracking import TrackingManager
from test_tracking import setup, batch, obj


def test_association_preserves_body_center_and_ignores_nonpeople():
    people = [obj(480, 270), obj(480, 270, 'tv')]
    body = deepcopy(people[0])
    FaceLocator.associate(people, [[450, 235, 470, 255]])
    assert people[0]['center'] == body['center']
    assert people[0]['box'] == body['box']
    assert people[0]['aim_center'] == [460, 245]
    assert 'aim_kind' not in people[1]


def test_overlapping_people_and_multiple_faces_are_rejected():
    people = [obj(480), obj(485)]
    FaceLocator.associate(people, [[460, 250, 480, 270]])
    assert all('aim_center' not in p for p in people)
    people = [obj(480)]
    FaceLocator.associate(people, [[450, 240, 465, 255], [480, 250, 495, 265]])
    assert people[0]['aim_kind'] == 'face_ambiguous'
    assert 'aim_center' not in people[0]


def test_missing_face_clears_previous_reference():
    people = [obj(480)]
    FaceLocator.associate(people, [[460, 250, 480, 270]])
    FaceLocator.associate(people, [])
    assert people[0]['aim_kind'] == 'face_missing'
    assert 'face_box' not in people[0] and 'aim_center' not in people[0]


def face_target(y=100, kind='face'):
    target = obj(480, 270)
    target['box'] = [350, 40, 610, 530]
    target['aim_kind'] = kind
    if kind == 'face':
        target['aim_center'] = [480, y]
    return target


def test_person_body_association_not_affected_by_face_position():
    tracker = TrackingManager()
    tracker.select(batch(1, 10, [face_target(100)]), 0, 1, 10)
    assert tracker.update(batch(2, 10.1, [face_target(400)]), 10.1)['mode'] == 'TRACKING'


def test_face_controls_tilt_when_body_centered_and_loss_stops():
    cam, g, tracker, c = setup(tilt_enabled=True)
    cam.batch = batch(2, 10, [face_target()])
    c.select(0, 2)
    cam.batch = batch(3, 10.07, [face_target()])
    c.step(10.08)
    assert g.speed == [0, .2]
    cam.batch = batch(4, 10.09, [face_target(kind='face_missing')])
    c.step(10.10)
    assert g.speed == [0, 0]
    assert tracker.snapshot()['mode'] == 'TRACKING'
    assert c.snapshot()['control_reason'] == 'face_missing'
    # Face returns: require fresh evidence, do not reuse old face or body centre.
    for version in (5, 6):
        stamp = 10 + version*.1
        cam.batch = batch(version, stamp, [face_target()])
        c.step(stamp+.01)
        assert g.speed == [0, 0]
    cam.batch = batch(7, 10.7, [face_target()])
    c.step(10.71)
    assert g.speed == [0, .2]
    c.stop_tracking()
    assert g.speed == [0, 0]


def test_missing_cascade_is_explicit_and_does_not_authorize_person_motion(monkeypatch):
    monkeypatch.setenv('TRACK_FACE_ENABLED', '1')
    monkeypatch.setenv('FACE_CASCADE_PATH', '/nonexistent/cascade.xml')
    locator = FaceLocator(cv2)
    targets = [obj()]
    locator.enrich(np.zeros((60, 100, 3), dtype=np.uint8), targets)
    assert locator.error
    assert targets[0]['aim_kind'] == 'face_missing'


def test_coordinates_rescaled_to_original_frame(monkeypatch):
    monkeypatch.setenv('TRACK_FACE_ENABLED', '0')
    locator = FaceLocator(cv2)
    locator.enabled = True
    def detect(gray, **kwargs):
        assert gray.shape == (360, 640)
        return [(200, 100, 40, 40)]
    locator.detector = SimpleNamespace(detectMultiScale=detect)
    targets = [obj()]
    targets[0]['box'] = [200, 100, 500, 500]
    locator.enrich(np.zeros((540, 960, 3), dtype=np.uint8), targets)
    assert targets[0]['face_box'] == [300, 150, 360, 210]
    assert targets[0]['aim_center'] == [330, 180]


def test_detector_failure_keeps_yolo_objects(monkeypatch):
    monkeypatch.setenv('TRACK_FACE_ENABLED', '0')
    locator = FaceLocator(cv2)
    locator.enabled = True
    def fail(*args, **kwargs):
        raise RuntimeError('test face failure')
    locator.detector = SimpleNamespace(detectMultiScale=fail)
    targets = [obj()]
    locator.enrich(np.zeros((60, 100, 3), dtype=np.uint8), targets)
    assert targets[0]['class'] == 'person'
    assert targets[0]['aim_kind'] == 'face_missing'
    assert locator.error == 'test face failure'
