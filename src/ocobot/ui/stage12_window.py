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
from ocobot.providers.binance import TESTNET_REST, TESTNET_WS
from ocobot.providers.sample_data import sample_ocos
from ocobot.domain.models import OCOOrder


STYLE = """
QMainWindow, QWidget { background:#eef2f6; color:#182637; }
QFrame#topbar { background:#14243a; border:0; }
QLabel#brand { color:white; font-size:22px; font-weight:800; }
QLabel#subtitle { color:#a9bbcd; font-size:11px; }
QLabel#status { color:#cfe4f7; font-weight:700; }
QLabel#pageTitle { font-size:24px; font-weight:800; color:#172b40; }
QLabel#pageSubtitle { color:#6e7d8d; font-size:12px; }
QLabel#metricLabel { color:#728294; font-size:11px; }
QLabel#metricValue { color:#172b40; font-size:23px; font-weight:800; }
QFrame#card { background:white; border:1px solid #d7e0e8; border-radius:12px; }
QTableWidget { background:white; border:1px solid #d7e0e8; gridline-color:#e8edf2; selection-background-color:#dcecff; selection-color:#14243a; font-size:12px; }
QHeaderView::section { background:#f3f6f8; color:#3d4e5f; padding:8px; border:0; border-bottom:1px solid #d7e0e8; font-weight:800; }
QLabel#sectionTitle { font-size:15px; font-weight:800; color:#25384c; }
QLabel#muted { color:#718092; }
QLabel#value { font-weight:700; }
QPushButton#refresh { background:#246fd1; color:white; border:0; border-radius:7px; padding:8px 13px; font-weight:800; }
QPushButton#refresh:hover { background:#1d5eaf; }
QLabel#green { color:#1b9861; font-weight:800; }
QLabel#amber { color:#8b6410; font-weight:800; }
QLabel#red { color:#a33a2c; font-weight:800; }
"""


class PriceBridge(QObject):
    snapshot = Signal(object)
    status = Signal(str)

    def on_price(self, snapshot: PriceSnapshot) -> None:
        self.snapshot.emit(snapshot)

    def on_status(self, status: str) -> None:
        self.status.emit(status)


class Stage12Window(QMainWindow):
    """Isolated UI for the already-proven Stage 1 price feed and Stage 2 OCO reader."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OCObot — السعر اللحظي و OCO")
        self.resize(1260, 780)
        self.setMinimumSize(1080, 680)
        self.setStyleSheet(STYLE)
        self.orders: list[OCOOrder] = sample_ocos()
        self.selected: OCOOrder | None = None
        self.feed: LivePriceFeed | None = None
        self.bridge = PriceBridge(self)
        self.bridge.snapshot.connect(self._on_price)
        self.bridge.status.connect(self._on_status)
        self._build_ui()
        self._populate_orders()
        if self.orders:
            self.orders_table.selectRow(0)
            self._select_row()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.feed is not None:
            self.feed.stop()
            self.feed = None
        super().closeEvent(event)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)
        self.setCentralWidget(root)

        title = QLabel("مراقبة السعر واختيار OCO")
        title.setObjectName("pageTitle")
        outer.addWidget(title)
        subtitle = QLabel("هذا القسم للعرض والاختيار فقط — لا إلغاء ولا إنشاء ولا تعديل للأوامر")
        subtitle.setObjectName("pageSubtitle")
        outer.addWidget(subtitle)

        price_card = QFrame(objectName="card")
        price_layout = QHBoxLayout(price_card)
        price_layout.setContentsMargins(16, 12, 16, 12)
        self.symbol_value = QLabel("—")
        self.symbol_value.setObjectName("metricValue")
        self.price_value = QLabel("—")
        self.price_value.setObjectName("metricValue")
        self.price_value.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.feed_status = QLabel("في انتظار تغذية السعر")
        self.feed_status.setObjectName("amber")
        self.last_update = QLabel("—")
        self.last_update.setObjectName("muted")
        for label, widget in (
            ("الرمز", self.symbol_value),
            ("السعر اللحظي", self.price_value),
            ("حالة المصدر", self.feed_status),
            ("آخر تحديث", self.last_update),
        ):
            column = QVBoxLayout()
            text = QLabel(label)
            text.setObjectName("metricLabel")
            column.addWidget(text)
            column.addWidget(widget)
            price_layout.addLayout(column, 1)
        self.source_value = QLabel("—")
        self.source_value.setObjectName("muted")
        source_column = QVBoxLayout()
        source_column.addWidget(QLabel("المصدر"))
        source_column.addWidget(self.source_value)
        price_layout.addLayout(source_column, 1)
        outer.addWidget(price_card)

        body = QHBoxLayout()
        body.setSpacing(12)
        outer.addLayout(body, 1)

        table_card = QFrame(objectName="card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(12, 12, 12, 12)
        header = QHBoxLayout()
        title_label = QLabel("OCO النشطة")
        title_label.setObjectName("sectionTitle")
        header.addWidget(title_label)
        header.addStretch(1)
        self.count_label = QLabel("0 أمر")
        self.count_label.setObjectName("muted")
        header.addWidget(self.count_label)
        refresh = QPushButton("إعادة تحميل")
        refresh.setObjectName("refresh")
        refresh.clicked.connect(self._populate_orders)
        header.addWidget(refresh)
        table_layout.addLayout(header)

        self.orders_table = QTableWidget(0, 6)
        self.orders_table.setHorizontalHeaderLabels(["Order List ID", "الرمز", "الكمية", "TP", "SL", "الحالة"])
        self.orders_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.orders_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.orders_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.orders_table.verticalHeader().setVisible(False)
        self.orders_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.orders_table.itemSelectionChanged.connect(self._select_row)
        table_layout.addWidget(self.orders_table, 1)
        body.addWidget(table_card, 3)

        detail_card = QFrame(objectName="card")
        detail_layout = QVBoxLayout(detail_card)
        detail_layout.setContentsMargins(18, 16, 18, 16)
        detail_layout.setSpacing(8)
        detail_title = QLabel("تفاصيل OCO المحدد")
        detail_title.setObjectName("sectionTitle")
        detail_layout.addWidget(detail_title)

        self.detail_id = QLabel("—")
        self.detail_symbol = QLabel("—")
        self.detail_status = QLabel("—")
        self.detail_quantity = QLabel("—")
        self.detail_tp = QLabel("—")
        self.detail_sl = QLabel("—")
        self.detail_tp.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.detail_sl.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        fields = [
            ("Order List ID", self.detail_id),
            ("الرمز", self.detail_symbol),
            ("الحالة", self.detail_status),
            ("الكمية", self.detail_quantity),
            ("سعر TP", self.detail_tp),
            ("Stop Price", self.detail_sl),
        ]
        for label, value in fields:
            row = QHBoxLayout()
            left = QLabel(label)
            left.setObjectName("muted")
            row.addWidget(left)
            row.addStretch(1)
            value.setObjectName("value")
            row.addWidget(value)
            detail_layout.addLayout(row)

        detail_layout.addSpacing(8)
        note = QLabel("اختيار OCO هنا لا يغيّر الأمر على Binance. التعديل والتنفيذ سيأتيان في مراحل لاحقة.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        detail_layout.addWidget(note)
        detail_layout.addStretch(1)
        body.addWidget(detail_card, 1)

        status_bar = QFrame()
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(0, 0, 0, 0)
        self.connection = QLabel("Testnet Public Market Data")
        self.connection.setObjectName("muted")
        status_layout.addWidget(self.connection)
        status_layout.addStretch(1)
        safety = QLabel("قراءة فقط")
        safety.setObjectName("green")
        status_layout.addWidget(safety)
        outer.addWidget(status_bar)

    def _populate_orders(self) -> None:
        self.orders = sample_ocos()
        self.orders_table.setRowCount(0)
        for order in sorted(self.orders, key=lambda x: (x.symbol, x.order_list_id)):
            row = self.orders_table.rowCount()
            self.orders_table.insertRow(row)
            tp = self._leg_price(order, "LIMIT")
            sl = self._leg_stop(order)
            values = [
                str(order.order_list_id),
                order.symbol,
                self._quantity(order),
                self._format_decimal(tp),
                self._format_decimal(sl),
                order.list_order_status,
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.orders_table.setItem(row, column, item)
        self.count_label.setText(f"{self.orders_table.rowCount()} أمر")

    def _select_row(self) -> None:
        rows = self.orders_table.selectionModel().selectedRows()
        if not rows:
            return
        order = sorted(self.orders, key=lambda x: (x.symbol, x.order_list_id))[rows[0].row()]
        self.selected = order
        self._show_order(order)
        self._start_feed(order.symbol)

    def _show_order(self, order: OCOOrder) -> None:
        self.detail_id.setText(str(order.order_list_id))
        self.detail_symbol.setText(order.symbol)
        self.detail_status.setText(order.list_order_status)
        self.detail_quantity.setText(self._quantity(order))
        self.detail_tp.setText(self._format_decimal(self._leg_price(order, "LIMIT")))
        self.detail_sl.setText(self._format_decimal(self._leg_stop(order)))
        self.symbol_value.setText(order.symbol)
        self.connection.setText("Paper OCO data • Binance field-shaped model")

    def _start_feed(self, symbol: str) -> None:
        if self.feed is not None:
            self.feed.stop()
        self.feed = LivePriceFeed(
            symbol=symbol,
            rest_base=TESTNET_REST,
            ws_base=TESTNET_WS,
            on_price=self.bridge.on_price,
            on_status=self.bridge.on_status,
        )
        self.price_value.setText("—")
        self.source_value.setText("—")
        self.feed_status.setText("جارٍ الاتصال…")
        self.feed.start()

    def _on_price(self, snapshot: PriceSnapshot) -> None:
        self.price_value.setText(f"{snapshot.price:f}")
        self.source_value.setText(snapshot.source)
        self.last_update.setText(datetime.fromtimestamp(snapshot.received_at).strftime("%H:%M:%S"))
        self.feed_status.setText("متصل" if snapshot.source.startswith("WS") else "REST fallback")
        self.feed_status.setObjectName("green" if snapshot.source.startswith("WS") else "amber")
        self.feed_status.style().unpolish(self.feed_status)
        self.feed_status.style().polish(self.feed_status)

    def _on_status(self, status: str) -> None:
        if status == "LIVE_WS_CONNECTED":
            self.feed_status.setText("WebSocket متصل")
            self.feed_status.setObjectName("green")
        elif status.startswith("WS_ERROR"):
            self.feed_status.setText("WebSocket غير متاح — REST يعمل")
            self.feed_status.setObjectName("amber")
        elif status == "LIVE_REST":
            if self.feed_status.text() not in {"WebSocket متصل"}:
                self.feed_status.setText("REST يعمل")
        else:
            self.feed_status.setText(status)
        self.feed_status.style().unpolish(self.feed_status)
        self.feed_status.style().polish(self.feed_status)

    @staticmethod
    def _quantity(order: OCOOrder) -> str:
        if not order.legs:
            return "—"
        return str(order.legs[0].quantity)

    @staticmethod
    def _leg_price(order: OCOOrder, kind: str) -> Decimal | None:
        for leg in order.legs:
            if kind == "LIMIT" and leg.price is not None and "STOP" not in leg.order_type.upper():
                return leg.price
        return None

    @staticmethod
    def _leg_stop(order: OCOOrder) -> Decimal | None:
        for leg in order.legs:
            if leg.stop_price is not None:
                return leg.stop_price
        return None

    @staticmethod
    def _format_decimal(value: Decimal | None) -> str:
        return f"{value:f}" if value is not None else "—"


def main() -> None:
    app = QApplication(sys.argv)
    window = Stage12Window()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
