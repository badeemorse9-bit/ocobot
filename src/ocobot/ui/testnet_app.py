from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox, QGroupBox, QGridLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout

from ocobot.domain.validation import highest_sell_stop_candidate
from ocobot.providers.binance import BinanceOCOProvider
from ocobot.ui.main_window import MainWindow


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
    """Compact TESTNET-only account-preparation utility; separate from V1."""

    def __init__(self, host: MainWindow) -> None:
        super().__init__("Testnet Account Prep — TESTNET only")
        self.host = host
        self.last_buy: dict[str, Any] | None = None
        self.executed_qty = Decimal("0")
        self.current_price = Decimal("0")
        self.tick_size = Decimal("0")
        self._build()
        self._price_timer = QTimer(self)
        self._price_timer.timeout.connect(self._refresh_market_price)
        self._price_timer.start(1500)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 5, 8, 5)
        root.setSpacing(4)

        note = QLabel("Prepare a Testnet asset, then create one SELL OCO from the filled quantity.")
        note.setStyleSheet("color:#5f6b76;")
        root.addWidget(note)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        for col in (1, 3, 5):
            grid.setColumnStretch(col, 1)

        self.symbol_edit = QLineEdit("BTCUSDT")
        self.amount_edit = QLineEdit("20")
        self.buy_button = QPushButton("TESTNET BUY")
        self.buy_button.clicked.connect(self._place_buy)
        self.buy_status = QLabel("No BUY")
        self.buy_status.setStyleSheet("font-weight:700;")
        grid.addWidget(QLabel("Symbol"), 0, 0)
        grid.addWidget(self.symbol_edit, 0, 1)
        grid.addWidget(QLabel("USDT"), 0, 2)
        grid.addWidget(self.amount_edit, 0, 3)
        grid.addWidget(self.buy_button, 0, 4)
        grid.addWidget(self.buy_status, 0, 5)

        self.executed_qty_label = QLabel("—")
        self.average_fill_label = QLabel("—")
        self.current_price_label = QLabel("—")
        grid.addWidget(QLabel("Filled qty"), 1, 0)
        grid.addWidget(self.executed_qty_label, 1, 1)
        grid.addWidget(QLabel("Avg fill"), 1, 2)
        grid.addWidget(self.average_fill_label, 1, 3)
        grid.addWidget(QLabel("Market"), 1, 4)
        grid.addWidget(self.current_price_label, 1, 5)

        self.tp_edit = QLineEdit()
        self.stop_edit = QLineEdit()
        self.stop_limit_edit = QLineEdit()
        self.tp_edit.setPlaceholderText("TP > market")
        self.stop_edit.setPlaceholderText("Stop < market")
        self.stop_limit_edit.setPlaceholderText("Stop-limit")
        self.auto_stop_check = QCheckBox("AUTO MAX STOP")
        self.auto_stop_check.setChecked(True)
        self.auto_stop_button = QPushButton("APPLY")
        self.auto_stop_button.clicked.connect(self._apply_auto_stop_loss)
        self.oco_button = QPushButton("CREATE TESTNET OCO")
        self.oco_button.setEnabled(False)
        self.oco_button.clicked.connect(self._create_oco)

        grid.addWidget(QLabel("TP"), 2, 0)
        grid.addWidget(self.tp_edit, 2, 1)
        grid.addWidget(self.auto_stop_check, 2, 2)
        grid.addWidget(self.auto_stop_button, 2, 3)
        grid.addWidget(QLabel("Stop"), 2, 4)
        grid.addWidget(self.stop_edit, 2, 5)

        grid.addWidget(QLabel("Stop-limit"), 3, 0)
        grid.addWidget(self.stop_limit_edit, 3, 1)
        grid.addWidget(self.oco_button, 3, 2, 1, 4)
        root.addLayout(grid)

        self.oco_status = QLabel("Waiting for BUY")
        self.oco_status.setStyleSheet("color:#5f6b76;")
        root.addWidget(self.oco_status)
        self.setMaximumHeight(145)

    def _provider(self) -> BinanceOCOProvider:
        if self.host.mode != "TESTNET" or not isinstance(self.host.provider, BinanceOCOProvider):
            raise RuntimeError("Switch OCObot to TESTNET mode first")
        return self.host.provider

    def _refresh_market_price(self) -> None:
        try:
            symbol = self.symbol_edit.text().strip().upper()
            if not symbol:
                return
            provider = self._provider()
            self.current_price = provider.get_last_price(symbol)
            self.current_price_label.setText(f"{self.current_price:f}")
            self.tick_size = provider.get_tick_size(symbol)
            if self.auto_stop_check.isChecked() and self.executed_qty > 0:
                self._apply_auto_stop_loss(silent=True)
        except Exception:
            pass

    def _apply_auto_stop_loss(self, silent: bool = False) -> None:
        try:
            provider = self._provider()
            symbol = self.symbol_edit.text().strip().upper()
            if not symbol.endswith("USDT") or len(symbol) <= 4:
                raise ValueError("Use a USDT Spot symbol such as BTCUSDT")
            current_price = provider.get_last_price(symbol)
            tick = provider.get_tick_size(symbol)
            stop = highest_sell_stop_candidate(current_price, tick)
            stop_limit = stop - tick
            if stop_limit <= 0:
                raise ValueError("No positive stop-limit price is available")
            self.current_price = current_price
            self.tick_size = tick
            self.current_price_label.setText(f"{current_price:f}")
            self.stop_edit.setText(f"{stop:f}")
            self.stop_limit_edit.setText(f"{stop_limit:f}")
            if not silent:
                self.oco_status.setText(f"AUTO MAX STOP: {stop:f}")
        except Exception as exc:
            self.oco_status.setText("Automatic Stop Loss failed")
            if not silent:
                QMessageBox.warning(self, "Automatic Stop Loss", str(exc))

    def _place_buy(self) -> None:
        try:
            provider = self._provider()
            symbol = self.symbol_edit.text().strip().upper()
            if not symbol.endswith("USDT") or len(symbol) <= 4:
                raise ValueError("Use a USDT Spot symbol such as BTCUSDT")
            try:
                amount = Decimal(self.amount_edit.text().strip())
            except (InvalidOperation, ValueError):
                raise ValueError("BUY amount must be a valid number")
            if amount <= 0:
                raise ValueError("BUY amount must be positive")
            response = provider.place_market_buy(symbol, amount)
            self.last_buy = response
            self.executed_qty, avg = executed_average_price(response)
            self.executed_qty_label.setText(f"{self.executed_qty:f}")
            self.average_fill_label.setText(f"{avg:f}")
            self.buy_status.setText(f"FILLED #{response.get('orderId', '—')}")
            self.oco_button.setEnabled(True)
            self._refresh_market_price()
            if self.auto_stop_check.isChecked():
                self._apply_auto_stop_loss()
            self.oco_status.setText("BUY filled — set TP; Auto Stop can refresh before OCO creation.")
        except Exception as exc:
            self.buy_status.setText("BUY failed")
            QMessageBox.warning(self, "Testnet BUY", str(exc))

    def _parse_price(self, edit: QLineEdit, label: str) -> Decimal:
        text = edit.text().strip()
        if not text:
            raise ValueError(f"Enter {label}")
        try:
            value = Decimal(text)
        except (InvalidOperation, ValueError):
            raise ValueError(f"{label} must be a valid number")
        if value <= 0:
            raise ValueError(f"{label} must be greater than zero")
        return value

    def _create_oco(self) -> None:
        try:
            provider = self._provider()
            if self.executed_qty <= 0:
                raise ValueError("Execute a successful Testnet BUY first")
            symbol = self.symbol_edit.text().strip().upper()
            current_price = provider.get_last_price(symbol)
            self.current_price_label.setText(f"{current_price:f}")
            if self.auto_stop_check.isChecked():
                self._apply_auto_stop_loss(silent=True)
            tp = self._parse_price(self.tp_edit, "Take Profit")
            stop = self._parse_price(self.stop_edit, "Stop trigger")
            stop_limit = self._parse_price(self.stop_limit_edit, "Stop-limit")
            if not (tp > current_price > stop):
                raise ValueError(f"Current market price is {current_price}. SELL OCO requires TP > current price > Stop.")
            if stop_limit > stop:
                raise ValueError("Stop-limit must be at or below Stop trigger")
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
                raise RuntimeError("Binance did not return orderListId")
            self.oco_status.setText(f"OCO CREATED #{list_id}")
            self.host._refresh_orders(preserve_selection=False)
        except Exception as exc:
            self.oco_status.setText("OCO failed")
            QMessageBox.warning(self, "Create Testnet OCO", str(exc))


class TestnetMainWindow(MainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.testnet_setup = TestnetTradeSetup(self)
        root = self.centralWidget().widget().layout()
        root.insertWidget(1, self.testnet_setup)


def run_app() -> None:
    from PySide6.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    window = TestnetMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
