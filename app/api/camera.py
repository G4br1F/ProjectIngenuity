import asyncio

import cv2

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.auth.authentication import get_current_user
from app.camera.camera import Camera


router = APIRouter(
    prefix="/api/camera",
    tags=["Camera"],
)


camera = Camera(
    device="/dev/video0",
    width=640,
    height=480,
    fps=30,
)


def generate_frames():

    while True:

        frame = camera.get_frame()

        if frame is None:
            continue

        success, encoded = cv2.imencode(
            ".jpg",
            frame,
            [
                cv2.IMWRITE_JPEG_QUALITY,
                80,
            ],
        )

        if not success:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
            + encoded.tobytes()
            + b"\r\n"
        )


@router.get("/stream")
async def stream(request: Request):

    get_current_user(request)

    if not camera.is_running():
        camera.start()

    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/status")
async def camera_status(request: Request):

    get_current_user(request)

    return {
        "camera": "C270",
        "device": camera.device,
        "running": camera.is_running(),
        "resolution": f"{camera.width}x{camera.height}",
        "fps": camera.fps,
    }
