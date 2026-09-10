from __future__ import annotations

import sys
from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ocobot.application.live_price import LivePriceFeed, PriceSnapshot
from ocobot.domain.models import OCOOrder
from ocobot.providers.binance import TESTNET_REST, TESTNET_WS
from ocobot.providers.sample_data import sample_ocos


STYLE = """
QMainWindow, QWidget { background:#eef2f6; color:#182637; }
QFrame#sidebar { background:#14243a; border:0; }
QLabel#brand { color:white; font-size:22px; font-weight:800; }
QLabel#sidehint { color:#9eb0c3; font-size:11px; }
QPushButton#nav { background:transparent; color:#d9e3ee; border:0; border-radius:8px; padding:10px 12px; text-align:right; font-weight:700; }
QPushButton#nav[selected="true"] { background:#285783; color:white; }
QLabel#topStatus { color:#cfe4f7; font-weight:700; }
QLabel#pageTitle { font-size:24px; font-weight:800; color:#172b40; }
QLabel#pageSubtitle { color:#6e7d8d; font-size:12px; }
QFrame#card { background:white; border:1px solid #d7e0e8; border-radius:12px; }
QLabel#metricLabel { color:#728294; font-size:11px; }
QLabel#metricValue { color:#172b40; font-size:22px; font-weight:800; }
QLabel#sectionTitle { font-size:15px; font-weight:800; color:#25384c; }
QLabel#muted { color:#718092; }
QLabel#value { font-weight:700; }
QTableWidget { background:white; border:0; gridline-color:#e8edf2; selection-background-color:#dcecff; selection-color:#14243a; font-size:12px; }
QHeaderView::section { background:#f3f6f8; color:#3d4e5f; padding:8px; border:0; border-bottom:1px solid #d7e0e8; font-weight:800; }
QPushButton#refresh { background:#246fd1; color:white; border:0; border-radius:7px; padding:8px 13px; font-weight:800; }
QLabel#green { color:#1b9861; font-weight:800; }
QLabel#amber { color:#8b6410; font-weight:800; }
"""


class PriceBridge(QObject):
    snapshot = Signal(object)
    status = Signal(str)

    def on_price(self, snapshot: PriceSnapshot) -> None:
        self.snapshot.emit(snapshot)

    def on_status(self, status: str) -> None:
        self.status.emit(status)


class Stage12Window(QMainWindow):
    """Isolated visual section for the proven Stage 1 price feed and Stage 2 OCO reader."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OCObot — السعر اللحظي و OCO")
        self.resize(1280, 800)
        self.setMinimumSize(1100, 700)
        self.setStyleSheet(STYLE)
        self.orders: list[OCOOrder] = sample_ocos()
        self.selected: OCOOrder | None = None
        self.feed: LivePriceFeed | None = None
        self.bridge = PriceBridge(self)
        self.bridge.snapshot.connect(self._on_price)
        self.bridge.status.connect(self._on_status)
        self._build_ui()
        self._populate_orders()
        if self.orders_table.rowCount():
            self.orders_table.selectRow(0)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.feed is not None:
            self.feed.stop()
            self.feed = None
        super().closeEvent(event)

    def _build_ui(self) -> None:
        outer = QWidget()
        outer.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setCentralWidget(outer)
        shell = QHBoxLayout(outer)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        sidebar = QFrame(objectName="sidebar")
        sidebar.setFixedWidth(210)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 18, 14, 14)
        brand = QLabel("OCObot")
        brand.setObjectName("brand")
        side.addWidget(brand)
        hint = QLabel("منظم • آمن • خفيف")
        hint.setObjectName("sidehint")
        side.addWidget(hint)
        side.addSpacing(18)
        for text, selected in [("الرئيسية", True), ("الأوامر", False), ("التتبع", False), ("Testnet", False), ("المراقبة", False), ("الإعدادات", False)]:
            button = QPushButton(text)
            button.setObjectName("nav")
            button.setProperty("selected", selected)
            side.addWidget(button)
        side.addStretch(1)
        mode = QLabel("TESTNET\nBinance Spot Testnet")
        mode.setObjectName("sidehint")
        side.addWidget(mode)
        shell.addWidget(sidebar)

        content = QWidget()
        content.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(content)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(9)
        shell.addWidget(content, 1)

        topbar = QFrame(objectName="card")
        tl = QHBoxLayout(topbar)
        tl.setContentsMargins(14, 9, 14, 9)
        self.system_status = QLabel("● System Online")
        self.system_status.setObjectName("topStatus")
        self.ws_status = QLabel("WS: —")
        self.ws_status.setObjectName("topStatus")
        self.rest_status = QLabel("REST: Live")
        self.rest_status.setObjectName("topStatus")
        tl.addWidget(self.system_status)
        tl.addStretch(1)
        tl.addWidget(self.ws_status)
        tl.addWidget(self.rest_status)
        root.addWidget(topbar)

        title = QLabel("مراقبة السعر واختيار OCO")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        subtitle = QLabel("عرض واختيار فقط — لا إلغاء ولا إنشاء ولا تعديل للأوامر في هذه المرحلة")
        subtitle.setObjectName("pageSubtitle")
        root.addWidget(subtitle)

        market = QFrame(objectName="card")
        ml = QHBoxLayout(market)
        ml.setContentsMargins(16, 12, 16, 12)
        symbol_col = self._metric_column("الرمز", "—")
        self.symbol_value = symbol_col.itemAt(1).widget()
        price_col = self._metric_column("السعر اللحظي", "—")
        self.price_value = price_col.itemAt(1).widget()
        self.price_value.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        source_col = self._metric_column("مصدر البيانات", "—")
        self.source_value = source_col.itemAt(1).widget()
        state_col = self._metric_column("حالة التغذية", "في انتظار الاتصال")
        self.feed_status = state_col.itemAt(1).widget()
        self.feed_status.setObjectName("amber")
        update_col = self._metric_column("آخر تحديث", "—")
        self.last_update = update_col.itemAt(1).widget()
        for col in (symbol_col, price_col, source_col, state_col, update_col):
            ml.addLayout(col, 1)
        root.addWidget(market)

        body = QHBoxLayout()
        body.setSpacing(11)
        root.addLayout(body, 1)

        left_card = QFrame(objectName="card")
        left = QVBoxLayout(left_card)
        left.setContentsMargins(10, 10, 10, 10)
        header = QHBoxLayout()
        heading = QLabel("OCO النشطة")
        heading.setObjectName("sectionTitle")
        header.addWidget(heading)
        header.addStretch(1)
        self.count_label = QLabel("0 أمر")
        self.count_label.setObjectName("muted")
        header.addWidget(self.count_label)
        refresh = QPushButton("تحديث")
        refresh.setObjectName("refresh")
        refresh.clicked.connect(self._populate_orders)
        header.addWidget(refresh)
        left.addLayout(header)
        self.orders_table = QTableWidget(0, 6)
        self.orders_table.setHorizontalHeaderLabels(["Order List ID", "الرمز", "الكمية", "TP", "SL", "الحالة"])
        self.orders_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.orders_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.orders_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.orders_table.verticalHeader().setVisible(False)
        self.orders_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.orders_table.itemSelectionChanged.connect(self._select_row)
        left.addWidget(self.orders_table, 1)
        body.addWidget(left_card, 3)

        right_card = QFrame(objectName="card")
        right = QVBoxLayout(right_card)
        right.setContentsMargins(16, 14, 16, 14)
        heading = QLabel("تفاصيل OCO المحدد")
        heading.setObjectName("sectionTitle")
        right.addWidget(heading)
        self.detail_id = QLabel("—")
        self.detail_symbol = QLabel("—")
        self.detail_status = QLabel("—")
        self.detail_quantity = QLabel("—")
        self.detail_tp = QLabel("—")
        self.detail_sl = QLabel("—")
        self.detail_tp.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.detail_sl.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        for label, value in [("Order List ID", self.detail_id), ("الرمز", self.detail_symbol), ("الحالة", self.detail_status), ("الكمية", self.detail_quantity), ("Take Profit", self.detail_tp), ("Stop Loss", self.detail_sl)]:
            row = QHBoxLayout()
            lab = QLabel(label)
            lab.setObjectName("muted")
            row.addWidget(lab)
            row.addStretch(1)
            value.setObjectName("value")
            row.addWidget(value)
            right.addLayout(row)
        right.addSpacing(8)
        note = QLabel("هذه اللوحة قراءة فقط. لا يوجد زر تنفيذ في هذه المرحلة.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        right.addWidget(note)
        right.addStretch(1)
        body.addWidget(right_card, 1)

    @staticmethod
    def _metric_column(label: str, value: str) -> QVBoxLayout:
        layout = QVBoxLayout()
        l = QLabel(label)
        l.setObjectName("metricLabel")
        v = QLabel(value)
        v.setObjectName("metricValue")
        layout.addWidget(l)
        layout.addWidget(v)
        return layout

    def _populate_orders(self) -> None:
        self.orders = sample_ocos()
        self.orders_table.setRowCount(0)
        ordered = sorted(self.orders, key=lambda x: (x.symbol, x.order_list_id))
        for order in ordered:
            row = self.orders_table.rowCount()
            self.orders_table.insertRow(row)
            values = [
                str(order.order_list_id), order.symbol, self._quantity(order),
                self._fmt(self._tp(order)), self._fmt(self._sl(order)), order.list_order_status,
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.orders_table.setItem(row, col, item)
        self.count_label.setText(f"{len(ordered)} OCO")
        if ordered and self.orders_table.currentRow() < 0:
            self.orders_table.selectRow(0)

    def _select_row(self) -> None:
        rows = self.orders_table.selectionModel().selectedRows()
        if not rows:
            return
        ordered = sorted(self.orders, key=lambda x: (x.symbol, x.order_list_id))
        order = ordered[rows[0].row()]
        self.selected = order
        self.detail_id.setText(str(order.order_list_id))
        self.detail_symbol.setText(order.symbol)
        self.detail_status.setText(order.list_order_status)
        self.detail_quantity.setText(self._quantity(order))
        self.detail_tp.setText(self._fmt(self._tp(order)))
        self.detail_sl.setText(self._fmt(self._sl(order)))
        self.symbol_value.setText(order.symbol)
        self._start_feed(order.symbol)

    def _start_feed(self, symbol: str) -> None:
        if self.feed is not None:
            self.feed.stop()
        self.feed = LivePriceFeed(symbol, TESTNET_REST, TESTNET_WS, self.bridge.on_price, self.bridge.on_status)
        self.price_value.setText("—")
        self.source_value.setText("—")
        self.last_update.setText("—")
        self.feed_status.setText("جارٍ الاتصال…")
        self.feed_status.setObjectName("amber")
        self.ws_status.setText("WS: Connecting")
        self.feed.start()

    def _on_price(self, snapshot: PriceSnapshot) -> None:
        self.price_value.setText(f"{snapshot.price:f}")
        self.source_value.setText(snapshot.source)
        self.last_update.setText(datetime.fromtimestamp(snapshot.received_at).strftime("%H:%M:%S"))
        if snapshot.source.startswith("WS"):
            self.feed_status.setText("WebSocket حي")
            self.feed_status.setObjectName("green")
            self.ws_status.setText("WS: Connected")
        else:
            self.feed_status.setText("REST fallback")
            self.feed_status.setObjectName("amber")
        self.feed_status.style().unpolish(self.feed_status)
        self.feed_status.style().polish(self.feed_status)

    def _on_status(self, status: str) -> None:
        if status == "LIVE_WS_CONNECTED":
            self.ws_status.setText("WS: Connected")
        elif status.startswith("WS_ERROR"):
            self.ws_status.setText("WS: Reconnecting")
        elif status == "RECONNECTING":
            self.ws_status.setText("WS: Reconnecting")
        elif status == "STOPPED":
            self.ws_status.setText("WS: Stopped")

    @staticmethod
    def _quantity(order: OCOOrder) -> str:
        return str(order.legs[0].quantity) if order.legs else "—"

    @staticmethod
    def _tp(order: OCOOrder) -> Decimal | None:
        for leg in order.legs:
            if leg.price is not None and "STOP" not in leg.order_type.upper():
                return leg.price
        return None

    @staticmethod
    def _sl(order: OCOOrder) -> Decimal | None:
        for leg in order.legs:
            if leg.stop_price is not None:
                return leg.stop_price
        return None

    @staticmethod
    def _fmt(value: Decimal | None) -> str:
        return f"{value:f}" if value is not None else "—"


def main() -> None:
    app = QApplication(sys.argv)
    window = Stage12Window()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
