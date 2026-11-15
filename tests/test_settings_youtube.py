import asyncio

import pytest

from quantis.services.net_proxy import set_youtube_proxy, youtube_proxy
from quantis.ui.preferences import UiPreferences
from quantis.ui.views import settings_page


class Bridge:
    def schedule(self, coro):
        asyncio.run(coro)

    def invoke_main(self, callback):
        callback()


@pytest.mark.parametrize("fails", [False, True])
def test_full_check_saves_visible_proxy_and_restores_controls(qapp, monkeypatch, fails):
    prefs = UiPreferences()
    old = prefs.youtube_proxy
    page = settings_page.SettingsPage(prefs, Bridge())

    async def check(progress):
        assert youtube_proxy() == "socks5://127.0.0.1:10808"
        assert not page._proxy_full_btn.isEnabled()
        assert not page._proxy_edit.isEnabled()
        progress("2/3 — проверка")
        assert page._proxy_status.text() == "2/3 — проверка"
        if fails:
            raise RuntimeError("failure")
        return True, "3/3 — готово"

    monkeypatch.setattr(settings_page, "check_youtube_full", check)
    try:
        page._proxy_edit.setText("socks5://127.0.0.1:10808")
        page._proxy_full_btn.click()
        assert page._proxy_full_btn.isEnabled()
        assert page._proxy_check_btn.isEnabled()
        assert page._proxy_edit.isEnabled()
        assert ("не удалась" if fails else "3/3") in page._proxy_status.text()
    finally:
        prefs.set_youtube_proxy(old)
        set_youtube_proxy(old)
        page.close()
