from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import db
from config import BOT_TOKEN, ADMIN_IDS, SHOW_ADMIN_BUTTON_FOR_ADMINS


# ------------------- Constants / States -------------------
(
    ADMIN_ADD_BAL_UID, ADMIN_ADD_BAL_AMT,
    ADMIN_DED_BAL_UID, ADMIN_DED_BAL_AMT,
    ADMIN_ALLOW_UID,
    ADMIN_DENY_UID,
    ADMIN_BAN_UID,
    ADMIN_UNBAN_UID,
    ADMIN_SET_PRICE,
    ADMIN_SET_LIMIT_UID, ADMIN_SET_LIMIT_VAL,
    ADMIN_EDIT_START,
    ADMIN_BROADCAST,
    TOPUP_AMOUNT,
    ADMIN_DECIDE_TOPUP_ID,
) = range(18)

CB_MAIN = "main"
CB_BAL = "bal"
CB_BUY = "buy"
CB_TOPUP = "topup"
CB_ORDERS = "orders"
CB_PROFILE = "profile"
CB_HELP = "help"
CB_ADMIN = "admin"

# Admin menu callback roots
CB_A_USERS = "a_users"
CB_A_WALLET = "a_wallet"
CB_A_ORDERS = "a_orders"
CB_A_STATS = "a_stats"
CB_A_SETTINGS = "a_settings"
CB_A_MSGS = "a_msgs"

# Admin wallet actions
CB_A_ADD_BAL = "a_add_bal"
CB_A_DED_BAL = "a_ded_bal"
CB_A_USER_BAL = "a_user_bal"   # simple view
CB_A_TOPUP_REQS = "a_topup_reqs"

# Admin users actions
CB_A_ALLOW = "a_allow"
CB_A_DENY = "a_deny"
CB_A_BAN = "a_ban"
CB_A_UNBAN = "a_unban"

# Admin settings actions
CB_A_SET_PRICE = "a_set_price"
CB_A_SET_LIMIT = "a_set_limit"
CB_A_MAINT_ON = "a_maint_on"
CB_A_MAINT_OFF = "a_maint_off"

# Admin messages actions
CB_A_EDIT_START = "a_edit_start"
CB_A_BROADCAST = "a_broadcast"

# Decide topup
CB_A_APPROVE_PREFIX = "a_appr_"  # +id
CB_A_REJECT_PREFIX = "a_rej_"    # +id


# ------------------- Helpers -------------------
def is_admin(user_id: int) -> bool:
    return user_id in set(ADMIN_IDS)


def money_ok(s: str) -> Optional[float]:
    s = s.strip().replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d{1,2})?", s):
        return None
    v = float(s)
    if v <= 0:
        return None
    return v


def k_main(is_admin_user: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("💰 رصيدي", callback_data=CB_BAL)],
        [InlineKeyboardButton("📲 شراء رقم 🇬🇧", callback_data=CB_BUY)],
        [InlineKeyboardButton("💳 شراء رصيد", callback_data=CB_TOPUP)],
        [InlineKeyboardButton("📩 طلباتي", callback_data=CB_ORDERS)],
        [InlineKeyboardButton("👤 حسابي", callback_data=CB_PROFILE)],
        [InlineKeyboardButton("ℹ️ مساعدة", callback_data=CB_HELP)],
    ]
    if is_admin_user and SHOW_ADMIN_BUTTON_FOR_ADMINS:
        rows.append([InlineKeyboardButton("🛠 لوحة الأدمن", callback_data=CB_ADMIN)])
    return InlineKeyboardMarkup(rows)


def k_back(to_cb: str = CB_MAIN) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=to_cb)]])


def k_admin_main() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data=CB_A_USERS)],
        [InlineKeyboardButton("💰 إدارة الرصيد", callback_data=CB_A_WALLET)],
        [InlineKeyboardButton("📦 إدارة الطلبات", callback_data=CB_A_ORDERS)],
        [InlineKeyboardButton("📊 الإحصائيات", callback_data=CB_A_STATS)],
        [InlineKeyboardButton("⚙️ إعدادات النظام", callback_data=CB_A_SETTINGS)],
        [InlineKeyboardButton("📝 إدارة الرسائل", callback_data=CB_A_MSGS)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CB_MAIN)],
    ]
    return InlineKeyboardMarkup(rows)


def gate_user(user_id: int) -> tuple[bool, str]:
    u = db.ensure_user(user_id)
    db.reset_daily_if_needed(user_id)

    if u.is_banned:
        return False, "🚫 حسابك محظور."
    if not u.is_allowed and not is_admin(user_id):
        return False, "🔒 هذا بوت تجريبي. حسابك غير مفعّل حالياً.\n📩 تواصل مع الأدمن لتفعيل حسابك."
    if db.is_maintenance() and not is_admin(user_id):
        return False, "🛠 البوت تحت الصيانة حالياً. حاول لاحقاً."
    return True, ""


async def safe_edit(query, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
    # Avoid edit error if message unchanged
    try:
        await query.edit_message_text(text=text, reply_markup=reply_markup)
    except Exception:
        # fallback: resend
        await query.message.reply_text(text=text, reply_markup=reply_markup)


# ------------------- User: /start -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.ensure_user(user_id)

    ok, msg = gate_user(user_id)
    if not ok:
        await update.message.reply_text(msg)
        return

    start_msg = db.get_start_message()
    await update.message.reply_text(
        start_msg,
        reply_markup=k_main(is_admin(user_id))
    )


# ------------------- Callback router -------------------
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # Gate for non-admin actions (admin also passes)
    ok, msg = gate_user(user_id)
    if not ok and query.data != CB_ADMIN:
        await safe_edit(query, msg, reply_markup=None)
        return

    data = query.data

    # Main navigation
    if data == CB_MAIN:
        await safe_edit(query, db.get_start_message(), reply_markup=k_main(is_admin(user_id)))
        return

    if data == CB_BAL:
        u = db.ensure_user(user_id)
        text = f"💰 رصيدك الحالي: **{u.balance:.2f}$**"
        await safe_edit(query, text, reply_markup=k_back(CB_MAIN))
        return

    if data == CB_PROFILE:
        u = db.ensure_user(user_id)
        db.reset_daily_if_needed(user_id)
        u = db.ensure_user(user_id)
        text = (
            f"👤 **حسابي**\n\n"
            f"🆔 ID: `{u.user_id}`\n"
            f"💰 الرصيد: **{u.balance:.2f}$**\n"
            f"📌 الحالة: {'✅ مفعل' if u.is_allowed or is_admin(user_id) else '⛔ غير مفعل'}\n"
            f"🛡 الحظر: {'🚫 محظور' if u.is_banned else '✅ لا'}\n"
            f"📆 حد اليوم: **{u.daily_limit}**\n"
            f"📊 مستخدم اليوم: **{u.daily_count}/{u.daily_limit}**"
        )
        await safe_edit(query, text, reply_markup=k_back(CB_MAIN))
        return

    if data == CB_HELP:
        text = (
            "ℹ️ **المساعدة**\n\n"
            "• استخدم زر **شراء رقم 🇬🇧** للحصول على رقم.\n"
            "• من **طلباتي** تتابع حالة الطلب.\n"
            "• زر **شراء رصيد** يرسل طلب شحن للأدمن.\n"
            "• يمكنك رؤية ID الخاص بك من **حسابي**."
        )
        await safe_edit(query, text, reply_markup=k_back(CB_MAIN))
        return

    # Buy number (provider integration intentionally omitted)
    if data == CB_BUY:
        u = db.ensure_user(user_id)
        db.reset_daily_if_needed(user_id)
        u = db.ensure_user(user_id)

        price = db.get_price_usd()

        if u.daily_count >= u.daily_limit and not is_admin(user_id):
            await safe_edit(query, "⛔ وصلت للحد اليومي. حاول غداً.", reply_markup=k_back(CB_MAIN))
            return

        if float(u.balance) < price and not is_admin(user_id):
            await safe_edit(query, f"رصيدك غير كافي.\nالسعر: {price:.2f}$", reply_markup=k_back(CB_MAIN))
            return

        # NOTE: Here you would call provider API (not included).
        # For now, simulate an order creation record only.
        if not is_admin(user_id):
            db.deduct_balance(user_id, price, kind="deduct", note="Buy UK temp number (stub)")
            db.increment_daily(user_id)

        await safe_edit(
            query,
            "✅ تم تسجيل عملية الشراء (نسخة تجريبية).\n"
            "سيتم ربط مزوّد الأرقام لاحقًا داخل جدول orders.",
            reply_markup=k_back(CB_MAIN)
        )
        return

    if data == CB_ORDERS:
        # orders table prepared; show last few
        # Keeping it minimal here (no provider integration)
        await safe_edit(
            query,
            "📩 **طلباتي**\n\nحالياً: لا يوجد عرض تلقائي للأكواد لأن ربط المزود غير مفعّل في هذه النسخة.\n"
            "عند تفعيل الربط سيتم عرض الطلبات هنا.",
            reply_markup=k_back(CB_MAIN)
        )
        return

    if data == CB_TOPUP:
        await safe_edit(
            query,
            "💳 **شراء رصيد**\n\n"
            "اضغط على (طلب شحن) ثم اكتب المبلغ المطلوب.\n"
            "سيصل طلبك للأدمن للمراجعة.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 طلب شحن", callback_data="topup_req")],
                [InlineKeyboardButton("🔙 رجوع", callback_data=CB_MAIN)]
            ])
        )
        return

    if data == "topup_req":
        context.user_data["await_topup_amount"] = True
        await safe_edit(query, "✍️ اكتب مبلغ الشحن المطلوب (مثال: 5 أو 10.5):", reply_markup=k_back(CB_TOPUP))
        return

    # ------------------- Admin Panel -------------------
    if data == CB_ADMIN:
        if not is_admin(user_id):
            await safe_edit(query, "🚫 غير مصرح.", reply_markup=k_back(CB_MAIN))
            return
        await safe_edit(query, "🛠 **لوحة الأدمن**", reply_markup=k_admin_main())
        return

    if not is_admin(user_id) and data.startswith("a_"):
        await safe_edit(query, "🚫 غير مصرح.", reply_markup=k_back(CB_MAIN))
        return

    # Admin sections
    if data == CB_A_USERS:
        await safe_edit(query, "👥 **إدارة المستخدمين**", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ تفعيل مستخدم", callback_data=CB_A_ALLOW)],
            [InlineKeyboardButton("⛔ إلغاء التفعيل", callback_data=CB_A_DENY)],
            [InlineKeyboardButton("🚫 حظر مستخدم", callback_data=CB_A_BAN)],
            [InlineKeyboardButton("✅ فك الحظر", callback_data=CB_A_UNBAN)],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CB_ADMIN)],
        ]))
        return

    if data == CB_A_WALLET:
        await safe_edit(query, "💰 **إدارة الرصيد**", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة رصيد", callback_data=CB_A_ADD_BAL)],
            [InlineKeyboardButton("➖ خصم رصيد", callback_data=CB_A_DED_BAL)],
            [InlineKeyboardButton("🔔 طلبات الشحن", callback_data=CB_A_TOPUP_REQS)],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CB_ADMIN)],
        ]))
        return

    if data == CB_A_ORDERS:
        await safe_edit(query, "📦 **إدارة الطلبات**\n\n(جاهزة للربط لاحقاً عبر جدول orders)", reply_markup=k_back(CB_ADMIN))
        return

    if data == CB_A_STATS:
        s = db.stats_today()
        text = (
            "📊 **إحصائيات اليوم**\n\n"
            f"👥 المستخدمين: {s['users_count']}\n"
            f"✅ نشطين اليوم: {s['active_today']}\n"
            f"🔁 العمليات اليوم: {s['tx_count']}\n"
            f"💵 صافي حركة الرصيد اليوم: {s['sum_amount']:.2f}$"
        )
        await safe_edit(query, text, reply_markup=k_back(CB_ADMIN))
        return

    if data == CB_A_SETTINGS:
        price = db.get_price_usd()
        maint = "✅ ON" if db.is_maintenance() else "❌ OFF"
        await safe_edit(query, f"⚙️ **إعدادات النظام**\n\nالسعر الحالي: {price:.2f}$\nالصيانة: {maint}", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💲 تغيير السعر", callback_data=CB_A_SET_PRICE)],
            [InlineKeyboardButton("📆 تحديد حد يومي لمستخدم", callback_data=CB_A_SET_LIMIT)],
            [InlineKeyboardButton("🛠 تشغيل الصيانة", callback_data=CB_A_MAINT_ON)],
            [InlineKeyboardButton("✅ إيقاف الصيانة", callback_data=CB_A_MAINT_OFF)],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CB_ADMIN)],
        ]))
        return

    if data == CB_A_MSGS:
        await safe_edit(query, "📝 **إدارة الرسائل**", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ تعديل رسالة /start", callback_data=CB_A_EDIT_START)],
            [InlineKeyboardButton("📢 رسالة جماعية", callback_data=CB_A_BROADCAST)],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CB_ADMIN)],
        ]))
        return

    # Admin: maintenance toggle
    if data == CB_A_MAINT_ON:
        db.set_setting("maintenance", "1")
        db.admin_log(user_id, "maintenance_on", {})
        await safe_edit(query, "✅ تم تشغيل وضع الصيانة.", reply_markup=k_back(CB_A_SETTINGS))
        return

    if data == CB_A_MAINT_OFF:
        db.set_setting("maintenance", "0")
        db.admin_log(user_id, "maintenance_off", {})
        await safe_edit(query, "✅ تم إيقاف وضع الصيانة.", reply_markup=k_back(CB_A_SETTINGS))
        return

    # Admin: pending topups list
    if data == CB_A_TOPUP_REQS:
        pending = db.list_pending_topups()
        if not pending:
            await safe_edit(query, "🔔 لا توجد طلبات شحن معلّقة.", reply_markup=k_back(CB_ADMIN))
            return

        lines = ["🔔 **طلبات الشحن المعلّقة**\n"]
        rows = []
        for (rid, uid, amt, created_at) in pending:
            lines.append(f"• #{rid} | `{uid}` | {float(amt):.2f}$")
            rows.append([
                InlineKeyboardButton(f"✅ #{rid}", callback_data=f"{CB_A_APPROVE_PREFIX}{rid}"),
                InlineKeyboardButton(f"❌ #{rid}", callback_data=f"{CB_A_REJECT_PREFIX}{rid}"),
            ])
        rows.append([InlineKeyboardButton("🔙 رجوع", callback_data=CB_ADMIN)])
        await safe_edit(query, "\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))
        return

    # Admin: approve/reject topup
    if data.startswith(CB_A_APPROVE_PREFIX) or data.startswith(CB_A_REJECT_PREFIX):
        approve = data.startswith(CB_A_APPROVE_PREFIX)
        rid = int(data.split("_")[-1])
        decided = db.decide_topup(rid, user_id, approve=approve)
        if not decided:
            await safe_edit(query, "⛔ الطلب غير موجود أو تم اتخاذ قرار مسبقاً.", reply_markup=k_back(CB_ADMIN))
            return
        tuid, amt = decided
        if approve:
            db.add_balance(tuid, amt, kind="topup", note=f"Topup approved #{rid}")
            db.admin_log(user_id, "topup_approved", {"req_id": rid, "user_id": tuid, "amount": amt})
            # notify user
            try:
                await context.bot.send_message(chat_id=tuid, text=f"✅ تم شحن رصيدك بمبلغ {amt:.2f}$")
            except Exception:
                pass
            await safe_edit(query, f"✅ تمت الموافقة وشحن {amt:.2f}$ للمستخدم `{tuid}`.", reply_markup=k_back(CB_ADMIN))
        else:
            db.admin_log(user_id, "topup_rejected", {"req_id": rid, "user_id": tuid, "amount": amt})
            try:
                await context.bot.send_message(chat_id=tuid, text=f"❌ تم رفض طلب شحن الرصيد ({amt:.2f}$).")
            except Exception:
                pass
            await safe_edit(query, f"❌ تم رفض الطلب #{rid}.", reply_markup=k_back(CB_ADMIN))
        return

    # Admin: action triggers that switch to conversation states
    if data in (CB_A_ADD_BAL, CB_A_DED_BAL, CB_A_ALLOW, CB_A_DENY, CB_A_BAN, CB_A_UNBAN, CB_A_SET_PRICE, CB_A_SET_LIMIT, CB_A_EDIT_START, CB_A_BROADCAST):
        # handled by conversation handlers via entry points (we just prompt here)
        if data == CB_A_ADD_BAL:
            context.user_data["admin_action"] = "addbal"
            await safe_edit(query, "🆔 أرسل ID المستخدم:", reply_markup=k_back(CB_ADMIN))
            return
        if data == CB_A_DED_BAL:
            context.user_data["admin_action"] = "dedbal"
            await safe_edit(query, "🆔 أرسل ID المستخدم:", reply_markup=k_back(CB_ADMIN))
            return
        if data == CB_A_ALLOW:
            context.user_data["admin_action"] = "allow"
            await safe_edit(query, "🆔 أرسل ID المستخدم لتفعيله:", reply_markup=k_back(CB_ADMIN))
            return
        if data == CB_A_DENY:
            context.user_data["admin_action"] = "deny"
            await safe_edit(query, "🆔 أرسل ID المستخدم لإلغاء تفعيله:", reply_markup=k_back(CB_ADMIN))
            return
        if data == CB_A_BAN:
            context.user_data["admin_action"] = "ban"
            await safe_edit(query, "🆔 أرسل ID المستخدم لحظره:", reply_markup=k_back(CB_ADMIN))
            return
        if data == CB_A_UNBAN:
            context.user_data["admin_action"] = "unban"
            await safe_edit(query, "🆔 أرسل ID المستخدم لفك الحظر:", reply_markup=k_back(CB_ADMIN))
            return
        if data == CB_A_SET_PRICE:
            context.user_data["admin_action"] = "setprice"
            await safe_edit(query, "💲 أرسل السعر الجديد (مثال: 0.5):", reply_markup=k_back(CB_ADMIN))
            return
        if data == CB_A_SET_LIMIT:
            context.user_data["admin_action"] = "setlimit_uid"
            await safe_edit(query, "🆔 أرسل ID المستخدم لتحديد حدّه اليومي:", reply_markup=k_back(CB_ADMIN))
            return
        if data == CB_A_EDIT_START:
            context.user_data["admin_action"] = "editstart"
            await safe_edit(query, "✏️ أرسل رسالة /start الجديدة كاملة:", reply_markup=k_back(CB_ADMIN))
            return
        if data == CB_A_BROADCAST:
            context.user_data["admin_action"] = "broadcast"
            await safe_edit(query, "📢 أرسل الرسالة التي تريد إرسالها للجميع:", reply_markup=k_back(CB_ADMIN))
            return

    # fallback
    await safe_edit(query, "⚠️ أمر غير معروف.", reply_markup=k_back(CB_MAIN))


# ------------------- Message handler (topup + admin prompts) -------------------
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = (update.message.text or "").strip()

    # Topup request flow
    if context.user_data.get("await_topup_amount"):
        context.user_data["await_topup_amount"] = False
        ok, msg = gate_user(user_id)
        if not ok:
            await update.message.reply_text(msg)
            return
        amt = money_ok(text)
        if amt is None:
            await update.message.reply_text("⛔ صيغة غير صحيحة. اكتب رقم مثل: 5 أو 10.5")
            return

        req_id = db.create_topup_request(user_id, amt)
        # notify admins
        for aid in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=aid,
                    text=f"🔔 طلب شحن جديد\n\n🆔 User ID: `{user_id}`\n💰 المبلغ: {amt:.2f}$\n📌 رقم الطلب: #{req_id}",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass

        await update.message.reply_text(f"✅ تم إرسال طلب الشحن (#{req_id}). سيتم مراجعته من الإدارة.")
        return

    # Admin prompts driven by context.user_data["admin_action"]
    if is_admin(user_id) and context.user_data.get("admin_action"):
        action = context.user_data.get("admin_action")

        if action == "addbal":
            if "admin_uid" not in context.user_data:
                if not text.isdigit():
                    await update.message.reply_text("⛔ أرسل ID صحيح (أرقام فقط).")
                    return
                context.user_data["admin_uid"] = int(text)
                await update.message.reply_text("💰 أرسل المبلغ للإضافة (مثال: 5 أو 10.5):")
                return
            else:
                amt = money_ok(text)
                if amt is None:
                    await update.message.reply_text("⛔ مبلغ غير صحيح.")
                    return
                uid = context.user_data.pop("admin_uid")
                context.user_data.pop("admin_action", None)
                db.add_balance(uid, amt, kind="adjust", note=f"Admin add by {user_id}")
                db.admin_log(user_id, "add_balance", {"user_id": uid, "amount": amt})
                try:
                    await context.bot.send_message(chat_id=uid, text=f"✅ تم إضافة {amt:.2f}$ إلى رصيدك.")
                except Exception:
                    pass
                await update.message.reply_text("✅ تم إضافة الرصيد.")
                return

        if action == "dedbal":
            if "admin_uid" not in context.user_data:
                if not text.isdigit():
                    await update.message.reply_text("⛔ أرسل ID صحيح (أرقام فقط).")
                    return
                context.user_data["admin_uid"] = int(text)
                await update.message.reply_text("➖ أرسل المبلغ للخصم (مثال: 1 أو 2.5):")
                return
            else:
                amt = money_ok(text)
                if amt is None:
                    await update.message.reply_text("⛔ مبلغ غير صحيح.")
                    return
                uid = context.user_data.pop("admin_uid")
                context.user_data.pop("admin_action", None)
                db.deduct_balance(uid, amt, kind="adjust", note=f"Admin deduct by {user_id}")
                db.admin_log(user_id, "deduct_balance", {"user_id": uid, "amount": amt})
                try:
                    await context.bot.send_message(chat_id=uid, text=f"ℹ️ تم خصم {amt:.2f}$ من رصيدك.")
                except Exception:
                    pass
                await update.message.reply_text("✅ تم خصم الرصيد.")
                return

        if action in ("allow", "deny", "ban", "unban"):
            if not text.isdigit():
                await update.message.reply_text("⛔ أرسل ID صحيح (أرقام فقط).")
                return
            uid = int(text)
            context.user_data.pop("admin_action", None)

            if action == "allow":
                db.ensure_user(uid)
                db.set_allowed(uid, True)
                db.admin_log(user_id, "allow_user", {"user_id": uid})
                await update.message.reply_text("✅ تم تفعيل المستخدم.")
                try:
                    await context.bot.send_message(chat_id=uid, text="✅ تم تفعيل حسابك. أرسل /start.")
                except Exception:
                    pass
                return

            if action == "deny":
                db.ensure_user(uid)
                db.set_allowed(uid, False)
                db.admin_log(user_id, "deny_user", {"user_id": uid})
                await update.message.reply_text("✅ تم إلغاء تفعيل المستخدم.")
                return

            if action == "ban":
                db.ensure_user(uid)
                db.set_banned(uid, True)
                db.admin_log(user_id, "ban_user", {"user_id": uid})
                await update.message.reply_text("✅ تم حظر المستخدم.")
                try:
                    await context.bot.send_message(chat_id=uid, text="🚫 تم حظر حسابك.")
                except Exception:
                    pass
                return

            if action == "unban":
                db.ensure_user(uid)
                db.set_banned(uid, False)
                db.admin_log(user_id, "unban_user", {"user_id": uid})
                await update.message.reply_text("✅ تم فك حظر المستخدم.")
                try:
                    await context.bot.send_message(chat_id=uid, text="✅ تم فك الحظر عن حسابك.")
                except Exception:
                    pass
                return

        if action == "setprice":
            amt = money_ok(text)
            if amt is None:
                await update.message.reply_text("⛔ سعر غير صحيح.")
                return
            context.user_data.pop("admin_action", None)
            db.set_setting("price_usd", str(amt))
            db.admin_log(user_id, "set_price", {"price": amt})
            await update.message.reply_text(f"✅ تم تغيير السعر إلى {amt:.2f}$")
            return

        if action == "setlimit_uid":
            if not text.isdigit():
                await update.message.reply_text("⛔ أرسل ID صحيح.")
                return
            context.user_data["admin_uid"] = int(text)
            context.user_data["admin_action"] = "setlimit_val"
            await update.message.reply_text("📆 أرسل الحد اليومي الجديد (مثال: 5):")
            return

        if action == "setlimit_val":
            if not text.isdigit():
                await update.message.reply_text("⛔ أرسل رقم صحيح.")
                return
            limit = int(text)
            uid = context.user_data.pop("admin_uid")
            context.user_data.pop("admin_action", None)
            db.ensure_user(uid)
            db.set_daily_limit(uid, limit)
            db.admin_log(user_id, "set_daily_limit", {"user_id": uid, "limit": limit})
            await update.message.reply_text("✅ تم ضبط الحد اليومي.")
            return

        if action == "editstart":
            context.user_data.pop("admin_action", None)
            new_msg = text
            db.set_setting("start_message", new_msg)
            db.admin_log(user_id, "edit_start_message", {"len": len(new_msg)})
            await update.message.reply_text("✅ تم حفظ رسالة /start الجديدة.")
            return

        if action == "broadcast":
            context.user_data.pop("admin_action", None)
            msg = text

            # fetch all user ids
            conn = db._conn()  # internal usage
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM users WHERE is_banned=FALSE")
            user_ids = [int(r[0]) for r in cur.fetchall()]
            cur.close(); conn.close()

            sent = 0
            for uid in user_ids:
                try:
                    await context.bot.send_message(chat_id=uid, text=msg)
                    sent += 1
                except Exception:
                    pass

            db.admin_log(user_id, "broadcast", {"sent": sent, "len": len(msg)})
            await update.message.reply_text(f"✅ تم إرسال الرسالة إلى {sent} مستخدم.")
            return

    # Default: show start again
    await update.message.reply_text("اكتب /start لفتح القائمة.")


# ------------------- Startup checks -------------------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")
    if not ADMIN_IDS:
        raise RuntimeError("ADMIN_IDS is missing (comma-separated)")

    db.init_db()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
