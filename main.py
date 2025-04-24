from db_init import create_tables
create_tables()

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.markdown import hbold
import psycopg2
import os
import asyncio

import os
TOKEN = os.getenv("BOT_TOKEN")
'YOUR_BOT_TOKEN'
bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

role_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="Клиент")],
    [KeyboardButton(text="Хозяин квартиры")]
], resize_keyboard=True)

class RegisterUser(StatesGroup):
    choosing_role = State()

class AddAd(StatesGroup):
    description = State()
    price = State()
    district = State()
    rooms = State()
    photo = State()

def add_user_to_db(telegram_id: int, role: str):
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (user_id, role) VALUES (%s, %s)", (user_id, role))
    cursor.execute("""
        INSERT INTO users (telegram_id, role)
        VALUES (%s, %s)
        ON CONFLICT (telegram_id) DO NOTHING
    """, (telegram_id, role))
    conn.commit()
    conn.close()

@dp.message(F.text == "/start")
async def start_cmd(message: Message, state: FSMContext):
    await state.set_state(RegisterUser.choosing_role)
    await message.answer("Привет! Кто вы?", reply_markup=role_kb)

@dp.message(RegisterUser.choosing_role)
async def handle_role_choice(message: Message, state: FSMContext):
    role_text = message.text.lower()
    if role_text in ["клиент", "хозяин квартиры"]:
        role = "client" if role_text == "клиент" else "owner"
        add_user_to_db(message.from_user.id, role)
        await message.answer(f"Вы зарегистрированы как {hbold(role_text)}.", reply_markup=types.ReplyKeyboardRemove())
        await state.clear()
    else:
        await message.answer("Пожалуйста, выберите один из вариантов на клавиатуре.")

@dp.message(F.text == "/add")
async def start_add_ad(message: Message, state: FSMContext):
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE telegram_id = ?", (message.from_user.id,))
    row = cursor.fetchone()
    conn.close()

    if not row or row[0] != "owner":
        await message.answer("Эта команда доступна только для хозяев квартир.")
        return

    await state.set_state(AddAd.description)
    await message.answer("Введите описание квартиры:")

@dp.message(AddAd.description)
async def get_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(AddAd.price)
    await message.answer("Укажите цену (в рублях):")

@dp.message(AddAd.price)
async def get_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите число.")
        return
    await state.update_data(price=int(message.text))
    await state.set_state(AddAd.district)
    await message.answer("Укажите район:")

@dp.message(AddAd.district)
async def get_district(message: Message, state: FSMContext):
    await state.update_data(district=message.text)
    await state.set_state(AddAd.rooms)
    await message.answer("Сколько комнат?")

@dp.message(AddAd.rooms)
async def get_rooms(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите число.")
        return
    await state.update_data(rooms=int(message.text))
    await state.set_state(AddAd.photo)
    await message.answer("Отправьте фото квартиры:")

@dp.message(AddAd.photo, F.photo)
async def get_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    data = await state.get_data()

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (message.from_user.id,))
    owner_row = cursor.fetchone()
    if owner_row:
        cursor.execute("""
            INSERT INTO ads (owner_id, description, price, district, rooms, photo_file_id, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """, (
            owner_row[0],
            data["description"],
            data["price"],
            data["district"],
            data["rooms"],
            photo_id
        ))
        conn.commit()
    conn.close()

    await message.answer("Объявление отправлено на модерацию. Спасибо!")
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

MODERATOR_ID = 424834337  # Telegram ID владельца

@dp.message(F.text == "/moderate")
async def moderate_ads(message: Message):
    if message.from_user.id != MODERATOR_ID:
        await message.answer("Доступ запрещён.")
        return

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ads.id, description, price, district, rooms, photo_file_id
        FROM ads
        WHERE status = 'pending'
        ORDER BY created_at ASC
        LIMIT 1
    """)
    ad = cursor.fetchone()
    conn.close()

    if not ad:
        await message.answer("Нет новых объявлений для модерации.")
        return

    ad_id, desc, price, district, rooms, photo_id = ad

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{ad_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{ad_id}")]
    ])

    text = f"<b>Описание:</b> {desc}\n<b>Цена:</b> {price} руб.\n<b>Район:</b> {district}\n<b>Комнат:</b> {rooms}"
    await message.answer_photo(photo_id, caption=text, reply_markup=kb)

@dp.callback_query(F.data.startswith("approve_") | F.data.startswith("reject_"))
async def handle_moderation_callback(call: CallbackQuery):
    action, ad_id = call.data.split("_")
    status = "approved" if action == "approve" else "rejected"

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cursor = conn.cursor()
    cursor.execute("UPDATE ads SET status = ? WHERE id = ?", (status, ad_id))
    conn.commit()
    conn.close()

    await call.message.edit_reply_markup()
    await call.message.answer(f"Объявление {status.upper()}")

class SearchAd(StatesGroup):
    max_price = State()
    district = State()
    rooms = State()

@dp.message(F.text == "/search")
async def start_search(message: Message, state: FSMContext):
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE telegram_id = ?", (message.from_user.id,))
    row = cursor.fetchone()
    conn.close()

    if not row or row[0] != "client":
        await message.answer("Эта команда доступна только для клиентов.")
        return

    await state.set_state(SearchAd.max_price)
    await message.answer("Введите максимальную цену (в рублях):")

@dp.message(SearchAd.max_price)
async def search_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите число.")
        return
    await state.update_data(max_price=int(message.text))
    await state.set_state(SearchAd.district)
    await message.answer("Введите желаемый район (или 'любой'):")

@dp.message(SearchAd.district)
async def search_district(message: Message, state: FSMContext):
    await state.update_data(district=message.text.strip())
    await state.set_state(SearchAd.rooms)
    await message.answer("Введите количество комнат (или 'любое'):")

@dp.message(SearchAd.rooms)
async def search_rooms(message: Message, state: FSMContext):
    data = await state.update_data(rooms=message.text.strip())
    await state.clear()

    price = data["max_price"]
    district = data["district"].lower()
    rooms = data["rooms"].lower()

    query = "SELECT description, price, district, rooms, photo_file_id FROM ads WHERE status = 'approved' AND price <= ?"
    params = [price]

    if district != "любой":
        query += " AND LOWER(district) = ?"
        params.append(district)

    if rooms != "любое":
        query += " AND rooms = ?"
        params.append(int(rooms))

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cursor = conn.cursor()
    cursor.execute(query, tuple(params))
    results = cursor.fetchall()
    conn.close()

    if not results:
        await message.answer("Нет подходящих квартир по заданным параметрам.")
    else:
        for desc, price, dist, rms, photo_id in results:
            text = f"<b>Описание:</b> {desc}\n<b>Цена:</b> {price} руб.\n<b>Район:</b> {dist}\n<b>Комнат:</b> {rms}"
            await message.answer_photo(photo_id, caption=text)

@dp.message(AddAdState.rooms)
async def process_rooms(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите число.")
        return
    await state.update_data(rooms=int(message.text))

    # Кнопки выбора аренды
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Посуточная", callback_data="rent_type_daily")],
        [InlineKeyboardButton(text="Долгосрочная", callback_data="rent_type_long")]
    ])
    await message.answer("Выберите тип аренды:", reply_markup=kb)

@dp.callback_query(F.data.startswith("rent_type_"))
async def process_rent_type(call: CallbackQuery, state: FSMContext):
    rent_type = "посуточная" if call.data == "rent_type_daily" else "долгосрочная"
    await state.update_data(rent_type=rent_type)

    data = await state.get_data()
    user_id = call.from_user.id

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ads (user_id, description, price, district, rooms, photo_file_id, rent_type)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        data['description'],
        data['price'],
        data['district'],
        data['rooms'],
        data['photo'],
        data['rent_type']
    ))
    conn.commit()
    conn.close()

    await state.clear()
    await call.message.answer("Объявление отправлено на модерацию. Спасибо!")
    await call.message.edit_reply_markup()

@dp.message(SearchAd.rooms)
async def search_rooms(message: Message, state: FSMContext):
    await state.update_data(rooms=message.text.strip())

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Посуточная", callback_data="search_rent_daily")],
        [InlineKeyboardButton(text="Долгосрочная", callback_data="search_rent_long")]
    ])
    await message.answer("Выберите тип аренды:", reply_markup=kb)

@dp.callback_query(F.data.startswith("search_rent_"))
async def search_by_rent_type(call: CallbackQuery, state: FSMContext):
    rent_type = "посуточная" if "daily" in call.data else "долгосрочная"
    data = await state.update_data(rent_type=rent_type)
    await state.clear()

    price = data["max_price"]
    district = data["district"].lower()
    rooms = data["rooms"].lower()

    query = "SELECT description, price, district, rooms, photo_file_id, rent_type FROM ads WHERE status = 'approved' AND price <= ? AND rent_type = ?"
    params = [price, rent_type]

    if district != "любой":
        query += " AND LOWER(district) = ?"
        params.append(district)

    if rooms != "любое":
        query += " AND rooms = ?"
        params.append(int(rooms))

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cursor = conn.cursor()
    cursor.execute(query, tuple(params))
    results = cursor.fetchall()
    conn.close()

    if not results:
        await call.message.answer("Нет подходящих квартир.")
    else:
        for desc, price, dist, rms, photo_id, rtype in results:
            text = f"<b>Описание:</b> {desc}\n<b>Цена:</b> {price} руб.\n<b>Район:</b> {dist}\n<b>Комнат:</b> {rms}\n<b>Тип аренды:</b> {rtype}"
            await call.message.answer_photo(photo_id, caption=text)
    await call.message.edit_reply_markup()
