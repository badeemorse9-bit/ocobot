from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from typing import Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ocobot.application.auto_trail import AutoTrailEngine, AutoTrailSettings
from ocobot.application.services import OCOEditorService
from ocobot.domain.validation import highest_sell_stop_candidate
from ocobot.providers.base import OCOProvider
from ocobot.providers.binance import BinanceOCOProvider
from ocobot.providers.paper import PaperOCOProvider
from ocobot.providers.sample_data import sample_ocos

APP_STYLE = """
QMainWindow, QWidget { background:#f3f5f7; color:#17212b; }
QGroupBox { background:#fff; border:1px solid #d5dce3; border-radius:8px; margin-top:10px; padding:7px; font-weight:700; }
QGroupBox::title { subcontrol-origin:margin; left:9px; padding:0 5px; color:#24313d; }
QLineEdit { background:#fff; border:1px solid #c7d0d9; border-radius:5px; padding:5px 7px; }
QLineEdit:focus { border:1px solid #4b8bd1; }
QPushButton { background:#eef1f4; border:1px solid #c7d0d9; border-radius:5px; padding:6px 9px; font-weight:700; }
QPushButton:hover { background:#e5e9ed; }
QPushButton:disabled { color:#9aa5af; background:#eef0f2; }
QPushButton#primary { background:#1f6feb; color:#fff; border:0; }
QPushButton#danger { background:#fff1ef; color:#a33a2c; border:1px solid #e3b5ad; }
QPushButton#on { background:#1f6feb; color:#fff; border:0; }
QPushButton#modeOff { background:#e8ecef; color:#707c87; }
QPushButton#modeTest { background:#eef5ff; color:#175da9; border:1px solid #bdd4ef; }
QTableWidget { background:#fff; border:1px solid #d5dce3; gridline-color:#e9edf0; selection-background-color:#dcecff; }
QHeaderView::section { background:#eef2f5; color:#34414e; padding:5px; border:0; border-bottom:1px solid #d5dce3; font-weight:700; }
QCheckBox { spacing:5px; }
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
        self.setMinimumWidth(460)
        root = QVBoxLayout(self)
        root.addWidget(QLabel("مفاتيح Testnet تحفظ في الذاكرة لهذه الجلسة فقط."))
        form = QGridLayout()
        self.api_key_edit = QLineEdit(api_key)
        self.secret_edit = QLineEdit(api_secret)
        self.secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addWidget(QLabel("API Key"), 0, 0); form.addWidget(self.api_key_edit, 0, 1)
        form.addWidget(QLabel("API Secret"), 1, 0); form.addWidget(self.secret_edit, 1, 1)
        root.addLayout(form)
        note = QLabel("TESTNET فقط — التداول الحقيقي غير متاح في V1.")
        note.setStyleSheet("color:#7c5a08;font-weight:700;"); root.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)

    @property
    def api_key(self) -> str: return self.api_key_edit.text().strip()
    @property
    def api_secret(self) -> str: return self.secret_edit.text().strip()


class MainWindow(QMainWindow):
    """Compact Arabic dashboard; selected-price updates come from WebSocket, not polling."""
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OCObot — محرر OCO الآمن V1")
        self.resize(1280, 720); self.setMinimumSize(1050, 650); self.setStyleSheet(APP_STYLE)
        self.mode="PAPER"; self.testnet_api_key=os.getenv("BINANCE_API_KEY",""); self.testnet_api_secret=os.getenv("BINANCE_API_SECRET","")
        self.provider:OCOProvider=self._new_paper_provider(); self.service=OCOEditorService(self.provider); self.unsubscribe:Callable[[],None]|None=None; self._tick_cache:dict[str,Decimal]={}
        self._price_bridge=PriceBridge(self); self._price_bridge.price.connect(self._on_price); self._worker_bridge=WorkerBridge(self); self._worker_bridge.finished.connect(self._worker_finished); self._workers=ThreadPoolExecutor(max_workers=2,thread_name_prefix="ocobot-ui")
        self.trail:AutoTrailEngine|None=None; self._building_table=False
        self._build_ui(); self._refresh_orders(False); self._set_mode_visuals(); self.statusBar().showMessage("وضع الورق جاهز — اختر OCO واحدًا للبدء")

    @staticmethod
    def _new_paper_provider()->PaperOCOProvider:
        orders=[o for o in sample_ocos() if o.symbol!="TUTUSDT"]
        return PaperOCOProvider(orders,{"FIDAUSDT":Decimal("0.078210")},{"FIDAUSDT":Decimal("0.000001")})

    def _build_ui(self)->None:
        root=QVBoxLayout(); root.setContentsMargins(10,7,10,8); root.setSpacing(6); central=QWidget(); central.setLayout(root); self.setCentralWidget(central)
        header=QHBoxLayout(); brand=QLabel("OCObot"); brand.setFont(QFont("Segoe UI",22,QFont.Weight.Bold)); sub=QLabel("محرر OCO الآمن • V1"); sub.setStyleSheet("color:#687581;font-size:13px;"); header.addWidget(brand); header.addWidget(sub); header.addStretch()
        self.paper_mode_btn=QPushButton("ورقي"); self.testnet_mode_btn=QPushButton("TESTNET"); self.api_button=QPushButton("إعداد API")
        for b in (self.paper_mode_btn,self.testnet_mode_btn): b.setMinimumWidth(84)
        self.paper_mode_btn.clicked.connect(lambda:self._switch_mode("PAPER")); self.testnet_mode_btn.clicked.connect(lambda:self._switch_mode("TESTNET")); self.api_button.clicked.connect(self._open_credentials)
        header.addWidget(self.paper_mode_btn); header.addWidget(self.testnet_mode_btn); header.addWidget(self.api_button); self.connection=QLabel(); self.connection.setStyleSheet("font-weight:700;margin-left:5px;"); header.addWidget(self.connection); root.addLayout(header)
        safety=QFrame(); safety.setStyleSheet("QFrame{background:#fff8e8;border:1px solid #efd79a;border-radius:6px;}"); sr=QHBoxLayout(safety); sr.setContentsMargins(8,4,8,4); lock=QLabel("OCO المحدد:"); lock.setStyleSheet("font-weight:800;color:#7c5a08;"); sr.addWidget(lock); self.target_label=QLabel("لا يوجد طلب محدد"); self.target_label.setStyleSheet("color:#5e4a16;"); sr.addWidget(self.target_label,1); sr.addWidget(QLabel("التعديل محلي حتى التفعيل")); root.addWidget(safety)
        grid=QGridLayout(); grid.setHorizontalSpacing(8); grid.setVerticalSpacing(6); grid.setColumnStretch(0,1); grid.setColumnStretch(1,1); root.addLayout(grid)
        orders=QGroupBox("الأوامر المفتوحة"); ol=QVBoxLayout(orders); ol.setContentsMargins(6,6,6,6); ol.setSpacing(4); top=QHBoxLayout(); t=QLabel("اختر OCO واحدًا فقط"); t.setStyleSheet("font-weight:800;"); top.addWidget(t); top.addStretch(); self.refresh_btn=QPushButton("تحديث"); self.refresh_btn.clicked.connect(lambda:self._refresh_orders(True)); top.addWidget(self.refresh_btn); ol.addLayout(top)
        self.orders=QTableWidget(0,6); self.orders.setHorizontalHeaderLabels(["List ID","العملة","الكمية","البيع","الاستوب","الحالة"]); self.orders.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows); self.orders.setSelectionMode(QTableWidget.SelectionMode.SingleSelection); self.orders.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); self.orders.verticalHeader().setVisible(False); self.orders.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); self.orders.itemSelectionChanged.connect(self._select_current); self.orders.setMinimumHeight(205); self.orders.setMaximumHeight(230); ol.addWidget(self.orders); grid.addWidget(orders,0,0)
        selected=QGroupBox("الطلب المحدد — حي"); sl=QGridLayout(selected); sl.setContentsMargins(8,7,8,7); sl.setHorizontalSpacing(7); sl.setVerticalSpacing(5)
        for r,(caption,attr) in enumerate([("العملة","monitor_symbol"),("السعر الآن","live_price"),("أعلى Stop صالح","max_stop"),("Tick","tick_size"),("حالة OCO","original_status")]):
            lab=QLabel(caption); val=QLabel("—"); val.setStyleSheet("background:#f3f5f7;padding:4px 6px;border-radius:3px;font-weight:700;"); setattr(self,attr,val); sl.addWidget(lab,r,0); sl.addWidget(val,r,1)
        sl.setColumnStretch(1,1); grid.addWidget(selected,0,1)
        trail=QGroupBox("تتبع الصعود التلقائي"); tl=QGridLayout(trail); tl.setContentsMargins(8,7,8,7); tl.setHorizontalSpacing(7); tl.setVerticalSpacing(5); self.trigger_edit=QLineEdit("1.00"); self.tp_move_edit=QLineEdit("1.00"); self.sl_move_edit=QLineEdit("0.50")
        for e in (self.trigger_edit,self.tp_move_edit,self.sl_move_edit): e.setMaximumWidth(115)
        tl.addWidget(QLabel("التفعيل بعد صعود %"),0,0); tl.addWidget(self.trigger_edit,0,1); tl.addWidget(QLabel("تحريك البيع %"),0,2); tl.addWidget(self.tp_move_edit,0,3); tl.addWidget(QLabel("تحريك الاستوب %"),0,4); tl.addWidget(self.sl_move_edit,0,5); self.trail_enable=QPushButton("تشغيل التتبع"); self.trail_enable.clicked.connect(self._toggle_trail); tl.addWidget(self.trail_enable,1,0,1,2); self.trail_state=QLabel("متوقف"); self.trail_state.setStyleSheet("font-weight:800;"); tl.addWidget(self.trail_state,1,2,1,4); self.anchor_label=QLabel("مرجع: —    التالي: —    حي: —"); tl.addWidget(self.anchor_label,2,0,1,6); grid.addWidget(trail,1,0,1,2)
        editor=QGroupBox("تعديل سريع للـ OCO"); el=QGridLayout(editor); el.setContentsMargins(8,7,8,7); el.setHorizontalSpacing(7); el.setVerticalSpacing(5); self.tp_edit=QLineEdit(); self.sl_edit=QLineEdit(); self.qty_edit=QLineEdit(); self.qty_edit.setReadOnly(True); el.addWidget(QLabel("سعر البيع"),0,0); el.addWidget(self.tp_edit,0,1); el.addWidget(QLabel("الكمية الأصلية"),0,2); el.addWidget(self.qty_edit,0,3); stoprow=QHBoxLayout(); stoprow.addWidget(self.sl_edit,1); self.max_stop_btn=QPushButton("MAX STOP"); self.max_stop_btn.clicked.connect(self._apply_max_stop); stoprow.addWidget(self.max_stop_btn); el.addWidget(QLabel("الاستوب"),1,0); el.addLayout(stoprow,1,1); self.activate_btn=QPushButton("تفعيل الاستبدال"); self.activate_btn.setObjectName("primary"); self.activate_btn.clicked.connect(self._activate); el.addWidget(self.activate_btn,1,2,1,2); self.state_label=QLabel("لا يوجد طلب محدد"); self.state_label.setStyleSheet("font-weight:700;"); el.addWidget(self.state_label,2,0,1,4); grid.addWidget(editor,2,0)
        activity=QGroupBox("آخر الأحداث"); al=QVBoxLayout(activity); al.setContentsMargins(6,6,6,6); self.event_log=QTableWidget(0,2); self.event_log.setHorizontalHeaderLabels(["الحدث","التفاصيل"]); self.event_log.verticalHeader().setVisible(False); self.event_log.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); self.event_log.setMinimumHeight(110); self.event_log.setMaximumHeight(135); al.addWidget(self.event_log); grid.addWidget(activity,2,1)
        self.demo_box=QGroupBox("محاكي الورق"); dl=QGridLayout(self.demo_box); dl.setContentsMargins(8,7,8,7); dl.setHorizontalSpacing(6); dl.setVerticalSpacing(4); self.price_input=QLineEdit("0.078210"); self.move_price_btn=QPushButton("تحريك السعر"); self.move_price_btn.clicked.connect(self._move_price); self.tp_hit_btn=QPushButton("ضرب البيع"); self.tp_hit_btn.clicked.connect(lambda:self._force_execute("TP")); self.sl_hit_btn=QPushButton("ضرب الاستوب"); self.sl_hit_btn.clicked.connect(lambda:self._force_execute("SL")); self.reset_btn=QPushButton("إعادة العرض"); self.reset_btn.setObjectName("danger"); self.reset_btn.clicked.connect(self._reset_demo); self.fail_place=QCheckBox("فشل الإنشاء"); self.fail_cancel=QCheckBox("فشل الإلغاء"); self.fail_place.stateChanged.connect(self._toggle_fail_place); self.fail_cancel.stateChanged.connect(self._toggle_fail_cancel); dl.addWidget(QLabel("السعر المحاكى"),0,0); dl.addWidget(self.price_input,0,1); dl.addWidget(self.move_price_btn,0,2); dl.addWidget(self.tp_hit_btn,0,3); dl.addWidget(self.sl_hit_btn,0,4); dl.addWidget(self.reset_btn,0,5); dl.addWidget(self.fail_place,1,0); dl.addWidget(self.fail_cancel,1,1); root.addWidget(self.demo_box)

    def _set_mode_visuals(self)->None:
        if self.mode=="PAPER": self.paper_mode_btn.setObjectName("on"); self.testnet_mode_btn.setObjectName("modeTest"); self.connection.setText("● ورقي — بدون Binance"); self.connection.setStyleSheet("color:#286b43;font-weight:700;")
        else: self.paper_mode_btn.setObjectName("modeOff"); self.testnet_mode_btn.setObjectName("on"); self.connection.setText("● TESTNET — Binance"); self.connection.setStyleSheet("color:#1557a6;font-weight:700;")
        for b in (self.paper_mode_btn,self.testnet_mode_btn): b.style().unpolish(b); b.style().polish(b)

    def _open_credentials(self)->None:
        d=TestnetCredentialsDialog(self,self.testnet_api_key,self.testnet_api_secret)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        if not d.api_key or not d.api_secret:QMessageBox.warning(self,"API","أدخل المفتاحين.");return
        self.testnet_api_key=d.api_key;self.testnet_api_secret=d.api_secret
        if self.mode=="TESTNET":self._switch_mode("PAPER");self._switch_mode("TESTNET")

    def _switch_mode(self,mode:str)->None:
        if mode==self.mode:
            if mode=="TESTNET":self._refresh_orders(False)
            return
        self._stop_price_subscription();self._disable_trail()
        if mode=="TESTNET":
            if not self.testnet_api_key or not self.testnet_api_secret:self._open_credentials()
            if not self.testnet_api_key or not self.testnet_api_secret:return
            try:provider=BinanceOCOProvider(mode="TESTNET",api_key=self.testnet_api_key,api_secret=self.testnet_api_secret);provider.list_open_ocos()
            except Exception as exc:QMessageBox.warning(self,"TESTNET",f"تعذر الاتصال:\n{exc}");return
            old=self.provider;self.provider=provider;self.service=OCOEditorService(provider);self._tick_cache.clear();self._clear_selection_ui();self._set_paper_controls_enabled(False);self._set_mode_visuals();self._refresh_orders(False);getattr(old,"close",lambda:None)()
        else:
            old=self.provider;self.provider=self._new_paper_provider();self.service=OCOEditorService(self.provider);self._tick_cache.clear();self._clear_selection_ui();self.mode="PAPER";self._set_paper_controls_enabled(True);self._set_mode_visuals();self._refresh_orders(False);getattr(old,"close",lambda:None)()

    def _refresh_orders(self,preserve_selection:bool=True)->None:
        selected=self.service.selection.order_list_id if preserve_selection and self.service.selection else None
        try:orders=self.service.refresh_open_orders()
        except Exception as exc:
            if self.mode=="TESTNET":self.statusBar().showMessage(f"خطأ قراءة الأوامر: {exc}")
            return
        self._building_table=True
        try:
            self.orders.setRowCount(len(orders));row_to_select=-1
            for r,o in enumerate(orders):
                upper=next((leg.price for leg in o.legs if leg.price is not None and leg.stop_price is None),None);stop=next((leg.stop_price for leg in o.legs if leg.stop_price is not None),None);qty=o.legs[0].quantity if o.legs else Decimal("0");vals=[str(o.order_list_id),o.symbol,str(qty),str(upper or ""),str(stop or ""),o.status.value]
                for c,v in enumerate(vals):self.orders.setItem(r,c,QTableWidgetItem(v))
                if selected is not None and o.order_list_id==selected:row_to_select=r
            if row_to_select>=0:self.orders.selectRow(row_to_select)
        finally:self._building_table=False

    def _select_current(self)->None:
        if self._building_table:return
        rows=self.orders.selectionModel().selectedRows()
        if not rows:return
        try:oid=int(self.orders.item(rows[0].row(),0).text())
        except Exception:return
        try:draft=self.service.select(oid)
        except Exception as exc:QMessageBox.warning(self,"اختيار",str(exc));return
        self._stop_price_subscription();self._disable_trail();self.tp_edit.setText(str(draft.values.get("abovePrice") or draft.values.get("leg1.price") or ""));self.sl_edit.setText(str(draft.values.get("belowStopPrice") or draft.values.get("leg2.stopPrice") or ""));self.qty_edit.setText(str(draft.values.get("quantity") or draft.values.get("leg1.quantity") or ""));self.monitor_symbol.setText(draft.selection.symbol);self.original_status.setText(str(draft.values.get("listOrderStatus") or "EXECUTING"));self.target_label.setText(f"{draft.selection.symbol} • OCO {oid} • الطلب الأصلي ما زال فعالًا");self.state_label.setText("مسودة محلية — الأصل لم يتغير");self._log("اختيار",f"تم تحديد OCO {oid}")
        try:self._tick_cache[draft.selection.symbol]=self.provider.get_tick_size(draft.selection.symbol)
        except Exception:self._tick_cache.pop(draft.selection.symbol,None)
        self.unsubscribe=self.provider.subscribe_price(draft.selection.symbol,self._price_bridge.push);self.statusBar().showMessage(f"مراقبة لحظية: {draft.selection.symbol}")

    def _stop_price_subscription(self)->None:
        if self.unsubscribe:
            try:self.unsubscribe()
            except Exception:pass
            self.unsubscribe=None

    def _on_price(self,price:Decimal)->None:
        self.live_price.setText(f"{price:f}  • حي");symbol=self.monitor_symbol.text()
        if not symbol or symbol=="—":return
        tick=self._tick_cache.get(symbol)
        if tick is None:
            try:tick=self.provider.get_tick_size(symbol);self._tick_cache[symbol]=tick
            except Exception:tick=None
        if tick is not None:self.tick_size.setText(f"{tick:f}");self.max_stop.setText(f"{highest_sell_stop_candidate(price,tick):f}")
        if self.trail and self.trail.snapshot().enabled and self.trail.snapshot().latest_price != price:self.anchor_label.setText(f"مرجع: {self.trail.snapshot().anchor_price or '—'}    التالي: {self.trail.snapshot().next_trigger or '—'}    حي: {price}")

    def _apply_max_stop(self)->None:
        if not self.service.selection:QMessageBox.information(self,"MAX STOP","اختر OCO أولًا.");return
        try:c=self.service.arm_max_stop();self.sl_edit.setText(f"{c:f}");self._log("MAX STOP",f"تم ضبط الاستوب {c}");self.state_label.setText("MAX STOP جاهز — يعاد تحديثه لحظة التفعيل")
        except Exception as exc:QMessageBox.warning(self,"MAX STOP",str(exc))

    def _toggle_trail(self)->None:
        if self.trail and self.trail.snapshot().enabled:self._disable_trail();self._resubscribe_selected();return
        if not self.service.original or not self.service.selection:QMessageBox.information(self,"التتبع","اختر OCO أولًا.");return
        try:
            settings=AutoTrailSettings.parse(self.trigger_edit.text(),self.tp_move_edit.text(),self.sl_move_edit.text());live=self.provider.get_last_price(self.service.selection.symbol);self._stop_price_subscription();self._disable_trail();self.trail=AutoTrailEngine(self.provider,self._trail_event,self._trail_finished,self._price_bridge.push);self.trail.enable(self.service.original,settings,live);self.trail_state.setText("● يعمل — السعر اللحظي مباشر");self.trail_enable.setText("إيقاف التتبع");self._on_price(live)
        except Exception as exc:QMessageBox.warning(self,"التتبع",str(exc))

    def _disable_trail(self)->None:
        if self.trail:
            try:self.trail.close()
            except Exception:pass
        self.trail=None;self.trail_state.setText("متوقف");self.trail_enable.setText("تشغيل التتبع");self.anchor_label.setText("مرجع: —    التالي: —    حي: —")

    def _resubscribe_selected(self)->None:
        if not self.service.selection:return
        self._stop_price_subscription();self.unsubscribe=self.provider.subscribe_price(self.service.selection.symbol,self._price_bridge.push)

    def _trail_event(self,kind:str,details:str)->None:self._worker_bridge.finished.emit(("event",kind,details))
    def _trail_finished(self,ok:bool,message:str,result:dict|None)->None:self._worker_bridge.finished.emit(("trail_done",ok,message,result))

    def _worker_finished(self,payload:object)->None:
        if not isinstance(payload,tuple) or not payload:return
        kind=payload[0]
        if kind=="event":self._log(str(payload[1]),str(payload[2]));return
        if kind=="trail_done":
            _,ok,message,result=payload
            if ok:
                self._log("نجاح",message);self._refresh_orders(False);new_id=result.get("orderListId") if isinstance(result,dict) else None
                if new_id:
                    try:draft=self.service.select(int(new_id));self.tp_edit.setText(str(draft.values.get("abovePrice") or draft.values.get("leg1.price") or ""));self.sl_edit.setText(str(draft.values.get("belowStopPrice") or draft.values.get("leg2.stopPrice") or ""));self.qty_edit.setText(str(draft.values.get("quantity") or draft.values.get("leg1.quantity") or ""));self._tick_cache[draft.selection.symbol]=self.provider.get_tick_size(draft.selection.symbol)
                    except Exception:pass
            else:self.trail_state.setText("متوقف — يحتاج مراجعة");self._log("توقف",message);QMessageBox.critical(self,"التتبع توقف",message)
            return
        if kind=="activate_done":self._finish_activation(payload[1])

    def _activate(self)->None:
        if not self.service.selection:QMessageBox.information(self,"تفعيل","اختر OCO أولًا.");return
        for key,edit in (("abovePrice",self.tp_edit),("belowStopPrice",self.sl_edit)):
            text=edit.text().strip()
            if not text:QMessageBox.warning(self,"مسودة",f"أدخل {key}.");return
            try:Decimal(text)
            except InvalidOperation:QMessageBox.warning(self,"مسودة",f"رقم غير صالح: {key}");return
            if not(key=="belowStopPrice" and self.service.max_stop_dynamic):self.service.set_draft_field(key,text)
        oid=self.service.selection.order_list_id
        if self.mode=="TESTNET" and QMessageBox.question(self,"تأكيد",f"استبدال OCO رقم {oid} على Testnet؟\nالقديم سيُلغى والجديد سيُنشأ.",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        self._log("تفعيل",f"بدء استبدال OCO {oid}");self.activate_btn.setEnabled(False);self.trail_enable.setEnabled(False);f=self._workers.submit(self.service.activate);f.add_done_callback(lambda fut:self._worker_bridge.finished.emit(("activate_done",fut.result())))

    def _finish_activation(self,result)->None:
        self.activate_btn.setEnabled(True);self.trail_enable.setEnabled(True);self.state_label.setText(f"{result.state.value} — {result.message}")
        if result.state.value=="SUCCESS":self._log("نجاح",result.message);self._refresh_orders(False);QMessageBox.information(self,"تم",result.message)
        else:self._log(result.state.value,result.message);(QMessageBox.critical(self,"التفعيل",result.message) if result.state.value=="FAILED_NEEDS_ATTENTION" else QMessageBox.warning(self,"التفعيل",result.message))

    def _clear_selection_ui(self)->None:
        self._stop_price_subscription();self._disable_trail();self.orders.clearSelection();self.monitor_symbol.setText("—");self.live_price.setText("—");self.max_stop.setText("—");self.tick_size.setText("—");self.original_status.setText("—");self.target_label.setText("لا يوجد طلب محدد");self.tp_edit.clear();self.sl_edit.clear();self.qty_edit.clear();self.state_label.setText("لا يوجد طلب محدد")

    def _set_paper_controls_enabled(self,enabled:bool)->None:
        for w in (self.demo_box,self.price_input,self.move_price_btn,self.tp_hit_btn,self.sl_hit_btn,self.reset_btn,self.fail_place,self.fail_cancel):w.setEnabled(enabled)

    def _move_price(self)->None:
        if self.mode!="PAPER" or not isinstance(self.provider,PaperOCOProvider) or not self.service.selection:return
        try:p=Decimal(self.price_input.text().strip());assert p>0
        except Exception:QMessageBox.warning(self,"المحاكي","أدخل سعرًا صحيحًا.");return
        sym=self.service.selection.symbol;before=self.provider.get_last_price(sym);self.provider.set_last_price(sym,p);self._on_price(p);self._log("سعر",f"{before} → {p}")

    def _force_execute(self,leg:str)->None:
        if self.mode!="PAPER" or not isinstance(self.provider,PaperOCOProvider) or not self.service.selection:return
        try:oid=self.service.selection.order_list_id;price=self.provider.get_last_price(self.service.selection.symbol);self.provider.force_execute(oid,leg,price);self._log("تنفيذ",f"محاكاة {leg} على OCO {oid}");self._refresh_orders()
        except Exception as exc:QMessageBox.warning(self,"المحاكي",str(exc))

    def _toggle_fail_place(self,state:int)->None:
        if self.mode=="PAPER" and isinstance(self.provider,PaperOCOProvider):self.provider.fail_next_place=bool(state)
    def _toggle_fail_cancel(self,state:int)->None:
        if self.mode=="PAPER" and isinstance(self.provider,PaperOCOProvider):self.provider.fail_next_cancel=bool(state)
    def _reset_demo(self)->None:
        if self.mode!="PAPER":return
        self.provider=self._new_paper_provider();self.service=OCOEditorService(self.provider);self._tick_cache.clear();self._clear_selection_ui();self._refresh_orders(False);self._log("إعادة","تمت إعادة حالة المحاكي")

    def _log(self,event:str,details:str)->None:
        r=self.event_log.rowCount();self.event_log.insertRow(r);self.event_log.setItem(r,0,QTableWidgetItem(event));self.event_log.setItem(r,1,QTableWidgetItem(details));self.event_log.scrollToBottom()

    def closeEvent(self,event)->None:
        self._stop_price_subscription();self._disable_trail()
        try:self._workers.shutdown(wait=False,cancel_futures=True)
        except Exception:pass
        try:getattr(self.provider,"close",lambda:None)()
        except Exception:pass
        event.accept()


def run_app()->None:
    app=QApplication(sys.argv);w=MainWindow();w.show();sys.exit(app.exec())

if __name__=="__main__":run_app()
