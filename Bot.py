import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode

DEFAULT_API_TOKEN = ' '  # Telegram Bot API Token
DEFAULT_GEMINI_KEY = ' '  # Gemini API Key

API_TOKEN = DEFAULT_API_TOKEN
GEMINI_API_KEY = DEFAULT_GEMINI_KEY

MESSAGES = {
    'welcome': """👋 *Hi! Tucnify is a free AI bot, you can ask it directly in the chat*""",
    'no_api_key': "⚠️ Error: Gemini API key not set",
    'api_error': "⚠️ Error accessing the API",
    'process_error': "❌ Couldn't process the response"
}

def get_gemini_url():
    return f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}'

bot = None
dp = Dispatcher()

async def generate_gemini_response(prompt: str) -> str:
    if not GEMINI_API_KEY:
        return MESSAGES['no_api_key']
        
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(get_gemini_url(), json=payload, headers=headers) as response:
            if response.status != 200:
                return MESSAGES['api_error']

            json_response = await response.json()
            try:
                return json_response['candidates'][0]['content']['parts'][0]['text']
            except (KeyError, IndexError):
                return MESSAGES['process_error']

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(MESSAGES['welcome'], parse_mode=ParseMode.MARKDOWN)

@dp.message()
async def handle_message(message: types.Message):
    user_input = message.text
    await bot.send_chat_action(message.chat.id, 'typing')
    response = await generate_gemini_response(user_input)
    if len(response) > 4096:
        response = response[:4090] + "..."
    await message.answer(response, parse_mode=ParseMode.MARKDOWN)

async def main():
    global bot
    
    if __name__ == '__main__':
        if not DEFAULT_API_TOKEN:
            print("Error: Please set DEFAULT_API_TOKEN before running directly")
            return
        bot = Bot(token=DEFAULT_API_TOKEN)
    else:
        bot = Bot(token=API_TOKEN)
    
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
