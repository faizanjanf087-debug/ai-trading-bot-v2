import asyncio
import logging

import certifi
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters)
from telegram.request import HTTPXRequest

from ai.deepseek_client import DeepSeekClient
from ai.memory import ChatMemory
from ai.speech import Transcriber
from ai.vision import ChartReader
from bot import handlers
from bot.notifier import TelegramNotifier
from config.settings import load_settings, mask_db_url
from data.budget import CreditBudget
from data.calendar import CalendarClient
from data.market_data import MarketData
from data.news import NewsClient
from data.providers import KrakenClient, TwelveDataClient
from db.alerts import AlertRepo
from db.chat import ChatRepo
from db.factory import open_database
from db.journal import JournalRepo
from db.kv import KV
from db.signals import SignalRepo
from db.users import UserRepo
from monitor.price_watcher import PriceWatcher
from monitor.scanner import Scanner
from services.analysis_service import AnalysisService
from services.approval import ApprovalService
from services.chat_service import ChatService
from services.container import Container
from services.discipline import DisciplineService
from services.media import MediaService
from services.signal_service import SignalService
from services.watchlist import Watchlist

log = logging.getLogger("main")


def build_container(settings) -> Container:
    db = open_database(settings)
    if settings.database_url:
        log.info("Database: Supabase/Postgres (%s)", mask_db_url(settings.database_url))
    else:
        log.info("Database: SQLite (%s)", settings.database_path)
    kv = KV(db)
    users = UserRepo(db)
    signal_repo = SignalRepo(db)
    journal = JournalRepo(db)
    alerts = AlertRepo(db)
    notifier = TelegramNotifier()

    budget = CreditBudget(kv, settings.td_per_minute, settings.td_per_day, settings.td_monitor_reserve)
    market = MarketData(TwelveDataClient(settings.twelvedata_key), KrakenClient(), budget)
    analysis = AnalysisService(market, settings.min_score, settings.counter_trend_extra)
    ai = DeepSeekClient(settings.deepseek_key, settings.deepseek_model)
    news = NewsClient()
    memory = ChatMemory(ChatRepo(db), ai)
    calendar = CalendarClient(kv, url=settings.calendar_url, enabled=settings.enable_calendar)
    discipline = DisciplineService(signal_repo, loss_streak_warn=settings.loss_streak_warn,
                                   daily_loss_limit_r=settings.daily_loss_limit_r,
                                   max_signals_per_day=settings.max_signals_per_day)
    chat = ChatService(ai, memory, analysis, news, signal_repo, calendar=calendar, discipline=discipline)
    speech = Transcriber(settings.stt_api_key, settings.stt_base_url, settings.stt_model)
    vision = ChartReader(settings.anthropic_api_key, settings.vision_model)
    media = MediaService(speech, vision, chat, settings.media_daily_limit)
    signal_service = SignalService(signal_repo, users, journal=journal)
    watchlist = Watchlist(kv, settings.watchlist)
    scanner = Scanner(settings, analysis, signal_service, users, ai, news, notifier.send, watchlist,
                      calendar=calendar)
    watcher = PriceWatcher(market, signal_service, alerts, notifier.send, budget)

    return Container(
        settings=settings, approval=ApprovalService(users, settings.owner_id), users=users,
        signal_repo=signal_repo, signal_service=signal_service, alerts=alerts, market=market,
        budget=budget, analysis=analysis, ai=ai, news=news, chat=chat, memory=memory,
        watchlist=watchlist, scanner=scanner, watcher=watcher, notifier=notifier, db=db, journal=journal,
        calendar=calendar, discipline=discipline, media=media, speech=speech, vision=vision,
    )


async def post_init(app: Application):
    c = app.bot_data["c"]
    c.notifier.bot = app.bot
    app.bot_data["tasks"] = [asyncio.create_task(c.watcher.run())]
    if c.settings.enable_scanner:
        app.bot_data["tasks"].append(asyncio.create_task(c.scanner.run()))
    if not c.settings.twelvedata_key:
        log.warning("TWELVEDATA_API_KEY set nahi: forex/gold ka data nahi aayega (crypto chalega).")
    if not c.settings.deepseek_key:
        log.warning("DEEPSEEK_API_KEY set nahi: AI chat/review band rahega.")
    log.info("Voice=%s Image=%s Calendar=%s", "ON" if c.speech.enabled else "OFF (STT_API_KEY nahi)",
             "ON" if c.vision.enabled else "OFF (ANTHROPIC_API_KEY nahi)", "ON" if c.settings.enable_calendar else "OFF")
    log.info("Bot shuru. Scanner=%s", c.settings.enable_scanner)


async def post_shutdown(app: Application):
    for t in app.bot_data.get("tasks", []):
        t.cancel()


def main():
    logging.basicConfig(format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO)
    # httpx har request ka URL log karta hai, jis mein bot token hota hai. Isay chup karwa do.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    settings = load_settings()
    container = build_container(settings)

    # Use certifi's maintained CA bundle for Telegram HTTPS requests.
    # Keep TLS certificate verification enabled for both API calls and long polling.
    telegram_request = HTTPXRequest(httpx_kwargs={"verify": certifi.where()})
    polling_request = HTTPXRequest(httpx_kwargs={"verify": certifi.where()})
    app = (Application.builder().token(settings.telegram_token)
           .request(telegram_request).get_updates_request(polling_request)
           .job_queue(None)  # This bot uses asyncio tasks, not PTB JobQueue/APScheduler.
           .post_init(post_init).post_shutdown(post_shutdown).build())
    app.bot_data["c"] = container

    commands = {
        "start": handlers.start, "help": handlers.help_command, "ping": handlers.ping,
        "users": handlers.users_list, "pending": handlers.pending_cmd, "approve": handlers.approve_cmd, "block": handlers.block_cmd,
        "watch": handlers.watch_cmd, "status": handlers.status_cmd, "backup": handlers.backup_cmd,
        "signal": handlers.signal_cmd, "analyze": handlers.analyze_cmd,
        "signals": handlers.signals_cmd, "history": handlers.history_cmd, "stats": handlers.stats_cmd,
        "report": handlers.report_cmd,
        "alert": handlers.alert_cmd, "alerts": handlers.alerts_cmd, "delalert": handlers.delalert_cmd,
        "watchlist": handlers.watchlist_cmd, "mute": handlers.mute_cmd, "unmute": handlers.unmute_cmd,
        "forget": handlers.forget_cmd,
        "news": handlers.news_cmd, "discipline": handlers.discipline_cmd, "event": handlers.event_cmd,
    }
    for name, fn in commands.items():
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(CallbackQueryHandler(handlers.approval_buttons, pattern=r"^(approve|reject):\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.chat_message))
    app.add_handler(MessageHandler(filters.Sticker.ALL, handlers.sticker_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handlers.voice_message))
    app.add_handler(MessageHandler(filters.PHOTO, handlers.photo_message))
    app.add_handler(MessageHandler(filters.Document.IMAGE, handlers.image_document_message))
    app.add_error_handler(handlers.on_error)

    app.run_polling()


if __name__ == "__main__":
    main()
