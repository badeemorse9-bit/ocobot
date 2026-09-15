"""R2 regression tests: after an OCO auto-rollover, MainWindow must rehydrate the
editor selection against the NEW orderListId (never keep the old cancelled
selection, never auto-select a different OCO); stale monitor results must be
dropped by the generation guard.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from ocobot.application.monitor_coordinator import MonitorReplacementResult
from ocobot.application.services import OCOEditorService
from ocobot.providers.paper import PaperOCOProvider
from ocobot.providers.sample_data import sample_ocos
from ocobot.ui.main_window import MainWindow

PRICES = {"FIDAUSDT": Decimal("0.078210")}
TICKS = {"FIDAUSDT": Decimal("0.000001")}


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _fidausdt_order():
    for order in sample_ocos():
        if order.order_list_id == 1003:
            return order
    raise AssertionError("sample_ocos() no longer contains the 1003 FIDAUSDT OCO")


def _two_oco_window():
    old = _fidausdt_order()
    new = replace(old, order_list_id=2003)
    provider = PaperOCOProvider([old, new], dict(PRICES), dict(TICKS))
    window = MainWindow()
    window.provider = provider
    window.service = OCOEditorService(provider)
    return window


def test_rollover_success_rehydrates_new_selection(qapp):
    window = _two_oco_window()
    window.service.select(1003)
    assert window.service.selection.order_list_id == 1003

    result = MonitorReplacementResult(
        success=True,
        message="rolled over",
        old_order_list_id=1003,
        new_order_list_id=2003,
        state="SUCCESS",
    )
    window._apply_monitor_result(result)

    assert window._selected_id == 2003
    assert window.service.selection is not None
    assert window.service.selection.order_list_id == 2003
    assert window.service.original.order_list_id == 2003
    window.close()


def test_rollover_reselect_failure_is_failsafe(qapp):
    window = _two_oco_window()
    window.service.select(1003)

    def _boom(*_args, **_kwargs):
        raise ValueError("simulated reload failure")

    select_calls = []
    original_boom = _boom

    def _boom_recording(*args, **kwargs):
        select_calls.append(args)
        return original_boom(*args, **kwargs)

    window.service.select = _boom_recording
    spy = MagicMock()
    window.dynamic_monitor_panel.set_monitoring_state = spy

    result = MonitorReplacementResult(
        success=True,
        message="rolled over",
        old_order_list_id=1003,
        new_order_list_id=2003,
        state="SUCCESS",
    )
    window._apply_monitor_result(result)

    assert window.service.selection is None
    assert window.service.original is None
    assert window.service.draft is None
    assert spy.called
    args, _kwargs = spy.call_args
    assert args[0] is False
    # select() was only ever attempted for the NEW id, never a different OCO.
    for call_args in select_calls:
        if call_args:
            assert call_args[0] == 2003
    window.close()


def test_stale_generation_result_is_dropped(qapp):
    window = MainWindow()
    window.service.select(1003)
    selection_before = window.service.selection
    window._selected_id = 1003

    window._finish_monitor_price(
        window._monitor_generation + 999,
        window.provider,
        window.monitor_coordinator,
        None,
    )

    assert window.service.selection is selection_before
    assert window._selected_id == 1003
    window.close()


def test_non_success_result_does_not_rehydrate(qapp):
    from ocobot.application.monitor_coordinator import ABORTED_NO_CREATE

    window = _two_oco_window()
    window.service.select(1003)
    selection_before = window.service.selection
    assert selection_before.order_list_id == 1003

    select_spy = MagicMock()
    window.service.select = select_spy
    state_spy = MagicMock()
    window.dynamic_monitor_panel.set_monitoring_state = state_spy

    result = MonitorReplacementResult(
        success=False,
        message="aborted before cancel",
        old_order_list_id=1003,
        new_order_list_id=None,
        state=ABORTED_NO_CREATE,
    )
    window._apply_monitor_result(result)

    select_spy.assert_not_called()
    assert window.service.selection is selection_before
    assert window.service.selection.order_list_id == 1003
    assert window.monitor_coordinator is None
    assert state_spy.called
    args, _kwargs = state_spy.call_args
    assert args[0] is False
    window.close()
