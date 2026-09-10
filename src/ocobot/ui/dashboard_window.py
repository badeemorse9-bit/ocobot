from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

import ocobot.ui.main_window as _base


class _SafeQFrame(QFrame):
    """Compatibility shim for Qt property-style construction used by the dashboard."""

    def __init__(self, *args, objectName: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if objectName:
            self.setObjectName(objectName)


# main_window.py is kept as the canonical implementation; this shim only
# makes its QWidget construction compatible across PySide6 builds.
_base.QFrame = _SafeQFrame


class DashboardWindow(_base.MainWindow):
    """Dashboard entry point with explicit Paper/Testnet/API controls."""

    def __init__(self) -> None:
        super().__init__()
        self._install_mode_controls()

    def _install_mode_controls(self) -> None:
        outer = self.centralWidget()
        if outer is None or outer.layout() is None:
            return
        sidebar = outer.layout().itemAt(0).widget()
        if sidebar is None or sidebar.layout() is None:
            return

        mode_widget = QWidget()
        mode_layout = QVBoxLayout(mode_widget)
        mode_layout.setContentsMargins(0, 8, 0, 0)
        mode_layout.setSpacing(5)
        self.paper_mode_button = QPushButton("ورقي")
        self.testnet_mode_button = QPushButton("TESTNET")
        self.api_mode_button = QPushButton("إعداد API")
        self.paper_mode_button.clicked.connect(lambda: self._switch_mode("PAPER"))
        self.testnet_mode_button.clicked.connect(lambda: self._switch_mode("TESTNET"))
        self.api_mode_button.clicked.connect(self._open_credentials)
        for button in (self.paper_mode_button, self.testnet_mode_button, self.api_mode_button):
            button.setMinimumHeight(34)
        mode_layout.addWidget(self.paper_mode_button)
        mode_layout.addWidget(self.testnet_mode_button)
        mode_layout.addWidget(self.api_mode_button)
        sidebar.layout().insertWidget(3, mode_widget)
        self._update_mode_buttons()

    def _set_mode_visuals(self) -> None:
        super()._set_mode_visuals()
        if hasattr(self, "paper_mode_button"):
            self._update_mode_buttons()

    def _update_mode_buttons(self) -> None:
        active = self.mode
        self.paper_mode_button.setEnabled(active != "PAPER")
        self.testnet_mode_button.setEnabled(active != "TESTNET")


MainWindow = DashboardWindow
