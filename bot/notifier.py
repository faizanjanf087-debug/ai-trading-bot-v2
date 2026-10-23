class TelegramNotifier:
    """Background tasks (scanner/monitor) ko Telegram message bhejne ka raasta."""

    def __init__(self):
        self.bot = None

    async def send(self, user_id: int, text: str) -> None:
        if self.bot is None:
            return
        await self.bot.send_message(chat_id=user_id, text=text)
