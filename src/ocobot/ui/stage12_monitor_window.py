from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame

from ocobot.application.live_price import PriceSnapshot
from ocobot.ui.dynamic_monitor_panel import DynamicMonitorPanel
from ocobot.ui.stage12_window import Stage12Window


class Stage12MonitorWindow(Stage12Window):
    """Stage 2 with the isolated Dynamic Trade Monitoring configuration panel."""

    def __init__(self) -> None:
        super().__init__()
        self.monitor_panel = DynamicMonitorPanel()
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
        self.monitor_panel.monitoring_stopped.connect(lambda: self.monitor_panel.set_monitoring_state(False))
        if self.selected is not None:
            self._refresh_monitor_preview()

    def _select_row(self) -> None:
        super()._select_row()
        self.monitor_panel.set_enabled(self.selected is not None)
        self._refresh_monitor_preview()

    def _on_price(self, snapshot: PriceSnapshot) -> None:
        super()._on_price(snapshot)
        self._refresh_monitor_preview(snapshot.price)

    def _refresh_monitor_preview(self, live_price: Decimal | None = None) -> None:
        if self.selected is None:
            return
        price = live_price or self._fixture_preview_price(self.selected.symbol)
        self.monitor_panel.set_live_price(price, Decimal("0.00001"))

    @staticmethod
    def _fixture_preview_price(symbol: str) -> Decimal:
        return Decimal("0.02300") if symbol == "TUTUSDT" else Decimal("1")

    def _monitor_requested(self, settings) -> None:
        self.monitor_panel.set_monitoring_state(
            True,
            f"Monitoring Active — Trigger +{settings.trigger_rise_percent:f}%",
        )


def main() -> None:
    app = QApplication.instance() or QApplication([])
    window = Stage12MonitorWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
