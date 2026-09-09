from __future__ import annotations

import os
import sys
from decimal import Decimal, InvalidOperation
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
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
QGroupBox { background: #ffffff; border: 1px solid #d7dde4; border-radius: 9px;
    margin-top: 11px; padding: 8px; font-weight: 700; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #24313d; }
QTableWidget { background: #ffffff; border: 1px solid #d7dde4; border-radius: 6px;
    gridline-color: #e7ebef; selection-background-color: #dcecff; selection-color: #102030; }
QHeaderView::section { background: #eef2f5; color: #33404d; padding: 6px; border: 0;
    border-bottom: 1px solid #d7dde4; font-weight: 700; }
QLineEdit { background: #ffffff; border: 1px solid #c8d0d8; border-radius: 5px; padding: 6px 8px; }
QLineEdit:focus { border: 1px solid #4a86c5; }
QPushButton { background: #edf1f4; border: 1px solid #c8d0d8; border-radius: 5px;
    padding: 7px 10px; font-weight: 700; }
QPushButton:hover { background: #e4e9ee; }
QPushButton:disabled { color: #9aa4ae; background: #edf0f2; }
QPushButton#primaryButton { background: #1f6feb; color: white; border: 0; }
QPushButton#primaryButton:hover { background: #185abd; }
QPushButton#dangerButton { background: #fff2f0; color: #a33125; border: 1px solid #e4b7b1; }
QPushButton#modeActive { background: #1f6feb; color: white; border: 0; }
QPushButton#modeDisabled { background: #e6eaee; color: #7b8792; }
QPushButton#modeTestnet { background: #f0f6ff; color: #1557a6; border: 1px solid #b9d4f5; }
QPushButton#settingsButton { background: #ffffff; color: #33404d; }
QCheckBox { spacing: 6px; }
"""


class PriceBridge(QObject):
    """Move provider price callbacks onto the Qt GUI thread safely."""

    price = Signal(object)

    def push(self, value: Decimal) -> None:
        self.price.emit(value)


class TestnetCredentialsDialog(QDialog):
    """Session-only Testnet credential entry; no secret is written to disk."""

    def __init__(self, parent: QWidget | None = None, api_key: str = "", api_secret: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Binance Testnet API")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)
        title = QLabel("Binance Spot Testnet connection")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(title)

        note = QLabel(
            "Enter your Testnet API credentials. They are kept in memory for this session only "
            "and are never written to the repository or displayed back in the UI."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#5f6b76;")
        layout.addWidget(note)

        form = QFormLayout()
        self.api_key_edit = QLineEdit(api_key)
        self.secret_edit = QLineEdit(api_secret)
        self.secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("Testnet API Key")
        self.secret_edit.setPlaceholderText("Testnet Secret Key")
        form.addRow("API Key", self.api_key_edit)
        form.addRow("API Secret", self.secret_edit)
        layout.addLayout(form)

        warning = QLabel("TESTNET only. LIVE trading remains disabled in V1.")
        warning.setStyleSheet("color:#7c5a08; font-weight:700;")
        layout.addWidget(warning)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def api_key(self) -> str:
        return self.api_key_edit.text().strip()

    @property
    def api_secret(self) -> str:
        return self.secret_edit.text().strip()


class MainWindow(QMainWindow):
    """V1 OCO Safe Editor with Paper Demo and controlled Binance Testnet mode."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OCObot — Binance OCO Safe Editor V1")
        self.resize(1320, 720)
        self.setMinimumSize(1100, 650)
        self.setStyleSheet(APP_STYLE)

        self.mode = "PAPER"
        self.testnet_api_key = os.getenv("BINANCE_API_KEY", "")
        self.testnet_api_secret = os.getenv("BINANCE_API_SECRET", "")
        self.provider: OCOProvider = self._new_paper_provider()
        self.service = OCOEditorService(self.provider)  # type: ignore[arg-type]
        self.unsubscribe: Callable[[], None] | None = None
        self._refreshing_orders = False
        self._price_bridge = PriceBridge(self)
        self._price_bridge.price.connect(self._on_price)

        self._build_ui()
        self._refresh_orders(preserve_selection=False)
        self._set_paper_controls_enabled(True)
        self._set_mode_visuals()

        self._price_timer = QTimer(self)
        self._price_timer.timeout.connect(self._refresh_current_price)
        self._price_timer.start(1500)

        self._orders_timer = QTimer(self)
        self._orders_timer.timeout.connect(self._refresh_periodic_orders)
        self._orders_timer.start(5000)

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
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(7)
        scroll.setWidget(central)
        self.setCentralWidget(scroll)

        header = QHBoxLayout()
        header.setSpacing(6)
        brand = QLabel("OCObot")
        brand.setFont(QFont("Segoe UI", 21, QFont.Weight.Bold))
        subtitle = QLabel("Binance OCO Safe Editor • V1")
        subtitle.setStyleSheet("color:#66727e; font-size:13px;")
        header.addWidget(brand)
        header.addWidget(subtitle)
        header.addStretch()

        self.paper_mode_btn = QPushButton("PAPER")
        self.paper_mode_btn.setMinimumWidth(92)
        self.paper_mode_btn.clicked.connect(lambda: self._switch_mode("PAPER"))
        self.testnet_mode_btn = QPushButton("TESTNET")
        self.testnet_mode_btn.setMinimumWidth(92)
        self.testnet_mode_btn.clicked.connect(lambda: self._switch_mode("TESTNET"))
        self.api_button = QPushButton("API SETTINGS")
        self.api_button.setObjectName("settingsButton")
        self.api_button.clicked.connect(self._open_credentials)
        header.addWidget(self.paper_mode_btn)
        header.addWidget(self.testnet_mode_btn)
        header.addWidget(self.api_button)

        self.connection = QLabel()
        self.connection.setStyleSheet("font-weight:700; margin-left:5px;")
        header.addWidget(self.connection)
        root.addLayout(header)

        safety = QFrame()
        safety.setStyleSheet(
            "QFrame { background:#fff8e8; border:1px solid #efd79a; border-radius:7px; }"
        )
        safety_row = QHBoxLayout(safety)
        safety_row.setContentsMargins(8, 5, 8, 5)
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

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(7)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        root.addLayout(grid)

        orders_box = QGroupBox("Open OCO Orders")
        orders_layout = QVBoxLayout(orders_box)
        orders_layout.setContentsMargins(8, 8, 8, 8)
        orders_layout.setSpacing(5)
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
        self.orders.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.orders.horizontalHeader().setStretchLastSection(True)
        self.orders.setMinimumHeight(205)
        self.orders.setMaximumHeight(235)
        orders_layout.addWidget(self.orders)
        grid.addWidget(orders_box, 0, 0)

        self.demo_box = QGroupBox("Paper Simulator")
        demo_layout = QVBoxLayout(self.demo_box)
        demo_layout.setContentsMargins(8, 8, 8, 8)
        demo_layout.setSpacing(5)
        demo_layout.addWidget(
            self._section_title("Controlled Demo Actions", "These controls never call Binance.")
        )
        price_row = QHBoxLayout()
        price_row.addWidget(QLabel("Simulated last price"))
        self.price_input = QLineEdit("0.078210")
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
        self.demo_box.setMinimumHeight(125)
        self.demo_box.setMaximumHeight(145)
        grid.addWidget(self.demo_box, 1, 0)

        self.monitor_box = QGroupBox("Live OCO Monitor")
        mf = QFormLayout(self.monitor_box)
        mf.setContentsMargins(8, 8, 8, 8)
        mf.setVerticalSpacing(5)
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
        self.monitor_box.setMinimumHeight(145)
        self.monitor_box.setMaximumHeight(160)
        grid.addWidget(self.monitor_box, 0, 1)

        editor_box = QGroupBox("OCO Editor — Local Draft")
        ef = QFormLayout(editor_box)
        ef.setContentsMargins(8, 8, 8, 8)
        ef.setVerticalSpacing(6)
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
        self.max_stop_btn.setMinimumWidth(120)
        self.max_stop_btn.clicked.connect(self._apply_max_stop)
        stop_row.addWidget(self.max_stop_btn)
        ef.addRow("Stop Loss price", stop_row)
        ef.addRow("Quantity (original)", self.qty_edit)
        self.state_label = QLabel("No OCO selected")
        self.state_label.setWordWrap(True)
        ef.addRow("Workflow state", self.state_label)
        self.activate_btn = QPushButton("ACTIVATE REPLACEMENT")
        self.activate_btn.setObjectName("primaryButton")
        self.activate_btn.setMinimumHeight(42)
        self.activate_btn.clicked.connect(self._activate)
        ef.addRow(self.activate_btn)
        editor_box.setMinimumHeight(175)
        editor_box.setMaximumHeight(195)
        grid.addWidget(editor_box, 1, 1)

        raw_box = QGroupBox("Selected OCO — Preserved Exchange Fields")
        raw_layout = QVBoxLayout(raw_box)
        raw_layout.setContentsMargins(8, 8, 8, 8)
        self.raw_table = QTableWidget(0, 2)
        self.raw_table.setHorizontalHeaderLabels(["Field", "Value"])
        self.raw_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.raw_table.verticalHeader().setVisible(False)
        self.raw_table.horizontalHeader().setStretchLastSection(True)
        self.raw_table.setMinimumHeight(110)
        self.raw_table.setMaximumHeight(130)
        raw_layout.addWidget(self.raw_table)
        grid.addWidget(raw_box, 2, 1)

        log_box = QGroupBox("Event Log")
        log_layout = QVBoxLayout(log_box)
        log_layout.setContentsMargins(8, 8, 8, 8)
        self.event_log = QTableWidget(0, 2)
        self.event_log.setHorizontalHeaderLabels(["Event", "Details"])
        self.event_log.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.event_log.verticalHeader().setVisible(False)
        self.event_log.horizontalHeader().setStretchLastSection(True)
        self.event_log.setMinimumHeight(110)
        self.event_log.setMaximumHeight(130)
        log_layout.addWidget(self.event_log)
        grid.addWidget(log_box, 2, 0)

        self.statusBar().showMessage("PAPER DEMO ready — select an active OCO to begin.")

    def _set_mode_visuals(self) -> None:
        if self.mode == "PAPER":
            self.paper_mode_btn.setObjectName("modeActive")
            self.testnet_mode_btn.setObjectName("modeTestnet")
            self.connection.setText("● PAPER DEMO — no Binance calls")
            self.connection.setStyleSheet("color:#286b43; font-weight:700; margin-left:5px;")
            self.monitor_box.setTitle("Live OCO Monitor — Paper Simulation")
        else:
            self.paper_mode_btn.setObjectName("modeDisabled")
            self.testnet_mode_btn.setObjectName("modeActive")
            self.connection.setText("● TESTNET — Binance Spot Testnet")
            self.connection.setStyleSheet("color:#1557a6; font-weight:700; margin-left:5px;")
            self.monitor_box.setTitle("Live OCO Monitor — Binance Testnet")
        for button in (self.paper_mode_btn, self.testnet_mode_btn):
            button.style().unpolish(button)
            button.style().polish(button)

    def _open_credentials(self) -> None:
        dialog = TestnetCredentialsDialog(self, self.testnet_api_key, self.testnet_api_secret)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not dialog.api_key or not dialog.api_secret:
            QMessageBox.warning(self, "API settings", "Both API Key and API Secret are required.")
            return
        self.testnet_api_key = dialog.api_key
        self.testnet_api_secret = dialog.api_secret
        self.statusBar().showMessage("Testnet credentials loaded for this session only.")
        if self.mode == "TESTNET":
            self._switch_mode("PAPER")
            self._switch_mode("TESTNET")

    def _switch_mode(self, mode: str) -> None:
        if mode == self.mode:
            if mode == "TESTNET":
                self._refresh_orders(preserve_selection=False)
            return

        self._stop_price_subscription()

        if mode == "TESTNET":
            if not self.testnet_api_key or not self.testnet_api_secret:
                self._open_credentials()
                if not self.testnet_api_key or not self.testnet_api_secret:
                    return
            try:
                provider = BinanceOCOProvider(
                    mode="TESTNET",
                    api_key=self.testnet_api_key,
                    api_secret=self.testnet_api_secret,
                )
                # Force an authenticated read before switching visible mode.
                provider.list_open_ocos()
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    "TESTNET connection",
                    "TESTNET was not activated.\n\n"
                    f"{exc}\n\n"
                    "Check that these are Binance Spot Testnet credentials."
                )
                self.statusBar().showMessage("TESTNET connection failed.")
                return

            old_provider = self.provider
            self.provider = provider
            self.service = OCOEditorService(self.provider)
            self.mode = "TESTNET"
            self._clear_selection_ui()
            self._set_paper_controls_enabled(False)
            self._set_mode_visuals()
            self._refresh_orders(preserve_selection=False)
            try:
                close = getattr(old_provider, "close", None)
                if close:
                    close()
            except Exception:
                pass
            self.statusBar().showMessage("TESTNET connected — live Binance OCO list loaded.")
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
                self.connection.setStyleSheet("color:#a33125; font-weight:700; margin-left:5px;")
                self.statusBar().showMessage(f"TESTNET read error: {exc}")
            return

        self._refreshing_orders = True
        try:
            self.orders.setRowCount(len(orders))
            selected_row = -1
            for row, order in enumerate(orders):
                upper = next(
                    (leg.price for leg in order.legs if leg.price is not None and leg.stop_price is None),
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

        self.tp_edit.setText(str(draft.values.get("abovePrice") or draft.values.get("leg1.price") or ""))
        self.sl_edit.setText(
            str(draft.values.get("belowStopPrice") or draft.values.get("leg2.stopPrice") or "")
        )
        self.qty_edit.setText(str(draft.values.get("quantity") or draft.values.get("leg1.quantity") or ""))
        self.monitor_symbol.setText(draft.selection.symbol)
        self.target_label.setText(
            f"OCO {order_list_id} • {draft.selection.symbol} • locked for local editing; original remains active"
        )
        self.state_label.setText(f"DRAFTING — OCO {order_list_id}; original remains active")
        self.original_status.setText(str(draft.values.get("listOrderStatus") or "ACTIVE"))
        self._populate_raw(draft.values)
        self._clear_log()
        self.max_stop_btn.setText("MAX STOP")
        self._stop_price_subscription()
        self.unsubscribe = self.provider.subscribe_price(
            draft.selection.symbol, self._price_bridge.push
        )
        self._refresh_current_price()
        self._set_demo_controls_for_selection(True)
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
            QMessageBox.information(self, "Paper Simulator", "Paper Simulator is disabled in TESTNET mode.")
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
            QMessageBox.warning(self, "Paper Demo", "Enter a positive decimal price.")
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
        self.service = OCOEditorService(self.provider)
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
        self._set_demo_controls_for_selection(False)

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
            if not (name == "belowStopPrice" and self.service.max_stop_dynamic):
                self.service.set_draft_field(name, value)

        selected_id = self.service.selection.order_list_id
        if self.mode == "TESTNET":
            confirm = QMessageBox.question(
                self,
                "Confirm Testnet replacement",
                f"You are about to replace OCO {selected_id} on Binance Spot Testnet.\n\n"
                "The selected OCO will be cancelled and the replacement will be created.\n"
                "No other OCO is targeted.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                self.statusBar().showMessage("Testnet activation cancelled by user.")
                return

        self._log("ACTIVATE", f"Requested for exact OCO {selected_id} in {self.mode}")
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
            self.statusBar().showMessage("FAILED_NEEDS_ATTENTION — manual review required.")
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
        self.max_stop_btn.setEnabled(enabled and self.mode in {"PAPER", "TESTNET"})
        self.activate_btn.setEnabled(enabled and self.mode in {"PAPER", "TESTNET"})

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
