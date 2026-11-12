import time
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from ingenuity.web.server import create_app
from ingenuity.auth.authentication import create_access_token
from test_tracking import Camera,Gimbal,batch


class WebCamera(Camera):
    def __init__(self): super().__init__();self.closed=False;self.batch=batch(stamp=time.monotonic())
    def get_status(self): return {'online':True,'ai_online':True,'fps':20,'inference_fps':4}
    def stop(self): self.closed=True


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('JWT_SECRET','a'*48)
    monkeypatch.setenv('ROBOT_PASSWORD','test-only-password')
    monkeypatch.setenv('ROBOT_USERNAME','admin')
    monkeypatch.delenv('ROBOT_PASSWORD_HASH',raising=False)
    camera,gimbal=WebCamera(),Gimbal()
    app=create_app(lambda:camera,lambda:gimbal)
    with TestClient(app) as client:
        client.camera=camera;client.gimbal=gimbal
        yield client
    assert camera.closed and gimbal.closed and gimbal.speed==[0,0]


def login(client):
    response=client.post('/login',data={'username':'admin','password':'test-only-password'},follow_redirects=False)
    assert response.status_code==303
    assert 'HttpOnly' in response.headers['set-cookie']


@pytest.mark.parametrize('method,path',[
    ('get','/api/status'),('get','/api/tracking/status'),('get','/api/camera/status'),
    ('get','/video_feed'),('get','/api/camera/stream'),
    ('post','/api/tracking/select'),('post','/api/tracking/stop')])
def test_protected_routes(client,method,path):
    assert getattr(client,method)(path).status_code==401


def test_websocket_rejects_anonymous(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/ws/status'): pass


def test_dashboard_and_selection(client):
    login(client)
    assert client.get('/').status_code==200
    assert client.get('/static/js/dashboard.js').status_code==200
    data=client.get('/api/status').json()
    assert data['camera_data']['version']==1
    assert data['tracking']['actuation']=='enabled'
    assert client.post('/api/tracking/select',json={'index':0,'version':0}).status_code==409
    assert client.post('/api/tracking/select',json={'index':False,'version':1}).status_code==422
    assert client.post('/api/tracking/select',json={'index':0,'version':1}).status_code==200
    assert client.post('/api/tracking/stop').json()['tracking']['mode']=='IDLE'
    assert client.gimbal.speed==[0,0]


def test_authenticated_websocket(client):
    login(client)
    with client.websocket_connect('/ws/status') as websocket:
        assert websocket.receive_json()['camera_data']['ai_online']


def test_origin_rejected(client):
    login(client)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/ws/status',headers={'origin':'https://untrusted.invalid'}): pass


def test_logout_stops_gimbal(client):
    login(client)
    client.post('/api/tracking/select',json={'index':0,'version':1})
    assert client.post('/logout',follow_redirects=False).status_code==303
    assert client.gimbal.speed==[0,0]
    assert client.get('/api/status').status_code==401


def test_missing_configuration_fails_before_hardware(monkeypatch):
    monkeypatch.setenv('JWT_SECRET','short')
    def forbidden(): raise AssertionError('Hardware must not start')
    with pytest.raises(RuntimeError,match='JWT_SECRET'):
        with TestClient(create_app(forbidden,forbidden)): pass


def test_camera_failure_keeps_authenticated_dashboard(monkeypatch):
    monkeypatch.setenv('JWT_SECRET','a'*48);monkeypatch.setenv('ROBOT_PASSWORD','test-only-password')
    def failed(): raise RuntimeError('Camera unavailable')
    with TestClient(create_app(failed,Gimbal)) as client:
        login(client)
        assert client.get('/').status_code==200
        assert not client.get('/api/status').json()['camera']
        assert client.get('/video_feed').status_code==503


def test_expired_cookie_is_rejected(client):
    from datetime import datetime,timedelta,timezone
    from jose import jwt
    token=jwt.encode({'sub':'admin','exp':datetime.now(timezone.utc)-timedelta(seconds=10)},'a'*48,algorithm='HS256')
    client.cookies.set('access_token',token)
    assert client.get('/api/status').status_code==401
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/ws/status'): pass


def test_gimbal_failure_does_not_close_video_early(monkeypatch):
    monkeypatch.setenv('JWT_SECRET','a'*48);monkeypatch.setenv('ROBOT_PASSWORD','test-only-password')
    camera=WebCamera()
    def failed():raise OSError('I2C unavailable')
    with TestClient(create_app(lambda:camera,failed)) as client:
        login(client)
        status=client.get('/api/status').json()
        assert status['camera'] and status['tracking']['actuation']=='disabled'
        assert not camera.closed
        assert client.post('/api/tracking/stop').status_code==503
    assert camera.closed


def test_cleanup_continues_when_gimbal_close_fails(monkeypatch):
    monkeypatch.setenv('JWT_SECRET','a'*48);monkeypatch.setenv('ROBOT_PASSWORD','test-only-password')
    camera,gimbal=WebCamera(),Gimbal()
    def failed():raise OSError('cleanup failure')
    gimbal.close=failed
    with TestClient(create_app(lambda:camera,lambda:gimbal)):pass
    assert camera.closed
