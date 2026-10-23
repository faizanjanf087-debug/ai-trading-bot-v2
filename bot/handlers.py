"""Telegram handlers. Yahan sirf Telegram ka kaam hai; asal logic services/ mein hai."""
import asyncio
import functools
import io
import json
import logging
import os
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from ai import prompts
from ai.deepseek_client import AIError
from config.markets import MODES, SYMBOLS, resolve_symbol
from data.base import BudgetExhausted, DataError
from data.sessions import forex_open
from services import approval as ap
from services import report
from services import formatter
from services.intents import route

log = logging.getLogger(__name__)
MAX_ALERTS_PER_USER = 10


def C(context: ContextTypes.DEFAULT_TYPE):
    """Services ka container."""
    return context.application.bot_data["c"]


def require_approved(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user is None or not C(context).approval.is_approved(user.id):
            await update.effective_message.reply_text(
                "Aap approved nahi hain. Pehle /start karke access ki request bhejein."
            )
            return
        return await func(update, context)

    return wrapper


def require_owner(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user is None or not C(context).approval.is_owner(user.id):
            await update.effective_message.reply_text("Yeh command sirf owner ke liye hai.")
            return
        return await func(update, context)

    return wrapper


# ---------- Access / approval ----------

def _approval_keyboard(user_id: int):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve:{user_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject:{user_id}"),
    ]])


async def _send_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = C(context).users.list_by_status("pending")
    if not pending:
        await update.message.reply_text("Abhi koi pending user nahi. Naya user /start karega to yahan request aa jayegi.")
        return
    for u in pending:
        name = u["full_name"] + (f" (@{u['username']})" if u["username"] else "")
        await update.message.reply_text(f"Pending: {name}\nID: {u['telegram_id']}",
                                        reply_markup=_approval_keyboard(u["telegram_id"]))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    svc = C(context).approval
    result = svc.request_access(user.id, user.username, user.full_name)

    if result == ap.APPROVED:
        await update.message.reply_text("Aap approved hain ✅ /help se commands dekhein, ya seedha sawal likhein.")
    elif result == ap.BLOCKED:
        await update.message.reply_text("Aap ko is bot ka access nahi hai.")
    elif result == ap.ALREADY_PENDING:
        await update.message.reply_text("Aap ki request pehle se bheji ja chuki hai. Owner ke approve karne ka intezar karein.")
    elif result == ap.NEW_REQUEST:
        await update.message.reply_text("Access ki request owner ko bhej di gayi hai. Approve hone par aap ko message aayega.")
        name = user.full_name + (f" (@{user.username})" if user.username else "")
        keyboard = _approval_keyboard(user.id)
        await context.bot.send_message(
            chat_id=svc.owner_id, text=f"Naya user access maang raha hai:\n{name}\nID: {user.id}",
            reply_markup=keyboard,
        )


async def approval_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    svc = C(context).approval
    if not svc.is_owner(query.from_user.id):
        await query.answer("Sirf owner kar sakta hai.", show_alert=True)
        return
    await query.answer()

    action, _, raw_id = (query.data or "").partition(":")
    if not raw_id.isdigit() or action not in ("approve", "reject"):
        return
    target = int(raw_id)

    if action == "approve":
        ok = svc.approve(target)
        text = f"✅ User {target} approve ho gaya." if ok else "User nahi mila."
        if ok:
            await _notify(context, target, "Aap ko access mil gaya hai ✅. /help se shuru karein.")
    else:
        ok = svc.reject(target)
        text = f"❌ User {target} reject (block) ho gaya." if ok else "User nahi mila."
        if ok:
            await _notify(context, target, "Aap ki request reject kar di gayi hai.")
    await query.edit_message_text(text)


async def _notify(context, user_id: int, text: str):
    try:
        await context.bot.send_message(chat_id=user_id, text=text)
    except Exception:
        log.warning("User %s ko message nahi bheja ja saka", user_id, exc_info=True)


HELP_USER = """Commands:
/signal <pair> [scalp|intraday] - naya trade setup (limit/market, SL, TP)
/analyze <pair> [scalp|intraday] - analysis + AI raay
/signals - aap ke open signals
/history - aakhri band signals
/stats - aap ke signals ka hisaab
/report - tafseeli report (kaunsa pattern/pair/AI raay kitni chali)
/alert <pair> <price> - price alert
/alerts - aap ke alerts   |   /delalert <id>
/watchlist - scanner kin pairs ko dekh raha hai
/mute  /unmute - auto signals band/chalu
/forget - AI ki yaad saaf karein
/ping - bot chal raha hai?

Pairs: XAUUSD, EURUSD, GBPUSD, USDJPY, GBPJPY, AUDUSD, USDCAD, BTCUSD, ETHUSD, SOLUSD
Aap seedha sawal bhi likh sakte hain (jaise "gold ka kya scene hai?") - AI jawab dega.
⚠️ Yeh financial advice nahi hai."""

HELP_OWNER = """
Owner commands:
/users - sab users
/pending - approval ke intezar mein users (buttons ke saath)
/approve <id>   /block <id>
/watch add <pair>  |  /watch remove <pair>
/status - bot ki halat, credits, open signals
/backup - database ki copy"""


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "/start - access ki request\n\n" + HELP_USER
    if C(context).approval.is_owner(update.effective_user.id):
        text += "\n" + HELP_OWNER
    await update.message.reply_text(text)


@require_approved
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong 🏓")


# ---------- Owner ----------

@require_owner
async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = C(context).users.list_by_status()
    if not users:
        await update.message.reply_text("Abhi koi user nahi.")
        return
    lines = [f"{u['telegram_id']} | {u['full_name']} | @{u['username'] or '-'} | {u['status']}"
             + (" | muted" if u.get("muted") else "") for u in users]
    await update.message.reply_text("\n".join(lines))


def _parse_id(context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].isdigit():
        return int(context.args[0])
    return None


@require_owner
async def pending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_pending(update, context)


@require_owner
async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = _parse_id(context)
    if target is None:
        await update.message.reply_text("Istemal: /approve <user_id>")
        return
    ok = C(context).approval.approve(target)
    await update.message.reply_text("Approve ho gaya ✅" if ok else "User nahi mila.")
    if ok:
        await _notify(context, target, "Aap ko access mil gaya hai ✅. /help se shuru karein.")


@require_owner
async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = _parse_id(context)
    if target is None:
        await update.message.reply_text("Istemal: /block <user_id>")
        return
    ok = C(context).approval.block(target)
    await update.message.reply_text("Block ho gaya ⛔" if ok else "User nahi mila (ya owner hai).")


@require_owner
async def watch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if len(args) != 2 or args[0] not in ("add", "remove"):
        await update.message.reply_text("Istemal: /watch add XAUUSD  ya  /watch remove XAUUSD")
        return
    sym = resolve_symbol(args[1])
    if not sym:
        await update.message.reply_text("Yeh pair support nahi hota. /help mein list dekhein.")
        return
    wl = C(context).watchlist
    ok = wl.add(sym) if args[0] == "add" else wl.remove(sym)
    await update.message.reply_text(("Ho gaya ✅ " if ok else "Koi tabdeeli nahi (pehle se aisa hi hai). ") + "Watchlist: " + ", ".join(wl.get()))


@require_owner
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = C(context)
    open_sigs = c.signal_repo.list_open()
    st = c.signal_repo.stats()
    lines = [
        "🤖 Bot status",
        f"Scanner: {'ON' if c.settings.enable_scanner else 'OFF'} | AI: {'ON' if c.ai.enabled else 'OFF'}"
        f"{' (veto)' if c.settings.ai_veto else ''}",
        f"Twelve Data credits aaj: {c.budget.used_today()}/{c.budget.per_day} "
        f"(baqi {c.budget.remaining_today()})" + ("" if c.settings.twelvedata_key else "  ⚠️ key set nahi"),
        f"Watchlist: {', '.join(c.watchlist.get())}",
        f"Open signals: {len(open_sigs)}",
        f"Approved users: {len(c.users.list_by_status('approved'))} | Pending: {len(c.users.list_by_status('pending'))}",
        formatter.format_stats(st, "Sab signals").replace("📊 ", "", 1),
    ]
    await update.message.reply_text("\n".join(lines))


@require_owner
async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = C(context).db
    if hasattr(db, "export_all"):            # Supabase/Postgres: poora data JSON file mein
        data = await asyncio.to_thread(db.export_all)
        buf = io.BytesIO(json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"))
        name = time.strftime("bot-backup-%Y%m%d-%H%M.json", time.gmtime())
        await update.message.reply_document(buf, filename=name, caption="Database backup (JSON)")
        return
    path = db.path
    if path == ":memory:" or not os.path.exists(path):
        await update.message.reply_text("Database file nahi mili.")
        return
    with open(path, "rb") as f:
        await update.message.reply_document(f, filename=os.path.basename(path), caption="Database backup")


# ---------- Signals / analysis ----------

def _parse_symbol_mode(args):
    sym = resolve_symbol(args[0]) if args else None
    mode = "scalp"
    if len(args) > 1:
        mode = args[1].lower()
    return sym, mode


async def _typing(update: Update):
    try:
        await update.effective_chat.send_action(ChatAction.TYPING)
    except Exception:
        pass


async def _run_analysis(update, context, sym, mode):
    """(analysis, setup) ya None (user ko error message bhej diya gaya)."""
    c = C(context)
    if SYMBOLS[sym]["kind"] == "forex" and not forex_open(c.market.clock()):
        await update.message.reply_text("Forex market abhi band hai (weekend). Crypto pairs 24/7 chalte hain.")
        return None
    await _typing(update)
    try:
        a, setup = await asyncio.to_thread(c.analysis.run_fresh, sym, mode, "normal")
    except BudgetExhausted:
        await update.message.reply_text("Twelve Data ke free credits abhi khatam/limit par hain. Thori der baad try karein, ya crypto pair use karein.")
        return None
    except DataError as e:
        await update.message.reply_text(f"Data nahi mil saka: {e}")
        return None
    if a is None:
        await update.message.reply_text("Analysis ke liye candles kam hain.")
        return None
    return a, setup


async def _do_signal(update: Update, context: ContextTypes.DEFAULT_TYPE, sym: str, mode: str):
    """Ek pair ka tracked signal banana (command aur seedhe text dono yahi use karte hain)."""
    c = C(context)
    res = await _run_analysis(update, context, sym, mode)
    if res is None:
        return
    a, setup = res
    if not setup:
        await update.message.reply_text(formatter.format_analysis(a, None))
        return
    uid = update.effective_user.id
    if not c.signal_service.can_create(sym, setup["side"], mode):
        await update.message.reply_text(f"{sym} par {setup['side']} ka signal pehle se open hai. /signals dekhein.")
        return
    sig = c.signal_service.create(setup, "user", [uid], owner_id=uid, analysis=a)
    await update.message.reply_text(formatter.format_signal(sig))


async def _do_best_signal(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str):
    """Pair na bataya ho to watchlist scan karke sab se behtar setup dena."""
    c = C(context)
    await _typing(update)
    await update.message.reply_text("Watchlist scan kar raha hoon, thora intezar karein...")
    best, best_a, scanned, skipped = None, None, [], []
    now = c.market.clock()
    for sym in c.watchlist.get():
        if SYMBOLS[sym]["kind"] == "forex" and not forex_open(now):
            skipped.append(sym)
            continue
        try:
            a, setup = await asyncio.to_thread(c.analysis.run_fresh, sym, mode, "normal")
        except (BudgetExhausted, DataError):
            skipped.append(sym)
            continue
        scanned.append(sym)
        if setup and c.signal_service.can_create(sym, setup["side"], mode):
            if best is None or setup["score"] > best["score"]:
                best, best_a = setup, a
    uid = update.effective_user.id
    if best:
        sig = c.signal_service.create(best, "user", [uid], owner_id=uid, analysis=best_a)
        await update.message.reply_text(formatter.format_signal(sig))
        return
    msg = "Abhi koi saaf signal nahi mila (score kam ya RR kharab). Scan kiye: " + (", ".join(scanned) or "koi nahi")
    if skipped:
        msg += "\nChhode (market band/credits/data): " + ", ".join(skipped)
    await update.message.reply_text(msg)


@require_approved
async def signal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await _do_best_signal(update, context, "scalp")
        return
    sym, mode = _parse_symbol_mode(context.args)
    if not sym or mode not in MODES:
        await update.message.reply_text("Istemal: /signal XAUUSD [scalp|intraday]  (ya sirf /signal)")
        return
    await _do_signal(update, context, sym, mode)


@require_approved
async def analyze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = C(context)
    sym, mode = _parse_symbol_mode(context.args or [])
    if not sym or mode not in MODES:
        await update.message.reply_text("Istemal: /analyze XAUUSD [scalp|intraday]")
        return
    res = await _run_analysis(update, context, sym, mode)
    if res is None:
        return
    a, setup = res
    await update.message.reply_text(formatter.format_analysis(a, setup))
    if c.ai.enabled:
        try:
            news = await asyncio.to_thread(c.news.context, SYMBOLS[sym]["kind"])
            text = await asyncio.to_thread(c.ai.chat, prompts.analysis_prompt(a, setup, news))
            await update.message.reply_text("🤖 " + text)
        except AIError:
            await update.message.reply_text("AI abhi jawab nahi de saka.")


@require_approved
async def signals_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sigs = C(context).signal_repo.open_for_user(update.effective_user.id)
    if not sigs:
        await update.message.reply_text("Aap ka koi open signal nahi.")
        return
    await update.message.reply_text("📂 Open signals\n" + "\n".join(formatter.format_signal_line(s) for s in sigs))


@require_approved
async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sigs = C(context).signal_repo.closed_for_user(update.effective_user.id, 10)
    if not sigs:
        await update.message.reply_text("Abhi koi band signal nahi.")
        return
    await update.message.reply_text("🗂 Aakhri band signals\n" + "\n".join(formatter.format_signal_line(s) for s in sigs))


@require_approved
async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Band signals ka tafseeli hisaab: kaunsa factor/pair/AI raay kitni chali. Owner ko sab ka, baqi ko apna."""
    c = C(context)
    uid = update.effective_user.id
    owner = c.approval.is_owner(uid)
    if c.journal is None:
        await update.message.reply_text("Journal abhi chalu nahi hai.")
        return
    rep = report.build(c.journal.closed_rows(None if owner else uid))
    await update.message.reply_text(formatter.format_report(rep, "Sab signals" if owner else "Aap ke signals"))


@require_approved
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(formatter.format_stats(C(context).signal_repo.stats(update.effective_user.id)))


# ---------- Alerts ----------

@require_approved
async def alert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = C(context)
    args = context.args or []
    sym = resolve_symbol(args[0]) if args else None
    try:
        target = float(args[1]) if len(args) > 1 else None
    except ValueError:
        target = None
    if not sym or target is None or target <= 0:
        await update.message.reply_text("Istemal: /alert XAUUSD 2650.5")
        return
    uid = update.effective_user.id
    if c.alerts.count_for_user(uid) >= MAX_ALERTS_PER_USER:
        await update.message.reply_text(f"Aap {MAX_ALERTS_PER_USER} alerts tak laga sakte hain. /delalert se purane hataein.")
        return
    try:
        df = await asyncio.to_thread(c.market.get_recent_1m, sym, 3, "normal")
    except BudgetExhausted:
        await update.message.reply_text("Credits abhi limit par hain, thori der baad try karein.")
        return
    except DataError as e:
        await update.message.reply_text(f"Maujooda price nahi mil saki: {e}")
        return
    price = float(df["close"].iloc[-1])
    direction = "above" if target > price else "below"
    aid = c.alerts.create(uid, sym, target, direction, int(c.market.clock()))
    await update.message.reply_text(
        f"🔔 Alert #{aid} set: {sym} {formatter.px(sym, target)} "
        f"{'se upar' if direction == 'above' else 'se neeche'} jane par (abhi {formatter.px(sym, price)})"
    )


@require_approved
async def alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = C(context).alerts.for_user(update.effective_user.id)
    if not rows:
        await update.message.reply_text("Aap ka koi active alert nahi.")
        return
    await update.message.reply_text("🔔 Alerts\n" + "\n".join(
        f"#{a['id']} {a['symbol']} {formatter.px(a['symbol'], a['price'])} ({a['direction']})" for a in rows))


@require_approved
async def delalert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    aid = _parse_id(context)
    if aid is None:
        await update.message.reply_text("Istemal: /delalert <id>")
        return
    ok = C(context).alerts.delete(aid, update.effective_user.id)
    await update.message.reply_text("Alert hata diya ✅" if ok else "Aisa alert nahi mila.")


# ---------- Misc ----------

@require_approved
async def watchlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👀 Scanner in pairs ko dekh raha hai:\n" + ", ".join(C(context).watchlist.get()))


@require_approved
async def mute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    C(context).users.set_muted(update.effective_user.id, True)
    await update.message.reply_text("🔕 Auto signals band. Aap ke apne signals ke alerts phir bhi aayenge. /unmute se wapas chalu.")


@require_approved
async def unmute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    C(context).users.set_muted(update.effective_user.id, False)
    await update.message.reply_text("🔔 Auto signals chalu.")


@require_approved
async def forget_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    C(context).memory.repo.clear(update.effective_user.id)
    await update.message.reply_text("AI ki yaad saaf kar di ✅")


async def _send_my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """"Total status batao" / "mera record": database ke asli figures (AI ka andaza nahi)."""
    c = C(context)
    uid = update.effective_user.id
    if c.journal is not None:
        text = formatter.format_report(report.build(c.journal.closed_rows(uid)), "Aap ke signals")
    else:
        text = formatter.format_stats(c.signal_repo.stats(uid), "Aap ke signals")
    text += f"\n\nAbhi open signals: {len(c.signal_repo.open_for_user(uid))}"
    await update.message.reply_text(text)


@require_approved
async def chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text:
        return
    c = C(context)
    uid = update.effective_user.id
    intent = route(text, is_owner=c.approval.is_owner(uid))
    if intent.kind == "pending":      # owner: "koi naya user aya?" (AI ko in cheezon ka pata nahi hota)
        await _send_pending(update, context)
        return
    if intent.kind == "stats":        # "total status batao" / "mera record" -> database se asli hisaab
        await _send_my_stats(update, context)
        return
    if intent.kind == "help":
        await help_command(update, context)
        return
    if intent.kind == "status":       # "tp hit howa?" / "jo signal diya uska kya hua" -> database se asli jawab
        sigs = c.signal_repo.open_for_user(uid) + c.signal_repo.closed_for_user(uid, 3)
        events = {s["id"]: c.signal_repo.events(s["id"]) for s in sigs}
        await update.message.reply_text(formatter.format_my_signals(sigs, events))
        return
    if intent.kind == "signal":       # "xauusd ka signal do" / "koi signal do" -> asli, tracked signal
        if intent.symbols:
            await _do_signal(update, context, intent.symbols[0], intent.mode)
        else:
            await _do_best_signal(update, context, intent.mode)
        return
    await _typing(update)
    reply = await c.chat.reply(uid, text[:2000], hint=intent.hint)
    await update.message.reply_text(reply[:4000])


async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    log.error("Handler error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("Kuch masla aa gaya, thori der baad dobara try karein.")
        except Exception:
            pass
