from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import QApplication, QFrame

from ocobot.application.dynamic_monitor import DynamicMonitorSettings
from ocobot.application.live_price import PriceSnapshot
from ocobot.application.monitor_coordinator import DynamicMonitorCoordinator, MonitorReplacementResult
from ocobot.providers.demo_monitor import DemoMonitorProvider
from ocobot.ui.dynamic_monitor_panel import DynamicMonitorPanel
from ocobot.ui.stage12_window import Stage12Window


class Stage12MonitorWindow(Stage12Window):
    """Stage 2 with Demo-only Dynamic Trade Monitoring."""

    def __init__(self) -> None:
        self.monitor_panel = DynamicMonitorPanel()
        self.demo_provider: DemoMonitorProvider | None = None
        self.monitor_coordinator: DynamicMonitorCoordinator | None = None
        super().__init__()
        cards = self.findChildren(QFrame, "card")
        if len(cards) < 2:
            raise RuntimeError("Stage 2 right detail card was not found")
        right_card = cards[1]
        layout = right_card.layout()
        if layout is None:
            raise RuntimeError("Stage 2 right detail layout was not found")
        raw = right_card.findChild(QFrame, "raw")
        insert_at = layout.indexOf(raw) if raw is not None else layout.count()
        layout.insertWidget(max(0, insert_at), self.monitor_panel)
        self.monitor_panel.set_enabled(self.selected is not None)
        self.monitor_panel.monitoring_requested.connect(self._monitor_requested)
        self.monitor_panel.monitoring_stopped.connect(self._stop_monitoring)
        if self.selected is not None:
            self._prepare_demo_provider()
            self._refresh_monitor_preview()

    def _select_row(self) -> None:
        self._stop_monitoring()
        super()._select_row()
        self.monitor_panel.set_enabled(self.selected is not None)
        if self.selected is not None:
            self._prepare_demo_provider()
            self._refresh_monitor_preview()

    def _on_price(self, snapshot: PriceSnapshot) -> None:
        super()._on_price(snapshot)
        if self.demo_provider is not None:
            self.demo_provider.set_price(snapshot.price)
        self._refresh_monitor_preview(snapshot.price)
        if self.monitor_coordinator is not None:
            result = self.monitor_coordinator.on_price(snapshot.price, symbol=snapshot.symbol)
            if result is not None:
                self._handle_replacement_result(result)

    def _prepare_demo_provider(self) -> None:
        if self.selected is None:
            self.demo_provider = None
            self.monitor_coordinator = None
            return
        self.demo_provider = DemoMonitorProvider(self.selected)
        preview = self._fixture_preview_price(self.selected.symbol)
        self.demo_provider.set_price(preview)
        self.monitor_coordinator = None

    def _refresh_monitor_preview(self, live_price: Decimal | None = None) -> None:
        if self.selected is None:
            return
        price = live_price or self._fixture_preview_price(self.selected.symbol)
        if self.demo_provider is not None:
            self.demo_provider.set_price(price)
        self.monitor_panel.set_live_price(price, Decimal("0.00001"))

    @staticmethod
    def _fixture_preview_price(symbol: str) -> Decimal:
        return Decimal("0.02300") if symbol == "TUTUSDT" else Decimal("1")

    def _monitor_requested(self, settings: DynamicMonitorSettings) -> None:
        if self.selected is None or self.demo_provider is None:
            self.monitor_panel.set_monitoring_state(False, "Select an OCO first")
            return
        try:
            self.monitor_coordinator = DynamicMonitorCoordinator(
                self.demo_provider,
                self.selected.order_list_id,
                settings,
            )
            self.monitor_coordinator.start(self.demo_provider.get_last_price(self.selected.symbol))
        except Exception as exc:
            self.monitor_coordinator = None
            self.monitor_panel.set_monitoring_state(False, f"Demo start failed: {exc}")
            return
        self.monitor_panel.set_monitoring_state(
            True,
            f"DEMO Monitoring Active — Trigger +{settings.trigger_rise_percent:f}%",
        )

    def _stop_monitoring(self) -> None:
        if self.monitor_coordinator is not None:
            self.monitor_coordinator.stop()
        self.monitor_coordinator = None
        if hasattr(self, "monitor_panel"):
            self.monitor_panel.set_monitoring_state(False)

    def _handle_replacement_result(self, result: MonitorReplacementResult) -> None:
        if result.success and self.demo_provider is not None:
            replacement = self.demo_provider.get_oco(result.new_order_list_id or result.old_order_list_id)
            if replacement is not None:
                self.selected = replacement
                self.selected_pill.setText(f"orderListId: {replacement.order_list_id}")
                self.raw_text.setText(self._raw_preview(replacement))
                self._fill_leg_card(self._leg_row.itemAt(0).widget(), self._tp_leg(replacement), "green")
                self._fill_leg_card(self._leg_row.itemAt(1).widget(), self._sl_leg(replacement), "red")
            self.monitor_panel.set_monitoring_state(
                True,
                f"DEMO Repositioned — New orderListId {replacement.order_list_id if replacement else '—'}",
            )
        else:
            self.monitor_panel.set_monitoring_state(False, f"DEMO stopped: {result.message}")
            self.monitor_coordinator = None

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._stop_monitoring()
        super().closeEvent(event)


def main() -> None:
    app = QApplication.instance() or QApplication([])
    window = Stage12MonitorWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
