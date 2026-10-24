import asyncio
import json

from fastapi import WebSocket

from ingenuity.core.system_monitor import SystemMonitor


async def status_socket(
    websocket,
    camera,
    tracking_manager,
):

    await websocket.accept()

    try:

        while True:

            status = SystemMonitor.get_status()

            status["camera_data"] = {
                "fps": camera.get_camera_fps(),
                "inference_fps": camera.get_inference_fps(),
                "objects": camera.get_detections(),
            }

            status["tracking"] = (
                tracking_manager.snapshot()
            )

            await websocket.send_text(
                json.dumps(status)
            )

            await asyncio.sleep(1)

    except Exception:

        try:
            await websocket.close()

        except Exception:
            pass
