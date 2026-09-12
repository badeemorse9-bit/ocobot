from __future__ import annotations

import sys

from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
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
from ocobot.domain.models import OCOOrder, OrderLeg
from ocobot.providers.binance import TESTNET_REST, TESTNET_WS


BG = "#031021"
SIDEBAR = "#020d1c"
CARD = "#061529"
CARD_ALT = "#081d32"
BORDER = "#0d2a43"
TEXT = "#f0f7fb"
TEXT_SOFT = "#dce9f2"
MUTED = "#6f8ba2"
BLUE = "#0876e8"
TEAL = "#073b42"
GREEN = "#19c58b"
RED = "#ff4b68"
AMBER = "#f08f1b"

STYLE = f"""
QMainWindow, QWidget {{ background:{BG}; color:{TEXT_SOFT}; font-family:'Segoe UI'; }}
QFrame#sidebar {{ background:{SIDEBAR}; border:0; }}
QLabel#brand {{ color:#f3f8fb; font-size:25px; font-weight:800; }}
QLabel#brandAccent {{ color:#ffc400; font-size:25px; font-weight:900; }}
QLabel#sidehint {{ color:{MUTED}; font-size:11px; }}
QPushButton#nav {{ background:transparent; color:#c4d4df; border:0; border-radius:7px; padding:11px 12px; text-align:left; font-weight:700; font-size:12px; }}
QPushButton#nav[selected="true"] {{ background:{TEAL}; color:#e9ffff; border-left:3px solid {GREEN}; }}
QFrame#topbar {{ background:{CARD}; border:1px solid {BORDER}; border-radius:10px; }}
QLabel#connected {{ color:{GREEN}; font-weight:800; font-size:11px; }}
QLabel#pageTitle {{ font-size:25px; font-weight:800; color:{TEXT}; }}
QLabel#pageSubtitle {{ color:#77a0bc; font-size:11px; }}
QFrame#metric {{ background:{CARD}; border:1px solid {BORDER}; border-radius:9px; }}
QLabel#metricLabel {{ color:#7fa0b7; font-size:11px; }}
QLabel#metricValue {{ color:{TEXT}; font-size:24px; font-weight:800; }}
QFrame#card {{ background:{CARD}; border:1px solid {BORDER}; border-radius:9px; }}
QLabel#sectionTitle {{ font-size:15px; font-weight:800; color:{TEXT}; }}
QLabel#sectionSubtitle {{ color:#86a5ba; font-size:11px; }}
QLabel#pill {{ background:{CARD_ALT}; color:#8db9dc; border:1px solid #154a72; border-radius:7px; padding:4px 8px; font-size:10px; font-weight:800; }}
QLabel#statusPill {{ background:#063a32; color:{GREEN}; border:1px solid #0c735c; border-radius:6px; padding:4px 8px; font-size:10px; font-weight:800; }}
QLabel#bluePill {{ background:#062c4e; color:#64b5ff; border:1px solid #0b5d9a; border-radius:6px; padding:4px 8px; font-size:10px; font-weight:800; }}
QTableWidget {{ background:{CARD}; color:{TEXT_SOFT}; border:0; gridline-color:{BORDER}; selection-background-color:#0a4e78; selection-color:#ffffff; font-size:11px; }}
QTableWidget::item {{ padding:8px 6px; border-bottom:1px solid #0b2238; }}
QHeaderView::section {{ background:{CARD_ALT}; color:#7c9ab0; padding:9px 6px; border:0; border-bottom:1px solid {BORDER}; font-weight:800; font-size:10px; }}
QPushButton#refresh {{ background:{BLUE}; color:#ffffff; border:0; border-radius:7px; padding:8px 13px; font-weight:800; font-size:10px; }}
QFrame#legTP {{ background:#062522; border:1px solid {GREEN}; border-radius:8px; }}
QFrame#legSL {{ background:#2a1420; border:1px solid {RED}; border-radius:8px; }}
QLabel#legTitleTP {{ color:{GREEN}; font-size:13px; font-weight:800; }}
QLabel#legTitleSL {{ color:{RED}; font-size:13px; font-weight:800; }}
QLabel#legBadgeTP {{ background:{GREEN}; color:#031021; border-radius:12px; padding:5px 7px; font-size:10px; font-weight:900; }}
QLabel#legBadgeSL {{ background:{RED}; color:#25060f; border-radius:12px; padding:5px 7px; font-size:10px; font-weight:900; }}
QLabel#fieldLabel {{ color:#81a4bc; font-size:10px; }}
QLabel#fieldValue {{ color:#edf6fb; font-size:11px; font-weight:700; }}
QLabel#fieldValueGreen {{ color:{GREEN}; font-size:11px; font-weight:800; }}
QLabel#fieldValueRed {{ color:#ff8ca0; font-size:11px; font-weight:800; }}
QFrame#raw {{ background:#04101f; border:1px solid #12344f; border-radius:8px; }}
QLabel#rawText {{ color:#72bbf7; font-family:'Consolas','Cascadia Code',monospace; font-size:9px; }}
QFrame#note {{ background:#08233a; border:0; border-radius:7px; }}
QLabel#noteText {{ color:#a7c2d3; font-size:10px; }}
"""


class PriceBridge(QObject):
    snapshot = Signal(object)
    status = Signal(str)

    def on_price(self, snapshot: PriceSnapshot) -> None:
        self.snapshot.emit(snapshot)

    def on_status(self, status: str) -> None:
        self.status.emit(status)


def visual_oco_fixture() -> list[OCOOrder]:
    return [
        _fixture_oco(7964, "TUTUSDT", "876", "0.02350000", "0.02280000", "0.02281000", 10467, 10466, 1788990986329),
        _fixture_oco(8001, "TUTUSDT", "8752", "0.02350000", "0.02283000", "0.02284000", 10541, 10540, 1788991289853),
    ]


def _fixture_oco(
    list_id: int,
    symbol: str,
    qty_s: str,
    tp_s: str,
    sl_limit_s: str,
    sl_stop_s: str,
    tp_order_id: int,
    sl_order_id: int,
    transaction_time: int,
) -> OCOOrder:
    qty = Decimal(qty_s)
    tp = Decimal(tp_s)
    sl_limit = Decimal(sl_limit_s)
    sl_stop = Decimal(sl_stop_s)
    return OCOOrder(
        order_list_id=list_id,
        symbol=symbol,
        contingency_type="OCO",
        list_status_type="EXEC_STARTED",
        list_order_status="EXECUTING",
        list_client_order_id=f"VISUAL-{list_id}",
        transaction_time=transaction_time,
        legs=(
            OrderLeg(symbol, tp_order_id, f"VISUAL-TP-{list_id}", "SELL", "LIMIT_MAKER", "NEW", qty, tp),
            OrderLeg(symbol, sl_order_id, f"VISUAL-SL-{list_id}", "SELL", "STOP_LOSS_LIMIT", "NEW", qty, sl_limit, sl_stop),
        ),
        raw={
            "contingencyType": "OCO",
            "listClientOrderId": f"VISUAL-{list_id}",
            "listOrderStatus": "EXECUTING",
            "listStatusType": "EXEC_STARTED",
            "orderListId": list_id,
            "orders": [
                {"symbol": symbol, "orderId": tp_order_id, "price": tp_s, "origQty": qty_s, "type": "LIMIT_MAKER", "timeInForce": "GTC"},
                {"symbol": symbol, "orderId": sl_order_id, "stopPrice": sl_stop_s, "price": sl_limit_s, "origQty": qty_s, "type": "STOP_LOSS_LIMIT", "timeInForce": "GTC"},
            ],
            "symbol": symbol,
            "transactionTime": transaction_time,
        },
    )


class Stage12Window(QMainWindow):
    """Stage 2 visual section: open OCO selection and read-only details."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OCObot — Stage 2")
        self.resize(1536, 960)
        self.setMinimumSize(1280, 820)
        self.setStyleSheet(STYLE)
        self.orders: list[OCOOrder] = visual_oco_fixture()
        self.selected: OCOOrder | None = None
        self.feed: LivePriceFeed | None = None
        self.bridge = PriceBridge(self)
        self.bridge.snapshot.connect(self._on_price)
        self.bridge.status.connect(self._on_status)
        self._build_ui()
        self._populate_orders()

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
        sidebar.setFixedWidth(232)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 18, 14, 14)
        brand_row = QHBoxLayout()
        brand = QLabel("OCO")
        brand.setObjectName("brand")
        accent = QLabel("BOT")
        accent.setObjectName("brandAccent")
        brand_row.addWidget(brand)
        brand_row.addWidget(accent)
        brand_row.addStretch(1)
        side.addLayout(brand_row)
        hint = QLabel("Binance OCO Management Bot")
        hint.setObjectName("sidehint")
        side.addWidget(hint)
        side.addSpacing(18)
        for text, sub, selected in [
            ("Dashboard", "الرئيسية", False),
            ("Stage 1", "Market & Price\nالسعر والسوق", False),
            ("Stage 2", "Open OCO Orders\nالأوامر المفتوحة (OCO)", True),
            ("Stage 3", "Edit OCO\nتعديل OCO", False),
            ("Stage 4", "Paper Simulator\nالمحاكي الورقي", False),
            ("Settings", "الإعدادات", False),
        ]:
            button = QPushButton(f"{text}\n{sub}")
            button.setObjectName("nav")
            button.setProperty("selected", selected)
            side.addWidget(button)
        side.addStretch(1)
        mode = QLabel("OCOBOT v1.0.0\nBuild: 2026-09-09")
        mode.setObjectName("sidehint")
        side.addWidget(mode)
        shell.addWidget(sidebar)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)
        shell.addWidget(content, 1)

        topbar = QFrame(objectName="topbar")
        tl = QHBoxLayout(topbar)
        tl.setContentsMargins(14, 10, 14, 10)
        env = QLabel("●  Testnet  ▾")
        env.setStyleSheet("color:#19c58b; font-size:11px; font-weight:800; background:#063a32; padding:6px 10px; border-radius:12px;")
        tl.addWidget(env)
        binance = QLabel("◆  Binance Testnet")
        binance.setStyleSheet("color:#f1f7fb; font-size:11px; font-weight:700;")
        tl.addWidget(binance)
        tl.addStretch(1)
        self.connected = QLabel("▮▮▮  Connected")
        self.connected.setObjectName("connected")
        tl.addWidget(self.connected)
        root.addWidget(topbar)

        title_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title = QLabel("Stage 2 – Open OCO Orders")
        title.setObjectName("pageTitle")
        title_col.addWidget(title)
        subtitle = QLabel("View your active OCO orders from Binance. Select an order to see full details.")
        subtitle.setObjectName("pageSubtitle")
        title_col.addWidget(subtitle)
        arabic = QLabel("عرض الأوامر المفتوحة — اختر أمرًا لعرض التفاصيل الكاملة")
        arabic.setObjectName("pageSubtitle")
        title_col.addWidget(arabic)
        title_row.addLayout(title_col, 1)
        self.read_only = QLabel("Read Only")
        self.read_only.setObjectName("statusPill")
        title_row.addWidget(self.read_only, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(title_row)

        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        total_frame, self.total_value = self._metric("Total Active OCO Orders", "—")
        metrics.addWidget(total_frame, 1)
        update_frame, self.update_value = self._metric("Last Update", "—")
        refresh_btn = QPushButton("↻")
        refresh_btn.setObjectName("refresh")
        refresh_btn.setFixedWidth(38)
        refresh_btn.clicked.connect(self._populate_orders)
        update_frame.layout().addWidget(refresh_btn)  # type: ignore[union-attr]
        metrics.addWidget(update_frame, 1)
        root.addLayout(metrics)

        body = QHBoxLayout()
        body.setSpacing(12)
        root.addLayout(body, 1)

        left_card = QFrame(objectName="card")
        left = QVBoxLayout(left_card)
        left.setContentsMargins(12, 12, 12, 12)
        header = QHBoxLayout()
        heading = QLabel("Active OCO Orders")
        heading.setObjectName("sectionTitle")
        header.addWidget(heading)
        arabic_head = QLabel("الأوامر المفتوحة")
        arabic_head.setObjectName("sectionSubtitle")
        header.addWidget(arabic_head)
        header.addStretch(1)
        self.count_label = QLabel("0 orders")
        self.count_label.setObjectName("pill")
        header.addWidget(self.count_label)
        left.addLayout(header)

        self.orders_table = QTableWidget(0, 8)
        self.orders_table.setHorizontalHeaderLabels(["#", "orderListId", "Symbol", "Status", "Qty", "Sale Price (TP)", "Stop Trigger", "Limit After Trigger"])
        self.orders_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.orders_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.orders_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.orders_table.verticalHeader().setVisible(False)
        header_view = self.orders_table.horizontalHeader()
        for column in range(8):
            header_view.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        for column, width in {
            0: 42,
            1: 92,
            2: 88,
            3: 110,
            4: 82,
            5: 128,
            6: 118,
            7: 148,
        }.items():
            self.orders_table.setColumnWidth(column, width)
        self.orders_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.orders_table.itemSelectionChanged.connect(self._select_row)
        left.addWidget(self.orders_table, 1)
        body.addWidget(left_card, 3)

        right_card = QFrame(objectName="card")
        right = QVBoxLayout(right_card)
        right.setContentsMargins(12, 12, 12, 12)
        right.setSpacing(9)
        selected_header = QHBoxLayout()
        heading = QLabel("Selected OCO Order")
        heading.setObjectName("sectionTitle")
        selected_header.addWidget(heading)
        arabic_order = QLabel("الأمر المحدد")
        arabic_order.setObjectName("sectionSubtitle")
        selected_header.addWidget(arabic_order)
        selected_header.addStretch(1)
        self.selected_pill = QLabel("orderListId: —")
        self.selected_pill.setObjectName("bluePill")
        selected_header.addWidget(self.selected_pill)
        right.addLayout(selected_header)

        info = QGridLayout()
        self.detail_symbol = self._info_value(info, 0, 0, "Symbol", "—")
        self.detail_contingency = self._info_value(info, 0, 1, "Contingency Type", "—")
        self.detail_list_type = self._info_value(info, 0, 2, "List Status Type", "—")
        self.detail_status = self._info_value(info, 0, 3, "List Order Status", "—")
        self.detail_status.setObjectName("statusPill")
        right.addLayout(info)

        self._leg_row = QHBoxLayout()
        self._leg_row.setSpacing(9)
        tp_frame = self._new_leg_frame("TP", "Take Profit — Sale Price (سعر البيع)", "green")
        sl_frame = self._new_leg_frame("SL", "Stop Loss — Trigger + Limit After Trigger", "red")
        self._leg_row.addWidget(tp_frame, 1)
        self._leg_row.addWidget(sl_frame, 1)
        right.addLayout(self._leg_row)

        raw = QFrame(objectName="raw")
        raw_l = QVBoxLayout(raw)
        raw_l.setContentsMargins(10, 8, 10, 8)
        raw_title = QLabel("{}  Raw OCO Fields  (from Binance)    الحقول الأصلية من Binance")
        raw_title.setObjectName("sectionSubtitle")
        raw_l.addWidget(raw_title)
        self.raw_text = QLabel("—")
        self.raw_text.setObjectName("rawText")
        self.raw_text.setWordWrap(True)
        raw_l.addWidget(self.raw_text)
        right.addWidget(raw)

        note = QFrame(objectName="note")
        nl = QHBoxLayout(note)
        nl.setContentsMargins(10, 8, 10, 8)
        icon = QLabel("ⓘ")
        icon.setStyleSheet("color:#74b8f0; font-size:13px; font-weight:800;")
        nl.addWidget(icon)
        note_text = QLabel("This view is read-only. No cancel, create or modify actions are performed.\nهذه الشاشة للقراءة فقط — لا يوجد إلغاء أو إنشاء أو تعديل.")
        note_text.setObjectName("noteText")
        note_text.setWordWrap(True)
        nl.addWidget(note_text, 1)
        right.addWidget(note)
        body.addWidget(right_card, 2)

    @staticmethod
    def _metric(label: str, value: str) -> tuple[QFrame, QLabel]:
        frame = QFrame(objectName="metric")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(15, 10, 15, 10)
        col = QVBoxLayout()
        l = QLabel(label)
        l.setObjectName("metricLabel")
        v = QLabel(value)
        v.setObjectName("metricValue")
        col.addWidget(l)
        col.addWidget(v)
        layout.addLayout(col, 1)
        return frame, v

    @staticmethod
    def _info_value(grid: QGridLayout, row: int, col: int, label: str, value: str) -> QLabel:
        box = QVBoxLayout()
        label_w = QLabel(label)
        label_w.setObjectName("fieldLabel")
        value_w = QLabel(value)
        value_w.setObjectName("fieldValue")
        box.addWidget(label_w)
        box.addWidget(value_w)
        grid.addLayout(box, row, col)
        return value_w

    @staticmethod
    def _new_leg_frame(badge: str, title: str, kind: str) -> QFrame:
        frame = QFrame(objectName="legTP" if kind == "green" else "legSL")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 9, 10, 9)
        head = QHBoxLayout()
        badge_label = QLabel(badge)
        badge_label.setObjectName("legBadgeTP" if kind == "green" else "legBadgeSL")
        head.addWidget(badge_label)
        title_label = QLabel(title)
        title_label.setObjectName("legTitleTP" if kind == "green" else "legTitleSL")
        head.addWidget(title_label)
        head.addStretch(1)
        layout.addLayout(head)
        return frame

    def _populate_orders(self) -> None:
        self.orders = visual_oco_fixture()
        ordered = sorted(self.orders, key=lambda x: (x.symbol, x.order_list_id))
        self.orders_table.setRowCount(0)
        self.total_value.setText(str(len(ordered)))
        self.count_label.setText(f"{len(ordered)} orders")
        for idx, order in enumerate(ordered, start=1):
            row = self.orders_table.rowCount()
            self.orders_table.insertRow(row)
            sl_leg = self._sl_leg(order)
            values = [
                str(idx),
                str(order.order_list_id),
                order.symbol,
                order.list_order_status,
                self._quantity(order),
                self._fmt(self._tp(order)),
                self._fmt(sl_leg.stop_price if sl_leg else None),
                self._fmt(sl_leg.price if sl_leg else None),
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.orders_table.setItem(row, col, item)
        if ordered:
            self.orders_table.setCurrentCell(0, 0)
            self.orders_table.selectRow(0)
            self._select_row()
        else:
            self.selected = None
        self.update_value.setText(datetime.now().strftime("%H:%M:%S"))

    def _select_row(self) -> None:
        row = self.orders_table.currentRow()
        if row < 0:
            return
        ordered = sorted(self.orders, key=lambda x: (x.symbol, x.order_list_id))
        if row >= len(ordered):
            return
        order = ordered[row]
        self.selected = order
        self.selected_pill.setText(f"orderListId: {order.order_list_id}")
        self.detail_symbol.setText(order.symbol)
        self.detail_contingency.setText(order.contingency_type)
        self.detail_list_type.setText(order.list_status_type)
        self.detail_status.setText(order.list_order_status)
        self.raw_text.setText(self._raw_preview(order))
        self._fill_leg_card(self._leg_row.itemAt(0).widget(), self._tp_leg(order), "green")
        self._fill_leg_card(self._leg_row.itemAt(1).widget(), self._sl_leg(order), "red")
        self._start_feed(order.symbol)

    @staticmethod
    def _fill_leg_card(frame: QWidget | None, leg: OrderLeg | None, kind: str) -> None:
        if frame is None or leg is None:
            return
        layout = frame.layout()
        while layout.count() > 1:
            item = layout.takeAt(1)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        rows = [("Order ID", str(leg.order_id)), ("Type", leg.order_type)]
        if kind == "green":
            rows.append(("Sale Price / سعر البيع", Stage12Window._fmt(leg.price)))
        else:
            rows.extend([
                ("Trigger Stop Price / سعر تفعيل الاستوب", Stage12Window._fmt(leg.stop_price)),
                ("Limit Price After Trigger / سعر الحد بعد التفعيل", Stage12Window._fmt(leg.price)),
            ])
        rows.extend([("Quantity", str(leg.quantity)), ("Time In Force", leg.time_in_force or "GTC")])
        for label, value in rows:
            row = QHBoxLayout()
            l = QLabel(label)
            l.setObjectName("fieldLabel")
            v = QLabel(value)
            v.setObjectName("fieldValueGreen" if kind == "green" else "fieldValueRed")
            v.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            row.addWidget(l)
            row.addStretch(1)
            row.addWidget(v)
            layout.addLayout(row)

    def _start_feed(self, symbol: str) -> None:
        if self.feed is not None:
            self.feed.stop()
        self.feed = LivePriceFeed(symbol, TESTNET_REST, TESTNET_WS, self.bridge.on_price, self.bridge.on_status)
        self.feed.start()

    def _on_price(self, snapshot: PriceSnapshot) -> None:
        self.update_value.setText(datetime.fromtimestamp(snapshot.received_at).strftime("%H:%M:%S"))

    def _on_status(self, status: str) -> None:
        if status == "LIVE_WS_CONNECTED":
            self.connected.setText("▮▮▮  Connected")
        elif status.startswith("WS_ERROR") or status == "RECONNECTING":
            self.connected.setText("▮▮  Reconnecting")
        elif status == "STOPPED":
            self.connected.setText("▮  Stopped")

    @staticmethod
    def _raw_preview(order: OCOOrder) -> str:
        keys = ", ".join(order.raw.keys())
        return "{\n  " + keys + "\n}"

    @staticmethod
    def _quantity(order: OCOOrder) -> str:
        return str(order.legs[0].quantity) if order.legs else "—"

    @staticmethod
    def _tp_leg(order: OCOOrder) -> OrderLeg | None:
        for leg in order.legs:
            if leg.price is not None and "STOP" not in leg.order_type.upper():
                return leg
        return None

    @staticmethod
    def _sl_leg(order: OCOOrder) -> OrderLeg | None:
        for leg in order.legs:
            if leg.stop_price is not None:
                return leg
        return None

    @staticmethod
    def _tp(order: OCOOrder) -> Decimal | None:
        leg = Stage12Window._tp_leg(order)
        return leg.price if leg else None

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
