import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt

from src.core import security


def credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_verify_wallet_owner_requires_credentials():
    with pytest.raises(HTTPException) as exc_info:
        security.verify_wallet_owner("wallet-1", auth=None)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Falta el token" in exc_info.value.detail


def test_verify_wallet_owner_accepts_test_token():
    assert security.verify_wallet_owner("wallet-1", credentials("test-token")) == "wallet-1"


def test_verify_wallet_owner_accepts_valid_jwt_for_same_wallet():
    token = jwt.encode(
        {"wallet_address": "wallet-1"},
        security.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )

    assert security.verify_wallet_owner("wallet-1", credentials(token)) == "wallet-1"


def test_verify_wallet_owner_rejects_valid_jwt_for_different_wallet():
    token = jwt.encode(
        {"wallet_address": "wallet-2"},
        security.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc_info:
        security.verify_wallet_owner("wallet-1", credentials(token))

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.detail == "No tienes permiso para ver el historial de esta wallet"


def test_verify_wallet_owner_rejects_jwt_without_wallet_address():
    token = jwt.encode({"sub": "user-1"}, security.SECRET_KEY, algorithm=security.ALGORITHM)

    with pytest.raises(HTTPException) as exc_info:
        security.verify_wallet_owner("wallet-1", credentials(token))

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


def test_verify_wallet_owner_rejects_invalid_jwt():
    with pytest.raises(HTTPException) as exc_info:
        security.verify_wallet_owner("wallet-1", credentials("not-a-jwt"))

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.detail == "Token invalido o expirado"


def test_verify_wallet_owner_rejects_wrong_signature():
    token = jwt.encode(
        {"wallet_address": "wallet-1"},
        "wrong-secret",
        algorithm=security.ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc_info:
        security.verify_wallet_owner("wallet-1", credentials(token))

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
