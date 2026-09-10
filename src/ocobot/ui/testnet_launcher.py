from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ocobot.ui.dashboard_window import DashboardWindow
from ocobot.ui.testnet_app import TestnetTradeSetup


def run_app() -> None:
    app = QApplication(sys.argv)
    window = DashboardWindow()
    setup = TestnetTradeSetup(window)
    window.attach_testnet_setup(setup)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
