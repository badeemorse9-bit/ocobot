from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ocobot.ui.stage12_monitor_window import Stage12MonitorWindow


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
AMBER = "#f08f1b"


STYLE = f"""
QMainWindow, QWidget {{ background:{BG}; color:{TEXT_SOFT}; font-family:'Segoe UI'; }}
QFrame#sidebar {{ background:{SIDEBAR}; border:0; }}
QLabel#brand {{ color:{TEXT}; font-size:25px; font-weight:900; }}
QLabel#brandAccent {{ color:#ffc400; font-size:25px; font-weight:900; }}
QLabel#sidehint {{ color:{MUTED}; font-size:11px; }}
QPushButton#nav {{ background:transparent; color:#c4d4df; border:0; border-radius:8px; padding:11px 12px; text-align:left; font-size:11px; font-weight:800; }}
QPushButton#nav:hover {{ background:#071a2c; }}
QPushButton#nav[selected="true"] {{ background:{TEAL}; color:#e9ffff; border-left:3px solid {GREEN}; }}
QFrame#topbar {{ background:{CARD}; border:1px solid {BORDER}; border-radius:10px; }}
QLabel#env {{ background:#063a32; color:{GREEN}; border-radius:12px; padding:6px 10px; font-size:10px; font-weight:900; }}
QLabel#connection {{ color:{MUTED}; font-size:10px; font-weight:800; }}
QLabel#pageTitle {{ color:{TEXT}; font-size:26px; font-weight:900; }}
QLabel#pageSubtitle {{ color:#77a0bc; font-size:11px; }}
QFrame#metric {{ background:{CARD}; border:1px solid {BORDER}; border-radius:10px; }}
QLabel#metricLabel {{ color:#7fa0b7; font-size:10px; font-weight:700; }}
QLabel#metricValue {{ color:{TEXT}; font-size:21px; font-weight:900; }}
QFrame#hero {{ background:{CARD}; border:1px solid #154a72; border-radius:12px; }}
QLabel#heroEyebrow {{ color:#64b5ff; font-size:9px; font-weight:900; }}
QLabel#heroTitle {{ color:{TEXT}; font-size:18px; font-weight:900; }}
QLabel#heroValue {{ color:{GREEN}; font-size:22px; font-weight:900; }}
QLabel#heroMuted {{ color:{MUTED}; font-size:10px; }}
QLabel#pill {{ background:{CARD_ALT}; color:#8db9dc; border:1px solid #154a72; border-radius:7px; padding:5px 8px; font-size:9px; font-weight:900; }}
QLabel#statusPill {{ background:#063a32; color:{GREEN}; border:1px solid #0c735c; border-radius:7px; padding:5px 8px; font-size:9px; font-weight:900; }}
QLabel#amberPill {{ background:#2b2111; color:#f5b955; border:1px solid #74501b; border-radius:7px; padding:5px 8px; font-size:9px; font-weight:900; }}
QFrame#subcard {{ background:{CARD_ALT}; border:1px solid {BORDER}; border-radius:9px; }}
QLabel#subTitle {{ color:{TEXT}; font-size:12px; font-weight:900; }}
QLabel#fieldLabel {{ color:#81a4bc; font-size:9px; }}
QLabel#fieldValue {{ color:#edf6fb; font-size:11px; font-weight:800; }}
QPushButton#primary {{ background:{BLUE}; color:white; border:0; border-radius:7px; padding:9px 13px; font-size:10px; font-weight:900; }}
QPushButton#primary:hover {{ background:#0b83ff; }}
QPushButton#secondary {{ background:{CARD_ALT}; color:#a8c6dc; border:1px solid #154a72; border-radius:7px; padding:9px 13px; font-size:10px; font-weight:900; }}
QPushButton#secondary:hover {{ background:#0a2742; }}
QLabel#footer {{ color:#56758e; font-size:9px; }}
"""


class DashboardWindow(QMainWindow):
    """Professional OCO-only dashboard shell for the V1 workflow."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OCObot — Dashboard")
        self.resize(1500, 900)
        self.setMinimumSize(1220, 760)
        self.setStyleSheet(STYLE)
        self._stage2_window: Stage12MonitorWindow | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QWidget()
        outer.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setCentralWidget(outer)
        shell = QHBoxLayout(outer)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        sidebar = QFrame(objectName="sidebar")
        sidebar.setFixedWidth(225)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 18, 14, 14)
        side.setSpacing(6)

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

        self._nav_button(side, "Dashboard\nالرئيسية", True, self._show_dashboard)
        self._nav_button(side, "Open OCO Orders\nالأوامر المفتوحة", False, self._open_orders)
        self._nav_button(side, "Dynamic Monitoring\nالمراقبة الديناميكية", False, self._open_monitoring)
        self._nav_button(side, "Settings\nالإعدادات", False, self._show_settings_placeholder)

        side.addStretch(1)
        stage = QLabel("V1 • OCO ONLY")
        stage.setObjectName("pill")
        stage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side.addWidget(stage)
        footer = QLabel("PAPER → TESTNET → LIVE later")
        footer.setObjectName("footer")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side.addWidget(footer)
        shell.addWidget(sidebar)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)
        shell.addWidget(content, 1)

        topbar = QFrame(objectName="topbar")
        tl = QHBoxLayout(topbar)
        tl.setContentsMargins(14, 10, 14, 10)
        env = QLabel("●  TESTNET")
        env.setObjectName("env")
        tl.addWidget(env)
        binance = QLabel("Binance Spot • OCO control")
        binance.setStyleSheet(f"color:{TEXT};font-size:11px;font-weight:800;")
        tl.addWidget(binance)
        tl.addStretch(1)
        connection = QLabel("Session ready • no LIVE access")
        connection.setObjectName("connection")
        tl.addWidget(connection)
        root.addWidget(topbar)

        title_col = QVBoxLayout()
        title = QLabel("OCO Dashboard")
        title.setObjectName("pageTitle")
        title_col.addWidget(title)
        subtitle = QLabel("Control one selected OCO at a time — monitor first, mutate only after explicit activation.")
        subtitle.setObjectName("pageSubtitle")
        title_col.addWidget(subtitle)
        arabic = QLabel("لوحة التحكم • اختيار OCO واحد فقط • المراقبة والاستبدال الآمن")
        arabic.setObjectName("pageSubtitle")
        title_col.addWidget(arabic)
        root.addLayout(title_col)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        metrics.addWidget(self._metric("Selected OCO", "—"), 1)
        metrics.addWidget(self._metric("Current Price", "—"), 1)
        metrics.addWidget(self._metric("Monitoring", "OFF"), 1)
        metrics.addWidget(self._metric("Environment", "TESTNET"), 1)
        root.addLayout(metrics)

        hero = QFrame(objectName="hero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(16, 14, 16, 14)
        hero_layout.setSpacing(10)
        row = QHBoxLayout()
        left = QVBoxLayout()
        eyebrow = QLabel("SELECTED OCO")
        eyebrow.setObjectName("heroEyebrow")
        left.addWidget(eyebrow)
        hero_title = QLabel("No OCO selected")
        hero_title.setObjectName("heroTitle")
        left.addWidget(hero_title)
        muted = QLabel("Open the OCO list to select an exact orderListId. The dashboard never assumes a symbol is enough.")
        muted.setObjectName("heroMuted")
        left.addWidget(muted)
        row.addLayout(left, 1)
        badge = QLabel("READ ONLY")
        badge.setObjectName("statusPill")
        row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        hero_layout.addLayout(row)

        details = QGridLayout()
        details.setHorizontalSpacing(12)
        details.setVerticalSpacing(8)
        fields = [
            ("orderListId", "—"),
            ("Symbol", "—"),
            ("TP Sale Price", "—"),
            ("SL Trigger", "—"),
            ("SL Limit", "—"),
            ("Reference Price", "—"),
        ]
        for i, (label, value) in enumerate(fields):
            card = QFrame(objectName="subcard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(9, 7, 9, 7)
            l = QLabel(label)
            l.setObjectName("fieldLabel")
            v = QLabel(value)
            v.setObjectName("fieldValue")
            card_layout.addWidget(l)
            card_layout.addWidget(v)
            details.addWidget(card, 0, i)
        hero_layout.addLayout(details)
        root.addWidget(hero)

        lower = QHBoxLayout()
        lower.setSpacing(10)
        status_card = QFrame(objectName="subcard")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(13, 12, 13, 12)
        st = QLabel("Monitoring Status")
        st.setObjectName("subTitle")
        status_layout.addWidget(st)
        s1 = QLabel("OFF")
        s1.setObjectName("heroValue")
        status_layout.addWidget(s1)
        status_layout.addWidget(QLabel("No OCO is currently selected for monitoring.", objectName="heroMuted"))
        warning = QLabel("LIVE disabled until V1 validation is complete")
        warning.setObjectName("amberPill")
        status_layout.addWidget(warning, 0, Qt.AlignmentFlag.AlignLeft)
        lower.addWidget(status_card, 1)

        action_card = QFrame(objectName="subcard")
        action_layout = QVBoxLayout(action_card)
        action_layout.setContentsMargins(13, 12, 13, 12)
        at = QLabel("Primary Actions")
        at.setObjectName("subTitle")
        action_layout.addWidget(at)
        action_row = QHBoxLayout()
        open_btn = QPushButton("Open Active OCOs")
        open_btn.setObjectName("primary")
        open_btn.clicked.connect(self._open_orders)
        monitor_btn = QPushButton("Open Monitoring")
        monitor_btn.setObjectName("secondary")
        monitor_btn.clicked.connect(self._open_monitoring)
        action_row.addWidget(open_btn)
        action_row.addWidget(monitor_btn)
        action_layout.addLayout(action_row)
        action_layout.addWidget(QLabel("No trading/entry workflow is exposed here. This dashboard is OCO management only.", objectName="heroMuted"))
        lower.addWidget(action_card, 1)
        root.addLayout(lower)

        root.addStretch(1)
        foot = QLabel("Safety model: select exact orderListId → prepare locally → re-check → replace selected OCO only")
        foot.setObjectName("footer")
        root.addWidget(foot)

    def _nav_button(self, layout: QVBoxLayout, text: str, selected: bool, callback) -> None:
        button = QPushButton(text)
        button.setObjectName("nav")
        button.setProperty("selected", selected)
        button.clicked.connect(callback)
        layout.addWidget(button)

    @staticmethod
    def _metric(title: str, value: str) -> QFrame:
        frame = QFrame(objectName="metric")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        label = QLabel(title)
        label.setObjectName("metricLabel")
        val = QLabel(value)
        val.setObjectName("metricValue")
        layout.addWidget(label)
        layout.addWidget(val)
        return frame

    def _show_dashboard(self) -> None:
        pass

    def _open_orders(self) -> None:
        if self._stage2_window is None:
            self._stage2_window = Stage12MonitorWindow()
            self._stage2_window.destroyed.connect(self._clear_stage2_reference)
        self._stage2_window.show()
        self._stage2_window.raise_()
        self._stage2_window.activateWindow()

    def _open_monitoring(self) -> None:
        self._open_orders()

    def _show_settings_placeholder(self) -> None:
        # Settings remains intentionally read-only until the safety/configuration phase.
        pass

    def _clear_stage2_reference(self) -> None:
        self._stage2_window = None

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._stage2_window is not None:
            self._stage2_window.close()
            self._stage2_window = None
        super().closeEvent(event)


def main() -> None:
    app = QApplication.instance() or QApplication([])
    window = DashboardWindow()
    window.show()
    app.exec()


MainWindow = DashboardWindow
