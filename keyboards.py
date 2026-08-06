"""
سازنده‌های کیبورد (Reply / Inline) با اشیای balethon.

نکته: در InlineKeyboard هر آیتم تاپل (text, callback_data) به صورت خودکار به
InlineKeyboardButton تبدیل می‌شود. در ReplyKeyboard هر رشته‌ی متنی هم به صورت
خودکار به ReplyKeyboardButton تبدیل می‌شود. برای دکمه‌های خاص (url / request_location)
باید مستقیماً از کلاس مربوطه استفاده کرد.
"""
from balethon.objects import InlineKeyboard, InlineKeyboardButton, ReplyKeyboard, ReplyKeyboardButton

import config


def ikb(*rows) -> InlineKeyboard:
    return InlineKeyboard(*rows)


def url_btn(text, url) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)


def ikb_row_btn(text, callback_data) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def ikb_log_moderation(
    primary_uid, secondary_uid=None, primary_label="⛔ بن کاربر", secondary_label="⛔ بن کاربر دوم"
):
    """دکمه‌های مدیریت زیر لاگ؛ callback فقط برای ادمین اصلی اجرا می‌شود."""
    rows = [[(primary_label, f"log_ban:{primary_uid}")]]
    if secondary_uid and str(secondary_uid) != str(primary_uid):
        rows.append([(secondary_label, f"log_ban:{secondary_uid}")])
    return ikb(*rows)


def rkb(*rows, resize=True, one_time=False, selective=True) -> ReplyKeyboard:
    return ReplyKeyboard(*rows, resize=resize, one_time=one_time, selective=selective)


# ---------------------------------------------------------------------------
# عمومی / قوانین
# ---------------------------------------------------------------------------
def ikb_rules_button():
    return ikb([("🚦 مشاهده قوانین", "show_rules")])


# ---------------------------------------------------------------------------
# ثبت‌نام / ادیت پروفایل
# ---------------------------------------------------------------------------
def ikb_gender():
    return ikb([("من🙎‍♂پسرم", "reg_gender_male"), ("من🙍‍♀دخترم", "reg_gender_female")])


def kb_gender_text():
    return rkb(["🙎‍♂️ پسر"], ["🙍‍♀️ دختر"], ["بازگشت 🔙"], one_time=True)


def kb_age_1_99():
    rows, row = [], []
    for n in range(1, 100):
        row.append(str(n))
        if len(row) == 7:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(["بازگشت 🔙"])
    return rkb(*rows, one_time=True)


def kb_provinces():
    rows, i = [], 0
    while i < len(config.PROVINCES):
        if i + 1 < len(config.PROVINCES):
            rows.append([config.PROVINCES[i], config.PROVINCES[i + 1]])
            i += 2
        else:
            rows.append([config.PROVINCES[i]])
            i += 1
    rows.append(["بازگشت 🔙"])
    return rkb(*rows, one_time=True)


def kb_cities():
    rows, i = [], 0
    while i < len(config.IRAN_CITIES):
        if i + 1 < len(config.IRAN_CITIES):
            rows.append([config.IRAN_CITIES[i], config.IRAN_CITIES[i + 1]])
            i += 2
        else:
            rows.append([config.IRAN_CITIES[i]])
            i += 1
    rows.append(["بازگشت 🔙"])
    return rkb(*rows, one_time=True)


def kb_back_only():
    return rkb(["بازگشت 🔙"])


def kb_cancel_only():
    return rkb(["لغو"])


def kb_gps_request_menu():
    loc_btn = ReplyKeyboardButton(text="ثبت موقعیت", request_location=True)
    return rkb([loc_btn], ["بازگشت 🔙"])


def kb_edit_profile_text_menu():
    return rkb(
        ["✏️ تغییر نام", "✏️ تغییر جنسیت"],
        ["✏️ تغییر سن", "✏️ تغییر استان"],
        ["✏️ تغییر شهر", "✏️ تغییر عکس"],
        ["✏️ تغییر موقعیت GPS"],
        ["بازگشت 🔙"],
    )


# ---------------------------------------------------------------------------
# منوی اصلی / چت / بازی‌ها
# ---------------------------------------------------------------------------
def kb_main_menu():
    return rkb(
        ["🔗 به یه ناشناس وصلم کن!️"],
        ["🔍 جستجوی کاربران 🔎", "📍افراد نزدیک"],
        ["👤پروفایل", "💰سکه بات"],#, "دوز 🎰"
        #["سنگ کاغذ قیچی ✂️"],
        ["🤔راهنما"],
        ["🚸 معرفی به دوستان (سکه رایگان)"],
        ["لینک ناشناس من 📬"],
    )


def kb_chat_menu():
    return rkb(
        ["🎁 هدیه", "👤 پروفایل مخاطب"],
        ["🎮 دوز با مخاطب", "✂️ سنگ کاغذ قیچی با مخاطب"],
        ["قطع چت"],
    )


def ikb_end_chat_confirm(owner_id):
    return ikb(
        [("✅ بله، قطع کن", f"chat_end:yes:{owner_id}")],
        [("💬 نه، ادامه می‌دم", f"chat_end:no:{owner_id}")],
    )


def kb_dooz_menu():
    return rkb(["دوز شانسی🎲", "دوز با لینک🎮"], ["بازگشت 🔙"])


def kb_rps_menu():
    return rkb(["سنگ کاغذ قیچی شانسی🎲", "سنگ کاغذ قیچی با لینک🎮"], ["بازگشت 🔙"])


def ikb_connect_menu():
    return ikb(
        [("🎲 جستجو شانسی (رایگان)", "mm_random")],
        [("جستجو  پسر 👦", "mm_boy"), ("جستجو دختر 👧", "mm_girl")],
        [("🪃جستحو اطراف", "mm_near")],
    )


def ikb_near_menu():
    return ikb(
        [("👧  دختر باشه ( 💰 4)", "mm_near_girl"), ("👦 پسر باشه ( 💰4)", "mm_near_boy")],
        [("فرقی نمیکنه (رایگان)", "mm_near_any")],
        [("بازگشت", "mm_back")],
    )


def ikb_nearby_pick():
    return ikb(
        [("🙍‍♀️ فقط دخترها", "nearby_gender:female"), ("🙎‍♂️ فقط پسرها", "nearby_gender:male")],
        [("👫 همه رو نشون بده", "nearby_gender:all")],
    )


def ikb_nearby_need_gps():
    return ikb([("📍 ثبت موقعیت GPS", "nearby_set_gps")])


# ---------------------------------------------------------------------------
# پنل ادمین
# ---------------------------------------------------------------------------
def kb_admin_panel():
    return rkb(
        ["📣 ارسال همگانی", "🪙 انتقال سکه"],
        ["🎁 سکه همگانی", "📌 جوین اجباری"],
        ["📊 آمار ربات", "⛔ بلاک کاربر"],
        ["✅ آنبلاک کاربر", "👤 اطلاعات کاربر"],
        ["🧾 پرداخت‌ها (لیست)", "🔙 خروج از پنل"],
    )


# ---------------------------------------------------------------------------
# خرید سکه
# ---------------------------------------------------------------------------
def ikb_coin_buy_menu():
    rows = []
    for coins, price in config.COIN_PACKAGES:
        label = f"{coins} سکه - {price:,} تومان"
        rows.append([(label, f"buy_pkg:{coins}:{price}")])
    rows.append([("🚸معرفی به دوستان(سکه رایگان)", "buy_invite")])
    return ikb(*rows)


def ikb_payment_actions(tx_id: str):
    return ikb(
        [("💰 پرداخت انجام شد", f"buy_paid:{tx_id}")],
        [("❌انصراف", f"buy_cancel:{tx_id}")],
    )


# ---------------------------------------------------------------------------
# پروفایل من / کاربر دیگر
# ---------------------------------------------------------------------------
def ikb_my_profile_buttons():
    return ikb(
        [("🚨مشاهده موقعیت GPS ثبت شده من", "profile_show_gps")],
        [("👨‍🦱👩‍🦱مخاطبین", "profile_contacts"), ("❤️لایک های من", "profile_my_likes")],
        [("🚫 بلاک شده ها", "profile_blocked"), ("🛎 سایلنت", "profile_silent")],
        [("✏️ ویرایش پروفایل من", "profile_edit_text")],
    )


def ikb_user_profile_actions(viewer_user: dict, target_user: dict, is_blocked: bool):
    pid = target_user.get("public_id")
    likes_cnt = int(target_user.get("likes", 0) or 0)
    my_likes = {str(x).strip() for x in (viewer_user.get("my_likes") or [])}
    liked = pid in my_likes

    btn_like = (f"Like❤️ ({likes_cnt})" + (" ✅" if liked else ""), f"like_toggle:{pid}")

    blocked_set = {str(x).strip() for x in (viewer_user.get("blocked_users") or [])}
    is_target_blocked = pid in blocked_set
    btn_block = (("🔐آنلاک کردن کاربر" if is_target_blocked else "🔒بلاک کردن کاربر"), f"block_toggle:{pid}")

    btn_direct = ("📨پیام دایرکت", f"direct:{pid}")
    btn_chat = ("💬درخواست چت", f"chatreq:{pid}")
    btn_add_contact = ("➕افزودن به مخاطبین", f"add_contact:{pid}")
    btn_report = ("🚫گزارش کاربر", f"report:{pid}")
    btn_export = ("دریافت فایل🪗", f"export_menu:{pid}")

    in_chat = bool(target_user.get("chat_with"))
    btn_notify_end = ("🛎به محض اتمام چت اطلاع بده", f"notify_end:{pid}")

    if is_blocked:
        rows = [[btn_block], [btn_report], [btn_export]]
    else:
        rows = [[btn_like], [btn_direct, btn_chat], [btn_block, btn_add_contact], [btn_report], [btn_export]]
        if in_chat:
            rows.append([btn_notify_end])

    rows.append([("بازگشت", "back_to_main_from_user")])
    return ikb(*rows)


def ikb_silent_buttons():
    return ikb(
        [("🛎سایلنت تا یک ساعت", "silent_1h"), ("🛎سایلنت تا ۲۰ دقیقه", "silent_20m")],
        [("🛎همیشه سایلنت", "silent_forever")],
        [("🛎🔑غیر فعال کردن سایلنت", "silent_off")],
        [("بازگشت", "back_to_my_profile")],
    )


def ikb_export_menu(pid):
    return ikb(
        [("جیسون | JSON", f"export_json:{pid}"), ("text | TXT", f"export_text:{pid}")],
        [("html وب | HTML", f"export_html:{pid}")],
        [("بازگشت", f"back_user_profile:{pid}")],
    )


# ---------------------------------------------------------------------------
# جستجو
# ---------------------------------------------------------------------------
def ikb_search_main():
    return ikb(
        [("👥هم سنی ها", "search_same_age"), ("🏳هم استانی ها", "search_same_province")],
        [("🔍 جستجوی پیشرفته🔎", "search_advanced")],
        [("🚶‍♂بدون چت ها🚶‍♂", "search_no_chat"), ("👦 کاربران جدید👧", "search_new_users")],
        [("بازگشت", "search_back_mainmenu")],
    )


def ikb_search_gender_pick(prefix):
    return ikb(
        [("فقط💁‍♀دختر ها", f"{prefix}:gender:female"), ("فقط🙅‍♂پسر ها", f"{prefix}:gender:male")],
        [("همه رو نشون بده", f"{prefix}:gender:all")],
        [("بازگشت", "search_back_root")],
    )


def ikb_search_results(meta_key, page, total, dropdown=False, results=None):
    results = results or []
    rows = []
    nav = []
    if page > 1:
        nav.append((" برگشت⬅️", f"search_page:{meta_key}:{page-1}"))
    if (page * 10) < total:
        nav.append(("ادامه ➡️", f"search_page:{meta_key}:{page+1}"))
    if nav:
        rows.append(nav)

    if results:
        rows.append([
            (("🔽 مشاهده بصورت کشویی" if not dropdown else "🔼 بستن کشویی"),
             f"search_dropdown:{meta_key}:{page}:{1 if not dropdown else 0}")
        ])

    if dropdown and results:
        chunk = results[(page - 1) * 10: (page - 1) * 10 + 10]
        for idx, pid in enumerate(chunk, start=(page - 1) * 10 + 1):
            rows.append([(f"👁‍🗨 مشاهده {idx} • /user_{pid}", f"search_open_user:{pid}")])

    rows.append([("🔙 بازگشت به لیست قبلی", f"search_back_category:{meta_key}")])
    rows.append([("🏠 منوی جستجو", "search_back_root")])
    return ikb(*rows)


def ikb_adv_gender_pick():
    return ikb(
        [("فقط💁‍♀دختر ها", "adv_gender:female"), ("فقط🙅‍♂پسر ها", "adv_gender:male")],
        [("همه رو نشون بده", "adv_gender:all")],
        [("بازگشت", "search_back_root")],
    )


def ikb_adv_province_select(viewer_user: dict):
    s = viewer_user.get("search") or {}
    selected = set(s.get("adv_selected_provinces") or [])
    near = bool(s.get("adv_near_me", False))

    rows = [
        [("➡️ مرحله بعدی", "adv_prov_next"), ("✅انتخاب همه", "adv_prov_all")],
        [(("📍 افراد نزدیک من ✔️" if near else "📍 افراد نزدیک من"), "adv_near_toggle")],
    ]

    i = 0
    provinces = config.PROVINCES
    while i < len(provinces):
        p1 = provinces[i]
        row = [(("✔️ " if p1 in selected else "") + p1, f"adv_prov_toggle:{p1}")]
        if i + 1 < len(provinces):
            p2 = provinces[i + 1]
            row.append((("✔️ " if p2 in selected else "") + p2, f"adv_prov_toggle:{p2}"))
            i += 2
        else:
            i += 1
        rows.append(row)

    rows.append([("بازگشت", "search_back_root")])
    return ikb(*rows)


# ---------------------------------------------------------------------------
# گزارش کاربر
# ---------------------------------------------------------------------------
def ikb_report_reasons(pid):
    rows = [[(title, f"report_reason:{pid}:{code}")] for title, code in config.REPORT_REASONS]
    rows.append([("بازگشت", f"back_user_profile:{pid}")])
    return ikb(*rows)


# ---------------------------------------------------------------------------
# دوز (Tic-Tac-Toe)
# ---------------------------------------------------------------------------
def dooz_symbol(mark: str):
    return "❌" if mark == "X" else "⭕️"


def ikb_dooz_board(session_id: int, board):
    rows = []
    for row_idx in range(3):
        row = []
        for col_idx in range(3):
            cell = row_idx * 3 + col_idx
            value = board[cell]
            if value:
                row.append((dooz_symbol(value), "dooz:noop"))
            else:
                row.append(("▫️", f"dooz:mv:{session_id}:{cell}"))
        rows.append(row)
    rows.append([("🚪 خروج از دوز", f"dooz:leaveask:{session_id}")])
    return ikb(*rows)


def ikb_dooz_queue_cancel(user_id):
    return ikb([("لغو جستجو", f"dooz:qcancel:{user_id}")])


def ikb_dooz_leave_confirm(session_id, owner_id):
    return ikb(
        [("✅ بله، خروج", f"dooz:leave:yes:{session_id}:{owner_id}")],
        [("💬 نه، ادامه بازی", f"dooz:leave:no:{session_id}:{owner_id}")],
    )


def ikb_dooz_link_request(request_id):
    return ikb(
        [("✅ تایید شروع بازی", f"dooz:linkreq:yes:{request_id}")],
        [("❌ رد درخواست", f"dooz:linkreq:no:{request_id}")],
    )


def ikb_chat_dooz_invite(inviter_id):
    return ikb(
        [("🎮 قبول دوز", f"chat_dooz:accept:{inviter_id}")],
        [("❌ رد دعوت", f"chat_dooz:reject:{inviter_id}")],
    )


def ikb_chat_dooz_cancel(inviter_id):
    return ikb([("❎ لغو دعوت", f"chat_dooz:cancel:{inviter_id}")])


def ikb_dooz_rematch(session_id):
    return ikb([("بازی مجدد🔄", f"dooz:rm:req:{session_id}")])


def ikb_dooz_rematch_confirm(session_id, requester_id):
    return ikb(
        [("قبول کردن✅", f"dooz:rm:yes:{session_id}:{requester_id}")],
        [("لغو کردن ❌", f"dooz:rm:no:{session_id}:{requester_id}")],
    )


# ---------------------------------------------------------------------------
# سنگ کاغذ قیچی
# ---------------------------------------------------------------------------
def ikb_rps_choice(session_id):
    return ikb(
        [
            ("🪨 سنگ", f"rps:pick:{session_id}:rock"),
            ("📄 کاغذ", f"rps:pick:{session_id}:paper"),
            ("✂️ قیچی", f"rps:pick:{session_id}:scissors"),
        ],
        [("🚪 خروج از بازی", f"rps:leave:{session_id}")],
    )


def ikb_rps_queue_cancel(user_id):
    return ikb([("لغو جستجو", f"rps:qcancel:{user_id}")])


def ikb_rps_link_request(request_id):
    return ikb(
        [("✅ تایید شروع بازی", f"rps:linkreq:yes:{request_id}")],
        [("❌ رد درخواست", f"rps:linkreq:no:{request_id}")],
    )


def ikb_chat_rps_invite(inviter_id):
    return ikb(
        [("✂️ قبول بازی", f"chat_rps:accept:{inviter_id}")],
        [("❌ رد دعوت", f"chat_rps:reject:{inviter_id}")],
    )


def ikb_chat_rps_cancel(inviter_id):
    return ikb([("❎ لغو دعوت", f"chat_rps:cancel:{inviter_id}")])


