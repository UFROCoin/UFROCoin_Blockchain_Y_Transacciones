from unittest.mock import MagicMock, patch

import httpx

from src.services.external_wallet_service import (
    DEFAULT_WALLET_TIMEOUT_SECONDS,
    ExternalWalletService,
)


VALID_ADDRESS = "a" * 40
OTHER_VALID_ADDRESS = "b" * 40


def make_response(status_code: int, json_body: dict | None = None, content: bytes | None = None):
    if content is not None:
        return httpx.Response(status_code=status_code, content=content)
    return httpx.Response(status_code=status_code, json=json_body)


def test_empty_address_is_rejected_without_http_call():
    service = ExternalWalletService()
    service._get_wallet = MagicMock()

    assert service.check_wallet_exist("") is False
    service._get_wallet.assert_not_called()


def test_invalid_address_format_is_rejected_without_http_call():
    service = ExternalWalletService()
    service._get_wallet = MagicMock()

    assert service.check_wallet_exist("INVALID-ADDRESS") is False
    assert service.check_wallet_exist("A" * 40) is False
    assert service.check_wallet_exist("a" * 39) is False
    service._get_wallet.assert_not_called()


def test_valid_wallet_response_with_standard_wrapper_returns_true():
    service = ExternalWalletService()
    service._get_wallet = MagicMock(
        return_value=make_response(
            200,
            {
                "success": True,
                "message": "Wallet consultada correctamente.",
                "data": {"address": VALID_ADDRESS, "balance": 100.0},
                "error": {"code": "", "details": ""},
            },
        )
    )

    assert service.check_wallet_exist(VALID_ADDRESS) is True
    service._get_wallet.assert_called_once_with(VALID_ADDRESS)


def test_valid_wallet_response_without_wrapper_returns_true():
    service = ExternalWalletService()
    service._get_wallet = MagicMock(return_value=make_response(200, {"address": VALID_ADDRESS}))

    assert service.check_wallet_exist(VALID_ADDRESS) is True


def test_success_response_for_different_address_returns_false():
    service = ExternalWalletService()
    service._get_wallet = MagicMock(
        return_value=make_response(200, {"success": True, "data": {"address": OTHER_VALID_ADDRESS}})
    )

    assert service.check_wallet_exist(VALID_ADDRESS) is False


def test_wallet_not_found_returns_false():
    service = ExternalWalletService()
    service._get_wallet = MagicMock(
        return_value=make_response(
            404,
            {
                "success": False,
                "message": "La billetera especificada no existe.",
                "data": {},
                "error": {"code": "WALLET_NOT_FOUND", "details": "No existe"},
            },
        )
    )

    assert service.check_wallet_exist(VALID_ADDRESS) is False


def test_bad_request_returns_false():
    service = ExternalWalletService()
    service._get_wallet = MagicMock(return_value=make_response(400, {"error": {"code": "VALIDATION_ERROR"}}))

    assert service.check_wallet_exist(VALID_ADDRESS) is False


def test_unauthorized_returns_false_without_leaking_token():
    service = ExternalWalletService(token="secret-token")
    service._get_wallet = MagicMock(return_value=make_response(401, {"error": {"code": "UNAUTHORIZED"}}))

    assert service.check_wallet_exist(VALID_ADDRESS) is False


def test_unexpected_status_returns_false():
    service = ExternalWalletService()
    service._get_wallet = MagicMock(return_value=make_response(503, {"message": "unavailable"}))

    assert service.check_wallet_exist(VALID_ADDRESS) is False


def test_network_error_returns_false():
    service = ExternalWalletService()
    service._get_wallet = MagicMock(side_effect=httpx.ConnectError("connection refused"))

    assert service.check_wallet_exist(VALID_ADDRESS) is False


def test_invalid_json_returns_false():
    service = ExternalWalletService()
    service._get_wallet = MagicMock(return_value=make_response(200, content=b"not-json"))

    assert service.check_wallet_exist(VALID_ADDRESS) is False


def test_non_object_json_returns_false():
    service = ExternalWalletService()
    service._get_wallet = MagicMock(return_value=httpx.Response(status_code=200, json=[]))

    assert service.check_wallet_exist(VALID_ADDRESS) is False


def test_get_wallet_builds_expected_url_headers_and_timeout():
    response = make_response(200, {"address": VALID_ADDRESS})
    client = MagicMock()
    client.get.return_value = response
    context_manager = MagicMock()
    context_manager.__enter__.return_value = client
    context_manager.__exit__.return_value = None

    with patch("src.services.external_wallet_service.httpx.Client", return_value=context_manager) as client_cls:
        service = ExternalWalletService(
            base_url="http://usuarios:8000/api/",
            token="internal-token",
            timeout_seconds=1.5,
        )

        result = service._get_wallet(VALID_ADDRESS)

    assert result is response
    client_cls.assert_called_once_with(timeout=1.5)
    client.get.assert_called_once_with(
        f"http://usuarios:8000/api/wallet/{VALID_ADDRESS}",
        headers={"Authorization": "Bearer internal-token"},
    )


def test_get_wallet_uses_empty_headers_without_token():
    response = make_response(200, {"address": VALID_ADDRESS})
    client = MagicMock()
    client.get.return_value = response
    context_manager = MagicMock()
    context_manager.__enter__.return_value = client
    context_manager.__exit__.return_value = None

    with patch("src.services.external_wallet_service.httpx.Client", return_value=context_manager):
        service = ExternalWalletService(base_url="http://usuarios:8000/api", token="")
        result = service._get_wallet(VALID_ADDRESS)

    assert result is response
    client.get.assert_called_once_with(
        f"http://usuarios:8000/api/wallet/{VALID_ADDRESS}",
        headers={},
    )


def test_env_configuration_is_used(monkeypatch):
    monkeypatch.setenv("WALLET_SERVICE_BASE_URL", "http://wallets.local/api")
    monkeypatch.setenv("WALLET_SERVICE_TOKEN", "env-token")
    monkeypatch.setenv("WALLET_SERVICE_TIMEOUT_SECONDS", "2.5")

    service = ExternalWalletService()

    assert service.base_url == "http://wallets.local/api"
    assert service.token == "env-token"
    assert service.timeout_seconds == 2.5


def test_invalid_env_timeout_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("WALLET_SERVICE_TIMEOUT_SECONDS", "not-a-number")

    service = ExternalWalletService()

    assert service.timeout_seconds == DEFAULT_WALLET_TIMEOUT_SECONDS


def test_non_positive_env_timeout_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("WALLET_SERVICE_TIMEOUT_SECONDS", "0")

    service = ExternalWalletService()

    assert service.timeout_seconds == DEFAULT_WALLET_TIMEOUT_SECONDS


def test_non_positive_explicit_timeout_falls_back_to_default():
    service = ExternalWalletService(timeout_seconds=0)

    assert service.timeout_seconds == DEFAULT_WALLET_TIMEOUT_SECONDS
