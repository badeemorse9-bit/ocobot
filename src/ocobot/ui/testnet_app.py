from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from typing import Any

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QTableWidgetItem,
)

from ocobot.domain.validation import highest_sell_stop_candidate
from ocobot.providers.binance import BinanceOCOProvider
from ocobot.ui.main_window import MainWindow, TestnetCredentialsDialog
from ocobot.application.services import OCOEditorService


class SetupPriceBridge(QObject):
    price = Signal(object)

    def push(self, price: Decimal) -> None:
        self.price.emit(price)


class ConnectionBridge(QObject):
    finished = Signal(object)


def executed_average_price(response: dict[str, Any]) -> tuple[Decimal, Decimal]:
    executed_qty = Decimal(str(response.get("executedQty", "0")))
    fills = response.get("fills")
    if isinstance(fills, list):
        total_qty = Decimal("0")
        total_value = Decimal("0")
        for fill in fills:
            if not isinstance(fill, dict):
                continue
            try:
                qty = Decimal(str(fill["qty"]))
                price = Decimal(str(fill["price"]))
            except (KeyError, InvalidOperation, ValueError):
                continue
            if qty > 0:
                total_qty += qty
                total_value += qty * price
        if total_qty > 0:
            return total_qty, total_value / total_qty
    if executed_qty <= 0:
        raise ValueError("Binance returned no executed quantity")
    price = Decimal(str(response.get("price", "0")))
    if price <= 0:
        raise ValueError("Binance response does not contain usable fill price data")
    return executed_qty, price


class TestnetTradeSetup(QGroupBox):
    """TESTNET-only account preparation; compact and WebSocket-driven."""

    def __init__(self, host: MainWindow) -> None:
        super().__init__("تجهيز صفقة Testnet")
        self.host = host
        self.executed_qty = Decimal("0")
        self.current_price = Decimal("0")
        self.tick_size = Decimal("0")
        self._unsubscribe: Any = None
        self._bridge = SetupPriceBridge(self)
        self._bridge.price.connect(self._on_live_price)
        self._build()
        self.symbol_edit.editingFinished.connect(self._restart_price_stream)
        self._restart_price_stream()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 5, 8, 5)
        root.setSpacing(4)
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        for col in (1, 3, 5):
            grid.setColumnStretch(col, 1)

        self.symbol_edit = QLineEdit("BTCUSDT")
        self.amount_edit = QLineEdit("20")
        self.buy_button = QPushButton("شراء Testnet")
        self.buy_status = QLabel("لا توجد عملية شراء")
        self.buy_status.setStyleSheet("font-weight:700;")
        grid.addWidget(QLabel("العملة"), 0, 0)
        grid.addWidget(self.symbol_edit, 0, 1)
        grid.addWidget(QLabel("USDT"), 0, 2)
        grid.addWidget(self.amount_edit, 0, 3)
        grid.addWidget(self.buy_button, 0, 4)
        grid.addWidget(self.buy_status, 0, 5)
        self.buy_button.clicked.connect(self._place_buy)

        self.executed_qty_label = QLabel("—")
        self.average_fill_label = QLabel("—")
        self.current_price_label = QLabel("—")
        grid.addWidget(QLabel("الكمية المنفذة"), 1, 0)
        grid.addWidget(self.executed_qty_label, 1, 1)
        grid.addWidget(QLabel("متوسط التنفيذ"), 1, 2)
        grid.addWidget(self.average_fill_label, 1, 3)
        grid.addWidget(QLabel("السعر الآن"), 1, 4)
        grid.addWidget(self.current_price_label, 1, 5)

        self.tp_edit = QLineEdit()
        self.stop_edit = QLineEdit()
        self.stop_limit_edit = QLineEdit()
        self.tp_edit.setPlaceholderText("أعلى من السعر")
        self.stop_edit.setPlaceholderText("أقل من السعر")
        self.stop_limit_edit.setPlaceholderText("Stop-limit")
        self.auto_stop_check = QCheckBox("ستوب تلقائي MAX")
        self.auto_stop_check.setChecked(True)
        self.auto_stop_button = QPushButton("تطبيق")
        self.auto_stop_button.clicked.connect(self._apply_auto_stop_loss)
        self.oco_button = QPushButton("إنشاء OCO Testnet")
        self.oco_button.setEnabled(False)
        self.oco_button.clicked.connect(self._create_oco)

        grid.addWidget(QLabel("بيع TP"), 2, 0)
        grid.addWidget(self.tp_edit, 2, 1)
        grid.addWidget(self.auto_stop_check, 2, 2)
        grid.addWidget(self.auto_stop_button, 2, 3)
        grid.addWidget(QLabel("الاستوب"), 2, 4)
        grid.addWidget(self.stop_edit, 2, 5)
        grid.addWidget(QLabel("Stop-limit"), 3, 0)
        grid.addWidget(self.stop_limit_edit, 3, 1)
        grid.addWidget(self.oco_button, 3, 2, 1, 4)
        root.addLayout(grid)
        self.oco_status = QLabel("بانتظار شراء ناجح")
        self.oco_status.setStyleSheet("color:#5f6b76;")
        root.addWidget(self.oco_status)
        self.setMaximumHeight(125)

    def _provider(self) -> BinanceOCOProvider:
        if self.host.mode != "TESTNET" or not isinstance(self.host.provider, BinanceOCOProvider):
            raise RuntimeError("فعّل TESTNET أولًا")
        return self.host.provider

    def _restart_price_stream(self) -> None:
        self._stop_stream()
        try:
            provider = self._provider()
            symbol = self.symbol_edit.text().strip().upper()
            if not symbol:
                return
            self.current_price = provider.get_last_price(symbol)
            self.tick_size = provider.get_tick_size(symbol)
            self._on_live_price(self.current_price)
            self._unsubscribe = provider.subscribe_price(symbol, self._bridge.push)
        except Exception:
            pass

    def start_live_stream(self) -> None:
        self._stop_stream()
        try:
            provider = self._provider()
            symbol = self.symbol_edit.text().strip().upper()
            if symbol:
                self._unsubscribe = provider.subscribe_price(symbol, self._bridge.push)
        except Exception:
            pass

    def _stop_stream(self) -> None:
        if self._unsubscribe:
            try:
                self._unsubscribe()
            except Exception:
                pass
            self._unsubscribe = None

    def _on_live_price(self, price: Decimal) -> None:
        self.current_price = price
        self.current_price_label.setText(f"{price:f}")
        if self.auto_stop_check.isChecked() and self.executed_qty > 0 and self.tick_size > 0:
            stop = highest_sell_stop_candidate(price, self.tick_size)
            self.stop_edit.setText(f"{stop:f}")
            self.stop_limit_edit.setText(f"{stop - self.tick_size:f}")

    def _apply_auto_stop_loss(self) -> None:
        try:
            provider = self._provider()
            symbol = self.symbol_edit.text().strip().upper()
            price = provider.get_last_price(symbol)
            tick = provider.get_tick_size(symbol)
            self.tick_size = tick
            self._on_live_price(price)
            self.oco_status.setText(f"ستوب تلقائي: {self.stop_edit.text()}")
        except Exception as exc:
            QMessageBox.warning(self, "الستوب التلقائي", str(exc))

    def _place_buy(self) -> None:
        try:
            provider = self._provider()
            symbol = self.symbol_edit.text().strip().upper()
            amount = Decimal(self.amount_edit.text().strip())
            if amount <= 0:
                raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
            response = provider.place_market_buy(symbol, amount)
            self.executed_qty, avg = executed_average_price(response)
            self.executed_qty_label.setText(f"{self.executed_qty:f}")
            self.average_fill_label.setText(f"{avg:f}")
            self.buy_status.setText(f"تم الشراء #{response.get('orderId', '—')}")
            self.oco_button.setEnabled(True)
            self._restart_price_stream()
            self.oco_status.setText("تم الشراء — حدد TP أو اترك الستوب التلقائي")
        except (InvalidOperation, ValueError) as exc:
            QMessageBox.warning(self, "شراء Testnet", str(exc))
        except Exception as exc:
            self.buy_status.setText("فشل الشراء")
            QMessageBox.warning(self, "شراء Testnet", str(exc))

    def _price(self, edit: QLineEdit, label: str) -> Decimal:
        text = edit.text().strip()
        if not text:
            raise ValueError(f"أدخل {label}")
        try:
            value = Decimal(text)
        except (InvalidOperation, ValueError):
            raise ValueError(f"{label} غير صحيح")
        if value <= 0:
            raise ValueError(f"{label} يجب أن يكون أكبر من صفر")
        return value

    def _create_oco(self) -> None:
        try:
            provider = self._provider()
            symbol = self.symbol_edit.text().strip().upper()
            current = provider.get_last_price(symbol)
            self._on_live_price(current)
            tp = self._price(self.tp_edit, "سعر البيع")
            stop = self._price(self.stop_edit, "الاستوب")
            stop_limit = self._price(self.stop_limit_edit, "Stop-limit")
            if not (tp > current > stop):
                raise ValueError(f"السعر الحالي {current}. يجب أن يكون TP > السعر الحالي > الاستوب")
            if stop_limit > stop:
                raise ValueError("Stop-limit يجب أن يكون عند أو أقل من الاستوب")
            response = provider.place_oco({
                "symbol": symbol,
                "side": "SELL",
                "quantity": str(self.executed_qty),
                "abovePrice": str(tp),
                "belowPrice": str(stop_limit),
                "belowStopPrice": str(stop),
                "aboveType": "LIMIT_MAKER",
                "belowType": "STOP_LOSS_LIMIT",
                "belowTimeInForce": "GTC",
            })
            list_id = response.get("orderListId")
            if list_id is None:
                raise RuntimeError("لم يعط Binance رقم OCO")
            self.oco_status.setText(f"تم إنشاء OCO #{list_id}")
            self.host._refresh_orders(False)
        except Exception as exc:
            self.oco_status.setText("فشل إنشاء OCO")
            QMessageBox.warning(self, "إنشاء OCO", str(exc))

    def close(self) -> None:
        self._stop_stream()


class TestnetMainWindow(MainWindow):
    """TESTNET entry point that never blocks the Qt GUI during connection/read."""

    def __init__(self) -> None:
        super().__init__()
        self._testnet_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ocobot-testnet")
        self._testnet_bridge = ConnectionBridge(self)
        self._testnet_bridge.finished.connect(self._testnet_worker_finished)
        self.testnet_setup = TestnetTradeSetup(self)
        self.centralWidget().layout().insertWidget(1, self.testnet_setup)
        self._testnet_connecting = False

    def _open_credentials(self) -> None:
        super()._open_credentials()
        if self.mode == "PAPER" and self.testnet_api_key and self.testnet_api_secret:
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
        future.add_done_callback(lambda fut: self._testnet_bridge.finished.emit(("connect", fut.result())))

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

    def _testnet_worker_finished(self, payload: object) -> None:
        if not isinstance(payload, tuple) or len(payload) != 2:
            return
        kind, result = payload
        if kind != "connect":
            return
        self._testnet_connecting = False
        self.testnet_mode_btn.setEnabled(True)
        self.api_button.setEnabled(True)
        ok, data = result
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
        self._render_orders(orders, preserve_selection=False)
        try:
            getattr(old, "close", lambda: None)()
        except Exception:
            pass
        self.testnet_setup.start_live_stream()
        self.statusBar().showMessage("Testnet متصل — الأوامر الحية جاهزة")

    def _render_orders(self, orders: list, preserve_selection: bool) -> None:
        selected = self.service.selection.order_list_id if preserve_selection and self.service.selection else None
        self.orders.setRowCount(len(orders))
        row_to_select = -1
        self._building_table = True
        try:
            for row, order in enumerate(orders):
                upper = next((leg.price for leg in order.legs if leg.price is not None and leg.stop_price is None), None)
                stop = next((leg.stop_price for leg in order.legs if leg.stop_price is not None), None)
                qty = order.legs[0].quantity if order.legs else Decimal("0")
                values = [str(order.order_list_id), order.symbol, str(qty), str(upper or ""), str(stop or ""), order.status.value]
                for col, value in enumerate(values):
                    self.orders.setItem(row, col, QTableWidgetItem(value))
                if selected is not None and order.order_list_id == selected:
                    row_to_select = row
            if row_to_select >= 0:
                self.orders.selectRow(row_to_select)
        finally:
            self._building_table = False

    def _refresh_orders(self, preserve_selection: bool = True) -> None:
        if self.mode != "TESTNET":
            return super()._refresh_orders(preserve_selection)
        if getattr(self, "_testnet_connecting", False):
            return
        selected = self.service.selection.order_list_id if preserve_selection and self.service.selection else None
        future = self._testnet_executor.submit(self.service.refresh_open_orders)
        future.add_done_callback(lambda fut: self._testnet_bridge.finished.emit(("orders", selected, fut)))

    def _testnet_worker_finished(self, payload: object) -> None:
        if not isinstance(payload, tuple):
            return
        if payload and payload[0] == "connect":
            kind, result = payload
            self._finish_connection(result)
            return
        if payload and payload[0] == "orders":
            _, selected, future = payload
            try:
                orders = future.result()
            except Exception as exc:
                self.statusBar().showMessage(f"خطأ قراءة الأوامر: {exc}")
                return
            self._render_orders(orders, preserve_selection=selected is not None)

    def _finish_connection(self, result: tuple[bool, object]) -> None:
        ok, data = result
        self._testnet_connecting = False
        self.testnet_mode_btn.setEnabled(True)
        self.api_button.setEnabled(True)
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
        self._render_orders(orders, preserve_selection=False)
        try:
            getattr(old, "close", lambda: None)()
        except Exception:
            pass
        self.testnet_setup.start_live_stream()
        self.statusBar().showMessage("Testnet متصل — الأوامر الحية جاهزة")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        try:
            self.testnet_setup.close()
        except Exception:
            pass
        try:
            self._testnet_executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        super().closeEvent(event)


def run_app() -> None:
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    window = TestnetMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
