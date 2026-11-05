"""Страница «Аккаунты»: состояния сервисов и никаких дампов исключений."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from quantis.services import membership  # noqa: E402
from quantis.services.membership import (  # noqa: E402
    AccountState,
    AccountStatus,
    MembershipSnapshot,
    youtube_account_from_menu,
)
from quantis.ui.views import member_page  # noqa: E402
from quantis.ui.views.member_page import MemberPage  # noqa: E402

_LOGGED_IN = {
    "actions": [
        {
            "openPopupAction": {
                "popup": {
                    "multiPageMenuRenderer": {
                        "header": {
                            "activeAccountHeaderRenderer": {
                                "accountName": {"runs": [{"text": "Илья"}]},
                                "channelHandle": {"runs": [{"text": "@ilya"}]},
                            }
                        }
                    }
                }
            }
        }
    ]
}
# Как в реальном ответе с истёкшей сессией: меню без шапки аккаунта.
_LOGGED_OUT = {
    "actions": [
        {
            "openPopupAction": {
                "popup": {
                    "multiPageMenuRenderer": {
                        "sections": [{"multiPageMenuSectionRenderer": {"items": []}}]
                    }
                }
            }
        }
    ]
}


def test_account_menu_parsing() -> None:
    assert youtube_account_from_menu(_LOGGED_IN) == (True, "Илья")
    assert youtube_account_from_menu(_LOGGED_OUT) == (False, None)
    assert youtube_account_from_menu({}) == (False, None)


class _YT:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self._response, self._error = response, error

    def _send_request(self, endpoint, body):
        if self._error is not None:
            raise self._error
        return self._response


@pytest.fixture
def youtube(monkeypatch):
    def use(client) -> AccountStatus:
        monkeypatch.setattr(membership, "yotube_cookie", lambda: "cookie")
        monkeypatch.setattr(
            membership.Clients, "get_youtube_client", lambda self: client
        )
        return membership._fetch_youtube_sync()

    return use


def test_expired_youtube_session_is_named_not_dumped(youtube) -> None:
    status = youtube(_YT(_LOGGED_OUT))
    assert status.state is AccountState.EXPIRED
    assert status.headline == "Сессия истекла"
    assert "{" not in status.detail


def test_youtube_logged_in_and_network_error(youtube) -> None:
    ok = youtube(_YT(_LOGGED_IN))
    assert ok.state is AccountState.OK and ok.account == "Илья"
    down = youtube(_YT(error=ConnectionError("Connection refused")))
    assert down.state is AccountState.ERROR and down.headline == "Нет связи"


def test_strange_error_text_never_reaches_status(youtube) -> None:
    dump = "Unable to find 'header' using path ['actions', 0] on {'sections': …}"
    status = youtube(_YT(error=KeyError(dump)))
    assert status.state is AccountState.ERROR
    assert "Unable" not in status.detail and "{" not in status.detail


def _status(state: AccountState, headline: str = "x") -> AccountStatus:
    return AccountStatus(state, headline, "Пояснение")


@pytest.fixture
def page(qapp, monkeypatch):
    saved = {"yandex": "token", "youtube": "cookie"}
    monkeypatch.setattr(member_page, "yandex_token", lambda: saved["yandex"])
    monkeypatch.setattr(member_page, "yotube_cookie", lambda: saved["youtube"])
    widget = MemberPage(bridge=None)
    return widget, saved


def test_saved_and_valid_hides_inputs(page) -> None:
    widget, _saved = page
    widget._apply_membership(
        MembershipSnapshot(
            yandex=AccountStatus(
                AccountState.OK, "Плюс до 12.11.2026", "", account="Илья"
            ),
            youtube=_status(AccountState.OK, "Вход выполнен"),
        )
    )
    assert widget._yandex.chip.text() == "Плюс до 12.11.2026"
    assert widget._yandex.chip.property("state") == "ok"
    assert widget._yandex.account.text() == "Илья"
    assert widget._yandex_editor.isHidden() and not widget._yandex_saved.isHidden()
    assert widget._youtube_editor.isHidden()


def test_expired_cookies_open_the_input_right_away(page) -> None:
    widget, _saved = page
    widget._apply_membership(
        MembershipSnapshot(
            yandex=_status(AccountState.OK),
            youtube=_status(AccountState.EXPIRED, "Сессия истекла"),
        )
    )
    assert widget._youtube.chip.property("state") == "expired"
    assert not widget._youtube_editor.isHidden()
    assert widget._youtube_saved.isHidden()


def test_nothing_saved_shows_inputs(page) -> None:
    widget, saved = page
    saved["yandex"] = saved["youtube"] = ""
    widget._sync_access()
    assert not widget._yandex_editor.isHidden()
    assert not widget._youtube_editor.isHidden()


def test_empty_token_is_an_inline_error(page) -> None:
    widget, _saved = page
    widget._edit_yandex_token()
    widget._on_save_yandex_token()
    assert widget._token_feedback.property("state") == "error"
    assert not widget._token_feedback.isHidden()
