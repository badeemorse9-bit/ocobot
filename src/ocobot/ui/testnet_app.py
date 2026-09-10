from __future__ import annotations

import sys
from decimal import Decimal, InvalidOperation
from typing import Any

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QCheckBox, QGridLayout, QGroupBox, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout

from ocobot.application.dynamic_stop import dynamic_sell_stop_limit, dynamic_sell_stop_price
from ocobot.domain.validation import validate_sell_oco_relationship
from ocobot.providers.binance import BinanceOCOProvider
from ocobot.ui.main_window import MainWindow, TestnetCredentialsDialog


class SetupPriceBridge(QObject):
    price = Signal(object)

    def push(self, price: Decimal) -> None:
        self.price.emit(price)


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
    """TESTNET-only buy preparation and OCO creation using the global dynamic stop."""

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
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(7)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(7)
        for col in (1, 3, 5):
            grid.setColumnStretch(col, 1)

        self.symbol_edit = QLineEdit("BTCUSDT")
        self.amount_edit = QLineEdit("20")
        self.buy_button = QPushButton("شراء Testnet")
        self.buy_status = QLabel("لا توجد عملية شراء")
        self.buy_status.setStyleSheet("font-weight:800;")
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
        self.tp_edit.setPlaceholderText("أعلى من السعر الحالي")
        self.stop_edit.setPlaceholderText("يحسب من النسبة العامة")
        self.stop_limit_edit.setPlaceholderText("أقل من Trigger")
        self.auto_stop_check = QCheckBox("استخدام الاستوب الديناميكي")
        self.auto_stop_check.setChecked(True)
        self.dynamic_stop_button = QPushButton("تطبيق الآن")
        self.dynamic_stop_button.setObjectName("accent")
        self.dynamic_stop_button.clicked.connect(self._apply_auto_stop_loss)
        self.oco_button = QPushButton("إنشاء OCO Testnet")
        self.oco_button.setObjectName("success")
        self.oco_button.setEnabled(False)
        self.oco_button.clicked.connect(self._create_oco)
        grid.addWidget(QLabel("بيع TP"), 2, 0)
        grid.addWidget(self.tp_edit, 2, 1)
        grid.addWidget(self.auto_stop_check, 2, 2)
        grid.addWidget(self.dynamic_stop_button, 2, 3)
        grid.addWidget(QLabel("الاستوب SL"), 2, 4)
        grid.addWidget(self.stop_edit, 2, 5)
        grid.addWidget(QLabel("Stop-limit"), 3, 0)
        grid.addWidget(self.stop_limit_edit, 3, 1)
        grid.addWidget(self.oco_button, 3, 2, 1, 4)
        root.addLayout(grid)
        self.oco_status = QLabel("الاستوب الديناميكي العام: 0.50% من السعر اللحظي")
        self.oco_status.setStyleSheet("color:#596b7c;")
        root.addWidget(self.oco_status)

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
            return

    def start_live_stream(self) -> None:
        self._restart_price_stream()

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
        self.oco_status.setText(f"الاستوب الديناميكي العام: {self.host.dynamic_stop_percent}% من السعر اللحظي")
        if self.auto_stop_check.isChecked() and self.tick_size > 0 and price > 0 and self.executed_qty > 0:
            try:
                stop = dynamic_sell_stop_price(price, self.host.dynamic_stop_percent, self.tick_size)
                self.stop_edit.setText(f"{stop:f}")
                self.stop_limit_edit.setText(f"{dynamic_sell_stop_limit(stop, self.tick_size):f}")
            except Exception:
                pass

    def _apply_auto_stop_loss(self) -> None:
        try:
            provider = self._provider()
            symbol = self.symbol_edit.text().strip().upper()
            price = provider.get_last_price(symbol)
            self.tick_size = provider.get_tick_size(symbol)
            self._on_live_price(price)
            self.oco_status.setText(f"تم تطبيق الاستوب الديناميكي {self.host.dynamic_stop_percent}%: {self.stop_edit.text()}")
        except Exception as exc:
            QMessageBox.warning(self, "الاستوب الديناميكي", str(exc))

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
            self._apply_auto_stop_loss()
            self.oco_status.setText("تم الشراء — حدد TP ثم أنشئ OCO")
        except (InvalidOperation, ValueError) as exc:
            QMessageBox.warning(self, "شراء Testnet", str(exc))
        except Exception as exc:
            self.buy_status.setText("فشل الشراء")
            QMessageBox.warning(self, "شراء Testnet", str(exc))

    @staticmethod
    def _price(edit: QLineEdit, label: str) -> Decimal:
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
            ok, message = validate_sell_oco_relationship(current, tp, stop)
            if not ok:
                raise ValueError(message)
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
    """Compatibility entry point; the main window now owns Testnet navigation."""

    def __init__(self) -> None:
        super().__init__()
        self.testnet_setup = TestnetTradeSetup(self)
        self.attach_testnet_setup(self.testnet_setup)


def run_app() -> None:
    app = __import__("PySide6.QtWidgets", fromlist=["QApplication"]).QApplication(sys.argv)
    window = TestnetMainWindow()
    window.show()
    sys.exit(app.exec())
