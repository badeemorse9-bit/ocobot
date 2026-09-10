from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from ocobot.application.services import OCOEditorService
from ocobot.providers.binance import BinanceOCOProvider
from ocobot.ui.main_window import MainWindow
from ocobot.ui.testnet_app import TestnetCredentialsDialog, TestnetTradeSetup


class ConnectionBridge(QObject):
    finished = Signal(object)


class TestnetWindow(MainWindow):
    """Stable Testnet entry point using MainWindow's actual central widget layout."""

    def __init__(self) -> None:
        super().__init__()
        self._testnet_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocobot-testnet")
        self._testnet_bridge = ConnectionBridge(self)
        self._testnet_bridge.finished.connect(self._on_connection_finished)
        self.testnet_setup = TestnetTradeSetup(self)
        # MainWindow uses QScrollArea as its central widget; its child owns the layout.
        container = self.centralWidget().widget()
        if container is None or container.layout() is None:
            raise RuntimeError("OCObot main content layout is unavailable")
        container.layout().insertWidget(1, self.testnet_setup)
        self._testnet_connecting = False

    def _open_credentials(self) -> None:
        dialog = TestnetCredentialsDialog(self, self.testnet_api_key, self.testnet_api_secret)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        if not dialog.api_key or not dialog.api_secret:
            QMessageBox.warning(self, "إعداد API", "أدخل API Key وAPI Secret.")
            return
        self.testnet_api_key = dialog.api_key
        self.testnet_api_secret = dialog.api_secret
        self._switch_mode("TESTNET")

    def _switch_mode(self, mode: str) -> None:
        if mode == "PAPER":
            super()._switch_mode("PAPER")
            return
        if mode != "TESTNET":
            return
        if self.mode == "TESTNET":
            self._refresh_orders(False)
            return
        if self._testnet_connecting:
            return
        if not self.testnet_api_key or not self.testnet_api_secret:
            self._open_credentials()
            return

        self._stop_price_subscription()
        self._disable_trail()
        self._testnet_connecting = True
        self.testnet_mode_btn.setEnabled(False)
        self.api_button.setEnabled(False)
        self.connection.setText("● جاري الاتصال بـ Testnet…")
        self.statusBar().showMessage("جارٍ الاتصال وقراءة أوامر Testnet…")
        future = self._testnet_executor.submit(
            self._connect_and_read,
            self.testnet_api_key,
            self.testnet_api_secret,
        )
        future.add_done_callback(lambda fut: self._testnet_bridge.finished.emit(fut.result()))

    @staticmethod
    def _connect_and_read(api_key: str, api_secret: str) -> tuple[bool, object]:
        provider: BinanceOCOProvider | None = None
        try:
            provider = BinanceOCOProvider(mode="TESTNET", api_key=api_key, api_secret=api_secret)
            orders = provider.list_open_ocos()
            return True, (provider, orders)
        except Exception as exc:
            if provider is not None:
                try:
                    provider.close()
                except Exception:
                    pass
            return False, exc

    def _on_connection_finished(self, payload: object) -> None:
        self._testnet_connecting = False
        self.testnet_mode_btn.setEnabled(True)
        self.api_button.setEnabled(True)
        ok, data = payload
        if not ok:
            self.connection.setText("● Testnet — فشل الاتصال")
            self.statusBar().showMessage("فشل اتصال Testnet")
            QMessageBox.warning(self, "TESTNET", f"تعذر الاتصال:\n{data}")
            return

        provider, orders = data
        old = self.provider
        self.provider = provider
        self.service = OCOEditorService(provider)
        self.mode = "TESTNET"
        self._tick_cache.clear()
        self._clear_selection_ui()
        self._set_paper_controls_enabled(False)
        self._set_mode_visuals()
        self._render_orders(orders)
        try:
            getattr(old, "close", lambda: None)()
        except Exception:
            pass
        self.testnet_setup.start_live_stream()
        self.statusBar().showMessage("Testnet متصل — الأوامر الحية جاهزة")

    def _render_orders(self, orders: list) -> None:
        self._building_table = True
        try:
            self.orders.setRowCount(len(orders))
            for row, order in enumerate(orders):
                upper = next((leg.price for leg in order.legs if leg.price is not None and leg.stop_price is None), None)
                stop = next((leg.stop_price for leg in order.legs if leg.stop_price is not None), None)
                qty = order.legs[0].quantity if order.legs else 0
                values = [str(order.order_list_id), order.symbol, str(qty), str(upper or ""), str(stop or ""), order.status.value]
                for col, value in enumerate(values):
                    from PySide6.QtWidgets import QTableWidgetItem
                    self.orders.setItem(row, col, QTableWidgetItem(value))
        finally:
            self._building_table = False

    def closeEvent(self, event) -> None:
        try:
            self._testnet_executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        super().closeEvent(event)


def run_app() -> None:
    app = QApplication(sys.argv)
    window = TestnetWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
