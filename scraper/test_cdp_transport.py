"""Exercise the pinned SeleniumBase adapters without Chrome or a paid proxy."""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("seleniumbase")
from seleniumbase import BaseCase
from seleniumbase.core.sb_cdp import CDPMethods
from seleniumbase.undetected.cdp_driver.tab import Tab

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser import BLOCKED, PROBE_JS, ChromeSession


@pytest.mark.parametrize("page_state", ["challenge", "offers"])
def test_resource_blocking_and_probe_keep_webdriver_disconnected(page_state):
    commands = []

    class Driver:
        _is_using_uc = True
        connected = False
        current_window_handle = "test-window"

        def is_connected(self):
            return self.connected

        def connect(self):
            self.connected = True

        def execute_cdp_cmd(self, *args):
            return {}

    driver = Driver()

    class Page(Tab):
        def __init__(self):
            pass

        async def send(self, command, **kwargs):
            request = next(command)
            commands.append(request)
            if request["method"] == "Runtime.evaluate":
                # A lost CDP transport returns None; Tab.evaluate then cannot
                # unpack its result, matching the reported TypeError.
                if driver.connected:
                    return None
                return SimpleNamespace(value=page_state), None

    loop = asyncio.new_event_loop()
    try:
        sb = BaseCase()
        sb.browser = "chrome"
        sb.driver = driver
        sb.cdp = CDPMethods(loop, Page(), driver)
        session = ChromeSession(None, net_log=False)
        session._sb = sb

        session.block_extra_resources()
        assert session.probe() == page_state
        assert not driver.connected
        assert [item["method"] for item in commands] == [
            "Network.enable", "Network.setBlockedURLs", "Runtime.evaluate",
        ]
        assert commands[1]["params"]["urls"] == BLOCKED
        assert commands[2]["params"]["expression"] == PROBE_JS.strip()
    finally:
        loop.close()
