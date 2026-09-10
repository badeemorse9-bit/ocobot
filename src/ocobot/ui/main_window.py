from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
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
    QStackedWidget,
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
from ocobot.application.dynamic_stop import dynamic_sell_stop_limit, dynamic_sell_stop_price


APP_STYLE = """
QMainWindow, QWidget { background:#eef2f6; color:#17212b; }
QFrame#sidebar { background:#14243a; border:0; }
QLabel#brand { color:white; font-size:22px; font-weight:800; }
QLabel#sidehint { color:#9eb0c3; font-size:11px; }
QPushButton#nav { background:transparent; color:#d9e3ee; border:0; border-radius:8px; padding:10px 12px; text-align:right; font-weight:700; }
QPushButton#nav:hover { background:#1e3552; }
QPushButton#nav[selected="true"] { background:#285783; color:white; }
QGroupBox { background:white; border:1px solid #d8e0e8; border-radius:12px; margin-top:12px; padding:10px; font-weight:800; }
QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 7px; color:#26384b; }
QLabel { font-size:12px; }
QLabel#pageTitle { font-size:24px; font-weight:800; color:#172b40; }
QLabel#pageSubtitle { color:#6e7d8d; font-size:12px; }
QLabel#metric { font-size:19px; font-weight:800; }
QLabel#muted { color:#728294; }
QLineEdit { background:white; border:1px solid #c8d2dc; border-radius:7px; padding:8px 10px; min-height:18px; font-size:12px; }
QLineEdit:focus { border:1px solid #4184c5; }
QPushButton { background:#edf1f5; border:1px solid #cbd5de; border-radius:7px; padding:8px 12px; min-height:18px; font-weight:700; }
QPushButton:hover { background:#e1e8ef; }
QPushButton:disabled { color:#9aa6b2; background:#edf0f2; }
QPushButton#primary { background:#246fd1; color:white; border:0; }
QPushButton#primary:hover { background:#1d5eaf; }
QPushButton#success { background:#1f9b64; color:white; border:0; }
QPushButton#danger { background:#fff0ed; color:#a63d32; border:1px solid #e5b8b0; }
QPushButton#accent { background:#fff6e2; color:#8b6410; border:1px solid #e7cd90; }
QTableWidget { background:white; border:1px solid #d8e0e8; gridline-color:#e7edf2; selection-background-color:#dcecff; selection-color:#152638; font-size:12px; }
QHeaderView::section { background:#f2f5f8; color:#3a4a5a; padding:8px 7px; border:0; border-bottom:1px solid #d8e0e8; font-weight:800; }
QStatusBar { background:#e7edf3; color:#536577; }
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
        root.addWidget(QLabel("مفاتيح Testnet تحفظ في الذاكرة لهذه الجلسة فقط."))
        form = QGridLayout()
        self.api_key_edit = QLineEdit(api_key)
        self.secret_edit = QLineEdit(api_secret)
        self.secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.secret_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        form.addWidget(QLabel("API Key"), 0, 0)
        form.addWidget(self.api_key_edit, 0, 1)
        form.addWidget(QLabel("API Secret"), 1, 0)
        form.addWidget(self.secret_edit, 1, 1)
        form.setColumnStretch(1, 1)
        root.addLayout(form)
        warning = QLabel("TESTNET فقط — التداول الحقيقي غير متاح في V1.")
        warning.setStyleSheet("color:#8b6410;font-weight:800;")
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
    """Lightweight Arabic dashboard for the paper/Testnet OCO workflow."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OCObot — محرر OCO الآمن")
        self.resize(1240, 820)
        self.setMinimumSize(1050, 700)
        self.setStyleSheet(APP_STYLE)
        self.mode = "PAPER"
        self.testnet_api_key = os.getenv("BINANCE_API_KEY", "")
        self.testnet_api_secret = os.getenv("BINANCE_API_SECRET", "")
        self.dynamic_stop_percent = Decimal("0.50")
        self.provider: OCOProvider = self._new_paper_provider()
        self.service = OCOEditorService(self.provider)
        self.unsubscribe: Callable[[], None] | None = None
        self.trail: AutoTrailEngine | None = None
        self._tick_cache: dict[str, Decimal] = {}
        self._building_table = False
        self._editor_guard = False
        self._selected_id: int | None = None
        self._workers = ThreadPoolExecutor(max_workers=3, thread_name_prefix="ocobot-ui")
        self._price_bridge = PriceBridge(self)
        self._price_bridge.price.connect(self._on_price)
        self._worker_bridge = WorkerBridge(self)
        self._worker_bridge.finished.connect(self._worker_finished)
        self._active_nav: list[QPushButton] = []
        self._build_ui()
        self._refresh_orders(False)
        self._show_page(0)
        self.statusBar().showMessage("وضع الورق جاهز — اختر OCO واحدًا للبدء")

    @staticmethod
    def _new_paper_provider() -> PaperOCOProvider:
        orders = [o for o in sample_ocos() if o.symbol != "TUTUSDT"]
        return PaperOCOProvider(orders, {"FIDAUSDT": Decimal("0.078210")}, {"FIDAUSDT": Decimal("0.000001")})

    def _build_ui(self) -> None:
        outer = QWidget()
        outer.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        outer_layout = QHBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        self.setCentralWidget(outer)

        sidebar = QFrame(objectName="sidebar")
        sidebar.setFixedWidth(205)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 18, 14, 14)
        side.setSpacing(7)
        brand = QLabel("OCObot")
        brand.setObjectName("brand")
        side.addWidget(brand)
        hint = QLabel("منظم • آمن • خفيف")
        hint.setObjectName("sidehint")
        side.addWidget(hint)
        side.addSpacing(16)
        nav_specs = [("الرئيسية", 0), ("الأوامر", 1), ("التتبع", 2), ("Testnet", 3), ("المراقبة", 4), ("الإعدادات", 5)]
        for text, index in nav_specs:
            button = QPushButton(text)
            button.setObjectName("nav")
            button.setProperty("page_index", index)
            button.clicked.connect(lambda _checked=False, i=index: self._show_page(i))
            side.addWidget(button)
            self._active_nav.append(button)
        side.addStretch(1)
        self.mode_label = QLabel("PAPER")
        self.mode_label.setStyleSheet("color:#9fe0be;font-weight:800;padding:8px 4px;")
        side.addWidget(self.mode_label)
        outer_layout.addWidget(side)

        content = QWidget()
        content.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(18, 16, 18, 16)
        content_layout.setSpacing(8)
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)
        outer_layout.addWidget(content, 1)

        self.pages = [self._build_home_page(), self._build_orders_page(), self._build_trail_page(), self._build_testnet_page(), self._build_monitor_page(), self._build_settings_page()]
        for page in self.pages:
            self.stack.addWidget(page)

    def _page_header(self, title: str, subtitle: str) -> QVBoxLayout:
        layout = QVBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)
        sub = QLabel(subtitle)
        sub.setObjectName("pageSubtitle")
        layout.addWidget(sub)
        return layout

    def _metric_card(self, title: str, value_attr: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet("QFrame{background:white;border:1px solid #d8e0e8;border-radius:12px;}")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        label = QLabel(title)
        label.setObjectName("muted")
        value = QLabel("—")
        value.setObjectName("metric")
        setattr(self, value_attr, value)
        layout.addWidget(label)
        layout.addWidget(value)
        return card

    def _build_home_page(self) -> QWidget:
        page = QWidget()
        root = self._page_header("الرئيسية", "الحالة الحالية في شاشة واحدة بدون ازدحام")
        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        for title, attr in [("OCO مفتوحة", "home_open_count"), ("OCO المحدد", "home_selected"), ("السعر اللحظي", "home_price"), ("الحالة", "home_state")]:
            metrics.addWidget(self._metric_card(title, attr), 1)
        root.addLayout(metrics)
        selected = QGroupBox("الحالة المختارة")
        grid = QGridLayout(selected)
        fields = [("العملة", "home_symbol"), ("TP", "home_tp"), ("SL", "home_sl"), ("المرجع", "home_reference"), ("التتبع", "home_trail")]
        for row, (label, attr) in enumerate(fields):
            grid.addWidget(QLabel(label), row // 3, (row % 3) * 2)
            value = QLabel("—")
            value.setObjectName("metric") if attr in {"home_tp", "home_sl"} else value.setObjectName("muted")
            setattr(self, attr, value)
            grid.addWidget(value, row // 3, (row % 3) * 2 + 1)
        root.addWidget(selected)
        event = QGroupBox("آخر الأحداث")
        self.home_events = QLabel("لا توجد أحداث بعد")
        self.home_events.setWordWrap(True)
        event_layout = QVBoxLayout(event)
        event_layout.addWidget(self.home_events)
        root.addWidget(event)
        root.addStretch(1)
        page.setLayout(root)
        return page

    def _build_orders_page(self) -> QWidget:
        page = QWidget()
        root = self._page_header("الأوامر", "اختر OCO واحدًا؛ كل التعديل يبقى محليًا حتى التفعيل")
        top = QHBoxLayout()
        self.refresh_btn = QPushButton("تحديث الأوامر")
        self.refresh_btn.clicked.connect(lambda: self._refresh_orders(True))
        top.addWidget(self.refresh_btn)
        top.addStretch()
        self.target_label = QLabel("لا يوجد OCO محدد")
        self.target_label.setStyleSheet("font-weight:800;color:#80620e;")
        top.addWidget(self.target_label)
        root.addLayout(top)
        self.orders = QTableWidget(0, 6)
        self.orders.setHorizontalHeaderLabels(["رقم OCO", "العملة", "الكمية", "TP", "SL", "الحالة"])
        self.orders.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.orders.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.orders.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.orders.verticalHeader().setVisible(False)
        self.orders.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.orders.itemSelectionChanged.connect(self._select_current)
        self.orders.setMinimumHeight(230)
        root.addWidget(self.orders)
        editor = QGroupBox("تعديل OCO المحدد")
        grid = QGridLayout(editor)
        self.tp_edit = QLineEdit()
        self.sl_edit = QLineEdit()
        self.qty_edit = QLineEdit()
        self.qty_edit.setReadOnly(True)
        for edit in (self.tp_edit, self.sl_edit, self.qty_edit):
            edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.tp_edit.textChanged.connect(self._on_manual_tp)
        self.sl_edit.textChanged.connect(self._on_manual_sl)
        grid.addWidget(QLabel("سعر البيع TP"), 0, 0)
        grid.addWidget(self.tp_edit, 0, 1)
        grid.addWidget(QLabel("الكمية الأصلية"), 0, 2)
        grid.addWidget(self.qty_edit, 0, 3)
        grid.addWidget(QLabel("الاستوب SL"), 1, 0)
        stop_row = QHBoxLayout()
        stop_row.addWidget(self.sl_edit, 1)
        self.dynamic_stop_button = QPushButton("استوب ديناميكي")
        self.dynamic_stop_button.setObjectName("accent")
        self.dynamic_stop_button.clicked.connect(self._apply_dynamic_stop_to_selected)
        stop_row.addWidget(self.dynamic_stop_button)
        grid.addLayout(stop_row, 1, 1)
        self.activate_btn = QPushButton("تفعيل الاستبدال")
        self.activate_btn.setObjectName("primary")
        self.activate_btn.clicked.connect(self._activate)
        grid.addWidget(self.activate_btn, 1, 2, 1, 2)
        self.editor_hint = QLabel("الاستوب الديناميكي: يُحسب من السعر اللحظي وفق النسبة العامة في الإعدادات.")
        self.editor_hint.setObjectName("muted")
        self.editor_hint.setWordWrap(True)
        grid.addWidget(self.editor_hint, 2, 0, 1, 4)
        root.addWidget(editor)
        page.setLayout(root)
        return page

    def _build_trail_page(self) -> QWidget:
        page = QWidget()
        root = self._page_header("التتبع", "تتبع صعود فقط — لا يرسل استبدالًا متتابعًا عند قفزة كبيرة")
        settings = QGroupBox("إعدادات التتبع")
        grid = QGridLayout(settings)
        self.trigger_edit = QLineEdit("1.00")
        self.tp_move_edit = QLineEdit("1.00")
        self.sl_move_edit = QLineEdit("0.50")
        for edit in (self.trigger_edit, self.tp_move_edit, self.sl_move_edit):
            edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        for i, (label, edit) in enumerate([("Trigger Rise %", self.trigger_edit), ("TP Move %", self.tp_move_edit), ("SL Move %", self.sl_move_edit)]):
            grid.addWidget(QLabel(label), 0, i * 2)
            grid.addWidget(edit, 0, i * 2 + 1)
        self.trail_enable = QPushButton("تشغيل التتبع")
        self.trail_enable.setObjectName("success")
        self.trail_enable.clicked.connect(self._toggle_trail)
        grid.addWidget(self.trail_enable, 1, 0, 1, 2)
        self.trail_state = QLabel("متوقف")
        self.trail_state.setStyleSheet("font-weight:800;")
        grid.addWidget(self.trail_state, 1, 2, 1, 4)
        self.anchor_label = QLabel("المرجع: —    التالي: —    حي: —")
        self.anchor_label.setObjectName("muted")
        grid.addWidget(self.anchor_label, 2, 0, 1, 6)
        root.addWidget(settings)
        behavior = QGroupBox("سلوك الاستبدال")
        bl = QVBoxLayout(behavior)
        bl.addWidget(QLabel("السعر اللحظي → Trigger → قراءة OCO الحالية → إلغاء OCO المحدد فقط → إنشاء البديل → تأكيد orderListId الجديد."))
        bl.addWidget(QLabel("عند القفز فوق عدة Triggers: تنفيذ استبدال واحد مضبوط، ثم يصبح السعر الأحدث هو المرجع الجديد."))
        root.addWidget(behavior)
        root.addStretch(1)
        page.setLayout(root)
        return page

    def _build_testnet_page(self) -> QWidget:
        page = QWidget()
        root = self._page_header("Testnet", "تجهيز شراء Testnet وإنشاء OCO بعد الحصول على الكمية المنفذة")
        banner = QFrame()
        banner.setStyleSheet("QFrame{background:#eef5ff;border:1px solid #c6dbf2;border-radius:12px;}")
        bl = QHBoxLayout(banner)
        bl.addWidget(QLabel("TESTNET فقط"))
        bl.addStretch(1)
        self.testnet_status = QLabel("غير متصل")
        self.testnet_status.setStyleSheet("font-weight:800;color:#2269a8;")
        bl.addWidget(self.testnet_status)
        root.addWidget(banner)
        self.testnet_page_layout = root
        root.addStretch(1)
        page.setLayout(root)
        return page

    def _build_monitor_page(self) -> QWidget:
        page = QWidget()
        root = self._page_header("المراقبة", "السعر اللحظي، مصدر البيانات، وحالة الطلب المحدد")
        metrics = QHBoxLayout()
        metrics.addWidget(self._metric_card("العملة", "monitor_symbol"), 1)
        metrics.addWidget(self._metric_card("السعر الآن", "monitor_price"), 1)
        metrics.addWidget(self._metric_card("أعلى Stop صالح للعرض", "monitor_max_stop"), 1)
        metrics.addWidget(self._metric_card("Tick Size", "monitor_tick"), 1)
        root.addLayout(metrics)
        connection = QGroupBox("المصدر والحالة")
        cg = QGridLayout(connection)
        self.connection = QLabel("● PAPER")
        self.connection.setStyleSheet("font-weight:800;color:#1f8b60;")
        self.feed_state = QLabel("في انتظار سعر")
        self.feed_state.setStyleSheet("font-weight:800;")
        self.last_update = QLabel("—")
        self.selected_status = QLabel("—")
        for r, (label, widget) in enumerate([("الاتصال", self.connection), ("تغذية السعر", self.feed_state), ("آخر تحديث", self.last_update), ("حالة OCO", self.selected_status)]):
            cg.addWidget(QLabel(label), r, 0)
            cg.addWidget(widget, r, 1)
        root.addWidget(connection)
        events = QGroupBox("سجل العمليات")
        self.event_log = QLabel("—")
        self.event_log.setWordWrap(True)
        events.setMinimumHeight(220)
        events_layout = QVBoxLayout(events)
        events_layout.addWidget(self.event_log)
        root.addWidget(events)
        root.addStretch(1)
        page.setLayout(root)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        root = self._page_header("الإعدادات", "النسب العامة خارج الطلب وتُستخدم في عمليات OCO اللاحقة")
        dynamic = QGroupBox("الاستوب الديناميكي")
        grid = QGridLayout(dynamic)
        self.dynamic_stop_edit = QLineEdit("0.50")
        self.dynamic_stop_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.dynamic_stop_edit.editingFinished.connect(self._save_dynamic_stop_setting)
        grid.addWidget(QLabel("Dynamic Stop Distance %"), 0, 0)
        grid.addWidget(self.dynamic_stop_edit, 0, 1)
        example = QLabel("مثال: 0.50% يعني السعر اللحظي × 0.995، ثم ضبط الرقم على tickSize الحقيقي.")
        example.setWordWrap(True)
        example.setObjectName("muted")
        grid.addWidget(example, 1, 0, 1, 2)
        root.addWidget(dynamic)
        stage = QGroupBox("مراحل التشغيل")
        sg = QVBoxLayout(stage)
        sg.addWidget(QLabel("PAPER → TESTNET → LIVE"))
        self.live_stage = QLabel("LIVE معطل في V1")
        self.live_stage.setStyleSheet("font-weight:800;color:#a33a2c;")
        sg.addWidget(self.live_stage)
        root.addWidget(stage)
        note = QLabel("النسبة لا تُكتب داخل الطلب. هي إعداد عام يمكن تغييره قبل إنشاء OCO جديد أو تعديل OCO قديم.")
        note.setWordWrap(True)
        root.addWidget(note)
        root.addStretch(1)
        page.setLayout(root)
        return page

    def _show_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for button in self._active_nav:
            button.setProperty("selected", button.property("page_index") == index)
            button.style().unpolish(button)
            button.style().polish(button)
        if index == 1:
            self._refresh_orders(False)
        if index == 4:
            self._update_monitor_labels()

    def _set_mode_visuals(self) -> None:
        self.mode_label.setText(self.mode)
        if hasattr(self, "connection"):
            self.connection.setText(f"● {self.mode}")
            self.connection.setStyleSheet("font-weight:800;color:#1f8b60;" if self.mode != "PAPER" else "font-weight:800;color:#286da8;")
        if hasattr(self, "testnet_status"):
            self.testnet_status.setText("متصل" if self.mode == "TESTNET" else "غير متصل")

    def attach_testnet_setup(self, setup: QWidget) -> None:
        if hasattr(self, "testnet_page_layout"):
            self.testnet_page_layout.insertWidget(self.testnet_page_layout.count() - 1, setup)
        self.testnet_setup = setup
        if hasattr(setup, "start_live_stream") and self.mode == "TESTNET":
            setup.start_live_stream()

    def _open_credentials(self) -> None:
        dialog = TestnetCredentialsDialog(self, self.testnet_api_key, self.testnet_api_secret)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        if not dialog.api_key or not dialog.api_secret:
            QMessageBox.warning(self, "إعداد API", "أدخل API Key وAPI Secret.")
            return
        self.testnet_api_key = dialog.api_key
        self.testnet_api_secret = dialog.api_secret
        self._switch_mode("TESTNET")

    def _switch_mode(self, mode: str) -> None:
        if mode == "PAPER":
            self._disable_trail()
            self._stop_price_subscription()
            old = self.provider
            self.provider = self._new_paper_provider()
            self.service = OCOEditorService(self.provider)
            self.mode = "PAPER"
            self._clear_selection_ui()
            self._set_mode_visuals()
            try:
                getattr(old, "close", lambda: None)()
            except Exception:
                pass
            self._refresh_orders(False)
            self.statusBar().showMessage("وضع الورق جاهز")
            return
        if mode != "TESTNET":
            return
        if self.mode == "TESTNET":
            self._refresh_orders(False)
            return
        if not self.testnet_api_key or not self.testnet_api_secret:
            self._open_credentials()
            return
        self._disable_trail()
        self._stop_price_subscription()
        self.testnet_status.setText("جاري الاتصال…")
        self.statusBar().showMessage("جارٍ الاتصال بـ Binance Testnet…")
        self._workers.submit(self._connect_testnet, self.testnet_api_key, self.testnet_api_secret).add_done_callback(lambda f: self._worker_bridge.finished.emit(("connect", f.result())))

    @staticmethod
    def _connect_testnet(api_key: str, api_secret: str) -> tuple[bool, object]:
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

    def _refresh_orders(self, notify: bool = False) -> None:
        provider = self.provider
        self.refresh_btn.setEnabled(False) if hasattr(self, "refresh_btn") else None
        self._workers.submit(lambda: provider.list_open_ocos()).add_done_callback(lambda f: self._worker_bridge.finished.emit(("orders", provider, f)))
        if notify:
            self.statusBar().showMessage("جارٍ تحديث الأوامر…")

    def _worker_finished(self, payload: object) -> None:
        if not isinstance(payload, tuple) or not payload:
            return
        kind = payload[0]
        if kind == "connect":
            _, result = payload
            ok, data = result
            if not ok:
                self.testnet_status.setText("فشل الاتصال")
                QMessageBox.warning(self, "TESTNET", f"تعذر الاتصال:\n{data}")
                return
            provider, orders = data
            old = self.provider
            self.provider = provider
            self.service = OCOEditorService(provider)
            self.mode = "TESTNET"
            self._tick_cache.clear()
            self._clear_selection_ui()
            self._set_mode_visuals()
            self._render_orders(orders)
            try:
                getattr(old, "close", lambda: None)()
            except Exception:
                pass
            if hasattr(self, "testnet_setup") and hasattr(self.testnet_setup, "start_live_stream"):
                self.testnet_setup.start_live_stream()
            self.statusBar().showMessage("Testnet متصل — الأوامر الحية جاهزة")
            return
        if kind == "orders":
            _, provider, future = payload
            try:
                orders = future.result()
            except Exception as exc:
                if provider is self.provider:
                    if hasattr(self, "refresh_btn"):
                        self.refresh_btn.setEnabled(True)
                    self.statusBar().showMessage(f"فشل تحديث الأوامر: {exc}")
                return
            if provider is self.provider:
                self._render_orders(orders, preserve_selection=True)
                if hasattr(self, "refresh_btn"):
                    self.refresh_btn.setEnabled(True)
                self._update_home_metrics(len(orders))
                self.statusBar().showMessage(f"تم تحديث {len(orders)} OCO")
            return
        if kind == "select":
            _, provider, order_id, future = payload
            if provider is not self.provider or order_id != self._selected_id:
                return
            try:
                draft = future.result()
            except Exception as exc:
                self.statusBar().showMessage(f"تعذر اختيار OCO: {exc}")
                return
            self._load_draft_ui(draft)
            self._start_price_monitor(draft.selection.symbol)
            self.statusBar().showMessage(f"تم تحديد OCO #{order_id}")
            return
        if kind == "price_setup":
            _, provider, symbol, future = payload
            if provider is not self.provider:
                return
            try:
                price, tick = future.result()
            except Exception as exc:
                self.feed_state.setText(f"فشل قراءة السعر: {exc}")
                return
            self._tick_cache[symbol] = tick
            self._on_price(price)
            self.feed_state.setText("Live")
            try:
                self.unsubscribe = provider.subscribe_price(symbol, self._price_bridge.push)
            except Exception as exc:
                self.feed_state.setText(f"تعذر فتح البث: {exc}")
            return

    def _render_orders(self, orders: list, preserve_selection: bool = False) -> None:
        old_selected = self._selected_id if preserve_selection else None
        self._building_table = True
        try:
            self.orders.setRowCount(len(orders))
            target_row = -1
            for row, order in enumerate(orders):
                upper = next((leg.price for leg in order.legs if leg.price is not None and leg.stop_price is None), None)
                stop = next((leg.stop_price for leg in order.legs if leg.stop_price is not None), None)
                qty = order.legs[0].quantity if order.legs else Decimal("0")
                values = [str(order.order_list_id), order.symbol, str(qty), str(upper or ""), str(stop or ""), order.status.value]
                for col, value in enumerate(values):
                    self.orders.setItem(row, col, QTableWidgetItem(value))
                if old_selected is not None and order.order_list_id == old_selected:
                    target_row = row
        finally:
            self._building_table = False
        if target_row >= 0:
            self.orders.selectRow(target_row)

    def _select_current(self) -> None:
        if self._building_table:
            return
        rows = self.orders.selectionModel().selectedRows()
        if not rows:
            return
        try:
            order_id = int(self.orders.item(rows[0].row(), 0).text())
        except (AttributeError, ValueError):
            return
        self._disable_trail()
        self._stop_price_subscription()
        self._selected_id = order_id
        provider = self.provider
        self.statusBar().showMessage(f"جارٍ قراءة OCO #{order_id}…")
        self._workers.submit(lambda: self.service.select(order_id)).add_done_callback(lambda f: self._worker_bridge.finished.emit(("select", provider, order_id, f)))

    def _load_draft_ui(self, draft: Any) -> None:
        self._editor_guard = True
        try:
            values = draft.values
            self.tp_edit.setText(str(values.get("abovePrice") or ""))
            self.sl_edit.setText(str(values.get("belowStopPrice") or ""))
            qty = values.get("quantity") or values.get("leg1.quantity") or values.get("leg2.quantity") or ""
            self.qty_edit.setText(str(qty))
        finally:
            self._editor_guard = False
        self.target_label.setText(f"OCO #{draft.selection.order_list_id} • {draft.selection.symbol}")
        self.home_symbol.setText(draft.selection.symbol)
        self.home_reference.setText(str(draft.selection.order_list_id))
        self.home_state.setText("DRAFTING")
        self.home_selected.setText(str(draft.selection.order_list_id))
        self.selected_status.setText("ACTIVE")
        self.home_trail.setText("متوقف")
        self.dynamic_stop_button.setEnabled(True)
        self.activate_btn.setEnabled(True)
        self._update_home_from_draft(draft)

    def _update_home_from_draft(self, draft: Any) -> None:
        values = draft.values
        self.home_tp.setText(str(values.get("abovePrice") or "—"))
        self.home_sl.setText(str(values.get("belowStopPrice") or "—"))
        self._update_home_metrics(self.orders.rowCount())

    def _on_manual_tp(self, text: str) -> None:
        if self._editor_guard or self.service.draft is None:
            return
        self.service.set_draft_field("abovePrice", text.strip())

    def _on_manual_sl(self, text: str) -> None:
        if self._editor_guard or self.service.draft is None or not text.strip():
            return
        self.service.set_draft_field("belowStopPrice", text.strip())
        try:
            stop = Decimal(text.strip())
            tick = self._tick_cache.get(self.service.selection.symbol if self.service.selection else "")
            if tick:
                self.service.set_draft_field("belowPrice", str(dynamic_sell_stop_limit(stop, tick)))
        except (InvalidOperation, ValueError):
            pass

    def _apply_dynamic_stop_to_selected(self) -> None:
        if not self.service.selection or not self.service.draft:
            QMessageBox.information(self, "الاستوب الديناميكي", "اختر OCO أولًا.")
            return
        symbol = self.service.selection.symbol
        provider = self.provider
        self.statusBar().showMessage("جارٍ حساب الاستوب من السعر اللحظي…")
        self._workers.submit(lambda: (provider.get_last_price(symbol), provider.get_tick_size(symbol))).add_done_callback(lambda f: self._worker_bridge.finished.emit(("dynamic_stop", provider, symbol, f)))

    def _apply_dynamic_stop_result(self, provider: OCOProvider, symbol: str, future: Any) -> None:
        if provider is not self.provider or not self.service.draft or not self.service.selection or self.service.selection.symbol != symbol:
            return
        try:
            price, tick = future.result()
            stop = dynamic_sell_stop_price(price, self.dynamic_stop_percent, tick)
            lower = dynamic_sell_stop_limit(stop, tick)
            self._tick_cache[symbol] = tick
            self._editor_guard = True
            try:
                self.sl_edit.setText(f"{stop:f}")
            finally:
                self._editor_guard = False
            self.service.set_draft_field("belowStopPrice", str(stop))
            self.service.set_draft_field("belowPrice", str(lower))
            self._on_price(price)
            self.statusBar().showMessage(f"تم تطبيق الاستوب الديناميكي {self.dynamic_stop_percent}% من السعر اللحظي")
        except Exception as exc:
            QMessageBox.warning(self, "الاستوب الديناميكي", str(exc))

    def _calculate_dynamic_stop_preview(self, price: Decimal, symbol: str) -> Decimal | None:
        tick = self._tick_cache.get(symbol)
        if tick is None:
            return None
        try:
            return dynamic_sell_stop_price(price, self.dynamic_stop_percent, tick)
        except Exception:
            return None

    def _start_price_monitor(self, symbol: str) -> None:
        self._stop_price_subscription()
        provider = self.provider
        self.monitor_symbol.setText(symbol)
        self.monitor_price.setText("—")
        self.feed_state.setText("جاري بدء البث…")
        self._workers.submit(lambda: (provider.get_last_price(symbol), provider.get_tick_size(symbol))).add_done_callback(lambda f: self._worker_bridge.finished.emit(("price_setup", provider, symbol, f)))

    def _stop_price_subscription(self) -> None:
        if self.unsubscribe:
            try:
                self.unsubscribe()
            except Exception:
                pass
            self.unsubscribe = None
        self.feed_state.setText("متوقف") if hasattr(self, "feed_state") else None

    def _on_price(self, price: Decimal) -> None:
        if price <= 0:
            return
        self.monitor_price.setText(f"{price:f}")
        self.home_price.setText(f"{price:f}")
        self.last_update.setText(time.strftime("%H:%M:%S"))
        symbol = self.service.selection.symbol if self.service.selection else self.monitor_symbol.text().strip()
        tick = self._tick_cache.get(symbol)
        if tick:
            max_stop = highest_sell_stop_candidate(price, tick)
            self.monitor_max_stop.setText(f"{max_stop:f}")
            self.monitor_tick.setText(f"{tick:f}")
            self.monitor_symbol.setText(symbol or "—")
            dynamic = self._calculate_dynamic_stop_preview(price, symbol) if symbol else None
            if dynamic is not None:
                self.editor_hint.setText(f"الديناميكي الآن ({self.dynamic_stop_percent}%): {dynamic:f}")
        self.feed_state.setText("Live")
        self._update_home_metrics(self.orders.rowCount())

    def _update_monitor_labels(self) -> None:
        if self.service.selection:
            self.monitor_symbol.setText(self.service.selection.symbol)
        self._update_home_metrics(self.orders.rowCount())

    def _update_home_metrics(self, count: int) -> None:
        self.home_open_count.setText(str(count))
        self.home_selected.setText(str(self._selected_id) if self._selected_id else "—")
        self.home_state.setText(self.service.state.value if self.service else "IDLE")
        self.home_trail.setText("نشط" if self.trail and self.trail.snapshot().enabled else "متوقف")

    def _toggle_trail(self) -> None:
        if self.trail and self.trail.snapshot().enabled:
            self._disable_trail()
            return
        if not self.service.original:
            QMessageBox.information(self, "التتبع", "اختر OCO أولًا.")
            return
        try:
            settings = AutoTrailSettings.parse(self.trigger_edit.text(), self.tp_move_edit.text(), self.sl_move_edit.text())
            live = self.provider.get_last_price(self.service.original.symbol)
            self.trail = AutoTrailEngine(self.provider, event=self._trail_event, finished=self._trail_finished, price=self._on_price)
            snap = self.trail.enable(self.service.original, settings, live)
            self.trail_state.setText("ACTIVE")
            self.trail_enable.setText("إيقاف التتبع")
            self.anchor_label.setText(f"المرجع: {snap.anchor_price}    التالي: {snap.next_trigger}    حي: {snap.latest_price}")
            self.home_trail.setText("نشط")
            self._show_page(2)
        except Exception as exc:
            QMessageBox.warning(self, "التتبع", str(exc))

    def _disable_trail(self) -> None:
        if self.trail:
            try:
                self.trail.disable()
            except Exception:
                pass
        self.trail = None
        if hasattr(self, "trail_state"):
            self.trail_state.setText("متوقف")
        if hasattr(self, "trail_enable"):
            self.trail_enable.setText("تشغيل التتبع")

    def _trail_event(self, kind: str, details: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        line = f"{stamp} • {kind} • {details}"
        self.event_log.setText(line + "\n" + self.event_log.text())
        self.home_events.setText(line + "\n" + self.home_events.text())

    def _trail_finished(self, ok: bool, message: str, result: dict[str, Any] | None) -> None:
        if ok:
            self._trail_event("TRAIL_SUCCESS", message)
            self._refresh_orders(False)
            new_id = result.get("orderListId") if result else None
            if new_id:
                self._selected_id = int(new_id)
            self.trail_state.setText("ACTIVE — تم استبدال OCO")
        else:
            self._trail_event("TRAIL_STOPPED", message)
            self.trail_state.setText("متوقف — FAILED_NEEDS_ATTENTION")
            self.trail_enable.setText("تشغيل التتبع")
            self._show_page(4)

    def _activate(self) -> None:
        if not self.service.draft:
            QMessageBox.information(self, "تفعيل", "اختر OCO أولًا.")
            return
        result = self.service.activate()
        self._trail_event("ACTIVATE", result.message)
        self.statusBar().showMessage(result.message)
        self._refresh_orders(False)
        if result.state.value == "SUCCESS" and result.create_result:
            new_id = result.create_result.get("orderListId")
            self._selected_id = int(new_id) if new_id else self._selected_id
            QMessageBox.information(self, "تم", f"تم إنشاء OCO البديل #{new_id}\nزمن الاستبدال: {result.elapsed_ms:.2f} ms")
        elif result.state.value == "FAILED_NEEDS_ATTENTION":
            QMessageBox.warning(self, "FAILED_NEEDS_ATTENTION", result.message)

    def _save_dynamic_stop_setting(self) -> None:
        try:
            value = Decimal(self.dynamic_stop_edit.text().strip())
            if value <= 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            QMessageBox.warning(self, "الإعدادات", "أدخل نسبة موجبة مثل 0.50")
            self.dynamic_stop_edit.setText(f"{self.dynamic_stop_percent:f}")
            return
        self.dynamic_stop_percent = value
        self.editor_hint.setText("الاستوب الديناميكي: يُحسب من السعر اللحظي وفق النسبة العامة في الإعدادات.")
        self.statusBar().showMessage(f"تم حفظ Dynamic Stop Distance = {value}%")

    def _update_home_from_price(self) -> None:
        self._update_home_metrics(self.orders.rowCount())

    def _clear_selection_ui(self) -> None:
        self._selected_id = None
        self._editor_guard = True
        try:
            self.tp_edit.clear()
            self.sl_edit.clear()
            self.qty_edit.clear()
        finally:
            self._editor_guard = False
        self.target_label.setText("لا يوجد OCO محدد")
        self.monitor_symbol.setText("—")
        self.monitor_price.setText("—")
        self.monitor_max_stop.setText("—")
        self.monitor_tick.setText("—")
        self.selected_status.setText("—")
        self.home_symbol.setText("—")
        self.home_tp.setText("—")
        self.home_sl.setText("—")
        self.home_reference.setText("—")
        self._update_home_metrics(0)

    def closeEvent(self, event) -> None:
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
        super().closeEvent(event)


def run_app() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
