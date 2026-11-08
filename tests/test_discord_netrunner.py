"""Discord NetRunner: RpcWorker (реконнект, последнее состояние) и payload."""

from __future__ import annotations

import importlib.util
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import quantis.models  # noqa: F401  (порядок импорта: см. providers↔models)

_PLUGIN = Path(__file__).resolve().parents[1] / "plugins_dir" / "discord_netrunner"
# plugins_dir не в git: плагины живут у разработчика локально.
if not _PLUGIN.is_dir():
    pytest.skip("нет plugins_dir/discord_netrunner", allow_module_level=True)
if str(_PLUGIN) not in sys.path:
    sys.path.insert(0, str(_PLUGIN))

_spec = importlib.util.spec_from_file_location(
    "discord_netrunner_plugin", _PLUGIN / "plugin.py"
)
dn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dn)


class FakeRpc:
    def __init__(self, log: list, *, fail_connect=False, fail_update=False):
        self.log = log
        self.fail_connect = fail_connect
        self.fail_update = fail_update
        self.closed = False

    def connect(self):
        if self.fail_connect:
            raise ConnectionRefusedError
        self.log.append(("connect", self))

    def update(self, **payload):
        if self.fail_update:
            raise BrokenPipeError
        self.log.append(("update", payload))

    def close(self):
        self.closed = True


def _wait_for(cond, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def _worker(factory, **kw):
    kw.setdefault("min_gap", 0.0)
    kw.setdefault("reconnect_every", 0.05)
    kw.setdefault("reconnect_after_drop", 0.05)
    w = dn.RpcWorker(factory, **kw)
    w.start()
    return w


def _updates(log):
    return [p for kind, p in log if kind == "update"]


def test_reconnects_when_discord_starts_later():
    log: list = []
    discord_up = threading.Event()

    def factory():
        return FakeRpc(log, fail_connect=not discord_up.is_set())

    w = _worker(factory)
    try:
        w.submit(lambda: {"details": "a"})
        time.sleep(0.15)
        assert _updates(log) == []
        discord_up.set()
        assert _wait_for(lambda: _updates(log) == [{"details": "a"}])
    finally:
        w.stop()


def test_reconnects_after_pipe_drop_and_resends_state():
    log: list = []
    rpcs: list[FakeRpc] = []

    def factory():
        rpc = FakeRpc(log, fail_update=not rpcs)  # первый — «умерший» Discord
        rpcs.append(rpc)
        return rpc

    w = _worker(factory)
    try:
        w.submit(lambda: {"details": "a"})
        assert _wait_for(lambda: _updates(log) == [{"details": "a"}])
        assert rpcs[0].closed
        assert len(rpcs) == 2
    finally:
        w.stop()


def test_only_latest_state_is_sent():
    log: list = []
    gate = threading.Event()

    def factory():
        gate.wait(2)
        return FakeRpc(log)

    w = _worker(factory)
    try:
        for i in range(10):
            w.submit(lambda i=i: {"details": str(i)})
        gate.set()
        assert _wait_for(lambda: _updates(log))
        time.sleep(0.1)
        assert _updates(log) == [{"details": "9"}]
    finally:
        w.stop()


def test_stop_closes_connection():
    log: list = []
    rpcs: list[FakeRpc] = []

    def factory():
        rpcs.append(FakeRpc(log))
        return rpcs[-1]

    w = _worker(factory)
    w.submit(lambda: {"details": "a"})
    assert _wait_for(lambda: _updates(log))
    w.stop()
    assert rpcs[-1].closed
    assert not w.connected


def test_old_pypresence_fallback_drops_new_fields():
    calls = []

    class Old:
        def update(self, details=None, state=None):
            calls.append((details, state))

    dn.call_update(Old(), {"details": "t", "state": "a", "details_url": "x"})
    assert calls == [("t", "a")]


def _plugin():
    p = dn.DiscordNetRunner.__new__(dn.DiscordNetRunner)
    p._cover_cache = {}
    p._activity_playing = 0
    p._activity_listening = 2
    p._status_details = None
    return p


_TRACK = SimpleNamespace(
    source="youtube", track_id="abc", title="Song", author="Band", thumbnail_url=""
)


def test_paused_payload_has_no_timeline_but_keeps_artist():
    p = _plugin()
    payload = p._payload(
        _TRACK, paused=True, duration_ms=200_000, position_ms=50_000, now=1000.0
    )
    assert "start" not in payload and "end" not in payload
    assert "Band" in payload["state"]


def test_playing_payload_timeline_follows_position():
    p = _plugin()
    payload = p._payload(
        _TRACK, paused=False, duration_ms=200_000, position_ms=50_000, now=1000.0
    )
    assert payload["start"] == 1_000_000 - 50_000
    assert payload["end"] == payload["start"] + 200_000
    assert payload["state"] == "Band"


def test_seek_uses_position_from_event():
    p = _plugin()
    jobs = []
    p._worker = SimpleNamespace(submit=jobs.append)
    p._current_track = _TRACK
    player = SimpleNamespace(
        on_pause=False, is_playing=lambda: True, duration=200_000, time=10_000
    )
    p.host = SimpleNamespace(playback=SimpleNamespace(player=player))
    p._on_playback_seeked(120_000)
    payload = jobs[-1]()
    assert payload["end"] - payload["start"] == 200_000
    assert abs((time.time() * 1000 - payload["start"]) - 120_000) < 2_000


def test_status_offline_then_connected():
    log: list = []
    statuses: list[str] = []
    discord_up = threading.Event()

    def factory():
        return FakeRpc(log, fail_connect=not discord_up.is_set())

    w = _worker(factory, on_status=statuses.append)
    try:
        w.submit(lambda: {"details": "a"})
        assert _wait_for(lambda: statuses == ["offline"])
        time.sleep(0.15)  # повторные неудачи не спамят
        assert statuses == ["offline"]
        discord_up.set()
        assert _wait_for(lambda: statuses == ["offline", "connected"])
    finally:
        w.stop()


def test_status_silent_on_first_successful_connect():
    log: list = []
    statuses: list[str] = []
    w = _worker(lambda: FakeRpc(log), on_status=statuses.append)
    try:
        w.submit(lambda: {"details": "a"})
        assert _wait_for(lambda: _updates(log))
        assert statuses == []
    finally:
        w.stop()


def test_status_lost_then_connected_without_offline():
    log: list = []
    statuses: list[str] = []
    rpcs: list[FakeRpc] = []
    discord_up = threading.Event()
    discord_up.set()

    def factory():
        # первый «умирает» на update, затем Discord какое-то время недоступен
        if rpcs and not discord_up.is_set():
            return FakeRpc(log, fail_connect=True)
        rpc = FakeRpc(log, fail_update=not rpcs)
        rpcs.append(rpc)
        if len(rpcs) == 1:
            discord_up.clear()
        return rpc

    w = _worker(factory, on_status=statuses.append)
    try:
        w.submit(lambda: {"details": "a"})
        assert _wait_for(lambda: statuses == ["lost"])
        time.sleep(0.15)
        assert statuses == ["lost"]  # без «offline» поверх «lost»
        discord_up.set()
        assert _wait_for(lambda: statuses == ["lost", "connected"])
        assert _wait_for(lambda: _updates(log) == [{"details": "a"}])
    finally:
        w.stop()


def test_plugin_maps_status_to_host_notify():
    p = _plugin()
    calls = []
    p.host = SimpleNamespace(notify=lambda *a: calls.append(a))
    p._on_rpc_status("lost")
    p._on_rpc_status("connected")
    p._on_rpc_status("unknown")
    assert [c[0] for c in calls] == ["Discord", "Discord"]
    assert [c[2] for c in calls] == ["error", "success"]


def test_plugin_status_without_host_notify_is_noop():
    p = _plugin()
    p.host = SimpleNamespace()
    p._on_rpc_status("offline")
