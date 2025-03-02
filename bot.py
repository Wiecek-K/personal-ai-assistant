from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

from os import getenv
from dotenv import load_dotenv

load_dotenv()
TOKEN = getenv('TELEGRAM_BOT_TOKEN')


async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Siema! Jestem Twoim botem!")


async def echo(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text(update.message.text)

app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

print("Bot wystartował!")
app.run_polling()
