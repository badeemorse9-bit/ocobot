"""R4 regression tests: MainWindow must tear down the OLD provider ONLY when no
monitor future is still running against it. On a PAPER mode switch the in-flight
monitor future is cooperatively drained with a bounded (<=2s) wait; if the worker
is still running past that bound, provider.close() is DEFERRED to the future's
completion so it can never race the in-flight task.

These tests exercise MainWindow._drain_monitor_future directly (a staticmethod),
so no QApplication / MainWindow instance is required.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from ocobot.ui.main_window import MainWindow


def test_drain_closes_immediately_when_future_is_none():
    calls = []
    MainWindow._drain_monitor_future(None, lambda: calls.append("closed"))
    assert calls == ["closed"]


def test_drain_closes_after_fast_future_finishes():
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(lambda: "done")
        calls = []
        MainWindow._drain_monitor_future(future, lambda: calls.append("closed"), timeout=2.0)
        assert future.done()
        assert calls == ["closed"]
    finally:
        executor.shutdown(wait=True)


def test_drain_closes_when_future_cancelled_before_start():
    executor = ThreadPoolExecutor(max_workers=1)
    blocker = threading.Event()
    try:
        # Occupy the single worker so the second task stays queued (cancellable).
        executor.submit(lambda: blocker.wait(timeout=5.0))
        queued = executor.submit(lambda: "never")
        assert queued.cancel()
        calls = []
        MainWindow._drain_monitor_future(queued, lambda: calls.append("closed"), timeout=2.0)
        assert calls == ["closed"]
    finally:
        blocker.set()
        executor.shutdown(wait=True)


def test_drain_defers_close_until_slow_future_completes():
    """The core R4 guarantee: while a monitor future is still running, the old
    provider is NOT closed; the close fires strictly after the task completes."""
    executor = ThreadPoolExecutor(max_workers=1)
    release = threading.Event()
    running = threading.Event()

    def slow_task():
        running.set()
        # Simulate a monitor task still using the old provider (slow REST/ws call)
        # past the bounded drain window.
        release.wait(timeout=5.0)
        return "late"

    closed = threading.Event()
    close_order = []

    def close_old():
        # Records whether the task had already been released when close ran.
        close_order.append(release.is_set())
        closed.set()

    try:
        future = executor.submit(slow_task)
        assert running.wait(timeout=2.0)

        # Bounded drain times out because the worker is blocked -> close DEFERRED.
        MainWindow._drain_monitor_future(future, close_old, timeout=0.1)

        # Guarantee: close has NOT happened while the worker is still running.
        assert not closed.is_set()
        assert future.running()

        # Release the task; the deferred close must now fire, strictly afterwards.
        release.set()
        assert closed.wait(timeout=2.0)
        assert future.done()
        assert close_order == [True]
    finally:
        release.set()
        executor.shutdown(wait=True)
