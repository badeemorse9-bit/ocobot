from __future__ import annotations

import sys
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ocobot.application.services import OCOEditorService
from ocobot.domain.validation import highest_sell_stop_candidate
from ocobot.providers.paper import PaperOCOProvider
from ocobot.providers.sample_data import sample_ocos


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OCObot — Binance OCO Safe Editor V1")
        self.resize(1180, 720)
        self.provider = PaperOCOProvider(sample_ocos(), {
            "TUTUSDT": Decimal("0.045183"),
            "FIDAUSDT": Decimal("0.078210"),
        })
        self.service = OCOEditorService(self.provider)  # type: ignore[arg-type]
        self.unsubscribe = None
        self._build_ui()
        self._refresh_orders()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_live)
        self._timer.start(500)

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)

        header = QLabel("OCObot  •  PAPER MODE")
        header.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(header)

        content = QHBoxLayout()
        left = QVBoxLayout()
        right = QVBoxLayout()

        self.orders = QTableWidget(0, 6)
        self.orders.setHorizontalHeaderLabels(["#", "Symbol", "Qty", "TP", "SL", "Status"])
        self.orders.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.orders.itemSelectionChanged.connect(self._select_current)
        left_box = QGroupBox("Open OCO Orders")
        lb = QVBoxLayout(left_box)
        lb.addWidget(self.orders)
        left.addWidget(left_box)

        monitor_box = QGroupBox("Live OCO Monitor")
        mf = QFormLayout(monitor_box)
        self.monitor_symbol = QLabel("—")
        self.live_price = QLabel("—")
        self.max_stop = QLabel("—")
        self.original_status = QLabel("—")
        mf.addRow("Symbol", self.monitor_symbol)
        mf.addRow("Last Price", self.live_price)
        mf.addRow("Highest valid sell stop", self.max_stop)
        mf.addRow("Original OCO", self.original_status)
        right.addWidget(monitor_box)

        editor_box = QGroupBox("OCO Editor — local draft")
        ef = QFormLayout(editor_box)
        self.tp_edit = QLineEdit()
        self.sl_edit = QLineEdit()
        self.qty_edit = QLineEdit()
        self.qty_edit.setReadOnly(True)
        self.state_label = QLabel("No OCO selected")
        ef.addRow("TP price", self.tp_edit)
        ef.addRow("Stop price", self.sl_edit)
        ef.addRow("Quantity", self.qty_edit)
        ef.addRow("State", self.state_label)
        self.activate_btn = QPushButton("ACTIVATE")
        self.activate_btn.setMinimumHeight(46)
        self.activate_btn.clicked.connect(self._activate)
        ef.addRow(self.activate_btn)
        right.addWidget(editor_box)

        content.addLayout(left, 1)
        content.addLayout(right, 1)
        layout.addLayout(content)
        self.setCentralWidget(root)

    def _refresh_orders(self) -> None:
        orders = self.service.refresh_open_orders()
        self.orders.setRowCount(len(orders))
        for row, order in enumerate(orders):
            upper = next((l.price for l in order.legs if l.price is not None and l.stop_price is None), None)
            stop = next((l.stop_price for l in order.legs if l.stop_price is not None), None)
            qty = order.legs[0].quantity if order.legs else Decimal("0")
            values = [str(order.order_list_id), order.symbol, str(qty), str(upper or ""), str(stop or ""), order.status.value]
            for col, value in enumerate(values):
                self.orders.setItem(row, col, QTableWidgetItem(value))
        self.orders.resizeColumnsToContents()

    def _select_current(self) -> None:
        rows = self.orders.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        order_id = int(self.orders.item(row, 0).text())
        try:
            draft = self.service.select(order_id)
        except ValueError as exc:
            QMessageBox.warning(self, "Selection", str(exc))
            return
        self.tp_edit.setText(str(draft.values.get("abovePrice") or draft.values.get("leg1.price") or ""))
        self.sl_edit.setText(str(draft.values.get("belowStopPrice") or draft.values.get("leg2.stopPrice") or ""))
        self.qty_edit.setText(str(draft.values.get("quantity") or draft.values.get("leg1.quantity") or ""))
        self.monitor_symbol.setText(draft.selection.symbol)
        self.state_label.setText("DRAFTING — original remains active")
        self.original_status.setText("ACTIVE")
        if self.unsubscribe:
            self.unsubscribe()
        self.unsubscribe = self.provider.subscribe_price(draft.selection.symbol, self._on_price)
        self._refresh_live()

    def _on_price(self, price: Decimal) -> None:
        self.live_price.setText(f"{price:f}  ● LIVE")
        if self.monitor_symbol.text() and self.monitor_symbol.text() in {"TUTUSDT", "FIDAUSDT"}:
            tick = Decimal("0.000001")
            self.max_stop.setText(f"{highest_sell_stop_candidate(price, tick):f}")

    def _refresh_live(self) -> None:
        symbol = self.monitor_symbol.text()
        if symbol and symbol != "—":
            try:
                self._on_price(self.provider.get_last_price(symbol))
                current = self.provider.get_oco(self.service.selection.order_list_id) if self.service.selection else None
                self.original_status.setText(current.status.value if current else "NOT FOUND")
            except Exception:
                pass

    def _activate(self) -> None:
        for name, edit in (("abovePrice", self.tp_edit), ("belowStopPrice", self.sl_edit)):
            value = edit.text().strip()
            if not value:
                QMessageBox.warning(self, "Draft", f"Enter {name} first.")
                return
            try:
                Decimal(value)
            except InvalidOperation:
                QMessageBox.warning(self, "Draft", f"Invalid decimal in {name}.")
                return
            self.service.set_draft_field(name, value)
        result = self.service.activate()
        self.state_label.setText(f"{result.state.value} — {result.message}")
        if result.state.value == "SUCCESS":
            QMessageBox.information(self, "Activation", f"Paper replacement complete. {result.elapsed_ms:.2f} ms")
            self._refresh_orders()
        elif result.state.value == "FAILED_NEEDS_ATTENTION":
            QMessageBox.critical(self, "Activation failed", result.message)
        else:
            QMessageBox.warning(self, "Activation", result.message)


def run_app() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
