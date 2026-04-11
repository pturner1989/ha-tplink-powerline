"""Tests for the TP-Link Powerline HTTP client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.tplink_powerline.client import (
    AuthenticationError,
    DeviceUnavailable,
    IncompatibleDevice,
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


# --- Write methods tests ---


# TS-01: set_data writes keys successfully
async def test_set_data_success() -> None:
    session = _make_session()
    session.post.return_value = _make_response("ERROR=000\r\n")
    client = PowerlineClient("192.168.1.34", "md5hash", session)
    client.token = "validtoken"

    await client.set_data({"TPLINK.LEDSCHEDULE.LED_ENABLE": "NO"})

    session.post.assert_called_once()
    call_kwargs = session.post.call_args
    body = call_kwargs.kwargs.get("data", call_kwargs.args[0] if call_kwargs.args else b"")
    assert b"TPLINK.LEDSCHEDULE.LED_ENABLE=NO" in body


# TS-02: set_data re-auths on expired session
async def test_set_data_reauth() -> None:
    session = _make_session()
    session.post.side_effect = [
        _make_response("ERROR=003\r\n"),  # first set_data fails
        _make_response("ERROR=000\r\nTOKEN=newtoken\r\n"),  # re-login
        _make_response("ERROR=000\r\n"),  # retry set_data
    ]
    client = PowerlineClient("192.168.1.34", "md5hash", session)
    client.token = "expiredtoken"

    await client.set_data({"KEY": "VAL"})

    assert client.token == "newtoken"


# TS-03: send_command returns result
async def test_send_command_success() -> None:
    session = _make_session()
    session.post.return_value = _make_response("ERROR=000\r\nRESULT=1\r\n")
    client = PowerlineClient("192.168.1.34", "md5hash", session)
    client.token = "validtoken"

    result = await client.send_command("get qos")

    assert result == {"RESULT": "1"}


# TS-04: send_command re-auths on expired session
async def test_send_command_reauth() -> None:
    session = _make_session()
    session.post.side_effect = [
        _make_response("ERROR=004\r\n"),  # first command fails
        _make_response("ERROR=000\r\nTOKEN=newtoken\r\n"),  # re-login
        _make_response("ERROR=000\r\nRESULT=1\r\n"),  # retry
    ]
    client = PowerlineClient("192.168.1.34", "md5hash", session)
    client.token = "expiredtoken"

    result = await client.send_command("get qos")

    assert result == {"RESULT": "1"}
    assert client.token == "newtoken"


# --- Network data tests ---


# TS-01: get_network_data with one remote adapter
async def test_get_network_data_one_remote() -> None:
    session = _make_session()
    session.get.return_value = _make_response(
        "ERROR=000\r\n"
        "DIDMNG.GENERAL.MACS=00:00:00:00:00:00,58:04:4f:d8:20:2d,b8:fb:b3:b6:dd:df\r\n"
        "DIDMNG.GENERAL.RX_BPS=0,10151,0\r\n"
        "DIDMNG.GENERAL.TX_BPS=0,11733,0\r\n"
        "SYSTEM.PRODUCTION.MAC_ADDR=b8:fb:b3:b6:dd:df\r\n"
    )
    client = PowerlineClient("192.168.1.34", "md5hash", session)
    client.token = "validtoken"

    result = await client.get_network_data()

    assert len(result["adapters"]) == 1
    adapter = result["adapters"][0]
    assert adapter["mac"] == "58-04-4F-D8-20-2D"
    assert adapter["tx_rate"] == 11733 // 32
    assert adapter["rx_rate"] == 10151 // 32
    assert result["connected_count"] == 1
    assert result["root_mac"] == "B8-FB-B3-B6-DD-DF"


# TS-02: get_network_data with no remote adapters
async def test_get_network_data_no_remotes() -> None:
    session = _make_session()
    session.get.return_value = _make_response(
        "ERROR=000\r\n"
        "DIDMNG.GENERAL.MACS=00:00:00:00:00:00,b8:fb:b3:b6:dd:df\r\n"
        "DIDMNG.GENERAL.RX_BPS=0,0\r\n"
        "DIDMNG.GENERAL.TX_BPS=0,0\r\n"
        "SYSTEM.PRODUCTION.MAC_ADDR=b8:fb:b3:b6:dd:df\r\n"
    )
    client = PowerlineClient("192.168.1.34", "md5hash", session)
    client.token = "validtoken"

    result = await client.get_network_data()

    assert len(result["adapters"]) == 0
    assert result["connected_count"] == 0


# TS-03: get_network_data with disconnected remote adapter
async def test_get_network_data_disconnected_remote() -> None:
    session = _make_session()
    session.get.return_value = _make_response(
        "ERROR=000\r\n"
        "DIDMNG.GENERAL.MACS=00:00:00:00:00:00,58:04:4f:d8:20:2d,b8:fb:b3:b6:dd:df\r\n"
        "DIDMNG.GENERAL.RX_BPS=0,0,0\r\n"
        "DIDMNG.GENERAL.TX_BPS=0,0,0\r\n"
        "SYSTEM.PRODUCTION.MAC_ADDR=b8:fb:b3:b6:dd:df\r\n"
    )
    client = PowerlineClient("192.168.1.34", "md5hash", session)
    client.token = "validtoken"

    result = await client.get_network_data()

    assert len(result["adapters"]) == 1
    assert result["adapters"][0]["tx_rate"] == 0
    assert result["adapters"][0]["rx_rate"] == 0
    assert result["connected_count"] == 0


# TS-04: get_network_name returns name
async def test_get_network_name() -> None:
    session = _make_session()
    session.get.return_value = _make_response(
        "ERROR=000\r\nNODE.GENERAL.DOMAIN_NAME=MyPowerline\r\n"
    )
    client = PowerlineClient("192.168.1.34", "md5hash", session)
    client.token = "validtoken"

    name = await client.get_network_name()

    assert name == "MyPowerline"


# --- Compatibility tests ---


# TS-01: Login detects HTML response as incompatible
async def test_login_html_response_raises_incompatible() -> None:
    session = _make_session()
    session.post.return_value = _make_response(
        "<!DOCTYPE html><html><body>Not a powerline</body></html>"
    )
    client = PowerlineClient("192.168.1.34", "md5hash", session)

    with pytest.raises(IncompatibleDevice):
        await client.login()


# TS-02: Login detects unparseable response as incompatible
async def test_login_no_error_pattern_raises_incompatible() -> None:
    session = _make_session()
    session.post.return_value = _make_response('{"error": "unknown"}')
    client = PowerlineClient("192.168.1.34", "md5hash", session)

    with pytest.raises(IncompatibleDevice):
        await client.login()


# TS-03: Login still works for compatible device (regression)
async def test_login_compatible_still_works() -> None:
    session = _make_session()
    session.post.return_value = _make_response("ERROR=000\r\nTOKEN=abc123\r\n")
    client = PowerlineClient("192.168.1.34", "md5hash", session)

    await client.login()

    assert client.token == "abc123"


# TS-04: Login still raises AuthenticationError for wrong password (regression)
async def test_login_wrong_password_still_works() -> None:
    session = _make_session()
    session.post.return_value = _make_response("ERROR=006\r\n")
    client = PowerlineClient("192.168.1.34", "md5hash", session)

    with pytest.raises(AuthenticationError):
        await client.login()


# TS-05: get_network_data handles mismatched array lengths
async def test_network_data_mismatched_arrays() -> None:
    session = _make_session()
    session.get.return_value = _make_response(
        "ERROR=000\r\n"
        "DIDMNG.GENERAL.MACS=00:00:00:00:00:00,58:04:4f:d8:20:2d,aa:bb:cc:dd:ee:ff\r\n"
        "DIDMNG.GENERAL.RX_BPS=0\r\n"
        "DIDMNG.GENERAL.TX_BPS=0,100\r\n"
        "SYSTEM.PRODUCTION.MAC_ADDR=aa:bb:cc:dd:ee:ff\r\n"
    )
    client = PowerlineClient("192.168.1.34", "md5hash", session)
    client.token = "validtoken"

    result = await client.get_network_data()

    assert len(result["adapters"]) == 1
    assert result["adapters"][0]["mac"] == "58-04-4F-D8-20-2D"
    assert result["adapters"][0]["rx_rate"] == 0  # missing index, defaults to 0
    assert result["adapters"][0]["tx_rate"] == 100 // 32


# TS-06: get_network_data handles empty MACS
async def test_network_data_empty_macs() -> None:
    session = _make_session()
    session.get.return_value = _make_response(
        "ERROR=000\r\n"
        "DIDMNG.GENERAL.MACS=\r\n"
        "DIDMNG.GENERAL.RX_BPS=\r\n"
        "DIDMNG.GENERAL.TX_BPS=\r\n"
        "SYSTEM.PRODUCTION.MAC_ADDR=aa:bb:cc:dd:ee:ff\r\n"
    )
    client = PowerlineClient("192.168.1.34", "md5hash", session)
    client.token = "validtoken"

    result = await client.get_network_data()

    assert len(result["adapters"]) == 0
    assert result["connected_count"] == 0
