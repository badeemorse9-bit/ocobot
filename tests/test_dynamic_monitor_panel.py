from decimal import Decimal

from PySide6.QtWidgets import QApplication

from ocobot.ui.dynamic_monitor_panel import DynamicMonitorPanel


def _app() -> QApplication:
    app = QApplication.instance()
    return app if app is not None else QApplication([])


def test_panel_exposes_only_three_user_percentage_inputs() -> None:
    _app()
    panel = DynamicMonitorPanel()
    assert panel.trigger_input.text() == "1.00"
    assert panel.tp_input.text() == "4.00"
    assert panel.sl_input.text() == "2.00"
    assert not hasattr(panel, "sl_limit_input")


def test_panel_derives_stop_limit_from_one_tick_gap() -> None:
    _app()
    panel = DynamicMonitorPanel()
    panel.set_live_price(Decimal("0.05000"), Decimal("0.00001"))
    assert panel.tp_value.text() == "0.05200"
    assert panel.sl_trigger_value.text() == "0.04900"
    assert panel.sl_limit_value.text() == "0.04901"


def test_panel_emits_valid_settings() -> None:
    _app()
    panel = DynamicMonitorPanel()
    received = []
    panel.monitoring_requested.connect(received.append)
    panel._request_start()
    assert len(received) == 1
    assert received[0].trigger_rise_percent == Decimal("1.00")
    assert received[0].tp_distance_percent == Decimal("4.00")
    assert received[0].sl_distance_percent == Decimal("2.00")
