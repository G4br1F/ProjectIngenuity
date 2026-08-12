import os
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from fastapi import HTTPException, Request, status
from jose import JWTError, jwt


password_hasher = PasswordHasher()

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60


def get_username() -> str:
    return os.getenv("ROBOT_USERNAME", "admin")


def get_password() -> str:
    return os.getenv("ROBOT_PASSWORD", "")


def get_secret_key() -> str:
    secret = os.getenv("JWT_SECRET")

    if not secret:
        raise RuntimeError("JWT_SECRET non configurato")

    return secret


def create_password_hash(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        password_hasher.verify(hashed_password, password)
        return True
    except Exception:
        return False


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=JWT_EXPIRE_MINUTES
    )

    payload = {
        "sub": username,
        "exp": expire,
    }

    return jwt.encode(
        payload,
        get_secret_key(),
        algorithm=JWT_ALGORITHM,
    )


def verify_access_token(token: str) -> str:
    try:
        payload = jwt.decode(
            token,
            get_secret_key(),
            algorithms=[JWT_ALGORITHM],
        )

        username = payload.get("sub")

        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token non valido",
            )

        return username

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token non valido o scaduto",
        )


def get_current_user(request: Request) -> str:
    token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticazione richiesta",
        )

    return verify_access_token(token)
