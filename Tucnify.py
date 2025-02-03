import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode

API_TOKEN = ' ' #Telegram Bot API token
GEMINI_API_KEY = ' ' #Gemini API key
GEMINI_API_URL = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}'

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

WELCOME_MESSAGE = """👋 *Hi! Tucnify is a free AI bot, you can ask it directly in the chat*"""

async def generate_gemini_response(prompt: str) -> str:
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(GEMINI_API_URL, json=payload, headers=headers) as response:
            if response.status != 200:
                return "⚠️ Error accessing the API"

            json_response = await response.json()
            try:
                return json_response['candidates'][0]['content']['parts'][0]['text']
            except (KeyError, IndexError):
                return "❌ Couldn't process the response"

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(WELCOME_MESSAGE, parse_mode=ParseMode.MARKDOWN)

@dp.message()
async def handle_message(message: types.Message):
    user_input = message.text

    await bot.send_chat_action(message.chat.id, 'typing')
    
    response = await generate_gemini_response(user_input)

    if len(response) > 4096:
        response = response[:4090] + "..."
    
    await message.answer(response, parse_mode=ParseMode.MARKDOWN)

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
