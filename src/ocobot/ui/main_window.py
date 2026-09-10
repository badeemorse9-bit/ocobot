from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from typing import Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
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

from ocobot.application.auto_trail import AutoTrailEngine, AutoTrailSettings
from ocobot.application.services import OCOEditorService
from ocobot.domain.validation import highest_sell_stop_candidate
from ocobot.providers.base import OCOProvider
from ocobot.providers.binance import BinanceOCOProvider
from ocobot.providers.paper import PaperOCOProvider
from ocobot.providers.sample_data import sample_ocos

APP_STYLE = """
QMainWindow, QWidget { background:#f3f5f7; color:#17212b; }
QGroupBox { background:#ffffff; border:1px solid #d2d9e0; border-radius:8px; margin-top:10px; padding:8px; font-weight:700; }
QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 6px; color:#24313d; }
QLabel { font-size:12px; }
QLineEdit { background:#ffffff; border:1px solid #bdc7d1; border-radius:5px; padding:7px 9px; min-height:18px; font-size:12px; }
QLineEdit:focus { border:1px solid #4b8bd1; }
QPushButton { background:#edf1f4; border:1px solid #c3ccd5; border-radius:5px; padding:7px 11px; min-height:18px; font-weight:700; }
QPushButton:hover { background:#e3e8ec; }
QPushButton:disabled { color:#9aa4ad; background:#edf0f2; }
QPushButton#primary { background:#1f6feb; color:#ffffff; border:0; }
QPushButton#primary:hover { background:#185abd; }
QPushButton#danger { background:#fff1ef; color:#a33a2c; border:1px solid #e3b5ad; }
QPushButton#on { background:#1f6feb; color:#ffffff; border:0; }
QPushButton#modeOff { background:#e8ecef; color:#707c87; }
QPushButton#modeTest { background:#eef5ff; color:#175da9; border:1px solid #bdd4ef; }
QTableWidget { background:#ffffff; border:1px solid #d2d9e0; gridline-color:#e6ebef; selection-background-color:#dcecff; selection-color:#17212b; font-size:12px; }
QHeaderView::section { background:#eef2f5; color:#34414e; padding:7px 6px; border:0; border-bottom:1px solid #d2d9e0; font-weight:700; }
QCheckBox { spacing:6px; font-size:12px; }
"""


class PriceBridge(QObject):
    price = Signal(object)

    def push(self, value: Decimal) -> None:
        self.price.emit(value)


class WorkerBridge(QObject):
    finished = Signal(object)


class TestnetCredentialsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, api_key: str = "", api_secret: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("إعداد Binance Testnet")
        self.setMinimumWidth(500)
        root = QVBoxLayout(self)
        root.setSpacing(8)
        note = QLabel("مفاتيح Testnet تحفظ في الذاكرة لهذه الجلسة فقط.")
        note.setWordWrap(True)
        root.addWidget(note)
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        self.api_key_edit = QLineEdit(api_key)
        self.secret_edit = QLineEdit(api_secret)
        self.secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.secret_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        k1 = QLabel("API Key")
        k2 = QLabel("API Secret")
        for label in (k1, k2):
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.addWidget(k1, 0, 0)
        form.addWidget(self.api_key_edit, 0, 1)
        form.addWidget(k2, 1, 0)
        form.addWidget(self.secret_edit, 1, 1)
        form.setColumnStretch(1, 1)
        root.addLayout(form)
        warning = QLabel("TESTNET فقط — التداول الحقيقي غير متاح في V1.")
        warning.setStyleSheet("color:#7c5a08;font-weight:700;")
        root.addWidget(warning)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @property
    def api_key(self) -> str:
        return self.api_key_edit.text().strip()

    @property
    def api_secret(self) -> str:
        return self.secret_edit.text().strip()


class MainWindow(QMainWindow):
    """Arabic vertical dashboard; selected price is fed by WebSocket."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OCObot — محرر OCO الآمن V1")
        self.resize(1180, 820)
        self.setMinimumSize(920, 680)
        self.setStyleSheet(APP_STYLE)
        self.mode = "PAPER"
        self.testnet_api_key = os.getenv("BINANCE_API_KEY", "")
        self.testnet_api_secret = os.getenv("BINANCE_API_SECRET", "")
        self.provider: OCOProvider = self._new_paper_provider()
        self.service = OCOEditorService(self.provider)
        self.unsubscribe: Callable[[], None] | None = None
        self._tick_cache: dict[str, Decimal] = {}
        self._price_bridge = PriceBridge(self)
        self._price_bridge.price.connect(self._on_price)
        self._worker_bridge = WorkerBridge(self)
        self._worker_bridge.finished.connect(self._worker_finished)
        self._workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ocobot-ui")
        self.trail: AutoTrailEngine | None = None
        self._building_table = False
        self._build_ui()
        self._refresh_orders(False)
        self._set_mode_visuals()
        self.statusBar().showMessage("وضع الورق جاهز — اختر OCO واحدًا للبدء")

    @staticmethod
    def _new_paper_provider() -> PaperOCOProvider:
        orders = [o for o in sample_ocos() if o.symbol != "TUTUSDT"]
        return PaperOCOProvider(orders, {"FIDAUSDT": Decimal("0.078210")}, {"FIDAUSDT": Decimal("0.000001")})

    @staticmethod
    def _make_label(text: str, width: int = 130) -> QLabel:
        label = QLabel(text)
        label.setFixedWidth(width)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return label

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)
        scroll.setWidget(central)
        self.setCentralWidget(scroll)
        central.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        header = QHBoxLayout()
        header.setSpacing(8)
        brand = QLabel("OCObot")
        brand.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        subtitle = QLabel("محرر OCO الآمن • V1")
        subtitle.setStyleSheet("color:#66727e;font-size:13px;")
        header.addWidget(brand)
        header.addWidget(subtitle)
        header.addStretch()
        self.paper_mode_btn = QPushButton("ورقي")
        self.testnet_mode_btn = QPushButton("TESTNET")
        self.api_button = QPushButton("إعداد API")
        for button in (self.paper_mode_btn, self.testnet_mode_btn):
            button.setMinimumWidth(88)
        self.paper_mode_btn.clicked.connect(lambda: self._switch_mode("PAPER"))
        self.testnet_mode_btn.clicked.connect(lambda: self._switch_mode("TESTNET"))
        self.api_button.clicked.connect(self._open_credentials)
        header.addWidget(self.paper_mode_btn)
        header.addWidget(self.testnet_mode_btn)
        header.addWidget(self.api_button)
        self.connection = QLabel()
        self.connection.setStyleSheet("font-weight:700;margin-right:4px;")
        header.addWidget(self.connection)
        root.addLayout(header)

        safety = QFrame()
        safety.setStyleSheet("QFrame{background:#fff8e8;border:1px solid #efd79a;border-radius:6px;}")
        sr = QHBoxLayout(safety)
        sr.setContentsMargins(9, 5, 9, 5)
        lock = QLabel("OCO المحدد")
        lock.setStyleSheet("font-weight:800;color:#7c5a08;")
        sr.addWidget(lock)
        self.target_label = QLabel("لا يوجد طلب محدد")
        self.target_label.setStyleSheet("color:#5e4a16;")
        sr.addWidget(self.target_label, 1)
        sr.addWidget(QLabel("التعديل محلي حتى التفعيل"))
        root.addWidget(safety)

        orders = QGroupBox("1 — الأوامر المفتوحة")
        ol = QVBoxLayout(orders)
        ol.setContentsMargins(8, 8, 8, 8)
        ol.setSpacing(6)
        top = QHBoxLayout()
        title = QLabel("اختر OCO واحدًا فقط — البوت سيقفل على List ID المحدد")
        title.setStyleSheet("font-weight:800;")
        top.addWidget(title)
        top.addStretch()
        self.refresh_btn = QPushButton("تحديث الأوامر")
        self.refresh_btn.clicked.connect(lambda: self._refresh_orders(True))
        top.addWidget(self.refresh_btn)
        ol.addLayout(top)
        self.orders = QTableWidget(0, 6)
        self.orders.setHorizontalHeaderLabels(["رقم OCO", "العملة", "الكمية", "البيع TP", "الاستوب SL", "الحالة"])
        self.orders.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.orders.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.orders.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.orders.setAlternatingRowColors(True)
        self.orders.verticalHeader().setVisible(False)
        self.orders.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.orders.itemSelectionChanged.connect(self._select_current)
        self.orders.setMinimumHeight(170)
        self.orders.setMaximumHeight(230)
        ol.addWidget(self.orders)
        root.addWidget(orders)

        selected = QGroupBox("2 — الطلب المحدد والمتابعة اللحظية")
        sl = QGridLayout(selected)
        sl.setContentsMargins(10, 8, 10, 8)
        sl.setHorizontalSpacing(10)
        sl.setVerticalSpacing(6)
        live_fields = [
            ("العملة", "monitor_symbol"),
            ("السعر الآن", "live_price"),
            ("أعلى Stop صالح", "max_stop"),
            ("Tick Size", "tick_size"),
            ("حالة OCO", "original_status"),
        ]
        for row, (caption, attr) in enumerate(live_fields):
            sl.addWidget(self._make_label(caption), row, 0)
            value = QLabel("—")
            value.setMinimumHeight(28)
            value.setStyleSheet("background:#f5f7f9;border:1px solid #e2e7eb;border-radius:4px;padding:4px 7px;font-weight:700;")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            setattr(self, attr, value)
            sl.addWidget(value, row, 1)
        sl.setColumnStretch(1, 1)
        root.addWidget(selected)

        trail = QGroupBox("3 — التتبع التلقائي للصعود")
        tl = QGridLayout(trail)
        tl.setContentsMargins(10, 8, 10, 8)
        tl.setHorizontalSpacing(10)
        tl.setVerticalSpacing(6)
        self.trigger_edit = QLineEdit("1.00")
        self.tp_move_edit = QLineEdit("1.00")
        self.sl_move_edit = QLineEdit("0.50")
        for edit in (self.trigger_edit, self.tp_move_edit, self.sl_move_edit):
            edit.setMaximumWidth(150)
            edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        trail_rows = [
            ("يبدأ بعد صعود %", self.trigger_edit),
            ("تحريك البيع %", self.tp_move_edit),
            ("تحريك الاستوب %", self.sl_move_edit),
        ]
        for col, (caption, edit) in enumerate(trail_rows):
            base = col * 2
            tl.addWidget(self._make_label(caption, 130), 0, base)
            tl.addWidget(edit, 0, base + 1)
        self.trail_enable = QPushButton("تشغيل التتبع")
        self.trail_enable.clicked.connect(self._toggle_trail)
        tl.addWidget(self.trail_enable, 1, 0, 1, 2)
        self.trail_state = QLabel("متوقف")
        self.trail_state.setStyleSheet("font-weight:800;")
        tl.addWidget(self.trail_state, 1, 2, 1, 4)
        self.anchor_label = QLabel("المرجع: —    التالي: —    حي: —")
        self.anchor_label.setMinimumHeight(28)
        self.anchor_label.setStyleSheet("background:#f5f7f9;border:1px solid #e2e7eb;border-radius:4px;padding:4px 7px;")
        tl.addWidget(self.anchor_label, 2, 0, 1, 6)
        root.addWidget(trail)

        editor = QGroupBox("4 — تعديل OCO يدويًا")
        el = QGridLayout(editor)
        el.setContentsMargins(10, 8, 10, 8)
        el.setHorizontalSpacing(10)
        el.setVerticalSpacing(6)
        self.tp_edit = QLineEdit()
        self.sl_edit = QLineEdit()
        self.qty_edit = QLineEdit()
        self.qty_edit.setReadOnly(True)
        for edit in (self.tp_edit, self.sl_edit, self.qty_edit):
            edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        el.addWidget(self._make_label("سعر البيع TP"), 0, 0)
        el.addWidget(self.tp_edit, 0, 1)
        el.addWidget(self._make_label("الكمية الأصلية"), 0, 2)
        el.addWidget(self.qty_edit, 0, 3)
        stop_row = QHBoxLayout()
        stop_row.setSpacing(7)
        stop_row.addWidget(self.sl_edit, 1)
        self.max_stop_btn = QPushButton("MAX STOP")
        self.max_stop_btn.clicked.connect(self._apply_max_stop)
        stop_row.addWidget(self.max_stop_btn)
        el.addWidget(self._make_label("الاستوب SL"), 1, 0)
        el.addLayout(stop_row, 1, 1)
        self.activate_btn = QPushButton("تفعيل الاستبدال")
        self.activate_btn.setObjectName("primary")
        self.activate_btn.clicked.connect(self._activate)
        el.addWidget(self.activate_btn, 1, 2, 1, 2)
        self.state_label = QLabel("لا يوجد طلب محدد")
        self.state_label.setStyleSheet("font-weight:700;")
        el.addWidget(self.state_label, 2, 0, 1, 4)
        root.addWidget(editor)

        activity = QGroupBox("5 — آخر الأحداث")
        al = QVBoxLayout(activity)
        al.setContentsMargins(8, 8, 8, 8)
        self.event_log = QTableWidget(0, 2)
        self.event_log.setHorizontalHeaderLabels(["الحدث", "التفاصيل"])
        self.event_log.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.event_log.verticalHeader().setVisible(False)
        self.event_log.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.event_log.setMinimumHeight(110)
        self.event_log.setMaximumHeight(145)
        al.addWidget(self.event_log)
        root.addWidget(activity)

        self.demo_box = QGroupBox("6 — محاكي الورق")
        dl = QGridLayout(self.demo_box)
        dl.setContentsMargins(10, 8, 10, 8)
        dl.setHorizontalSpacing(8)
        dl.setVerticalSpacing(6)
        self.price_input = QLineEdit("0.078210")
        self.price_input.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.move_price_btn = QPushButton("تحريك السعر")
        self.move_price_btn.clicked.connect(self._move_price)
        self.tp_hit_btn = QPushButton("ضرب TP")
        self.tp_hit_btn.clicked.connect(lambda: self._force_execute("TP"))
        self.sl_hit_btn = QPushButton("ضرب SL")
        self.sl_hit_btn.clicked.connect(lambda: self._force_execute("SL"))
        self.reset_btn = QPushButton("إعادة العرض")
        self.reset_btn.setObjectName("danger")
        self.reset_btn.clicked.connect(self._reset_demo)
        self.fail_place = QCheckBox("محاكاة فشل الإنشاء")
        self.fail_cancel = QCheckBox("محاكاة فشل الإلغاء")
        self.fail_place.stateChanged.connect(self._toggle_fail_place)
        self.fail_cancel.stateChanged.connect(self._toggle_fail_cancel)
        dl.addWidget(self._make_label("السعر المحاكى"), 0, 0)
        dl.addWidget(self.price_input, 0, 1)
        dl.addWidget(self.move_price_btn, 0, 2)
        dl.addWidget(self.tp_hit_btn, 0, 3)
        dl.addWidget(self.sl_hit_btn, 0, 4)
        dl.addWidget(self.reset_btn, 0, 5)
        dl.addWidget(self.fail_place, 1, 0, 1, 3)
        dl.addWidget(self.fail_cancel, 1, 3, 1, 3)
        root.addWidget(self.demo_box)

    def _set_mode_visuals(self) -> None:
        if self.mode == "PAPER":
            self.paper_mode_btn.setObjectName("on")
            self.testnet_mode_btn.setObjectName("modeTest")
            self.connection.setText("● ورقي — بدون Binance")
            self.connection.setStyleSheet("color:#286b43;font-weight:700;")
        else:
            self.paper_mode_btn.setObjectName("modeOff")
            self.testnet_mode_btn.setObjectName("on")
            self.connection.setText("● TESTNET — Binance")
            self.connection.setStyleSheet("color:#1557a6;font-weight:700;")
        for button in (self.paper_mode_btn, self.testnet_mode_btn):
            button.style().unpolish(button)
            button.style().polish(button)

    def _open_credentials(self) -> None:
        dialog = TestnetCredentialsDialog(self, self.testnet_api_key, self.testnet_api_secret)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not dialog.api_key or not dialog.api_secret:
            QMessageBox.warning(self, "API", "أدخل المفتاحين.")
            return
        self.testnet_api_key = dialog.api_key
        self.testnet_api_secret = dialog.api_secret
        if self.mode == "TESTNET":
            self._switch_mode("PAPER")
            self._switch_mode("TESTNET")
        else:
            self._switch_mode("TESTNET")

    def _switch_mode(self, mode: str) -> None:
        if mode == self.mode:
            if mode == "TESTNET":
                self._refresh_orders(False)
            return
        self._stop_price_subscription()
        self._disable_trail()
        if mode == "TESTNET":
            if not self.testnet_api_key or not self.testnet_api_secret:
                self._open_credentials()
                if not self.testnet_api_key or not self.testnet_api_secret:
                    return
            try:
                provider = BinanceOCOProvider(mode="TESTNET", api_key=self.testnet_api_key, api_secret=self.testnet_api_secret)
                provider.list_open_ocos()
            except Exception as exc:
                QMessageBox.warning(self, "TESTNET", f"تعذر الاتصال:\n{exc}")
                return
            old_provider = self.provider
            self.provider = provider
            self.service = OCOEditorService(provider)
            self.mode = "TESTNET"
            self._tick_cache.clear()
            self._clear_selection_ui()
            self._set_paper_controls_enabled(False)
            self._set_mode_visuals()
            self._refresh_orders(False)
            try:
                getattr(old_provider, "close", lambda: None)()
            except Exception:
                pass
        else:
            old_provider = self.provider
            self.provider = self._new_paper_provider()
            self.service = OCOEditorService(self.provider)
            self.mode = "PAPER"
            self._tick_cache.clear()
            self._clear_selection_ui()
            self._set_paper_controls_enabled(True)
            self._set_mode_visuals()
            self._refresh_orders(False)
            try:
                getattr(old_provider, "close", lambda: None)()
            except Exception:
                pass

    def _refresh_orders(self, preserve_selection: bool = True) -> None:
        selected_id = self.service.selection.order_list_id if preserve_selection and self.service.selection else None
        try:
            orders = self.service.refresh_open_orders()
        except Exception as exc:
            if self.mode == "TESTNET":
                self.statusBar().showMessage(f"خطأ قراءة الأوامر: {exc}")
            return
        self._building_table = True
        try:
            self.orders.setRowCount(len(orders))
            row_to_select = -1
            for row, order in enumerate(orders):
                upper = next((leg.price for leg in order.legs if leg.price is not None and leg.stop_price is None), None)
                stop = next((leg.stop_price for leg in order.legs if leg.stop_price is not None), None)
                qty = order.legs[0].quantity if order.legs else Decimal("0")
                values = [str(order.order_list_id), order.symbol, str(qty), str(upper or ""), str(stop or ""), order.status.value]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if col in {0, 2, 3, 4}:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.orders.setItem(row, col, item)
                if selected_id is not None and order.order_list_id == selected_id:
                    row_to_select = row
            if row_to_select >= 0:
                self.orders.selectRow(row_to_select)
        finally:
            self._building_table = False

    def _select_current(self) -> None:
        if self._building_table:
            return
        rows = self.orders.selectionModel().selectedRows()
        if not rows:
            return
        try:
            order_list_id = int(self.orders.item(rows[0].row(), 0).text())
        except Exception:
            return
        try:
            draft = self.service.select(order_list_id)
        except Exception as exc:
            QMessageBox.warning(self, "اختيار", str(exc))
            return
        self._stop_price_subscription()
        self._disable_trail()
        self.tp_edit.setText(str(draft.values.get("abovePrice") or draft.values.get("leg1.price") or ""))
        self.sl_edit.setText(str(draft.values.get("belowStopPrice") or draft.values.get("leg2.stopPrice") or ""))
        self.qty_edit.setText(str(draft.values.get("quantity") or draft.values.get("leg1.quantity") or ""))
        self.monitor_symbol.setText(draft.selection.symbol)
        self.original_status.setText(str(draft.values.get("listOrderStatus") or "EXECUTING"))
        self.target_label.setText(f"{draft.selection.symbol} • OCO {order_list_id} • الطلب الأصلي ما زال فعالًا")
        self.state_label.setText("مسودة محلية — الأصل لم يتغير")
        self._log("اختيار", f"تم تحديد OCO {order_list_id}")
        try:
            self._tick_cache[draft.selection.symbol] = self.provider.get_tick_size(draft.selection.symbol)
        except Exception:
            self._tick_cache.pop(draft.selection.symbol, None)
        self.unsubscribe = self.provider.subscribe_price(draft.selection.symbol, self._price_bridge.push)
        try:
            self._on_price(self.provider.get_last_price(draft.selection.symbol))
        except Exception:
            pass
        self.statusBar().showMessage(f"مراقبة لحظية: {draft.selection.symbol}")

    def _stop_price_subscription(self) -> None:
        if self.unsubscribe:
            try:
                self.unsubscribe()
            except Exception:
                pass
            self.unsubscribe = None

    def _on_price(self, price: Decimal) -> None:
        self.live_price.setText(f"{price:f}  • حي")
        symbol = self.monitor_symbol.text()
        if not symbol or symbol == "—":
            return
        tick = self._tick_cache.get(symbol)
        if tick is None:
            try:
                tick = self.provider.get_tick_size(symbol)
                self._tick_cache[symbol] = tick
            except Exception:
                tick = None
        if tick is not None:
            self.tick_size.setText(f"{tick:f}")
            self.max_stop.setText(f"{highest_sell_stop_candidate(price, tick):f}")
        if self.trail and self.trail.snapshot().enabled:
            snap = self.trail.snapshot()
            self.anchor_label.setText(
                f"المرجع: {snap.anchor_price or '—'}    التالي: {snap.next_trigger or '—'}    حي: {price}"
            )

    def _apply_max_stop(self) -> None:
        if not self.service.selection:
            QMessageBox.information(self, "MAX STOP", "اختر OCO أولًا.")
            return
        try:
            candidate = self.service.arm_max_stop()
            self.sl_edit.setText(f"{candidate:f}")
            self._log("MAX STOP", f"تم ضبط الاستوب {candidate}")
            self.state_label.setText("MAX STOP جاهز — يعاد تحديثه لحظة التفعيل")
        except Exception as exc:
            QMessageBox.warning(self, "MAX STOP", str(exc))

    def _toggle_trail(self) -> None:
        if self.trail and self.trail.snapshot().enabled:
            self._disable_trail()
            self._resubscribe_selected()
            return
        if not self.service.original or not self.service.selection:
            QMessageBox.information(self, "التتبع", "اختر OCO أولًا.")
            return
        try:
            settings = AutoTrailSettings.parse(self.trigger_edit.text(), self.tp_move_edit.text(), self.sl_move_edit.text())
            live = self.provider.get_last_price(self.service.selection.symbol)
            self._stop_price_subscription()
            self._disable_trail()
            self.trail = AutoTrailEngine(
                self.provider,
                self._trail_event,
                self._trail_finished,
                self._price_bridge.push,
            )
            self.trail.enable(self.service.original, settings, live)
            self.trail_state.setText("● يعمل — السعر اللحظي مباشر")
            self.trail_enable.setText("إيقاف التتبع")
            self._on_price(live)
        except Exception as exc:
            QMessageBox.warning(self, "التتبع", str(exc))

    def _disable_trail(self) -> None:
        if self.trail:
            try:
                self.trail.close()
            except Exception:
                pass
        self.trail = None
        self.trail_state.setText("متوقف")
        self.trail_enable.setText("تشغيل التتبع")
        self.anchor_label.setText("المرجع: —    التالي: —    حي: —")

    def _resubscribe_selected(self) -> None:
        if not self.service.selection:
            return
        self._stop_price_subscription()
        self.unsubscribe = self.provider.subscribe_price(self.service.selection.symbol, self._price_bridge.push)

    def _trail_event(self, kind: str, details: str) -> None:
        self._worker_bridge.finished.emit(("event", kind, details))

    def _trail_finished(self, ok: bool, message: str, result: dict | None) -> None:
        self._worker_bridge.finished.emit(("trail_done", ok, message, result))

    def _worker_finished(self, payload: object) -> None:
        if not isinstance(payload, tuple) or not payload:
            return
        kind = payload[0]
        if kind == "event":
            self._log(str(payload[1]), str(payload[2]))
            return
        if kind == "trail_done":
            _, ok, message, result = payload
            if ok:
                self._log("نجاح", message)
                self._refresh_orders(False)
                new_id = result.get("orderListId") if isinstance(result, dict) else None
                if new_id:
                    try:
                        draft = self.service.select(int(new_id))
                        self.tp_edit.setText(str(draft.values.get("abovePrice") or draft.values.get("leg1.price") or ""))
                        self.sl_edit.setText(str(draft.values.get("belowStopPrice") or draft.values.get("leg2.stopPrice") or ""))
                        self.qty_edit.setText(str(draft.values.get("quantity") or draft.values.get("leg1.quantity") or ""))
                        self._tick_cache[draft.selection.symbol] = self.provider.get_tick_size(draft.selection.symbol)
                        self._on_price(self.provider.get_last_price(draft.selection.symbol))
                    except Exception:
                        pass
            else:
                self.trail_state.setText("متوقف — يحتاج مراجعة")
                self._log("توقف", message)
                QMessageBox.critical(self, "التتبع توقف", message)
            return
        if kind == "activate_done":
            self._finish_activation(payload[1])

    def _activate(self) -> None:
        if not self.service.selection:
            QMessageBox.information(self, "تفعيل", "اختر OCO أولًا.")
            return
        for key, edit in (("abovePrice", self.tp_edit), ("belowStopPrice", self.sl_edit)):
            text = edit.text().strip()
            if not text:
                QMessageBox.warning(self, "مسودة", f"أدخل {key}.")
                return
            try:
                Decimal(text)
            except InvalidOperation:
                QMessageBox.warning(self, "مسودة", f"رقم غير صالح: {key}")
                return
            if not (key == "belowStopPrice" and self.service.max_stop_dynamic):
                self.service.set_draft_field(key, text)
        order_list_id = self.service.selection.order_list_id
        if self.mode == "TESTNET":
            answer = QMessageBox.question(
                self,
                "تأكيد",
                f"استبدال OCO رقم {order_list_id} على Testnet؟\nالقديم سيُلغى والجديد سيُنشأ.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._log("تفعيل", f"بدء استبدال OCO {order_list_id}")
        self.activate_btn.setEnabled(False)
        self.trail_enable.setEnabled(False)
        future = self._workers.submit(self.service.activate)
        future.add_done_callback(lambda fut: self._worker_bridge.finished.emit(("activate_done", fut.result())))

    def _finish_activation(self, result) -> None:
        self.activate_btn.setEnabled(True)
        self.trail_enable.setEnabled(True)
        self.state_label.setText(f"{result.state.value} — {result.message}")
        if result.state.value == "SUCCESS":
            self._log("نجاح", result.message)
            self._refresh_orders(False)
            QMessageBox.information(self, "تم", result.message)
        else:
            self._log(result.state.value, result.message)
            if result.state.value == "FAILED_NEEDS_ATTENTION":
                QMessageBox.critical(self, "التفعيل", result.message)
            else:
                QMessageBox.warning(self, "التفعيل", result.message)

    def _clear_selection_ui(self) -> None:
        self._stop_price_subscription()
        self._disable_trail()
        self.orders.clearSelection()
        self.monitor_symbol.setText("—")
        self.live_price.setText("—")
        self.max_stop.setText("—")
        self.tick_size.setText("—")
        self.original_status.setText("—")
        self.target_label.setText("لا يوجد طلب محدد")
        self.tp_edit.clear()
        self.sl_edit.clear()
        self.qty_edit.clear()
        self.state_label.setText("لا يوجد طلب محدد")

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

    def _move_price(self) -> None:
        if self.mode != "PAPER" or not isinstance(self.provider, PaperOCOProvider) or not self.service.selection:
            return
        try:
            price = Decimal(self.price_input.text().strip())
            if price <= 0:
                raise ValueError
        except Exception:
            QMessageBox.warning(self, "المحاكي", "أدخل سعرًا صحيحًا.")
            return
        symbol = self.service.selection.symbol
        before = self.provider.get_last_price(symbol)
        self.provider.set_last_price(symbol, price)
        self._on_price(price)
        self._log("سعر", f"{before} → {price}")

    def _force_execute(self, leg: str) -> None:
        if self.mode != "PAPER" or not isinstance(self.provider, PaperOCOProvider) or not self.service.selection:
            return
        try:
            order_list_id = self.service.selection.order_list_id
            price = self.provider.get_last_price(self.service.selection.symbol)
            self.provider.force_execute(order_list_id, leg, price)
            self._log("تنفيذ", f"محاكاة {leg} على OCO {order_list_id}")
            self._refresh_orders()
        except Exception as exc:
            QMessageBox.warning(self, "المحاكي", str(exc))

    def _toggle_fail_place(self, state: int) -> None:
        if self.mode == "PAPER" and isinstance(self.provider, PaperOCOProvider):
            self.provider.fail_next_place = bool(state)

    def _toggle_fail_cancel(self, state: int) -> None:
        if self.mode == "PAPER" and isinstance(self.provider, PaperOCOProvider):
            self.provider.fail_next_cancel = bool(state)

    def _reset_demo(self) -> None:
        if self.mode != "PAPER":
            return
        self.provider = self._new_paper_provider()
        self.service = OCOEditorService(self.provider)
        self._tick_cache.clear()
        self._clear_selection_ui()
        self._refresh_orders(False)
        self._log("إعادة", "تمت إعادة حالة المحاكي")

    def _log(self, event: str, details: str) -> None:
        row = self.event_log.rowCount()
        self.event_log.insertRow(row)
        self.event_log.setItem(row, 0, QTableWidgetItem(event))
        self.event_log.setItem(row, 1, QTableWidgetItem(details))
        self.event_log.scrollToBottom()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._stop_price_subscription()
        self._disable_trail()
        try:
            self._workers.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        try:
            getattr(self.provider, "close", lambda: None)()
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
