from __future__ import annotations

import sys
from decimal import Decimal, InvalidOperation
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ocobot.application.services import OCOEditorService
from ocobot.domain.validation import highest_sell_stop_candidate
from ocobot.providers.base import OCOProvider
from ocobot.providers.binance import BinanceOCOProvider
from ocobot.providers.paper import PaperOCOProvider
from ocobot.providers.sample_data import sample_ocos

APP_STYLE = """
QMainWindow, QWidget { background: #f4f6f8; color: #18212b; }
QGroupBox { background: #ffffff; border: 1px solid #d7dde4; border-radius: 10px;
    margin-top: 12px; padding: 10px; font-weight: 700; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #24313d; }
QTableWidget { background: #ffffff; border: 1px solid #d7dde4; border-radius: 7px;
    gridline-color: #e7ebef; selection-background-color: #dcecff; selection-color: #102030; }
QHeaderView::section { background: #eef2f5; color: #33404d; padding: 7px; border: 0;
    border-bottom: 1px solid #d7dde4; font-weight: 700; }
QLineEdit { background: #ffffff; border: 1px solid #c8d0d8; border-radius: 6px; padding: 7px 8px; }
QLineEdit:focus { border: 1px solid #4a86c5; }
QPushButton { background: #edf1f4; border: 1px solid #c8d0d8; border-radius: 6px;
    padding: 8px 12px; font-weight: 700; }
QPushButton:hover { background: #e4e9ee; }
QPushButton:disabled { color: #9aa4ae; background: #edf0f2; }
QPushButton#primaryButton { background: #1f6feb; color: white; border: 0; }
QPushButton#primaryButton:hover { background: #185abd; }
QPushButton#dangerButton { background: #fff2f0; color: #a33125; border: 1px solid #e4b7b1; }
QPushButton#modeActive { background: #1f6feb; color: white; border: 0; }
QPushButton#modeDisabled { background: #e6eaee; color: #7b8792; }
QPushButton#modeTestnet { background: #f0f6ff; color: #1557a6; border: 1px solid #b9d4f5; }
QCheckBox { spacing: 7px; }
"""


class PriceBridge(QObject):
    """Move provider price callbacks onto the Qt GUI thread safely."""

    price = Signal(object)

    def push(self, value: Decimal) -> None:
        self.price.emit(value)


class MainWindow(QMainWindow):
    """V1 OCO Safe Editor with Paper Demo and controlled Binance Testnet mode."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OCObot — Binance OCO Safe Editor V1")
        self.resize(1480, 940)
        self.setMinimumSize(1180, 700)
        self.setStyleSheet(APP_STYLE)

        self.mode = "PAPER"
        self.provider: OCOProvider = self._new_paper_provider()
        self.service = OCOEditorService(self.provider)  # type: ignore[arg-type]
        self.unsubscribe: Callable[[], None] | None = None
        self._refreshing_orders = False
        self._price_bridge = PriceBridge(self)
        self._price_bridge.price.connect(self._on_price)

        self._build_ui()
        self._refresh_orders(preserve_selection=False)
        self._set_demo_enabled(True)
        self._set_mode_visuals()

        self._price_timer = QTimer(self)
        self._price_timer.timeout.connect(self._refresh_current_price)
        self._price_timer.start(1500)

        self._orders_timer = QTimer(self)
        self._orders_timer.timeout.connect(self._refresh_periodic_orders)
        self._orders_timer.start(3000)

    @staticmethod
    def _new_paper_provider() -> PaperOCOProvider:
        paper_orders = [order for order in sample_ocos() if order.symbol != "TUTUSDT"]
        return PaperOCOProvider(
            paper_orders,
            {"FIDAUSDT": Decimal("0.078210")},
            {"FIDAUSDT": Decimal("0.000001")},
        )

    @staticmethod
    def _section_title(text: str, hint: str = "") -> QWidget:
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        title = QLabel(text)
        title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        row.addWidget(title)
        if hint:
            note = QLabel(hint)
            note.setStyleSheet("color:#6b7681; font-weight:400;")
            row.addWidget(note)
        row.addStretch()
        return widget

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)
        scroll.setWidget(central)
        self.setCentralWidget(scroll)

        header = QHBoxLayout()
        brand = QLabel("OCObot")
        brand.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        subtitle = QLabel("Binance OCO Safe Editor • V1")
        subtitle.setStyleSheet("color:#66727e; font-size:13px;")
        header.addWidget(brand)
        header.addWidget(subtitle)
        header.addStretch()

        self.paper_mode_btn = QPushButton("PAPER")
        self.paper_mode_btn.setMinimumWidth(105)
        self.paper_mode_btn.setToolTip("Paper Simulator / Demo mode")
        self.paper_mode_btn.clicked.connect(lambda: self._switch_mode("PAPER"))

        self.testnet_mode_btn = QPushButton("TESTNET")
        self.testnet_mode_btn.setMinimumWidth(105)
        self.testnet_mode_btn.setToolTip(
            "Controlled Binance Spot Testnet mode. Credentials are read locally "
            "from BINANCE_API_KEY and BINANCE_API_SECRET."
        )
        self.testnet_mode_btn.clicked.connect(lambda: self._switch_mode("TESTNET"))
        header.addWidget(self.paper_mode_btn)
        header.addWidget(self.testnet_mode_btn)

        self.connection = QLabel()
        self.connection.setStyleSheet("font-weight:700; margin-left:10px;")
        header.addWidget(self.connection)
        root.addLayout(header)

        safety = QFrame()
        safety.setStyleSheet(
            "QFrame { background:#fff8e8; border:1px solid #efd79a; border-radius:8px; }"
        )
        safety_row = QHBoxLayout(safety)
        safety_row.setContentsMargins(10, 7, 10, 7)
        lock = QLabel("LOCKED TARGET")
        lock.setStyleSheet("font-weight:800; color:#7c5a08;")
        safety_row.addWidget(lock)
        self.target_label = QLabel("No OCO selected")
        self.target_label.setStyleSheet("color:#5e4a16;")
        safety_row.addWidget(self.target_label, 1)
        safety_note = QLabel("Editing is local until ACTIVATE")
        safety_note.setStyleSheet("color:#5e4a16;")
        safety_row.addWidget(safety_note)
        root.addWidget(safety)

        content = QHBoxLayout()
        content.setSpacing(10)
        left = QVBoxLayout()
        right = QVBoxLayout()
        left.setSpacing(8)
        right.setSpacing(8)

        orders_box = QGroupBox("Open OCO Orders")
        orders_layout = QVBoxLayout(orders_box)
        orders_layout.addWidget(
            self._section_title(
                "Select exactly one active OCO",
                "Only the selected order may be replaced.",
            )
        )
        self.orders = QTableWidget(0, 6)
        self.orders.setHorizontalHeaderLabels(
            ["Order List ID", "Symbol", "Qty", "Take Profit", "Stop Loss", "Status"]
        )
        self.orders.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.orders.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.orders.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.orders.setAlternatingRowColors(True)
        self.orders.setSortingEnabled(False)
        self.orders.itemSelectionChanged.connect(self._select_current)
        self.orders.verticalHeader().setVisible(False)
        self.orders.setMinimumHeight(300)
        self.orders.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.orders.horizontalHeader().setStretchLastSection(True)
        orders_layout.addWidget(self.orders, 1)
        left.addWidget(orders_box, 1)

        self.demo_box = QGroupBox("Paper Simulator")
        demo_layout = QVBoxLayout(self.demo_box)
        demo_layout.addWidget(
            self._section_title(
                "Controlled Demo Actions", "These controls never call Binance."
            )
        )
        price_row = QHBoxLayout()
        price_row.addWidget(QLabel("Simulated last price"))
        self.price_input = QLineEdit("0.078210")
        self.price_input.setMinimumWidth(150)
        price_row.addWidget(self.price_input)
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
        self.reset_btn.setObjectName("dangerButton")
        self.reset_btn.clicked.connect(self._reset_demo)
        scenario_row.addWidget(self.tp_hit_btn)
        scenario_row.addWidget(self.sl_hit_btn)
        scenario_row.addWidget(self.reset_btn)
        demo_layout.addLayout(scenario_row)
        fault_row = QHBoxLayout()
        self.fail_place = QCheckBox("Fail next replacement creation")
        self.fail_place.stateChanged.connect(self._toggle_fail_place)
        self.fail_cancel = QCheckBox("Fail next cancellation")
        self.fail_cancel.stateChanged.connect(self._toggle_fail_cancel)
        fault_row.addWidget(self.fail_place)
        fault_row.addWidget(self.fail_cancel)
        fault_row.addStretch()
        demo_layout.addLayout(fault_row)
        left.addWidget(self.demo_box)

        self.monitor_box = QGroupBox("Live OCO Monitor")
        mf = QFormLayout(self.monitor_box)
        self.monitor_symbol = QLabel("—")
        self.live_price = QLabel("—")
        self.max_stop = QLabel("—")
        self.tick_size = QLabel("—")
        self.original_status = QLabel("—")
        mf.addRow("Selected symbol", self.monitor_symbol)
        mf.addRow("Current / last price", self.live_price)
        mf.addRow("Highest valid sell stop", self.max_stop)
        mf.addRow("Price tick size", self.tick_size)
        mf.addRow("Original OCO status", self.original_status)
        right.addWidget(self.monitor_box)

        editor_box = QGroupBox("OCO Editor — Local Draft")
        ef = QFormLayout(editor_box)
        self.tp_edit = QLineEdit()
        self.sl_edit = QLineEdit()
        self.qty_edit = QLineEdit()
        self.qty_edit.setReadOnly(True)
        self.qty_edit.setToolTip(
            "Quantity is copied from the selected original OCO and is not editable in V1."
        )
        self.sl_edit.textEdited.connect(self._manual_stop_edit)
        ef.addRow("Take Profit price", self.tp_edit)

        stop_row = QHBoxLayout()
        stop_row.addWidget(self.sl_edit, 1)
        self.max_stop_btn = QPushButton("MAX STOP")
        self.max_stop_btn.setMinimumWidth(135)
        self.max_stop_btn.setToolTip(
            "Arm dynamic MAX STOP. The displayed candidate is refreshed with the latest "
            "price and recalculated again immediately before CREATE."
        )
        self.max_stop_btn.clicked.connect(self._apply_max_stop)
        stop_row.addWidget(self.max_stop_btn)
        ef.addRow("Stop Loss price", stop_row)
        ef.addRow("Quantity (original)", self.qty_edit)
        self.state_label = QLabel("No OCO selected")
        self.state_label.setWordWrap(True)
        ef.addRow("Workflow state", self.state_label)
        self.activate_btn = QPushButton("ACTIVATE REPLACEMENT")
        self.activate_btn.setObjectName("primaryButton")
        self.activate_btn.setMinimumHeight(50)
        self.activate_btn.setToolTip(
            "Final action: validate → cancel selected OCO → create replacement → confirm new OCO"
        )
        self.activate_btn.clicked.connect(self._activate)
        ef.addRow(self.activate_btn)
        right.addWidget(editor_box)

        raw_box = QGroupBox("Selected OCO — Preserved Exchange Fields")
        raw_layout = QVBoxLayout(raw_box)
        self.raw_table = QTableWidget(0, 2)
        self.raw_table.setHorizontalHeaderLabels(["Field", "Value"])
        self.raw_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.raw_table.verticalHeader().setVisible(False)
        self.raw_table.horizontalHeader().setStretchLastSection(True)
        raw_layout.addWidget(self.raw_table)
        right.addWidget(raw_box, 1)

        log_box = QGroupBox("Event Log")
        log_layout = QVBoxLayout(log_box)
        self.event_log = QTableWidget(0, 2)
        self.event_log.setHorizontalHeaderLabels(["Event", "Details"])
        self.event_log.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.event_log.verticalHeader().setVisible(False)
        self.event_log.horizontalHeader().setStretchLastSection(True)
        log_layout.addWidget(self.event_log)
        right.addWidget(log_box, 1)

        content.addLayout(left, 1)
        content.addLayout(right, 1)
        root.addLayout(content, 1)
        self.statusBar().showMessage("PAPER DEMO ready — select an active OCO to begin.")

    def _set_mode_visuals(self) -> None:
        if self.mode == "PAPER":
            self.paper_mode_btn.setObjectName("modeActive")
            self.testnet_mode_btn.setObjectName("modeTestnet")
            self.connection.setText("● PAPER DEMO — no Binance calls")
            self.connection.setStyleSheet(
                "color:#286b43; font-weight:700; margin-left:10px;"
            )
            self.monitor_box.setTitle("Live OCO Monitor — Paper Simulation")
        else:
            self.paper_mode_btn.setObjectName("modeDisabled")
            self.testnet_mode_btn.setObjectName("modeActive")
            self.connection.setText("● TESTNET — Binance Spot Testnet")
            self.connection.setStyleSheet(
                "color:#1557a6; font-weight:700; margin-left:10px;"
            )
            self.monitor_box.setTitle("Live OCO Monitor — Binance Testnet")
        for button in (self.paper_mode_btn, self.testnet_mode_btn):
            button.style().unpolish(button)
            button.style().polish(button)

    def _switch_mode(self, mode: str) -> None:
        if mode == self.mode:
            return
        self._stop_price_subscription()

        if mode == "TESTNET":
            try:
                provider = BinanceOCOProvider(mode="TESTNET")
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    "TESTNET setup",
                    "TESTNET was not activated.\n\n"
                    f"{exc}\n\n"
                    "Configure BINANCE_API_KEY and BINANCE_API_SECRET locally, "
                    "then press TESTNET again.",
                )
                self.statusBar().showMessage(
                    "TESTNET not connected — local credentials required."
                )
                self._set_mode_visuals()
                return

            self.provider = provider
            self.service = OCOEditorService(self.provider)
            self.mode = "TESTNET"
            self._clear_selection_ui()
            self._set_paper_controls_enabled(False)
            self._set_mode_visuals()
            self._refresh_orders(preserve_selection=False)
            self.statusBar().showMessage(
                "TESTNET connected — live Binance OCO list loaded."
            )
            return

        old_provider = self.provider
        self.provider = self._new_paper_provider()
        self.service = OCOEditorService(self.provider)
        self.mode = "PAPER"
        self._clear_selection_ui()
        try:
            close = getattr(old_provider, "close", None)
            if close:
                close()
        except Exception:
            pass
        self._set_paper_controls_enabled(True)
        self._set_mode_visuals()
        self._refresh_orders(preserve_selection=False)
        self.statusBar().showMessage("PAPER DEMO ready — no Binance calls.")

    def _refresh_orders(self, preserve_selection: bool = True) -> None:
        selected_id: int | None = None
        if preserve_selection and self.service.selection:
            selected_id = self.service.selection.order_list_id

        try:
            orders = self.service.refresh_open_orders()
        except Exception as exc:
            if self.mode == "TESTNET":
                self.connection.setText("● TESTNET — connection/read error")
                self.connection.setStyleSheet(
                    "color:#a33125; font-weight:700; margin-left:10px;"
                )
                self.statusBar().showMessage(f"TESTNET read error: {exc}")
            return

        self._refreshing_orders = True
        try:
            self.orders.setRowCount(len(orders))
            selected_row = -1
            for row, order in enumerate(orders):
                upper = next(
                    (
                        leg.price
                        for leg in order.legs
                        if leg.price is not None and leg.stop_price is None
                    ),
                    None,
                )
                stop = next(
                    (leg.stop_price for leg in order.legs if leg.stop_price is not None),
                    None,
                )
                qty = order.legs[0].quantity if order.legs else Decimal("0")
                values = [
                    str(order.order_list_id),
                    order.symbol,
                    str(qty),
                    str(upper or ""),
                    str(stop or ""),
                    order.status.value,
                ]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if col == 0:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.orders.setItem(row, col, item)
                if selected_id is not None and order.order_list_id == selected_id:
                    selected_row = row
            if selected_row >= 0:
                self.orders.selectRow(selected_row)
        finally:
            self._refreshing_orders = False

    def _select_current(self) -> None:
        if self._refreshing_orders:
            return
        rows = self.orders.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        id_item = self.orders.item(row, 0)
        if id_item is None:
            return
        try:
            order_list_id = int(id_item.text())
        except ValueError:
            return

        try:
            draft = self.service.select(order_list_id)
        except ValueError as exc:
            QMessageBox.warning(self, "Selection", str(exc))
            return

        self.tp_edit.setText(
            str(draft.values.get("abovePrice") or draft.values.get("leg1.price") or "")
        )
        self.sl_edit.setText(
            str(
                draft.values.get("belowStopPrice")
                or draft.values.get("leg2.stopPrice")
                or ""
            )
        )
        self.qty_edit.setText(
            str(draft.values.get("quantity") or draft.values.get("leg1.quantity") or "")
        )
        self.monitor_symbol.setText(draft.selection.symbol)
        self.target_label.setText(
            f"OCO {order_list_id} • {draft.selection.symbol} • "
            "locked for local editing; original remains active"
        )
        self.state_label.setText(
            f"DRAFTING — OCO {order_list_id}; original remains active"
        )
        self.original_status.setText(
            str(draft.values.get("listOrderStatus") or "ACTIVE")
        )
        self._populate_raw(draft.values)
        self._clear_log()
        self.max_stop_btn.setText("MAX STOP")
        self._log("SELECT", f"Locked target OCO {order_list_id} ({draft.selection.symbol})")

        self._stop_price_subscription()
        self.unsubscribe = self.provider.subscribe_price(
            draft.selection.symbol, self._price_bridge.push
        )
        self._refresh_current_price()
        self._set_demo_enabled_for_selection(True)
        self.statusBar().showMessage(
            f"Selected OCO {order_list_id} — no exchange mutation until ACTIVATE."
        )

    def _stop_price_subscription(self) -> None:
        if self.unsubscribe:
            try:
                self.unsubscribe()
            except Exception:
                pass
            self.unsubscribe = None

    def _populate_raw(self, values: dict[str, object]) -> None:
        self.raw_table.setRowCount(len(values))
        for row, (key, value) in enumerate(sorted(values.items())):
            self.raw_table.setItem(row, 0, QTableWidgetItem(str(key)))
            self.raw_table.setItem(row, 1, QTableWidgetItem(str(value)))
        self.raw_table.resizeColumnsToContents()

    def _refresh_current_price(self) -> None:
        symbol = self.monitor_symbol.text()
        if not symbol or symbol == "—":
            return
        try:
            self._on_price(self.provider.get_last_price(symbol))
        except Exception:
            if self.mode == "TESTNET":
                self.statusBar().showMessage(
                    "TESTNET price read unavailable — WebSocket may still update."
                )

    def _refresh_periodic_orders(self) -> None:
        if self.mode == "TESTNET" or self.service.selection:
            self._refresh_orders()

    def _on_price(self, price: Decimal) -> None:
        self.live_price.setText(f"{price:f}  • LIVE")
        symbol = self.monitor_symbol.text()
        if not symbol or symbol == "—":
            return
        try:
            tick = self.provider.get_tick_size(symbol)
            candidate = highest_sell_stop_candidate(price, tick)
            self.tick_size.setText(f"{tick:f}")
            self.max_stop.setText(f"{candidate:f}")
        except Exception:
            self.max_stop.setText("—")

    def _move_price(self) -> None:
        if self.mode != "PAPER":
            QMessageBox.information(
                self, "Paper Simulator", "Paper Simulator is disabled in TESTNET mode."
            )
            return
        symbol = self.monitor_symbol.text()
        if not symbol or symbol == "—":
            QMessageBox.information(self, "Paper Demo", "Select an OCO first.")
            return
        try:
            price = Decimal(self.price_input.text().strip())
            if price <= 0:
                raise ValueError
        except Exception:
            QMessageBox.warning(
                self, "Paper Demo", "Enter a positive decimal price."
            )
            return
        before = self.provider.get_last_price(symbol)
        paper = self.provider
        assert isinstance(paper, PaperOCOProvider)
        paper.set_last_price(symbol, price)
        self._log("PRICE", f"{before} → {price}")

    def _apply_max_stop(self) -> None:
        if self.service.selection is None:
            QMessageBox.information(self, "MAX STOP", "Select an OCO first.")
            return
        try:
            candidate = self.service.arm_max_stop()
            self.sl_edit.setText(f"{candidate:f}")
            self.max_stop_btn.setText("MAX STOP • ARMED")
            self.state_label.setText(
                "DYNAMIC MAX STOP ARMED — recalculated immediately before CREATE"
            )
            self.max_stop.setText(f"{candidate:f}  ← armed candidate")
            symbol = self.service.selection.symbol
            price = self.provider.get_last_price(symbol)
            tick = self.provider.get_tick_size(symbol)
            self._log(
                "MAX STOP",
                f"Dynamic mode armed: candidate {candidate} from price {price} (tick {tick})",
            )
        except Exception as exc:
            QMessageBox.warning(self, "MAX STOP", str(exc))

    def _manual_stop_edit(self, _text: str) -> None:
        if self.service.max_stop_dynamic:
            self.service.max_stop_dynamic = False
            self.max_stop_btn.setText("MAX STOP")
            self.state_label.setText("DRAFTING — manual Stop Loss is now fixed")
            if self.service.selection:
                self._log("MAX STOP", "Dynamic mode disarmed by manual Stop Loss edit")

    def _force_execute(self, leg: str) -> None:
        if self.mode != "PAPER" or self.service.selection is None:
            return
        try:
            order_id = self.service.selection.order_list_id
            price = self.provider.get_last_price(self.service.selection.symbol)
            paper = self.provider
            assert isinstance(paper, PaperOCOProvider)
            paper.force_execute(order_id, leg, price)
            self._log("EXECUTE", f"Simulated {leg} fill on OCO {order_id} at {price}")
            self._refresh_orders()
            self.state_label.setText("ORIGINAL COMPLETED — activation must abort")
        except Exception as exc:
            self._log("ERROR", str(exc))
            QMessageBox.warning(self, "Paper Demo", str(exc))

    def _toggle_fail_place(self, state: int) -> None:
        if self.mode == "PAPER":
            paper = self.provider
            assert isinstance(paper, PaperOCOProvider)
            paper.fail_next_place = bool(state)
            if state:
                self._log("FAULT", "Next replacement creation will fail")

    def _toggle_fail_cancel(self, state: int) -> None:
        if self.mode == "PAPER":
            paper = self.provider
            assert isinstance(paper, PaperOCOProvider)
            paper.fail_next_cancel = bool(state)
            if state:
                self._log("FAULT", "Next cancellation will fail")

    def _reset_demo(self) -> None:
        if self.mode != "PAPER":
            return
        self._stop_price_subscription()
        self.provider = self._new_paper_provider()
        self.service = OCOEditorService(self.provider)  # type: ignore[arg-type]
        self._clear_selection_ui()
        self.fail_place.setChecked(False)
        self.fail_cancel.setChecked(False)
        self._refresh_orders(preserve_selection=False)
        self._log("RESET", "Paper state restored to initial demo fixtures")
        self.statusBar().showMessage("PAPER DEMO reset.")

    def _clear_selection_ui(self) -> None:
        self.orders.clearSelection()
        self.monitor_symbol.setText("—")
        self.live_price.setText("—")
        self.max_stop.setText("—")
        self.tick_size.setText("—")
        self.original_status.setText("—")
        self.target_label.setText("No OCO selected")
        self.tp_edit.clear()
        self.sl_edit.clear()
        self.qty_edit.clear()
        self.state_label.setText("No OCO selected")
        self.max_stop_btn.setText("MAX STOP")
        self.raw_table.setRowCount(0)
        self._clear_log()

    def _clear_log(self) -> None:
        self.event_log.setRowCount(0)

    def _log(self, event: str, details: str) -> None:
        row = self.event_log.rowCount()
        self.event_log.insertRow(row)
        self.event_log.setItem(row, 0, QTableWidgetItem(event))
        self.event_log.setItem(row, 1, QTableWidgetItem(details))
        self.event_log.scrollToBottom()

    def _activate(self) -> None:
        if self.service.selection is None:
            QMessageBox.information(self, "Activation", "Select an OCO first.")
            return

        for name, edit in (
            ("abovePrice", self.tp_edit),
            ("belowStopPrice", self.sl_edit),
        ):
            value = edit.text().strip()
            if not value:
                QMessageBox.warning(self, "Draft", f"Enter {name} first.")
                return
            try:
                Decimal(value)
            except InvalidOperation:
                QMessageBox.warning(self, "Draft", f"Invalid decimal in {name}.")
                return
            if not (name == "belowStopPrice" and self.service.max_stop_dynamic):
                self.service.set_draft_field(name, value)

        selected_id = self.service.selection.order_list_id
        self._log("ACTIVATE", f"Requested for exact OCO {selected_id}")
        self.statusBar().showMessage(f"Activating replacement for OCO {selected_id}…")
        result = self.service.activate()
        self.state_label.setText(f"{result.state.value} — {result.message}")

        if result.state.value == "SUCCESS":
            self.max_stop_btn.setText("MAX STOP")
            new_id = result.create_result.get("orderListId") if result.create_result else None
            if new_id and result.elapsed_ms is not None:
                detail = f"Replacement OCO {new_id} created in {result.elapsed_ms:.2f} ms"
            elif result.elapsed_ms is not None:
                detail = f"Replacement created in {result.elapsed_ms:.2f} ms"
            else:
                detail = "Replacement created successfully"
            self._log("SUCCESS", detail)
            self._refresh_orders(preserve_selection=False)
            self.statusBar().showMessage(detail)
            QMessageBox.information(self, "Activation", detail)
        elif result.state.value == "FAILED_NEEDS_ATTENTION":
            self._log("FAILED_NEEDS_ATTENTION", result.message)
            self.statusBar().showMessage(
                "FAILED_NEEDS_ATTENTION — manual review required."
            )
            QMessageBox.critical(self, "Activation failed", result.message)
        else:
            self._log("ABORTED", result.message)
            self.statusBar().showMessage(
                "Activation aborted; original protection was not changed."
            )
            QMessageBox.warning(self, "Activation", result.message)

    def _set_paper_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self.demo_box,
            self.price_input,
            self.move_price_btn,
            self.tp_hit_btn,
            self.sl_hit_btn,
            self.reset_btn,
            self.fail_place,
            self.fail_cancel,
        ):
            widget.setEnabled(enabled)

    def _set_demo_controls_for_selection(self, enabled: bool) -> None:
        self.max_stop_btn.setEnabled(enabled)
        self.activate_btn.setEnabled(enabled)

    def _set_demo_enabled(self, enabled: bool) -> None:
        self._set_paper_controls_enabled(enabled)
        self._set_demo_controls_for_selection(enabled)

    def _set_demo_enabled_for_selection(self, enabled: bool) -> None:
        self._set_demo_controls_for_selection(enabled)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._stop_price_subscription()
        try:
            close = getattr(self.provider, "close", None)
            if close:
                close()
        except Exception:
            pass
        event.accept()


def run_app() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
