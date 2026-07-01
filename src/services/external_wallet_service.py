import logging
import os
import re
from typing import Any

import httpx


LOGGER = logging.getLogger(__name__)

DEFAULT_WALLET_SERVICE_BASE_URL = "http://api-users:8001/api"
DEFAULT_WALLET_TIMEOUT_SECONDS = 3.0
WALLET_ADDRESS_PATTERN = re.compile(r"^[a-f0-9]{40}$")


class ExternalWalletService:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout_seconds: float | None = None,
    ):
        self.base_url = (
            base_url
            or os.getenv("WALLET_SERVICE_BASE_URL")
            or DEFAULT_WALLET_SERVICE_BASE_URL
        ).rstrip("/")
        self.token = (
            token
            if token is not None
            else (os.getenv("WALLET_INTERNAL_TOKEN") or os.getenv("WALLET_SERVICE_TOKEN"))
        )
        self.timeout_seconds = self._resolve_timeout(timeout_seconds)

    def check_wallet_exist(self, address: str) -> bool:
        if not self._is_valid_wallet_address(address):
            return False

        try:
            response = self._get_wallet(address)
        except httpx.RequestError as exc:
            LOGGER.warning(
                "No se pudo verificar wallet externa por error de red: %s",
                exc.__class__.__name__,
            )
            return False

        if response.status_code == httpx.codes.OK:
            return self._response_confirms_wallet(response, address)

        if response.status_code in {
            httpx.codes.BAD_REQUEST,
            httpx.codes.NOT_FOUND,
        }:
            return False

        if response.status_code == httpx.codes.UNAUTHORIZED:
            LOGGER.warning("Wallet externa rechazo la verificacion por autorizacion")
            return False

        LOGGER.warning(
            "Wallet externa respondio con estado inesperado: %s",
            response.status_code,
        )
        return False

    def _get_wallet(self, address: str) -> httpx.Response:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        with httpx.Client(timeout=self.timeout_seconds) as client:
            return client.get(
                f"{self.base_url}/internal/wallet/{address}/exists", headers=headers
            )

    @staticmethod
    def _is_valid_wallet_address(address: str) -> bool:
        return bool(address and WALLET_ADDRESS_PATTERN.fullmatch(address))

    @staticmethod
    def _response_confirms_wallet(response: httpx.Response, address: str) -> bool:
        try:
            body: Any = response.json()
        except ValueError:
            LOGGER.warning("Wallet externa respondio JSON invalido")
            return False

        if not isinstance(body, dict):
            return False

        data = body.get("data")
        return (
            body.get("success") is True
            and isinstance(data, dict)
            and data.get("exists") is True
            and data.get("address") == address
        )

    @staticmethod
    def _resolve_timeout(timeout_seconds: float | None) -> float:
        if timeout_seconds is not None:
            if timeout_seconds <= 0:
                LOGGER.warning("El timeout de wallet externa debe ser positivo; usando valor por defecto")
                return DEFAULT_WALLET_TIMEOUT_SECONDS
            return timeout_seconds

        configured_timeout = os.getenv("WALLET_SERVICE_TIMEOUT_SECONDS")
        if configured_timeout is None:
            return DEFAULT_WALLET_TIMEOUT_SECONDS

        try:
            timeout = float(configured_timeout)
        except ValueError:
            LOGGER.warning("WALLET_SERVICE_TIMEOUT_SECONDS invalido; usando valor por defecto")
            return DEFAULT_WALLET_TIMEOUT_SECONDS

        if timeout <= 0:
            LOGGER.warning("WALLET_SERVICE_TIMEOUT_SECONDS debe ser positivo; usando valor por defecto")
            return DEFAULT_WALLET_TIMEOUT_SECONDS

        return timeout
