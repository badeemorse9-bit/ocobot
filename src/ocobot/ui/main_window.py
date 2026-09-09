from __future__ import annotations

import sys
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from ocobot.application.services import OCOEditorService
from ocobot.domain.validation import highest_sell_stop_candidate
from ocobot.providers.paper import PaperOCOProvider
from ocobot.providers.sample_data import sample_ocos


class MainWindow(QMainWindow):
    """Interactive Paper Demo for the OCO Safe Editor workflow."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OCObot — Binance OCO Safe Editor V1")
        self.resize(1440, 900)
        self.provider = self._new_provider()
        self.service = OCOEditorService(self.provider)  # type: ignore[arg-type]
        self.unsubscribe = None
        self._build_ui()
        self._refresh_orders()
        self._set_demo_enabled(True)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_live)
        self._timer.start(250)

    @staticmethod
    def _new_provider() -> PaperOCOProvider:
        return PaperOCOProvider(
            sample_ocos(),
            {"TUTUSDT": Decimal("0.06500"), "FIDAUSDT": Decimal("0.078210")},
            {"TUTUSDT": Decimal("0.000001"), "FIDAUSDT": Decimal("0.000001")},
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout()
        central = QGroupBox()
        central.setLayout(root)

        header = QHBoxLayout()
        title = QLabel("OCObot  •  PAPER DEMO")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        self.connection = QLabel("● PAPER — no Binance calls")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.connection)
        root.addLayout(header)

        content = QHBoxLayout()
        left = QVBoxLayout()
        right = QVBoxLayout()

        self.orders = QTableWidget(0, 6)
        self.orders.setHorizontalHeaderLabels(["Order List ID", "Symbol", "Qty", "TP", "SL", "Status"])
        self.orders.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.orders.itemSelectionChanged.connect(self._select_current)
        left_box = QGroupBox("Open OCO Orders — select exactly one")
        lb = QVBoxLayout(left_box)
        lb.addWidget(self.orders)
        left.addWidget(left_box, 1)

        demo_box = QGroupBox("Paper Simulator Controls")
        demo_layout = QVBoxLayout(demo_box)
        self.price_input = QLineEdit("0.06500")
        self.price_input.setPlaceholderText("Simulated last price")
        price_row = QHBoxLayout()
        price_row.addWidget(QLabel("Move price to"))
        price_row.addWidget(self.price_input, 1)
        self.move_price_btn = QPushButton("MOVE PRICE")
        self.move_price_btn.clicked.connect(self._move_price)
        price_row.addWidget(self.move_price_btn)
        demo_layout.addLayout(price_row)

        scenario_row = QHBoxLayout()
        self.tp_hit_btn = QPushButton("SIMULATE TP HIT")
        self.tp_hit_btn.clicked.connect(lambda: self._force_execute("TP"))
        self.sl_hit_btn = QPushButton("SIMULATE SL HIT")
        self.sl_hit_btn.clicked.connect(lambda: self._force_execute("SL"))
        self.reset_btn = QPushButton("RESET DEMO")
        self.reset_btn.clicked.connect(self._reset_demo)
        scenario_row.addWidget(self.tp_hit_btn)
        scenario_row.addWidget(self.sl_hit_btn)
        scenario_row.addWidget(self.reset_btn)
        demo_layout.addLayout(scenario_row)

        fail_row = QHBoxLayout()
        self.fail_place = QCheckBox("Fail next replacement creation")
        self.fail_place.stateChanged.connect(self._toggle_fail_place)
        self.fail_cancel = QCheckBox("Fail next cancellation")
        self.fail_cancel.stateChanged.connect(self._toggle_fail_cancel)
        fail_row.addWidget(self.fail_place)
        fail_row.addWidget(self.fail_cancel)
        fail_row.addStretch()
        demo_layout.addLayout(fail_row)
        left.addWidget(demo_box)

        monitor_box = QGroupBox("Live OCO Monitor — separate from editor")
        mf = QFormLayout(monitor_box)
        self.monitor_symbol = QLabel("—")
        self.live_price = QLabel("—")
        self.max_stop = QLabel("—")
        self.tick_size = QLabel("—")
        self.original_status = QLabel("—")
        mf.addRow("Selected symbol", self.monitor_symbol)
        mf.addRow("Last price", self.live_price)
        mf.addRow("Highest valid sell stop", self.max_stop)
        mf.addRow("Tick size", self.tick_size)
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
        ef.addRow("Quantity (original)", self.qty_edit)
        ef.addRow("State", self.state_label)
        self.activate_btn = QPushButton("ACTIVATE")
        self.activate_btn.setMinimumHeight(52)
        self.activate_btn.clicked.connect(self._activate)
        ef.addRow(self.activate_btn)
        right.addWidget(editor_box)

        raw_box = QGroupBox("Selected OCO — all preserved exchange fields")
        raw_layout = QVBoxLayout(raw_box)
        self.raw_table = QTableWidget(0, 2)
        self.raw_table.setHorizontalHeaderLabels(["Field", "Value"])
        self.raw_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        raw_layout.addWidget(self.raw_table)
        right.addWidget(raw_box, 1)

        log_box = QGroupBox("Paper Event Log")
        log_layout = QVBoxLayout(log_box)
        self.event_log = QTableWidget(0, 2)
        self.event_log.setHorizontalHeaderLabels(["Event", "Details"])
        self.event_log.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        log_layout.addWidget(self.event_log)
        right.addWidget(log_box, 1)

        content.addLayout(left, 1)
        content.addLayout(right, 1)
        root.addLayout(content, 1)
        self.setCentralWidget(central)

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
        order_list_id = int(self.orders.item(row, 0).text())
        try:
            draft = self.service.select(order_list_id)
        except ValueError as exc:
            QMessageBox.warning(self, "Selection", str(exc))
            return

        self.tp_edit.setText(str(draft.values.get("abovePrice") or draft.values.get("leg1.price") or ""))
        self.sl_edit.setText(str(draft.values.get("belowStopPrice") or draft.values.get("leg2.stopPrice") or ""))
        self.qty_edit.setText(str(draft.values.get("quantity") or draft.values.get("leg1.quantity") or ""))
        self.monitor_symbol.setText(draft.selection.symbol)
        self.state_label.setText(f"DRAFTING — OCO {order_list_id}; original remains active")
        self.original_status.setText("ACTIVE")
        self._populate_raw(draft.values)
        self._clear_log()
        self._log("SELECT", f"Locked target OCO {order_list_id} ({draft.selection.symbol})")
        if self.unsubscribe:
            self.unsubscribe()
        self.unsubscribe = self.provider.subscribe_price(draft.selection.symbol, self._on_price)
        self._refresh_live()
        self._set_demo_enabled(True)

    def _populate_raw(self, values: dict[str, object]) -> None:
        self.raw_table.setRowCount(len(values))
        for row, (key, value) in enumerate(sorted(values.items())):
            self.raw_table.setItem(row, 0, QTableWidgetItem(str(key)))
            self.raw_table.setItem(row, 1, QTableWidgetItem(str(value)))
        self.raw_table.resizeColumnsToContents()

    def _on_price(self, price: Decimal) -> None:
        self.live_price.setText(f"{price:f}  ● LIVE")
        symbol = self.monitor_symbol.text()
        if symbol and symbol != "—":
            try:
                tick = self.provider.get_tick_size(symbol)
                self.tick_size.setText(f"{tick:f}")
                self.max_stop.setText(f"{highest_sell_stop_candidate(price, tick):f}")
            except Exception:
                self.max_stop.setText("—")

    def _refresh_live(self) -> None:
        symbol = self.monitor_symbol.text()
        if symbol and symbol != "—":
            try:
                self._on_price(self.provider.get_last_price(symbol))
                current = self.provider.get_oco(self.service.selection.order_list_id) if self.service.selection else None
                self.original_status.setText(current.status.value if current else "NOT FOUND")
                self._refresh_orders()
            except Exception:
                pass

    def _move_price(self) -> None:
        symbol = self.monitor_symbol.text()
        if not symbol or symbol == "—":
            QMessageBox.information(self, "Paper Demo", "Select an OCO first.")
            return
        try:
            price = Decimal(self.price_input.text().strip())
            if price <= 0:
                raise ValueError
        except Exception:
            QMessageBox.warning(self, "Paper Demo", "Enter a positive decimal price.")
            return
        before = self.provider.get_last_price(symbol)
        self.provider.set_last_price(symbol, price)
        self._log("PRICE", f"{before} → {price}")

    def _force_execute(self, leg: str) -> None:
        if not self.service.selection:
            QMessageBox.information(self, "Paper Demo", "Select an OCO first.")
            return
        try:
            order_id = self.service.selection.order_list_id
            price = self.provider.get_last_price(self.service.selection.symbol)
            self.provider.force_execute(order_id, leg, price)
            self._log("EXECUTE", f"Simulated {leg} fill on OCO {order_id} at {price}")
            self._refresh_orders()
            self.state_label.setText("ORIGINAL COMPLETED — activation must abort")
        except Exception as exc:
            self._log("ERROR", str(exc))
            QMessageBox.warning(self, "Paper Demo", str(exc))

    def _toggle_fail_place(self, state: int) -> None:
        self.provider.fail_next_place = bool(state)
        if state:
            self._log("FAULT", "Next replacement creation will fail")

    def _toggle_fail_cancel(self, state: int) -> None:
        self.provider.fail_next_cancel = bool(state)
        if state:
            self._log("FAULT", "Next cancellation will fail")

    def _reset_demo(self) -> None:
        if self.unsubscribe:
            self.unsubscribe()
            self.unsubscribe = None
        self.provider = self._new_provider()
        self.service = OCOEditorService(self.provider)  # type: ignore[arg-type]
        self.orders.clearSelection()
        self.monitor_symbol.setText("—")
        self.live_price.setText("—")
        self.max_stop.setText("—")
        self.tick_size.setText("—")
        self.original_status.setText("—")
        self.tp_edit.clear()
        self.sl_edit.clear()
        self.qty_edit.clear()
        self.state_label.setText("No OCO selected")
        self.raw_table.setRowCount(0)
        self._clear_log()
        self.fail_place.setChecked(False)
        self.fail_cancel.setChecked(False)
        self._refresh_orders()
        self._log("RESET", "Paper state restored to initial demo fixtures")

    def _clear_log(self) -> None:
        self.event_log.setRowCount(0)

    def _log(self, event: str, details: str) -> None:
        row = self.event_log.rowCount()
        self.event_log.insertRow(row)
        self.event_log.setItem(row, 0, QTableWidgetItem(event))
        self.event_log.setItem(row, 1, QTableWidgetItem(details))
        self.event_log.scrollToBottom()

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

        self._log("ACTIVATE", f"Requested for OCO {self.service.selection.order_list_id if self.service.selection else '—'}")
        result = self.service.activate()
        self.state_label.setText(f"{result.state.value} — {result.message}")
        if result.state.value == "SUCCESS":
            self._log("SUCCESS", f"Replacement created in {result.elapsed_ms:.2f} ms")
            self._refresh_orders()
            QMessageBox.information(self, "Activation", f"Paper replacement complete. {result.elapsed_ms:.2f} ms")
        elif result.state.value == "FAILED_NEEDS_ATTENTION":
            self._log("FAILED", result.message)
            QMessageBox.critical(self, "Activation failed", result.message)
        else:
            self._log("ABORTED", result.message)
            QMessageBox.warning(self, "Activation", result.message)

    def _set_demo_enabled(self, enabled: bool) -> None:
        for widget in (self.move_price_btn, self.tp_hit_btn, self.sl_hit_btn, self.fail_place, self.fail_cancel):
            widget.setEnabled(enabled)


def run_app() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
