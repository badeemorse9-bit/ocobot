from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QCheckBox, QGridLayout, QGroupBox, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout

from ocobot.domain.validation import highest_sell_stop_candidate
from ocobot.providers.binance import BinanceOCOProvider
from ocobot.ui.main_window import MainWindow


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
        root = QVBoxLayout(self); root.setContentsMargins(8,5,8,5); root.setSpacing(4)
        grid = QGridLayout(); grid.setHorizontalSpacing(6); grid.setVerticalSpacing(4)
        for col in (1,3,5): grid.setColumnStretch(col,1)

        self.symbol_edit=QLineEdit("BTCUSDT"); self.amount_edit=QLineEdit("20"); self.buy_button=QPushButton("شراء Testnet"); self.buy_status=QLabel("لا توجد عملية شراء")
        self.buy_status.setStyleSheet("font-weight:700;")
        grid.addWidget(QLabel("العملة"),0,0); grid.addWidget(self.symbol_edit,0,1); grid.addWidget(QLabel("USDT"),0,2); grid.addWidget(self.amount_edit,0,3); grid.addWidget(self.buy_button,0,4); grid.addWidget(self.buy_status,0,5)
        self.buy_button.clicked.connect(self._place_buy)

        self.executed_qty_label=QLabel("—"); self.average_fill_label=QLabel("—"); self.current_price_label=QLabel("—")
        grid.addWidget(QLabel("الكمية المنفذة"),1,0); grid.addWidget(self.executed_qty_label,1,1); grid.addWidget(QLabel("متوسط التنفيذ"),1,2); grid.addWidget(self.average_fill_label,1,3); grid.addWidget(QLabel("السعر الآن"),1,4); grid.addWidget(self.current_price_label,1,5)

        self.tp_edit=QLineEdit(); self.stop_edit=QLineEdit(); self.stop_limit_edit=QLineEdit(); self.tp_edit.setPlaceholderText("أعلى من السعر"); self.stop_edit.setPlaceholderText("أقل من السعر"); self.stop_limit_edit.setPlaceholderText("Stop-limit")
        self.auto_stop_check=QCheckBox("ستوب تلقائي MAX"); self.auto_stop_check.setChecked(True); self.auto_stop_button=QPushButton("تطبيق"); self.auto_stop_button.clicked.connect(self._apply_auto_stop_loss); self.oco_button=QPushButton("إنشاء OCO Testnet"); self.oco_button.setEnabled(False); self.oco_button.clicked.connect(self._create_oco)
        grid.addWidget(QLabel("بيع TP"),2,0); grid.addWidget(self.tp_edit,2,1); grid.addWidget(self.auto_stop_check,2,2); grid.addWidget(self.auto_stop_button,2,3); grid.addWidget(QLabel("الاستوب"),2,4); grid.addWidget(self.stop_edit,2,5)
        grid.addWidget(QLabel("Stop-limit"),3,0); grid.addWidget(self.stop_limit_edit,3,1); grid.addWidget(self.oco_button,3,2,1,4)
        root.addLayout(grid)
        self.oco_status=QLabel("بانتظار شراء ناجح"); self.oco_status.setStyleSheet("color:#5f6b76;"); root.addWidget(self.oco_status)
        self.setMaximumHeight(125)

    def _provider(self) -> BinanceOCOProvider:
        if self.host.mode != "TESTNET" or not isinstance(self.host.provider, BinanceOCOProvider): raise RuntimeError("فعّل TESTNET أولًا")
        return self.host.provider

    def _restart_price_stream(self) -> None:
        if self._unsubscribe:
            try:self._unsubscribe()
            except Exception:pass
            self._unsubscribe=None
        try:
            provider=self._provider(); symbol=self.symbol_edit.text().strip().upper()
            if not symbol:return
            self.current_price=provider.get_last_price(symbol); self.tick_size=provider.get_tick_size(symbol); self._on_live_price(self.current_price); self._unsubscribe=provider.subscribe_price(symbol,self._bridge.push)
        except Exception: pass

    def _on_live_price(self, price: Decimal) -> None:
        self.current_price=price; self.current_price_label.setText(f"{price:f}")
        if self.auto_stop_check.isChecked() and self.executed_qty>0 and self.tick_size>0:
            stop=highest_sell_stop_candidate(price,self.tick_size); self.stop_edit.setText(f"{stop:f}"); self.stop_limit_edit.setText(f"{stop-self.tick_size:f}")

    def _apply_auto_stop_loss(self) -> None:
        try:
            provider=self._provider(); symbol=self.symbol_edit.text().strip().upper(); price=provider.get_last_price(symbol); tick=provider.get_tick_size(symbol); self.tick_size=tick; self._on_live_price(price); self.oco_status.setText(f"ستوب تلقائي: {self.stop_edit.text()}")
        except Exception as exc: QMessageBox.warning(self,"الستوب التلقائي",str(exc))

    def _place_buy(self) -> None:
        try:
            provider=self._provider(); symbol=self.symbol_edit.text().strip().upper(); amount=Decimal(self.amount_edit.text().strip())
            if amount<=0: raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
            response=provider.place_market_buy(symbol,amount); self.executed_qty,avg=executed_average_price(response); self.executed_qty_label.setText(f"{self.executed_qty:f}"); self.average_fill_label.setText(f"{avg:f}"); self.buy_status.setText(f"تم الشراء #{response.get('orderId','—')}"); self.oco_button.setEnabled(True); self._restart_price_stream(); self.oco_status.setText("تم الشراء — حدد TP أو اترك الستوب التلقائي")
        except (InvalidOperation,ValueError) as exc: QMessageBox.warning(self,"شراء Testnet",str(exc))
        except Exception as exc: self.buy_status.setText("فشل الشراء"); QMessageBox.warning(self,"شراء Testnet",str(exc))

    def _price(self, edit: QLineEdit, label: str) -> Decimal:
        text=edit.text().strip()
        if not text: raise ValueError(f"أدخل {label}")
        try:value=Decimal(text)
        except (InvalidOperation,ValueError): raise ValueError(f"{label} غير صحيح")
        if value<=0: raise ValueError(f"{label} يجب أن يكون أكبر من صفر")
        return value

    def _create_oco(self) -> None:
        try:
            provider=self._provider(); symbol=self.symbol_edit.text().strip().upper(); current=provider.get_last_price(symbol); self._on_live_price(current)
            tp=self._price(self.tp_edit,"سعر البيع"); stop=self._price(self.stop_edit,"الاستوب"); stop_limit=self._price(self.stop_limit_edit,"Stop-limit")
            if not(tp>current>stop): raise ValueError(f"السعر الحالي {current}. يجب أن يكون TP > السعر الحالي > الاستوب")
            if stop_limit>stop: raise ValueError("Stop-limit يجب أن يكون عند أو أقل من الاستوب")
            response=provider.place_oco({"symbol":symbol,"side":"SELL","quantity":str(self.executed_qty),"abovePrice":str(tp),"belowPrice":str(stop_limit),"belowStopPrice":str(stop),"aboveType":"LIMIT_MAKER","belowType":"STOP_LOSS_LIMIT","belowTimeInForce":"GTC"}); list_id=response.get("orderListId")
            if list_id is None: raise RuntimeError("لم يعط Binance رقم OCO")
            self.oco_status.setText(f"تم إنشاء OCO #{list_id}"); self.host._refresh_orders(False)
        except Exception as exc: self.oco_status.setText("فشل إنشاء OCO"); QMessageBox.warning(self,"إنشاء OCO",str(exc))

    def close(self) -> None:
        if self._unsubscribe:
            try:self._unsubscribe()
            except Exception:pass
            self._unsubscribe=None


class TestnetMainWindow(MainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.testnet_setup=TestnetTradeSetup(self)
        self.centralWidget().layout().insertWidget(1,self.testnet_setup)


def run_app()->None:
    from PySide6.QtWidgets import QApplication
    app=QApplication(sys.argv); window=TestnetMainWindow(); window.show(); sys.exit(app.exec())

if __name__=="__main__": run_app()
