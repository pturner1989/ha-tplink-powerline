"""Tests for device identity helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.tplink_powerline.const import DOMAIN
from custom_components.tplink_powerline.device import (
    normalize_mac,
    root_device_identifier,
    root_device_info,
)


@pytest.mark.parametrize(
    "raw",
    ["B8-FB-B3-B6-DD-DF", "b8:fb:b3:b6:dd:df", "B8FBB3B6DDDF", " B8-FB-B3-B6-DD-DF "],
)
def test_normalize_mac_formats(raw: str) -> None:
    assert normalize_mac(raw) == "b8:fb:b3:b6:dd:df"


@pytest.mark.parametrize(
    "raw",
    [None, "", "   ", "00-00-00-00-00-00", "not-a-mac", "ZZ-FB-B3-B6-DD-DF", "B8-FB-B3-B6-DD", 1234, MagicMock()],
)
def test_normalize_mac_rejects_invalid(raw: object) -> None:
    assert normalize_mac(raw) is None


def test_root_device_keyed_by_entry_id() -> None:
    entry = MagicMock()
    entry.entry_id = "abc123"
    assert root_device_identifier(entry) == (DOMAIN, "abc123")
    assert root_device_info(entry)["identifiers"] == {(DOMAIN, "abc123")}
