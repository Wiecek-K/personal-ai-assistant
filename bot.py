from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from openai import OpenAI
from os import getenv
from dotenv import load_dotenv

load_dotenv()
TOKEN = getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = getenv('OPENAI_API_KEY')

if not TOKEN:
    raise ValueError("🚨 No token found! Check your .env file.")
if not OPENAI_API_KEY:
    raise ValueError("🚨 No OpenAI API key found! Check your .env file.")

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)


async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Hi! I'm your bot! Send me a message and I'll respond using GPT-4!")


async def handle_message(update: Update, context: CallbackContext) -> None:
    user_message = update.message.text

    try:
        # Send message to OpenAI API
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )

        # Get the response from OpenAI
        ai_response = response.choices[0].message.content

        # Send the response back to the user
        await update.message.reply_text(ai_response)
    except Exception as e:
        await update.message.reply_text(f"Sorry, an error occurred: {str(e)}")

app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(
    filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot started!")
app.run_polling()
