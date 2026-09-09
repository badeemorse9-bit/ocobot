from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout

from ocobot.domain.validation import highest_sell_stop_candidate
from ocobot.providers.binance import BinanceOCOProvider
from ocobot.ui.main_window import MainWindow


def executed_average_price(response: dict[str, Any]) -> tuple[Decimal, Decimal]:
    """Return (executed quantity, weighted average fill price) from Binance's response."""
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
    """TESTNET-only account-preparation utility; separate from V1 OCO editing."""

    def __init__(self, host: MainWindow) -> None:
        super().__init__("Testnet Trade Setup — account preparation only")
        self.host = host
        self.last_buy: dict[str, Any] | None = None
        self.executed_qty = Decimal("0")
        self.average_fill = Decimal("0")
        self._build()
        self._price_timer = QTimer(self)
        self._price_timer.timeout.connect(self._refresh_market_price)
        self._price_timer.start(1500)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)
        note = QLabel(
            "TESTNET only. This utility is not part of V1 strategy logic. "
            "It creates a market BUY so the account has an asset on which we can create an OCO."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#5f6b76;")
        layout.addWidget(note)

        form = QFormLayout()
        self.symbol_edit = QLineEdit("BTCUSDT")
        self.amount_edit = QLineEdit("20")
        self.symbol_edit.setPlaceholderText("Example: BTCUSDT")
        self.amount_edit.setPlaceholderText("USDT amount")
        form.addRow("Symbol", self.symbol_edit)
        form.addRow("BUY amount (USDT)", self.amount_edit)
        layout.addLayout(form)

        buy_row = QHBoxLayout()
        self.buy_button = QPushButton("PLACE TESTNET MARKET BUY")
        self.buy_button.clicked.connect(self._place_buy)
        buy_row.addWidget(self.buy_button)
        self.buy_status = QLabel("No testnet buy executed")
        self.buy_status.setWordWrap(True)
        buy_row.addWidget(self.buy_status, 1)
        layout.addLayout(buy_row)

        fill_form = QFormLayout()
        self.executed_qty_label = QLabel("—")
        self.average_fill_label = QLabel("—")
        self.current_price_label = QLabel("—")
        fill_form.addRow("Executed quantity", self.executed_qty_label)
        fill_form.addRow("Weighted average fill", self.average_fill_label)
        fill_form.addRow("Current market price", self.current_price_label)
        layout.addLayout(fill_form)

        oco_box = QGroupBox("Create OCO from the actual filled quantity")
        oco_form = QFormLayout(oco_box)
        self.tp_edit = QLineEdit()
        self.stop_edit = QLineEdit()
        self.stop_limit_edit = QLineEdit()
        self.tp_edit.setPlaceholderText("Above current market price")
        self.stop_edit.setPlaceholderText("Below current market price")
        self.stop_limit_edit.setPlaceholderText("At or below stop trigger")
        self.auto_stop_check = QCheckBox("Use automatic MAX STOP Loss")
        self.auto_stop_check.setChecked(True)
        self.auto_stop_check.setToolTip(
            "At OCO creation, use Binance tick size and the live price to select the highest valid SELL stop below the current price."
        )
        auto_row = QHBoxLayout()
        auto_row.addWidget(self.auto_stop_check)
        self.auto_stop_button = QPushButton("APPLY NOW")
        self.auto_stop_button.clicked.connect(self._apply_auto_stop_loss)
        auto_row.addWidget(self.auto_stop_button)
        auto_row.addStretch(1)
        oco_form.addRow("Stop Loss", auto_row)
        oco_form.addRow("Take Profit price", self.tp_edit)
        oco_form.addRow("Stop trigger price", self.stop_edit)
        oco_form.addRow("Stop-limit sell price", self.stop_limit_edit)
        self.oco_button = QPushButton("CREATE TESTNET OCO")
        self.oco_button.setEnabled(False)
        self.oco_button.clicked.connect(self._create_oco)
        oco_form.addRow(self.oco_button)
        layout.addWidget(oco_box)

        self.oco_status = QLabel("OCO setup waiting for a filled BUY")
        self.oco_status.setWordWrap(True)
        layout.addWidget(self.oco_status)

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
            price = provider.get_last_price(symbol)
            self.current_price_label.setText(f"{price:f}")
        except Exception:
            pass

    def _apply_auto_stop_loss(self) -> None:
        try:
            provider = self._provider()
            symbol = self.symbol_edit.text().strip().upper()
            if not symbol.endswith("USDT") or len(symbol) <= 4:
                raise ValueError("For this setup utility, use a USDT Spot symbol such as BTCUSDT")
            current_price = provider.get_last_price(symbol)
            tick = provider.get_tick_size(symbol)
            stop = highest_sell_stop_candidate(current_price, tick)
            stop_limit = stop - tick
            if stop_limit <= 0:
                raise ValueError("No positive stop-limit price is available for this symbol")
            self.current_price_label.setText(f"{current_price:f}")
            self.stop_edit.setText(f"{stop:f}")
            self.stop_limit_edit.setText(f"{stop_limit:f}")
            self.oco_status.setText(
                f"Automatic MAX STOP applied from live price {current_price} using Binance tick size {tick}."
            )
        except Exception as exc:
            self.oco_status.setText(f"Automatic Stop Loss failed: {exc}")
            QMessageBox.warning(self, "Automatic Stop Loss", str(exc))

    def _place_buy(self) -> None:
        try:
            provider = self._provider()
            symbol = self.symbol_edit.text().strip().upper()
            if not symbol.endswith("USDT") or len(symbol) <= 4:
                raise ValueError("For this setup utility, use a USDT Spot symbol such as BTCUSDT")
            try:
                amount = Decimal(self.amount_edit.text().strip())
            except (InvalidOperation, ValueError):
                raise ValueError("BUY amount must be a valid number, for example 20")
            if amount <= 0:
                raise ValueError("BUY amount must be positive")
            response = provider.place_market_buy(symbol, amount)
            qty, avg = executed_average_price(response)
            self.last_buy = response
            self.executed_qty = qty
            self.average_fill = avg
            self.executed_qty_label.setText(f"{qty:f}")
            self.average_fill_label.setText(f"{avg:f}")
            self.buy_status.setText(f"FILLED — Binance orderId {response.get('orderId', '—')}")
            self.oco_button.setEnabled(True)
            self._refresh_market_price()
            if self.auto_stop_check.isChecked():
                self._apply_auto_stop_loss()
            self.oco_status.setText(
                "BUY filled. Automatic MAX STOP is enabled; it will be refreshed again immediately before OCO creation."
                if self.auto_stop_check.isChecked()
                else "Enter TP, Stop trigger and Stop-limit prices. Quantity will be the actual executed BUY quantity."
            )
            self.host.statusBar().showMessage("Testnet BUY filled; actual execution data captured.")
        except Exception as exc:
            self.buy_status.setText(f"BUY failed: {exc}")
            QMessageBox.warning(self, "Testnet BUY", str(exc))

    def _parse_price(self, edit: QLineEdit, label: str) -> Decimal:
        text = edit.text().strip()
        if not text:
            raise ValueError(f"Enter {label} first")
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
            if not symbol.endswith("USDT"):
                raise ValueError("Use a USDT Spot symbol for this test setup")

            current_price = provider.get_last_price(symbol)
            self.current_price_label.setText(f"{current_price:f}")
            if self.auto_stop_check.isChecked():
                self._apply_auto_stop_loss()

            tp = self._parse_price(self.tp_edit, "Take Profit price")
            stop = self._parse_price(self.stop_edit, "Stop trigger price")
            stop_limit = self._parse_price(self.stop_limit_edit, "Stop-limit sell price")

            if not (tp > current_price > stop):
                raise ValueError(
                    f"Current market price is {current_price}. For SELL OCO use Take Profit > current price > Stop trigger."
                )
            if stop_limit > stop:
                raise ValueError("For this SELL STOP_LOSS_LIMIT test, Stop-limit sell price should be at or below the Stop trigger price.")

            payload = {
                "symbol": symbol,
                "side": "SELL",
                "quantity": str(self.executed_qty),
                "abovePrice": str(tp),
                "belowPrice": str(stop_limit),
                "belowStopPrice": str(stop),
                "aboveType": "LIMIT_MAKER",
                "belowType": "STOP_LOSS_LIMIT",
                "belowTimeInForce": "GTC",
            }
            response = provider.place_oco(payload)
            list_id = response.get("orderListId")
            if list_id is None:
                raise RuntimeError("Binance did not return orderListId")
            self.oco_status.setText(f"OCO CREATED — orderListId {list_id}")
            self.host._refresh_orders(preserve_selection=False)
            self.host.statusBar().showMessage(f"Testnet OCO {list_id} created; it should now be visible in V1.")
        except Exception as exc:
            self.oco_status.setText(f"OCO failed: {exc}")
            QMessageBox.warning(self, "Create Testnet OCO", str(exc))


class TestnetMainWindow(MainWindow):
    """Same OCObot window with the isolated TESTNET preparation panel."""

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
