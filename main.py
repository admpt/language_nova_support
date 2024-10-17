import asyncio
import logging
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import Router

from config import API_TOKEN, ADMIN_ID

# Настройка логирования
logging.basicConfig(level=logging.INFO)

from aiogram.client.session.aiohttp import AiohttpSession

session = AiohttpSession(proxy="http://proxy.server:3128")
bot = Bot(token=API_TOKEN, session=session)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# Определение состояний
class FeedbackStates(StatesGroup):
    waiting_for_question = State()


# Создаем маршрутизатор
router = Router()


@router.message(Command('start'))
async def cmd_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Приветствую! Я бот поддержки Language Nova. Здесь вы можете получить помощь по вопросам, связанным с использованием нашего сервиса. Мы готовы ответить на ваши запросы и предоставить нужную информацию.")
    await state.set_state(FeedbackStates.waiting_for_question.state)


@router.message(FeedbackStates.waiting_for_question)
async def process_question(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    question = message.text

    # Сохраняем вопрос в БД
    async with aiosqlite.connect('questions.db') as db:
        async with db.execute('INSERT INTO questions (user_id, question, answered) VALUES (?, ?, ?)',
                              (user_id, question, 0)) as cursor:
            await db.commit()
            question_id = cursor.lastrowid  # Получаем ID последней вставленной строки

    # Отправляем вопрос администратору в нужном формате
    await bot.send_message(
        ADMIN_ID,
        f"Сообщение от пользователя <a href='tg://user?id={user_id}'>{message.from_user.full_name}</a> (ID: {question_id}):\n{question}",
        parse_mode='HTML'
    )

    await message.answer("<b>Ваш вопрос в процессе обработки.</b>\n• Пожалуйста, ожидайте ответ в течение 24 часов.\n• Если по истечении этого времени ответа не будет, попробуйте ещё раз", parse_mode='HTML')


@router.message(lambda message: message.from_user.id == ADMIN_ID)
async def process_answer(message: types.Message):
    text_parts = message.text.split('. ', 1)  # Разделяем текст на ID и ответ
    if len(text_parts) == 2:
        question_id, answer_text = text_parts
        question_id = question_id.strip()

        async with aiosqlite.connect('questions.db') as db:
            # Находим вопрос по ID
            async with db.execute('SELECT user_id FROM questions WHERE id = ? AND answered = 0',
                                  (question_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    user_id = row[0]
                    # Отправляем ответ пользователю
                    await bot.send_message(user_id, answer_text)

                    # Обновляем статус вопроса на "отвечен"
                    await db.execute('UPDATE questions SET answered = 1 WHERE id = ?', (question_id,))
                    await db.commit()
                    await message.answer("Ответ отправлен пользователю.")
                else:
                    await message.answer("Вопрос с таким ID не найден или уже был отвечен.")
    else:
        await message.answer("Пожалуйста, укажите ID вопроса в формате 'ID. Ответ'.")


@router.message()
async def forward_user_message(message: types.Message):
    # Игнорируем сообщения от администратора
    if message.from_user.id == ADMIN_ID:
        return

    # Пересылаем сообщения от пользователей администратору
    user_id = message.from_user.id
    user_message = message.text

    # Сохраняем вопрос в БД
    async with aiosqlite.connect('questions.db') as db:
        async with db.execute('INSERT INTO questions (user_id, question, answered) VALUES (?, ?, ?)',
                              (user_id, user_message, 0)) as cursor:
            await db.commit()
            question_id = cursor.lastrowid  # Получаем ID последней вставленной строки

    await bot.send_message(
        ADMIN_ID,
        f"Сообщение от пользователя <a href='tg://user?id={user_id}'>{message.from_user.full_name}</a> (ID: {question_id}):\n{user_message}",
        parse_mode='HTML'
    )
    # Уведомляем пользователя о том, что его сообщение обрабатывается
    await message.answer("<b>Ваш вопрос в процессе обработки.</b>\n• Пожалуйста, ожидайте ответ в течение 24 часов.\n• Если по истечении этого времени ответа не будет, попробуйте ещё раз", parse_mode='HTML')

# Создаем или открываем базу данных
async def db_setup():
    async with aiosqlite.connect('questions.db') as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            answered BOOLEAN NOT NULL DEFAULT 0
        )''')
        await db.commit()


# Запуск бота
async def main() -> None:
    await db_setup()  # Настройка БД
    dp.include_router(router)  # Включаем маршрутизатор
    logging.info("Bot is starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
