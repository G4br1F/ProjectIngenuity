import socket

from fastapi import APIRouter, Request

from app.auth.authentication import get_current_user
from app.robot.system import get_system_status


router = APIRouter(
    prefix="/api",
    tags=["System"],
)


def get_hostname() -> str:
    return socket.gethostname()


def get_ip_address() -> str:
    try:
        hostname = socket.gethostname()
        return socket.gethostbyname(hostname)
    except socket.error:
        return "unknown"


@router.get("/status")
async def status(request: Request):

    username = get_current_user(request)

    system = get_system_status()

    return {
        "robot": {
            "name": "Ingenuity",
            "status": "online",
            "mode": "manual",
        },

        "user": username,

        "system": system,

        "network": {
            "hostname": get_hostname(),
            "ip": get_ip_address(),
        },

        "components": {
            "motors": {
                "status": "standby",
            },

            "camera": {
                "status": "online",
            },

            "ai": {
                "status": "offline",
            },
        },
    }
