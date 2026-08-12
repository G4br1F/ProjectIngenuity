from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.api.status import router as status_router
from dotenv import load_dotenv
from app.api.camera import router as camera_router

from app.auth.authentication import (
    get_current_user,
    get_password,
    get_username,
    verify_password,
    create_access_token,
)


load_dotenv()


app = FastAPI(
    title="Robot OS",
    description="Control system for the Raspberry Pi robot",
    version="0.1.0",
)

app.include_router(status_router)
app.include_router(camera_router)

app.mount(
    "/static",
    StaticFiles(directory="frontend/static"),
    name="static",
)


templates = Jinja2Templates(
    directory="frontend/templates"
)


@app.get("/")
async def root(request: Request):

    try:
        username = get_current_user(request)

    except Exception:
        return RedirectResponse(
            url="/login",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "username": username,
        },
    )


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

    token = create_access_token(username)

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


@app.post("/logout")
async def logout():

    response = RedirectResponse(
        url="/login",
        status_code=303,
    )

    response.delete_cookie("access_token")

    return response


