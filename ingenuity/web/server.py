"""Authenticated dashboard with a single hardware owner per process."""
import asyncio
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from ingenuity.auth.authentication import (credentials_valid, create_access_token,
    get_current_user, validate_configuration, verify_access_token)
from ingenuity.core.system_monitor import SystemMonitor
from ingenuity.hardware.pan_tracker import PanTracker
from ingenuity.vision.tracking import TrackingManager

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]


class Selection(BaseModel):
    index: int = Field(strict=True, ge=0)
    version: int = Field(strict=True, ge=0)


def make_camera():
    from ingenuity.vision.camera import Camera
    return Camera()


def make_gimbal():
    from ingenuity.hardware.gimbal import Gimbal
    return Gimbal()


def telemetry(runtime):
    data = SystemMonitor.get_status()
    camera = runtime.camera
    state = camera.get_status() if camera else {'online': False, 'ai_online': False,
        'fps': 0, 'inference_fps': 0, 'camera_error': runtime.camera_error}
    batch = camera.get_detection_snapshot() if camera else {'version': 0, 'objects': []}
    data['camera'] = state['online']
    data['camera_data'] = {**state, 'objects': batch['objects'], 'version': batch['version']}
    data['tracking'] = runtime.controller.snapshot() if runtime.controller else {
        **runtime.tracker.snapshot(), 'actuation': 'disabled', 'error': runtime.gimbal_error}
    return data


def create_app(camera_factory=make_camera, gimbal_factory=make_gimbal):
    @asynccontextmanager
    async def lifespan(app):
        load_dotenv(ROOT/'.env')
        validate_configuration()
        rt = SimpleNamespace(camera=None, gimbal=None, controller=None, tracker=TrackingManager(),
                             camera_error=None, gimbal_error=None)
        app.state.runtime = rt
        try:
            try:
                rt.camera = await asyncio.to_thread(camera_factory)
            except Exception as exc:
                rt.camera_error = str(exc)
                log.exception('Camera non disponibile')
            if rt.camera is not None:
                try:
                    rt.gimbal = await asyncio.to_thread(gimbal_factory)
                    rt.controller = PanTracker(rt.camera, rt.gimbal, rt.tracker)
                except Exception as exc:
                    rt.gimbal_error = str(exc)
                    log.exception('Gimbal non disponibile: tracking disabilitato')
                    if rt.gimbal is not None:
                        await asyncio.to_thread(rt.gimbal.close)
                        rt.gimbal = None
            yield
        finally:
            # Each resource is closed even when another cleanup fails.
            for resource, method in ((rt.controller,'stop'), (rt.gimbal,'close'), (rt.camera,'stop')):
                if resource is not None:
                    try:
                        await asyncio.to_thread(getattr(resource,method))
                    except Exception:
                        log.exception('Errore rilascio risorsa %s',method)

    app = FastAPI(title='Project Ingenuity', lifespan=lifespan)
    templates = Jinja2Templates(directory=str(ROOT/'ingenuity/templates'))
    app.mount('/static',StaticFiles(directory=str(ROOT/'ingenuity/static')),name='static')

    def runtime(request: Request):
        return request.app.state.runtime

    def controller(request: Request):
        value = runtime(request).controller
        if value is None:
            raise HTTPException(503,'Gimbal o camera non disponibili')
        return value

    @app.get('/login')
    async def login_page(request: Request):
        return templates.TemplateResponse(request=request,name='login.html')

    @app.post('/login')
    async def login(request: Request):
        form = await request.form()
        if not await asyncio.to_thread(credentials_valid,form.get('username'),form.get('password')):
            return templates.TemplateResponse(request=request,name='login.html',
                context={'error':'Credenziali non valide'},status_code=401)
        response = RedirectResponse('/',status_code=303)
        secure = request.url.scheme == 'https' or os.getenv('COOKIE_SECURE','0') == '1'
        response.set_cookie('access_token',create_access_token(form['username']),
                            httponly=True,samesite='strict',secure=secure,max_age=3600)
        return response

    @app.post('/logout',dependencies=[Depends(get_current_user)])
    async def logout(request: Request):
        if runtime(request).controller:
            runtime(request).controller.stop_tracking()
        response = RedirectResponse('/login',status_code=303)
        response.delete_cookie('access_token')
        return response

    @app.get('/')
    async def home(request: Request):
        try:
            username = get_current_user(request)
        except HTTPException:
            return RedirectResponse('/login',status_code=303)
        return templates.TemplateResponse(request=request,name='dashboard.html',context={'username':username})

    @app.get('/api/status',dependencies=[Depends(get_current_user)])
    async def api_status(request: Request):
        return await asyncio.to_thread(telemetry,runtime(request))

    @app.post('/api/tracking/select',dependencies=[Depends(get_current_user)])
    async def tracking_select(selection: Selection, request: Request):
        try:
            state = controller(request).select(selection.index,selection.version)
        except ValueError as exc:
            raise HTTPException(409,str(exc)) from exc
        return {'success':True,'tracking':state}

    @app.post('/api/tracking/stop',dependencies=[Depends(get_current_user)])
    async def tracking_stop(request: Request):
        return {'success':True,'tracking':controller(request).stop_tracking()}

    @app.get('/api/tracking/status',dependencies=[Depends(get_current_user)])
    async def tracking_status(request: Request):
        return {'success':True,'tracking':telemetry(runtime(request))['tracking']}

    @app.get('/api/camera/status',dependencies=[Depends(get_current_user)])
    async def camera_status(request: Request):
        return telemetry(runtime(request))['camera_data']

    @app.get('/api/camera/stream',dependencies=[Depends(get_current_user)])
    @app.get('/video_feed',dependencies=[Depends(get_current_user)])
    async def video_feed(request: Request):
        camera = runtime(request).camera
        if camera is None:
            raise HTTPException(503,'Camera non disponibile')
        token = request.cookies['access_token']
        async def frames():
            last = -1
            while camera.is_running() and not await request.is_disconnected():
                try:
                    verify_access_token(token)
                except HTTPException:
                    return
                last,jpeg = await asyncio.to_thread(camera.next_jpeg,last,.5)
                if jpeg is not None:
                    yield camera.multipart(jpeg)
        return StreamingResponse(frames(),media_type='multipart/x-mixed-replace; boundary=frame',
            headers={'Cache-Control':'no-cache, no-store, must-revalidate','X-Accel-Buffering':'no'})

    @app.websocket('/ws/status')
    async def websocket_status(websocket: WebSocket):
        from ingenuity.web.websocket import status_socket
        await status_socket(websocket,lambda: telemetry(websocket.app.state.runtime))

    return app


app = create_app()
