from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import WebSocket
from ingenuity.web.websocket import status_socket
from ingenuity.core.system_monitor import SystemMonitor
from ingenuity.vision.camera import Camera

# ==========================
# Inizializzazione
# ==========================

app = FastAPI(title="Project Ingenuity")

@app.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    await status_socket(websocket)

camera = Camera()

templates = Jinja2Templates(directory="ingenuity/templates")

app.mount(
    "/static",
    StaticFiles(directory="ingenuity/static"),
    name="static"
)

# ==========================
# Dashboard
# ==========================

@app.get("/")
def home(request: Request):

    status = SystemMonitor.get_status()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "status": status
        }
    )

# ==========================
# API
# ==========================

@app.get("/api/status")
def api_status():
    return JSONResponse(
        content=SystemMonitor.get_status()
    )

# ==========================
# Webcam
# ==========================

@app.get("/video_feed")
def video_feed():

    return StreamingResponse(
        camera.frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )
