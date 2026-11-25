# Telegram setup

Telegram integration is optional. The backend uses the official Telegram Bot API through the open source `python-telegram-bot` package. It sends notifications and accepts commands only from the configured chat ID. The bot token and chat ID stay in the backend environment and are never returned by the API.

## Configure the bot

1. In Telegram, create a bot with **@BotFather** and copy its token.
2. Start a private chat with your bot and send `/start`.
3. Obtain your chat ID from the bot's update information using a trusted Telegram client. Do not paste the bot token into a public issue, dashboard, or source file.
4. Add these values to the private environment used by the backend:

   ```dotenv
   TELEGRAM_ENABLED=true
   TELEGRAM_BOT_TOKEN=<private bot token>
   TELEGRAM_CHAT_ID=<authorized numeric chat ID>
   ```

5. Restart the desktop app so it reloads private environment settings. Open **Autonomous** and confirm Telegram shows configured. Use **Send Telegram test** only when you want the backend to deliver an actual test message.
6. In **Settings**, enable Telegram and choose the notification categories. The Telegram bot can respond to `/status`, `/pause`, `/resume`, `/positions`, `/balance`, `/performance`, `/learning`, and `/help` from the authorized chat. `/pause` stops new entries while the engine keeps monitoring open paper positions.

Autonomous orders remain simulation-only. Telegram commands cannot enable real-money execution. If either credential is missing, Telegram stays unavailable and the application continues without it.
