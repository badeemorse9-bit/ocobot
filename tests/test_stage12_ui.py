from PySide6.QtWidgets import QApplication

from ocobot.ui.stage12_window import Stage12Window


def test_stage12_window_builds_read_only_oco_section() -> None:
    app = QApplication.instance() or QApplication([])
    window = Stage12Window()
    assert window.orders_table.columnCount() == 6
    assert window.orders_table.rowCount() == 4

    # Verify the same selection path used by a user clicking the first row.
    window.orders_table.setCurrentCell(0, 0)
    window.orders_table.selectRow(0)
    app.processEvents()
    window._select_row()

    assert window.selected is not None
    assert window.selected.order_list_id == 1003
    assert window.detail_id.text() == "1003"
    assert window.detail_symbol.text() == "FIDAUSDT"
    assert window.feed is not None
    window.close()
    app.processEvents()
