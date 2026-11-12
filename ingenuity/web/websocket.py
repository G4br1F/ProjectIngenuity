import asyncio
from urllib.parse import urlsplit
from fastapi import HTTPException, WebSocketDisconnect
from ingenuity.auth.authentication import verify_access_token


async def status_socket(websocket, status_provider):
    token = websocket.cookies.get('access_token')
    origin = websocket.headers.get('origin')
    try:
        if not token or (origin and urlsplit(origin).netloc != websocket.headers.get('host')):
            raise HTTPException(401,'Autenticazione richiesta')
        verify_access_token(token)
    except HTTPException:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        while True:
            verify_access_token(token)
            await websocket.send_json(await asyncio.to_thread(status_provider))
            await asyncio.sleep(0.1)
    except HTTPException:
        await websocket.close(code=1008)
    except WebSocketDisconnect:
        pass
