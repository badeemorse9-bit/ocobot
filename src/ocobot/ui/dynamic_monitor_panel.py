from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ocobot.application.dynamic_monitor import (
    DynamicMonitorSettings,
    calculate_reposition_levels,
)


CARD = "#061529"
CARD_ALT = "#081d32"
BORDER = "#0d2a43"
TEXT = "#f0f7fb"
MUTED = "#6f8ba2"
BLUE = "#0876e8"
GREEN = "#19c58b"
RED = "#ff4b68"

STYLE = f"""
QFrame#monitorPanel {{ background:{CARD}; border:1px solid {BORDER}; border-radius:9px; }}
QLabel#sectionTitle {{ color:{TEXT}; font-size:14px; font-weight:800; }}
QLabel#sectionSubtitle {{ color:#86a5ba; font-size:10px; }}
QLabel#fieldLabel {{ color:#9bb6c8; font-size:9px; font-weight:700; }}
QLineEdit#percentInput {{ background:{CARD_ALT}; color:{TEXT}; border:1px solid #154a72; border-radius:6px; padding:5px 8px; font-size:11px; font-weight:800; min-height:28px; selection-background-color:#0a4e78; selection-color:#ffffff; }}
QLineEdit#percentInput:focus {{ border:1px solid {BLUE}; }}
QPushButton#monitorAction {{ background:{BLUE}; color:#ffffff; border:0; border-radius:7px; padding:6px 11px; min-height:27px; font-size:9px; font-weight:800; }}
QPushButton#monitorStop {{ background:#2a1420; color:#ff8ca0; border:1px solid {RED}; border-radius:7px; padding:6px 11px; min-height:27px; font-size:9px; font-weight:800; }}
QLabel#state {{ color:{MUTED}; font-size:9px; font-weight:800; }}
QFrame#derived {{ background:#041a25; border:1px solid #0d4254; border-radius:7px; }}
QLabel#derivedLabel {{ color:#8caabd; font-size:8px; font-weight:700; }}
QLabel#derivedValueTP {{ color:{GREEN}; font-size:11px; font-weight:800; }}
QLabel#derivedValueSL {{ color:#ff8ca0; font-size:11px; font-weight:800; }}
QLabel#formulaNote {{ color:#91aec0; font-size:8px; }}
"""


class DynamicMonitorPanel(QFrame):
    """UI-only configuration panel for the new three-percentage monitor strategy."""

    monitoring_requested = Signal(object)
    monitoring_stopped = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("monitorPanel")
        self.setMinimumHeight(188)
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())
        self.setStyleSheet(STYLE)
        self._build_ui()
        self.set_enabled(False)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 9, 10, 9)
        root.setSpacing(7)

        title_row = QHBoxLayout()
        title_row.setSpacing(7)
        title = QLabel("Dynamic Trade Monitoring")
        title.setObjectName("sectionTitle")
        title_row.addWidget(title)
        subtitle = QLabel("المراقبة الديناميكية للصفقة")
        subtitle.setObjectName("sectionSubtitle")
        title_row.addWidget(subtitle)
        title_row.addStretch(1)
        self.state_label = QLabel("Select an OCO first")
        self.state_label.setObjectName("state")
        title_row.addWidget(self.state_label)
        root.addLayout(title_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(2)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        self.trigger_input = self._field(grid, 0, 0, "Reposition Trigger Rise %", "1.00")
        self.tp_input = self._field(grid, 0, 1, "TP Distance Above Current %", "4.00")
        self.sl_input = self._field(grid, 0, 2, "SL Distance Below Current %", "2.00")
        root.addLayout(grid)

        actions = QHBoxLayout()
        actions.setSpacing(7)
        self.start_button = QPushButton("Start Dynamic Monitoring")
        self.start_button.setObjectName("monitorAction")
        self.start_button.clicked.connect(self._request_start)
        actions.addWidget(self.start_button)
        self.stop_button = QPushButton("Stop Monitoring")
        self.stop_button.setObjectName("monitorStop")
        self.stop_button.clicked.connect(self._request_stop)
        actions.addWidget(self.stop_button)
        actions.addStretch(1)
        root.addLayout(actions)

        derived = QFrame(objectName="derived")
        derived_grid = QGridLayout(derived)
        derived_grid.setContentsMargins(8, 5, 8, 5)
        derived_grid.setHorizontalSpacing(8)
        for col in range(4):
            derived_grid.setColumnStretch(col, 1)
        self.live_value = self._derived(derived_grid, 0, 0, "Live Price", "—", "tp")
        self.tp_value = self._derived(derived_grid, 0, 1, "Calculated TP Sale", "—", "tp")
        self.sl_trigger_value = self._derived(derived_grid, 0, 2, "Calculated SL Trigger", "—", "sl")
        self.sl_limit_value = self._derived(derived_grid, 0, 3, "Calculated SL Limit", "—", "sl")
        root.addWidget(derived)

        note = QLabel(
            "SL Limit is derived automatically from SL Trigger using the internal 1 tickSize gap. "
            "The user enters only one SL percentage."
        )
        note.setObjectName("formulaNote")
        note.setWordWrap(True)
        root.addWidget(note)

    @staticmethod
    def _field(grid: QGridLayout, row: int, col: int, label: str, value: str) -> QLineEdit:
        box = QVBoxLayout()
        box.setSpacing(2)
        label_widget = QLabel(label)
        label_widget.setObjectName("fieldLabel")
        edit = QLineEdit(value)
        edit.setObjectName("percentInput")
        edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        edit.setPlaceholderText("0.00")
        edit.setMinimumHeight(31)
        box.addWidget(label_widget)
        box.addWidget(edit)
        grid.addLayout(box, row, col)
        return edit

    @staticmethod
    def _derived(grid: QGridLayout, row: int, col: int, label: str, value: str, kind: str) -> QLabel:
        box = QVBoxLayout()
        box.setSpacing(2)
        label_widget = QLabel(label)
        label_widget.setObjectName("derivedLabel")
        value_widget = QLabel(value)
        value_widget.setObjectName("derivedValueTP" if kind == "tp" else "derivedValueSL")
        box.addWidget(label_widget)
        box.addWidget(value_widget)
        grid.addLayout(box, row, col)
        return value_widget

    def set_enabled(self, enabled: bool, reason: str = "Select an OCO first") -> None:
        for widget in (self.trigger_input, self.tp_input, self.sl_input, self.start_button):
            widget.setEnabled(enabled)
        self.stop_button.setEnabled(False)
        self.state_label.setText("Ready" if enabled else reason)

    def set_live_price(self, live_price: Decimal, tick_size: Decimal) -> None:
        self.live_value.setText(f"{live_price:f}")
        try:
            settings = DynamicMonitorSettings.from_values(
                self.trigger_input.text(), self.tp_input.text(), self.sl_input.text()
            )
            levels = calculate_reposition_levels(live_price, settings, tick_size)
        except (InvalidOperation, ValueError):
            self.tp_value.setText("—")
            self.sl_trigger_value.setText("—")
            self.sl_limit_value.setText("—")
            return
        self.tp_value.setText(f"{levels.tp_sale_price:f}")
        self.sl_trigger_value.setText(f"{levels.sl_trigger_price:f}")
        self.sl_limit_value.setText(f"{levels.sl_limit_price:f}")

    def set_monitoring_state(self, monitoring: bool, message: str | None = None) -> None:
        self.start_button.setEnabled(not monitoring and self.trigger_input.isEnabled())
        self.stop_button.setEnabled(monitoring)
        self.state_label.setText(message or ("Monitoring Active" if monitoring else "Ready"))

    def _request_start(self) -> None:
        try:
            settings = DynamicMonitorSettings.from_values(
                self.trigger_input.text(), self.tp_input.text(), self.sl_input.text()
            )
        except (InvalidOperation, ValueError) as exc:
            self.state_label.setText(str(exc))
            return
        self.monitoring_requested.emit(settings)

    def _request_stop(self) -> None:
        self.monitoring_stopped.emit()
