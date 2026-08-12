from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ingenuity.core.system_monitor import SystemMonitor
from ingenuity.vision.camera import Camera
from ingenuity.web.websocket import status_socket


# ======================================
# Project Ingenuity
# ======================================

app = FastAPI(
    title="Project Ingenuity"
)


# ======================================
# Camera
# ======================================

camera = Camera()


# ======================================
# Templates
# ======================================

templates = Jinja2Templates(
    directory="ingenuity/templates"
)


# ======================================
# Static files
# ======================================

app.mount(
    "/static",
    StaticFiles(
        directory="ingenuity/static"
    ),
    name="static"
)


# ======================================
# Dashboard
# ======================================

@app.get("/")
def home(request: Request):

    status = SystemMonitor.get_status()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "status": status
        }
    )


# ======================================
# API status
# ======================================

@app.get("/api/status")
def api_status():

    return JSONResponse(
        content=SystemMonitor.get_status()
    )


# ======================================
# Webcam stream
# ======================================

@app.get("/video_feed")
def video_feed():

    return StreamingResponse(
        camera.frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",
        }
    )

# ======================================
# WebSocket
# ======================================

@app.websocket("/ws/status")
async def websocket_status(
    websocket: WebSocket
):

    await status_socket(
        websocket,
        camera
    )
