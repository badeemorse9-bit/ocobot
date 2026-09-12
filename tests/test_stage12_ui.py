from PySide6.QtWidgets import QApplication

from ocobot.ui.stage12_window import Stage12Window


def test_stage12_window_builds_approved_read_only_oco_screen() -> None:
    app = QApplication.instance() or QApplication([])
    window = Stage12Window()

    assert window.orders_table.columnCount() == 8
    assert window.orders_table.rowCount() == 2
    assert window.read_only.text() == "Read Only"
    assert window.total_value.text() == "2"
    assert window.orders_table.item(0, 5).text() == "0.02350000"
    assert window.orders_table.item(0, 6).text() == "0.02281000"
    assert window.orders_table.item(0, 7).text() == "0.02280000"

    # Verify the same selection path used by a user clicking an OCO row.
    window.orders_table.setCurrentCell(0, 0)
    window.orders_table.selectRow(0)
    app.processEvents()
    window._select_row()

    assert window.selected is not None
    assert window.selected.order_list_id == 7964
    assert window.detail_symbol.text() == "TUTUSDT"
    assert window.detail_status.text() == "EXECUTING"
    assert window.selected_pill.text() == "orderListId: 7964"
    assert window.feed is not None

    # The three OCO prices must remain explicitly distinguishable.
    tp_texts = [w.text() for w in window._leg_row.itemAt(0).widget().findChildren(type(window.detail_symbol))]
    sl_texts = [w.text() for w in window._leg_row.itemAt(1).widget().findChildren(type(window.detail_symbol))]
    assert any("Sale Price / سعر البيع" in text for text in tp_texts)
    assert any("Trigger Stop Price / سعر تفعيل الاستوب" in text for text in sl_texts)
    assert any("Limit Price After Trigger / سعر الحد بعد التفعيل" in text for text in sl_texts)

    window.close()
    app.processEvents()
