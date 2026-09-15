# OCObot — خطة العمل الأساسية V1

> هذه الوثيقة هي المرجع الأساسي لتنفيذ المشروع. لا يتم تجاوز ترتيب المراحل، ولا يتم دمج أكثر من نقطة أثناء اختبار نقطة مستقلة.

## قاعدة العمل

**نصمم الجزء → نعتمده → ننفذه وحده → نختبره وحده → نثبت نجاحه → ننتقل للجزء التالي.**

أي قاعدة جديدة تُثبت في المواصفات أولًا قبل كتابة التنفيذ.

---

# المرحلة 0 — تجميد المواصفات

- نطاق V1: Binance Spot OCO فقط.
- التشغيل: `PAPER → TESTNET → LIVE لاحقًا`.
- هوية كل OCO هي `orderListId`، وليس الرمز وحده.
- الـ OCO الأصلي يبقى كما هو حتى عملية الاستبدال.
- الـ TP والـ Stop Trigger والـ Stop Limit ثلاثة أسعار مستقلة يجب عرضها بوضوح.
- المراقبة التلقائية اختيارية وتفعل يدويًا للصفقة المحددة.
- LIVE يظل معطلًا حتى نجاح الاختبارات والمراجعة النهائية.

## القواعد التي تم حذفها

تم إلغاء التصميم السابق القائم على `Dynamic Stop Distance %` كآلية مستقلة، وتم إلغاء Auto Trail الذي كان يحرك TP/SL انطلاقًا من المستويات القديمة.

المرجع الجديد هو `AUTO_MONITOR_STRATEGY.md` فقط.

---

# المرحلة 1 — محرك السعر اللحظي ✅

تم إثبات استقبال سعر Binance المستمر مع WebSocket وREST fallback وإعادة الاتصال.

---

# المرحلة 2 — قارئ OCO ✅

تم إثبات قراءة OCO الحقيقية من Binance Testnet واختيار `orderListId` محدد دون mutation.

---

# المرحلة 3 — واجهة الأساس وواجهة المرحلة 2 ✅

تم اعتماد النمط البصري الداكن وألوان OCObot، وتم بناء واجهة المرحلة 2 قراءة فقط.

يجب أن تعرض الواجهة دائمًا:

```text
TP Sale Price
SL Trigger Price
SL Limit Price
```

---

# المرحلة 4 — الصفحة الرئيسية

عرض سريع للـ OCO المحدد، السعر الحالي، حالة الاتصال، وحالة المراقبة.

---

# المرحلة 5 — صفحة الأوامر والتعديل اليدوي

- قائمة OCO المفتوحة.
- اختيار OCO محدد بالـ `orderListId`.
- تحميل المسودة محليًا.
- تعديل TP أو Stop Trigger أو Stop Limit.
- لا mutation أثناء الكتابة.

---

# المرحلة 6 — محرك حساب أسعار المراقبة الديناميكية

## المدخلات

```text
Reposition Trigger Rise %
TP Distance Above Current %
SL Distance Below Current %
```

لا توجد نسبة مستقلة لـ `SL Limit Price`؛ النظام يشتقها داخليًا.

## الحساب

```text
TP Sale Price    = live × (1 + TP%/100)
SL Trigger Price = live × (1 - SL%/100)
SL Limit Price   = normalized SL Trigger + 1 × tickSize
```

ثم التطبيع وفق `tickSize` وفحص قيود Binance مع الحفاظ على:

```text
SL Trigger Price < SL Limit Price < live price
```

لا يعتمد الحساب على سعر الدخول أو TP/SL القديم.

---

# المرحلة 7 — محرك المراقبة التلقائية

عند بدء المراقبة:

```text
reference_price = current_live_price
```

وعند:

```text
current_price >= reference × (1 + Trigger/100)
```

يصبح حدث التحريك مستحقًا.

الحدث **edge-triggered**: بعد عبور Trigger لا يتم إبطاله بسبب رجوع بسيط للسعر أثناء تنفيذ الاستبدال.

## المرونة

مثال:

```text
0.05050 → Trigger crossed
0.05047 → الحدث ما زال صالحًا
0.05044 → الحدث ما زال صالحًا
```

## القفزات

إذا قفز السعر فوق عدة Trigger intervals، لا نعيد تشغيل كل Trigger مفقود.

```text
0.05000 → 0.05300
```

يؤدي إلى **عملية reposition واحدة** محسوبة من أحدث سعر صالح.

## منع التوازي

لا توجد أكثر من عملية replacement واحدة قيد التنفيذ لنفس OCO. الأسعار الجديدة أثناء التنفيذ تُحفظ كحالة حديثة ولا تطلق عمليات متوازية.

---

# المرحلة 8 — محرك الاستبدال الآمن

```text
Trigger
  ↓
إعادة قراءة OCO المحدد
  ↓
تأكيد الهوية والحالة
  ↓
التقاط أحدث سعر صالح
  ↓
حساب TP/SL
  ↓
التحقق
  ↓
Cancel للـ orderListId المحدد فقط
  ↓
تحديث/فحص السعر
  ↓
Create للبديل
  ↓
تأكيد orderListId الجديد
  ↓
اعتماد المرجع الجديد
```

قواعد الفشل:

- فشل Cancel ⇒ لا Create.
- اكتمال OCO الأصلي قبل Cancel ⇒ لا Create.
- Cancel نجح وCreate فشل ⇒ `FAILED_NEEDS_ATTENTION` ولا إعادة محاولة عمياء.

---

# المرحلة 9 — تصميم صفحة المراقبة

تعرض للمستخدم:

```text
Monitoring: ON/OFF
Reference Price
Current Price
Next Trigger
TP Distance %
SL Distance %
Current TP
Current SL Trigger
Current SL Limit
Last Reposition
State / Error
```

لا يوجد تدخل يدوي مطلوب بعد تشغيل المراقبة.

---

# المرحلة 10 — اختبار المحرك المستقل

يجب اختبار:

1. Trigger عادي.
2. هبوط بسيط بعد Trigger مع بقاء الحدث صالحًا.
3. قفزة فوق عدة Triggers.
4. وصول سعر جديد أثناء replacement.
5. OCO أكمل قبل Cancel.
6. Cancel نجح وCreate فشل.
7. عدم وجود replacement متوازٍ.
8. تحديث `orderListId` بعد النجاح.

لا توجد أوامر حقيقية أثناء اختبار الحساب والمنطق.

---

# المرحلة 11 — Paper/Demo

تطبيق المراقبة الجديدة كاملة في Paper/Demo قبل Testnet.

---

# المرحلة 12 — Testnet

تشغيل نفس المنطق على Binance Spot Testnet، مع عمليات OCO حقيقية بعد نجاح Paper.

---

# المرحلة 13 — مراجعة السلامة والزمن

- قياس زمن replacement.
- مراجعة الحالات الحرجة.
- التأكد من عدم لمس OCO آخر.
- التأكد من عدم وجود blind retry.

---

# المرحلة 14 — LIVE

يبقى معطلًا حتى اعتماد كل الأدلة السابقة صراحة.


## Canonical Dynamic Monitor completion

Local implementation is complete: asynchronous start/live-price handling, serialized coalesced replacements, exact-selection lifecycle stops, explicit ABORTED_NO_CREATE versus FAILED_NEEDS_ATTENTION, result display, and orderListId rollover. Legacy AutoTrail is unreachable from the default UI and LIVE remains disabled. Local compile and 53-test suite pass. Remaining gates are automated Testnet acceptance and human safety/code review; see RELEASE_CHECKLIST.md.
