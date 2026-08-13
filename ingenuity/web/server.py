from dotenv import load_dotenv

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import (
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ingenuity.auth.authentication import (
    create_access_token,
    get_current_user,
    get_password,
    get_username,
)

from ingenuity.core.system_monitor import SystemMonitor
from ingenuity.vision.camera import Camera
from ingenuity.web.websocket import status_socket


# ======================================
# Environment
# ======================================

load_dotenv()


# ======================================
# Project Ingenuity
# ======================================

app = FastAPI(
    title="Project Ingenuity",
    description="Control system for the Raspberry Pi robot",
    version="0.1.0",
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
    name="static",
)


# ======================================
# Login
# ======================================

@app.get("/login")
async def login_page(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="login.html",
    )


@app.post("/login")
async def login(request: Request):

    form = await request.form()

    username = form.get("username")
    password = form.get("password")

    if (
        username != get_username()
        or password != get_password()
    ):

        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "Credenziali non valide"
            },
            status_code=401,
        )

    token = create_access_token(
        username
    )

    response = RedirectResponse(
        url="/",
        status_code=303,
    )

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="strict",
        secure=False,
        max_age=60 * 60,
    )

    return response


# ======================================
# Logout
# ======================================

@app.post("/logout")
async def logout():

    response = RedirectResponse(
        url="/login",
        status_code=303,
    )

    response.delete_cookie(
        "access_token"
    )

    return response


# ======================================
# Dashboard
# ======================================

@app.get("/")
async def home(request: Request):

    try:

        username = get_current_user(
            request
        )

    except Exception:

        return RedirectResponse(
            url="/login",
            status_code=303,
        )

    status = SystemMonitor.get_status()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "status": status,
            "username": username,
        },
    )


# ======================================
# API status
# ======================================

@app.get("/api/status")
async def api_status():

    return JSONResponse(
        content=SystemMonitor.get_status()
    )


# ======================================
# Webcam stream
# ======================================

@app.get("/video_feed")
async def video_feed():

    return StreamingResponse(
        camera.frames(),
        media_type=(
            "multipart/x-mixed-replace;"
            " boundary=frame"
        ),
        headers={
            "Cache-Control":
                "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",
        },
    )


# ======================================
# WebSocket
# ======================================

@app.websocket("/ws/status")
async def websocket_status(
    websocket: WebSocket,
):

    await status_socket(
        websocket,
        camera,
    )