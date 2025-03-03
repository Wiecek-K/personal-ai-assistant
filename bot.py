from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from openai import OpenAI
from os import getenv
from dotenv import load_dotenv
from collections import defaultdict
from cryptography.fernet import Fernet
from asyncio import create_task
import json
import base64
import aiohttp

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

# Supported image formats
SUPPORTED_FORMATS = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB - OpenAI limit


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
    await update.message.reply_text(
        "Hi! I'm your AI assistant! I can:\n"
        "1. Chat with you using GPT-4\n"
        "2. Analyze images you send\n"
        "3. Generate images using DALL-E (/generate)\n"
        "And I'll remember our conversation context!")


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


async def handle_image(update: Update, context: CallbackContext) -> None:
    """Handle image messages from users"""
    try:
        # Get the largest available photo
        photo = update.message.photo[-1]

        # Get file information
        file = await context.bot.get_file(photo.file_id)

        # Download the image
        async with aiohttp.ClientSession() as session:
            async with session.get(file.file_path) as response:
                if response.status != 200:
                    await update.message.reply_text("Sorry, I couldn't download the image.")
                    return

                # Check file size
                content = await response.read()
                if len(content) > MAX_IMAGE_SIZE:
                    await update.message.reply_text("The image is too large. Maximum size is 20MB.")
                    return

                # Convert to base64
                image_base64 = base64.b64encode(content).decode('utf-8')

                # Send to OpenAI for analysis
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "What's in this image? Please describe it in detail."},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_base64}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=500
                )

                # Get the response
                description = response.choices[0].message.content

                # Save to conversation history
                user_id = update.effective_user.id
                conversation_history[user_id].append(
                    {"role": "user", "content": "[User sent an image]"})
                conversation_history[user_id].append(
                    {"role": "assistant", "content": description})

                # Trim history if needed
                if len(conversation_history[user_id]) > MAX_HISTORY * 2:
                    conversation_history[user_id] = conversation_history[user_id][-MAX_HISTORY * 2:]

                # Save conversation history
                save_conversation_history()

                # Send the description back to user
                await update.message.reply_text(description)

    except Exception as e:
        await update.message.reply_text(f"Sorry, I couldn't analyze the image: {str(e)}")


async def handle_document(update: Update, context: CallbackContext) -> None:
    """Handle document messages that might be images"""
    try:
        if not update.message.document.mime_type in SUPPORTED_FORMATS:
            await update.message.reply_text(
                "Sorry, I can only analyze images in these formats: JPEG, PNG, GIF, WEBP")
            return

        # Get file information
        file = await context.bot.get_file(update.message.document.file_id)

        # Process the same way as photos
        async with aiohttp.ClientSession() as session:
            async with session.get(file.file_path) as response:
                if response.status != 200:
                    await update.message.reply_text("Sorry, I couldn't download the image.")
                    return

                content = await response.read()
                if len(content) > MAX_IMAGE_SIZE:
                    await update.message.reply_text("The image is too large. Maximum size is 20MB.")
                    return

                image_base64 = base64.b64encode(content).decode('utf-8')

                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "What's in this image? Please describe it in detail."},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_base64}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=500
                )

                description = response.choices[0].message.content

                # Save to conversation history
                user_id = update.effective_user.id
                conversation_history[user_id].append(
                    {"role": "user", "content": "[User sent an image]"})
                conversation_history[user_id].append(
                    {"role": "assistant", "content": description})

                if len(conversation_history[user_id]) > MAX_HISTORY * 2:
                    conversation_history[user_id] = conversation_history[user_id][-MAX_HISTORY * 2:]

                save_conversation_history()

                await update.message.reply_text(description)

    except Exception as e:
        await update.message.reply_text(f"Sorry, I couldn't analyze the image: {str(e)}")


async def generate_image(update: Update, context: CallbackContext) -> None:
    """Generate an image using DALL-E based on user's description"""
    async def process_image_generation(update: Update, prompt: str, processing_message):
        try:
            # Generate image using DALL-E
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1
            )

            # Get the URL of the generated image
            image_url = response.data[0].url

            # Download the image
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as img_response:
                    if img_response.status != 200:
                        await processing_message.edit_text(
                            "Sorry, I couldn't download the generated image.")
                        return

                    image_data = await img_response.read()

            # Save to conversation history
            user_id = update.effective_user.id
            conversation_history[user_id].append(
                {"role": "user", "content": f"[Generated image with prompt: {prompt}]"})

            # Send the image
            await update.message.reply_photo(
                photo=image_data,
                caption=f"🎨 Here's your generated image based on:\n\"{prompt}\""
            )

            # Delete the processing message
            await processing_message.delete()

        except Exception as e:
            await processing_message.edit_text(
                f"Sorry, I couldn't generate the image: {str(e)}")

    try:
        # Get the prompt from user's message
        prompt = ' '.join(context.args)

        if not prompt:
            await update.message.reply_text(
                "Please provide a description for the image you want to generate.\n"
                "Example: /generate a cute cat playing with a ball of yarn")
            return

        # Send a temporary message to show that we're working
        processing_message = await update.message.reply_text(
            "🎨 Generating your image... This might take a moment.")

        # Start image generation in a separate task
        create_task(process_image_generation(
            update, prompt, processing_message))

    except Exception as e:
        await update.message.reply_text(
            f"Sorry, an error occurred: {str(e)}")


app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("clear", clear_history))
app.add_handler(CommandHandler("generate", generate_image))
app.add_handler(MessageHandler(
    filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(MessageHandler(filters.PHOTO, handle_image))
app.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))

print("Bot started!")
app.run_polling()
