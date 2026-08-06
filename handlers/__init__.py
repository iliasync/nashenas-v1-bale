"""
بسته‌ی هندلرها.

⚠️ ترتیب importها اینجا بسیار مهم است: بله‌تون هندلرها را دقیقاً به ترتیب
ثبت‌شدن (= ترتیب اجرای دکوریتورها در زمان import) بررسی می‌کند و اولین
هندلری که شرطش True باشد، اجرا و دیسپچ متوقف می‌شود (مگر اینکه خودِ هندلر
ContinueDispatching پرتاب کند). این دقیقاً معادل زنجیره‌ی if/elif/continue
در حلقه‌ی polling نسخه‌ی اصلی است.

ترتیب منطقی (خلاصه):
    1) gate        → بن/جوین‌اجباری (باید همیشه اول باشد)
    2) chat         → چت فعال (دکمه‌های چت + رله‌ی پیام) — در نسخه‌ی اصلی هم
                      تقریباً هرچیزی غیر از «پیام دایرکت در حال نوشتن» وقتی
                      کاربر چت فعال دارد، رله می‌شود نه چیز دیگری.
    3) payments     → خریدِ سکه و رسید
    4) registration → ثبت‌نام / start
    5) gps          → ثبت GPS
    6) profile      → پروفایل/ادیت/لایک/بلاک/مخاطبین/گزارش
    7) search       → جستجو
    8) nearby       → افراد نزدیک
    9) matchmaking  → اتصال تصادفی/فیلتر/اطراف
   10) invites      → دعوت/لینک ناشناس
   11) dooz         → بازی دوز
   12) rps          → سنگ‌کاغذقیچی
   13) admin        → پنل مدیریت
   14) misc         → راهنما/قوانین
   15) export       → خروجی پروفایل (فقط callback؛ ترتیب بی‌اهمیت)
   16) fallback     → فال‌بک «بازگشت 🔙» (باید همیشه آخر باشد)

نکته‌ی شناخته‌شده (ساده‌سازی نسبت به نسخه‌ی اصلی): در نسخه‌ی اصلی، عکسِ
رسیدِ پرداخت حتی در میانه‌ی یک چتِ فعال هم پردازش می‌شد. در این بازنویسی،
برای سادگی، اگر کاربر هم‌زمان در یک چتِ فعال باشد و هم منتظرِ ارسال رسید،
پیام (عکس) به‌جای پردازش‌شدن به‌عنوان رسید، به مخاطبِ چت رله می‌شود. این یک
حالتِ گوشه‌ایِ نادر است (هم‌زمانیِ خرید سکه با اتصال به یک چتِ ناشناس).
"""
from . import gate
from . import chat
from . import payments
from . import registration
from . import gps
from . import profile
from . import search
from . import nearby
from . import matchmaking
from . import invites
from . import dooz
from . import rps
from . import chat_cleanup
from . import admin
from . import misc
from . import export
from . import fallback

__all__ = [
    "gate", "chat", "payments", "registration", "gps", "profile", "search", "nearby",
    "matchmaking", "invites", "dooz", "rps", "chat_cleanup", "admin", "misc", "export", "fallback",
]

