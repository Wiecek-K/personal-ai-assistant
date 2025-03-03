from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from openai import OpenAI
from os import getenv
from dotenv import load_dotenv
from collections import defaultdict
from cryptography.fernet import Fernet
import json
import base64

load_dotenv()
TOKEN = getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = getenv('OPENAI_API_KEY')
# Get or generate encryption key
ENCRYPTION_KEY = getenv('ENCRYPTION_KEY')
if not ENCRYPTION_KEY:
    # Generate a new key if not exists
    encryption_key = Fernet.generate_key()
    ENCRYPTION_KEY = base64.b64encode(encryption_key).decode('utf-8')
    print(
        f"Generated new encryption key. Please add this to your .env file:\nENCRYPTION_KEY={ENCRYPTION_KEY}")
else:
    # Decode the existing key
    encryption_key = base64.b64decode(ENCRYPTION_KEY.encode('utf-8'))

# Initialize encryption
fernet = Fernet(encryption_key)

if not TOKEN:
    raise ValueError("🚨 No token found! Check your .env file.")
if not OPENAI_API_KEY:
    raise ValueError("🚨 No OpenAI API key found! Check your .env file.")

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Maximum number of messages to keep in history per user
MAX_HISTORY = 10

# Dictionary to store conversation history for each user
conversation_history = defaultdict(list)


def save_conversation_history():
    """Save encrypted conversation history to a file"""
    try:
        # Convert defaultdict to regular dict for JSON serialization
        history_dict = {str(k): v for k, v in conversation_history.items()}
        # Convert to JSON string
        json_data = json.dumps(history_dict, ensure_ascii=False)
        # Encrypt the data
        encrypted_data = fernet.encrypt(json_data.encode('utf-8'))
        # Save to file
        with open('conversation_history.json', 'wb') as f:
            f.write(encrypted_data)
    except Exception as e:
        print(f"Error saving conversation history: {e}")


def load_conversation_history():
    """Load and decrypt conversation history from file"""
    try:
        with open('conversation_history.json', 'rb') as f:
            # Read encrypted data
            encrypted_data = f.read()
            # Decrypt the data
            decrypted_data = fernet.decrypt(encrypted_data)
            # Parse JSON
            history_dict = json.loads(decrypted_data.decode('utf-8'))
            # Convert back to defaultdict
            return defaultdict(list, {int(k): v for k, v in history_dict.items()})
    except FileNotFoundError:
        return defaultdict(list)
    except Exception as e:
        print(f"Error loading conversation history: {e}")
        return defaultdict(list)


# Load existing conversation history if available
conversation_history = load_conversation_history()


async def start(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    conversation_history[user_id] = []  # Reset history for this user
    await update.message.reply_text("Hi! I'm your bot! Send me a message and I'll respond using GPT-4! I'll remember our conversation context.")


async def handle_message(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    user_message = update.message.text

    try:
        # Prepare messages including conversation history
        messages = []

        # Add conversation history
        for msg in conversation_history[user_id]:
            messages.append(msg)

        # Add current message
        messages.append({"role": "user", "content": user_message})

        # Send message to OpenAI API with conversation history
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=messages
        )

        # Get the response from OpenAI
        ai_response = response.choices[0].message.content

        # Update conversation history
        conversation_history[user_id].append(
            {"role": "user", "content": user_message})
        conversation_history[user_id].append(
            {"role": "assistant", "content": ai_response})

        # Trim history if it exceeds maximum length
        # *2 because we store pairs of messages
        if len(conversation_history[user_id]) > MAX_HISTORY * 2:
            conversation_history[user_id] = conversation_history[user_id][-MAX_HISTORY * 2:]

        # Save updated conversation history
        save_conversation_history()

        # Send the response back to the user
        await update.message.reply_text(ai_response)
    except Exception as e:
        await update.message.reply_text(f"Sorry, an error occurred: {str(e)}")


async def clear_history(update: Update, context: CallbackContext) -> None:
    """Command to clear conversation history for the current user"""
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    save_conversation_history()
    await update.message.reply_text("Conversation history has been cleared!")

app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("clear", clear_history))
app.add_handler(MessageHandler(
    filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot started!")
app.run_polling()
