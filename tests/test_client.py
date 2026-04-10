"""Tests for the TP-Link Powerline HTTP client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.tplink_powerline.client import (
    AuthenticationError,
    DeviceUnavailable,
    PowerlineClient,
    UnexpectedResponse,
)


def _make_response(text: str, status: int = 200) -> AsyncMock:
    """Create a mock aiohttp response."""
    resp = AsyncMock()
    resp.status = status
    resp.text = AsyncMock(return_value=text)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _make_session() -> MagicMock:
    """Create a mock aiohttp session."""
    return MagicMock(spec=aiohttp.ClientSession)


# TS-10: Successful login
async def test_successful_login() -> None:
    session = _make_session()
    session.post.return_value = _make_response("ERROR=000\r\nTOKEN=abc123def456\r\n")
    client = PowerlineClient("192.168.1.34", "md5hash", session)

    await client.login()

    assert client.token == "abc123def456"
    session.post.assert_called_once()
    call_kwargs = session.post.call_args
    assert "charset" not in call_kwargs.kwargs.get("headers", {}).get("Content-Type", "")


# TS-11: Login with wrong password
async def test_login_wrong_password() -> None:
    session = _make_session()
    session.post.return_value = _make_response("ERROR=006\r\nLOGIN_TIMES=1\r\n")
    client = PowerlineClient("192.168.1.34", "wronghash", session)

    with pytest.raises(AuthenticationError, match="Wrong password"):
        await client.login()


# TS-12: Login with device unreachable
async def test_login_device_unreachable() -> None:
    session = _make_session()
    session.post.side_effect = aiohttp.ClientError("Connection refused")
    client = PowerlineClient("192.168.1.34", "md5hash", session)

    with pytest.raises(DeviceUnavailable):
        await client.login()


# TS-13: Successful data fetch
async def test_successful_data_fetch() -> None:
    session = _make_session()
    session.get.return_value = _make_response(
        "ERROR=000\r\nKEY1=val1\r\nKEY2=val2\r\n"
    )
    client = PowerlineClient("192.168.1.34", "md5hash", session)
    client.token = "validtoken"

    result = await client.get_data(["KEY1", "KEY2"])

    assert result == {"KEY1": "val1", "KEY2": "val2"}


# TS-14: Data fetch with expired session triggers re-auth
async def test_data_fetch_reauth_on_expired_session() -> None:
    session = _make_session()
    # First GET returns auth error, re-login succeeds, second GET returns data
    session.get.side_effect = [
        _make_response("ERROR=003\r\n"),
        _make_response("ERROR=000\r\nKEY1=val1\r\n"),
    ]
    session.post.return_value = _make_response("ERROR=000\r\nTOKEN=newtoken\r\n")
    client = PowerlineClient("192.168.1.34", "md5hash", session)
    client.token = "expiredtoken"

    result = await client.get_data(["KEY1"])

    assert result == {"KEY1": "val1"}
    assert client.token == "newtoken"


# TS-15: Data fetch with device unreachable
async def test_data_fetch_device_unreachable() -> None:
    session = _make_session()
    session.get.side_effect = aiohttp.ClientError("Connection refused")
    client = PowerlineClient("192.168.1.34", "md5hash", session)
    client.token = "validtoken"

    with pytest.raises(DeviceUnavailable):
        await client.get_data(["KEY1"])


# TS-16: get_device_info returns structured data
async def test_get_device_info() -> None:
    session = _make_session()
    session.get.return_value = _make_response(
        "ERROR=000\r\n"
        "SYSTEM.PRODUCTION.HW_PRODUCT=PG2400P\r\n"
        "SYSTEM.PRODUCTION.HW_REVISION=1.0\r\n"
        "SYSTEM.GENERAL.FW_VERSION=1.0.3 Build 20221213 Rel.62540\r\n"
    )
    client = PowerlineClient("192.168.1.34", "md5hash", session)
    client.token = "validtoken"

    info = await client.get_device_info()

    assert info == {
        "model": "PG2400P",
        "firmware": "1.0.3 Build 20221213 Rel.62540",
        "hardware": "1.0",
    }


# TS-17: Logout clears token
async def test_logout_clears_token() -> None:
    session = _make_session()
    session.post.return_value = _make_response("ERROR=000\r\nRESULT=0\r\n")
    client = PowerlineClient("192.168.1.34", "md5hash", session)
    client.token = "validtoken"

    await client.logout()

    assert client.token is None


# TS-18: Content-Type has no charset
async def test_content_type_no_charset() -> None:
    session = _make_session()
    session.post.return_value = _make_response("ERROR=000\r\nTOKEN=tok\r\n")
    session.get.return_value = _make_response("ERROR=000\r\nKEY=val\r\n")
    client = PowerlineClient("192.168.1.34", "md5hash", session)

    await client.login()
    await client.get_data(["KEY"])

    for call in session.post.call_args_list + session.get.call_args_list:
        headers = call.kwargs.get("headers", {})
        ct = headers.get("Content-Type", "")
        assert ct == "application/x-www-form-urlencoded", f"Bad Content-Type: {ct}"
        assert "charset" not in ct
