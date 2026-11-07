"""Cookie authentication shared by HTTP and WebSocket endpoints."""
import hmac
import os
from datetime import datetime, timedelta, timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import HTTPException, Request
from jose import JWTError, jwt

password_hasher = PasswordHasher()
JWT_ALGORITHM = 'HS256'
JWT_EXPIRE_MINUTES = 60


def get_username():
    return os.getenv('ROBOT_USERNAME', 'admin')


def get_password():
    return os.getenv('ROBOT_PASSWORD', '')


def get_secret_key():
    secret = os.getenv('JWT_SECRET', '')
    if len(secret) < 32:
        raise RuntimeError('JWT_SECRET deve contenere almeno 32 caratteri')
    return secret


def validate_configuration():
    get_secret_key()
    if not get_username() or not (get_password() or os.getenv('ROBOT_PASSWORD_HASH')):
        raise RuntimeError('Configurare ROBOT_USERNAME e ROBOT_PASSWORD oppure ROBOT_PASSWORD_HASH')


def create_password_hash(password):
    return password_hasher.hash(password)


def verify_password(password, hashed_password):
    try:
        return password_hasher.verify(hashed_password, password)
    except (VerificationError, InvalidHashError):
        return False


def credentials_valid(username, password):
    if not isinstance(username, str) or not isinstance(password, str) or not password:
        return False
    if not hmac.compare_digest(username.encode(), get_username().encode()):
        return False
    hashed = os.getenv('ROBOT_PASSWORD_HASH')
    return verify_password(password, hashed) if hashed else hmac.compare_digest(password.encode(), get_password().encode())


def create_access_token(username):
    return jwt.encode({'sub': username, 'exp': datetime.now(timezone.utc)+timedelta(minutes=JWT_EXPIRE_MINUTES)},
                      get_secret_key(), algorithm=JWT_ALGORITHM)


def verify_access_token(token):
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=[JWT_ALGORITHM],
                             options={'require_exp': True, 'require_sub': True})
        if payload.get('sub') != get_username():
            raise JWTError('Utente non valido')
        return payload['sub']
    except JWTError as exc:
        raise HTTPException(status_code=401, detail='Token non valido o scaduto') from exc


def get_current_user(request: Request):
    token = request.cookies.get('access_token')
    if not token:
        raise HTTPException(status_code=401, detail='Autenticazione richiesta')
    return verify_access_token(token)
