import asyncio
import json

from fastapi import WebSocket
from ingenuity.core.system_monitor import SystemMonitor


async def status_socket(websocket: WebSocket):

    await websocket.accept()

    try:
        while True:

            await websocket.send_text(
                json.dumps(SystemMonitor.get_status())
            )

            await asyncio.sleep(1)

    except Exception:
        await websocket.close()
