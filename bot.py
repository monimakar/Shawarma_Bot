import asyncio
import logging
import os
import json
import math
from datetime import datetime
from io import BytesIO
from collections import Counter
from aiohttp import web

from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

# Проверяем наличие библиотек
try:
    import qrcode
    from PIL import Image, ImageDraw, ImageFont
    QRCODE_AVAILABLE = True
    print("✅ QR-коды доступны")
except ImportError:
    QRCODE_AVAILABLE = False
    print("❌ qrcode не установлен. Выполните: pip install qrcode[pil]")

# Настройки
BOT_TOKEN = "8727707627:AAHHa0oyMg99PizWley4gTM-umg87mpWZ3I"
COOK_CHAT_ID = -1003831452564

# Реквизиты
PHONE_NUMBER = "+7 961 239-18-02"
CARD_NUMBER = "4080 2810 5000 0680 9533"
BANK_NAME = "Т-Банк (Тинькофф)"

# Файл для хранения истории заказов
ORDERS_HISTORY_FILE = "orders_history.json"

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Меню шаурмы
MENU = {
    "Классика": {
        "prices": {"мини": 170, "средняя": 250, "мега": 280},
        "desc": "пекинская капуста, морковь по-корейски, помидоры, огурцы, жаренное филе цыпленка"
    },
    "Сырная": {
        "prices": {"мини": 190, "средняя": 260, "мега": 300},
        "desc": "сыр, картофель фри, помидоры, огурцы, жаренное филе цыпленка"
    },
    "Царская": {
        "prices": {"мини": 180, "средняя": 260, "мега": 300},
        "desc": "пекинская капуста, морковь по-корейски, помидоры, огурцы, картофель фри, жаренное филе цыпленка"
    },
    "Народная": {
        "prices": {"мини": 190, "средняя": 260, "мега": 300},
        "desc": "пекинская капуста, помидоры, огурцы, картофель фри, жаренное филе цыпленка"
    },
    "Мясная": {
        "prices": {"мини": 190, "средняя": 260, "мега": 300},
        "desc": "морковь по-корейски, лук, маринованные огурцы, помидоры, жаренное филе цыпленка"
    },
    "Цезарь": {
        "prices": {"мини": 190, "средняя": 260, "мега": 300},
        "desc": "пекинская капуста, сыр, сухарики, помидоры, огурцы, жаренное филе цыпленка"
    },
    "Гавайская": {
        "prices": {"мини": 190, "средняя": 260, "мега": 300},
        "desc": "ананас, сыр, картофель фри, жаренное филе цыпленка"
    },
    "Грибная": {
        "prices": {"мини": 190, "средняя": 260, "мега": 300},
        "desc": "грибы (шампиньоны), лук, маринованные огурцы, картофель фри, жаренное филе цыпленка"
    },
    "Корейская": {
        "prices": {"мини": 190, "средняя": 260, "мега": 300},
        "desc": "имбирь маринованный, морковь по-корейски, помидоры, огурцы, жаренное филе цыпленка"
    },
    "Веган": {
        "prices": {"мини": 190, "средняя": 260, "мега": 300},
        "desc": "пекинская капуста, морковь по-корейски, помидоры, огурцы, картофель фри, жаренные грибы"
    },
}

SAUCES = ["Чесночный", "Грибной", "Острый", "Классический", "Сырный", "Кетчуп", "Дубай"]

ADDONS = {
    "Грибы": 60,
    "Мясо": 80,
    "Ананасы": 60,
    "Халапеньо": 30,
    "Гранатовый соус": 30,
    "Огурец маринованный": 30,
    "Лук маринованный": 30,
    "Картофель фри": 30,
    "Сыр": 30,
}

# Хранилище
user_orders = {}
pending_payments = {}
loyalty_points = {}

# ===== ЗАГРУЗКА И СОХРАНЕНИЕ ИСТОРИИ =====
def load_orders_history():
    global orders_history
    try:
        with open(ORDERS_HISTORY_FILE, 'r', encoding='utf-8') as f:
            orders_history = json.load(f)
        print(f"📜 История заказов загружена")
    except FileNotFoundError:
        orders_history = {}
        print("📜 Создан новый файл истории заказов")

def save_orders_history():
    try:
        with open(ORDERS_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(orders_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Ошибка сохранения истории: {e}")

orders_history = {}


class OrderState(StatesGroup):
    selecting_item = State()
    selecting_size = State()
    selecting_sauce = State()
    selecting_addons = State()
    waiting_phone = State()
    waiting_comment = State()
    waiting_time = State()
    waiting_screenshot = State()


class EditState(StatesGroup):
    selecting_replacement = State()
    selecting_replacement_size = State()
    selecting_new_sauce = State()
    selecting_new_addons = State()


bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


def main_menu():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="🍖 Меню")],
            [
                types.KeyboardButton(text="🛒 Корзина"), 
                types.KeyboardButton(text="📜 История заказов")
            ],
            [types.KeyboardButton(text="❌ Очистить корзину")],
        ],
        resize_keyboard=True
    )


def menu_keyboard():
    buttons = [[types.KeyboardButton(text=name)] for name in MENU.keys()]
    buttons.append([types.KeyboardButton(text="🔙 Назад")])
    return types.ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def size_keyboard(item_name):
    prices = MENU[item_name]["prices"]
    buttons = [
        [types.KeyboardButton(text=f"мини - {prices['мини']}₽")],
        [types.KeyboardButton(text=f"средняя - {prices['средняя']}₽")],
        [types.KeyboardButton(text=f"мега - {prices['мега']}₽")],
        [types.KeyboardButton(text="🔙 Назад")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def sauce_keyboard():
    buttons = [[types.KeyboardButton(text=sauce)] for sauce in SAUCES]
    buttons.append([types.KeyboardButton(text="🔙 Назад")])
    return types.ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def yes_no_keyboard():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="✅ Да")],
            [types.KeyboardButton(text="❌ Нет")]
        ],
        resize_keyboard=True
    )


def addons_list_keyboard(selected_addons=None):
    selected_addons = selected_addons or []
    buttons = []
    for addon, price in ADDONS.items():
        mark = "✅ " if addon in selected_addons else ""
        buttons.append([types.KeyboardButton(text=f"{mark}{addon} - {price}₽")])
    buttons.append([types.KeyboardButton(text="✅ Готово")])
    buttons.append([types.KeyboardButton(text="🔙 Назад")])
    return types.ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def add_more_keyboard():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="➕ Добавить ещё шаурму")],
            [types.KeyboardButton(text="💳 Перейти к оплате")],
            [types.KeyboardButton(text="🛒 Корзина")]
        ],
        resize_keyboard=True
    )


def payment_keyboard():
    """Клавиатура выбора способа оплаты"""
    keyboard = [
        [types.KeyboardButton(text="📱 Оплата по номеру телефона")],
    ]
    
    if QRCODE_AVAILABLE:
        keyboard.append([types.KeyboardButton(text="🤖 Оплата по QR-коду")])
    
    keyboard.append([types.KeyboardButton(text="🔙 Назад")])
    
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def out_of_stock_keyboard(user_id: int, order_index: int, has_addons: bool = True):
    keyboard = [
        [
            types.InlineKeyboardButton(text="🌯 Нет шаурмы", callback_data=f"no_item_{user_id}_{order_index}"),
            types.InlineKeyboardButton(text="🥫 Нет соуса", callback_data=f"no_sauce_{user_id}_{order_index}"),
        ]
    ]
    
    if has_addons:
        keyboard.append([
            types.InlineKeyboardButton(text="➕ Нет добавок", callback_data=f"no_addon_{user_id}_{order_index}")
        ])
    
    keyboard.append([
        types.InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel_{user_id}")
    ])
    
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def client_edit_keyboard():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="🔄 Изменить заказ", callback_data="edit_order"),
            types.InlineKeyboardButton(text="❌ Отменить заказ", callback_data="cancel_client_order")
        ]
    ])


# ===== ФУНКЦИЯ ГЕНЕРАЦИИ QR-КОДА =====
async def generate_payment_qr(amount: float = None):
    if not QRCODE_AVAILABLE:
        raise ImportError("Библиотека qrcode не установлена")
    
    try:
        payment_info = (
            f"Shawarma Sheikh\n"
            f"Тел: {PHONE_NUMBER}\n"
            f"Карта: {CARD_NUMBER}"
        )
        if amount:
            payment_info += f"\nСумма: {amount} руб."
        
        qr = qrcode.QRCode(version=3, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
        qr.add_data(payment_info)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        bio = BytesIO()
        img.save(bio, format='PNG', optimize=True)
        bio.seek(0)
        return bio
    except Exception as e:
        logging.error(f"Ошибка создания QR-кода: {e}")
        raise


# ===== WEB-СЕРВЕР =====
async def health_check(request):
    return web.Response(text="✅ Бот работает!", status=200)

async def web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/ping', health_check)
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.getenv('PORT', 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    print(f"🌐 Веб-сервер запущен на порту {port}")
    await site.start()
    return runner


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user_orders[user_id] = []
    
    hour = datetime.now().hour
    if 6 <= hour < 12:
        greeting = "☀️ Доброе утро"
    elif 12 <= hour < 17:
        greeting = "🌤 Добрый день"
    elif 17 <= hour < 23:
        greeting = "🌙 Добрый вечер"
    else:
        greeting = "🦉 Доброй ночи"
    
    points = loyalty_points.get(user_id, 0)
    bonus_text = f"\n\n🎁 Бонусных баллов: {points}" if points > 0 else ""
    
    await message.answer(
        f"{greeting}, {message.from_user.full_name}!\n\n"
        f"🌯 <b>Shawarma Sheikh</b>\n"
        f"Лучшая шаурма в городе!{bonus_text}\n\n"
        f"💳 Оплата переводом или QR-кодом\n"
        f"📜 История заказов для быстрого повтора\n\n"
        f"Нажми 🍖 <b>Меню</b> чтобы заказать",
        reply_markup=main_menu()
    )


@dp.message(F.text == "🍖 Меню")
async def show_menu(message: types.Message, state: FSMContext):
    text = "🌯 <b>Наше меню:</b>\n\n"
    for name, data in MENU.items():
        text += f"<b>{name}</b>\n└ {data['desc']}\n💰 мини {data['prices']['мини']}₽ / средняя {data['prices']['средняя']}₽ / мега {data['prices']['мега']}₽\n\n"
    text += "Выбери шаурму 👇"
    await state.set_state(OrderState.selecting_item)
    await message.answer(text, reply_markup=menu_keyboard())


@dp.message(OrderState.selecting_item, F.text.in_(MENU.keys()))
async def select_item(message: types.Message, state: FSMContext):
    item_name = message.text
    await state.update_data(item_name=item_name)
    await state.set_state(OrderState.selecting_size)
    text = f"🌯 <b>{item_name}</b>\n\n{MENU[item_name]['desc']}\n\nВыбери размер:"
    await message.answer(text, reply_markup=size_keyboard(item_name))


@dp.message(OrderState.selecting_size, F.text.contains(" - "))
async def select_size(message: types.Message, state: FSMContext):
    size = message.text.split(" - ")[0]
    data = await state.get_data()
    item_name = data["item_name"]
    price = MENU[item_name]["prices"][size]
    await state.update_data(size=size, base_price=price)
    await state.set_state(OrderState.selecting_sauce)
    text = f"✅ <b>{item_name}</b> ({size}) - {price}₽\n\nВыбери соус:"
    await message.answer(text, reply_markup=sauce_keyboard())


@dp.message(OrderState.selecting_sauce, F.text.in_(SAUCES))
async def select_sauce(message: types.Message, state: FSMContext):
    sauce = message.text
    await state.update_data(sauce=sauce, addons=[], addons_price=0)
    await state.set_state(OrderState.selecting_addons)
    data = await state.get_data()
    total = data["base_price"]
    text = f"✅ Соус: <b>{sauce}</b>\n\nНужны добавки?\nТекущая сумма: {total}₽"
    await message.answer(text, reply_markup=yes_no_keyboard())


@dp.message(OrderState.selecting_addons, F.text == "❌ Нет")
async def skip_addons(message: types.Message, state: FSMContext):
    await state.update_data(addons=[], addons_price=0)
    await add_to_cart_and_show(message, state)


@dp.message(OrderState.selecting_addons, F.text == "✅ Да")
async def show_addons(message: types.Message, state: FSMContext):
    await message.answer("Выбери добавки (нажми несколько раз чтобы убрать):", reply_markup=addons_list_keyboard())


@dp.message(OrderState.selecting_addons, F.text.contains(" - ") & ~F.text.contains("Готово"))
async def toggle_addon(message: types.Message, state: FSMContext):
    addon_name = message.text.replace("✅ ", "").split(" - ")[0].strip()
    if addon_name not in ADDONS:
        return
    data = await state.get_data()
    addons = data.get("addons", [])
    addons_price = data.get("addons_price", 0)
    if addon_name in addons:
        addons.remove(addon_name)
        addons_price -= ADDONS[addon_name]
    else:
        addons.append(addon_name)
        addons_price += ADDONS[addon_name]
    await state.update_data(addons=addons, addons_price=addons_price)
    await message.answer("Добавки обновлены:", reply_markup=addons_list_keyboard(addons))


@dp.message(OrderState.selecting_addons, F.text == "✅ Готово")
async def finish_addons(message: types.Message, state: FSMContext):
    await add_to_cart_and_show(message, state)


async def add_to_cart_and_show(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    order_item = {
        "item": data["item_name"],
        "size": data["size"],
        "sauce": data["sauce"],
        "addons": data.get("addons", []),
        "price": data["base_price"] + data.get("addons_price", 0)
    }
    if user_id not in user_orders:
        user_orders[user_id] = []
    user_orders[user_id].append(order_item)
    text = f"✅ Добавлено:\n🌯 {order_item['item']} ({order_item['size']})\n🥫 {order_item['sauce']}\n"
    if order_item['addons']:
        text += f"➕ {', '.join(order_item['addons'])}\n"
    text += f"💰 {order_item['price']}₽"
    await message.answer(text, reply_markup=add_more_keyboard())
    await state.clear()


@dp.message(F.text == "➕ Добавить ещё шаурму")
async def add_more(message: types.Message, state: FSMContext):
    await show_menu(message, state)


@dp.message(F.text == "🛒 Корзина")
async def show_cart(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    orders = user_orders.get(user_id, [])
    if not orders:
        await message.answer("🙁 Корзина пуста", reply_markup=main_menu())
        return
    total = sum(item["price"] for item in orders)
    text = "🛒 <b>Ваша корзина:</b>\n\n"
    for i, item in enumerate(orders, 1):
        text += f"{i}. <b>{item['item']}</b> ({item['size']})\n   🥫 {item['sauce']}\n"
        if item['addons']:
            text += f"   ➕ {', '.join(item['addons'])}\n"
        text += f"   💰 {item['price']}₽\n\n"
    text += f"<b>ИТОГО: {total}₽</b>\n\n💳 Нажми 'Перейти к оплате'"
    await message.answer(text, reply_markup=add_more_keyboard())


# ===== ИСТОРИЯ ЗАКАЗОВ =====
@dp.message(F.text == "📜 История заказов")
async def show_order_history(message: types.Message):
    user_id = str(message.from_user.id)
    user_history = orders_history.get(user_id, [])
    if not user_history:
        await message.answer("📜 <b>История заказов пуста</b>\n\nЗдесь будут отображаться ваши последние заказы\nдля быстрого повтора!", reply_markup=main_menu())
        return
    recent_orders = user_history[-5:]
    text = "📜 <b>Последние заказы:</b>\n\n"
    for i, order in enumerate(reversed(recent_orders), 1):
        total = sum(item["price"] for item in order["items"])
        text += f"<b>Заказ #{i}</b> 📅 {order['date']}\n"
        for item in order["items"]:
            text += f"• {item['item']} ({item['size']}) - {item['price']}₽\n  🥫 {item['sauce']}"
            if item['addons']:
                text += f" | ➕ {', '.join(item['addons'])}"
            text += "\n"
        text += f"💰 <b>Итого: {total}₽</b>\n\n"
    kb = types.InlineKeyboardMarkup(inline_keyboard=[])
    for i, order in enumerate(reversed(recent_orders), 1):
        total = sum(item["price"] for item in order["items"])
        kb.inline_keyboard.append([types.InlineKeyboardButton(text=f"🔄 Повторить заказ #{i} - {total}₽", callback_data=f"repeat_{len(user_history) - i}")])
    await message.answer(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("repeat_"))
async def repeat_order(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    order_index = int(callback.data.split("_")[1])
    user_history = orders_history.get(user_id, [])
    if not user_history or order_index >= len(user_history):
        await callback.answer("Заказ не найден")
        return
    order = user_history[order_index]
    user_orders[callback.from_user.id] = order["items"].copy()
    total = sum(item["price"] for item in order["items"])
    text = "✅ <b>Заказ повторен!</b>\n\n🛒 Корзина:\n\n"
    for i, item in enumerate(order["items"], 1):
        text += f"{i}. <b>{item['item']}</b> ({item['size']})\n   🥫 {item['sauce']}\n"
        if item['addons']:
            text += f"   ➕ {', '.join(item['addons'])}\n"
        text += f"   💰 {item['price']}₽\n\n"
    text += f"<b>ИТОГО: {total}₽</b>\n\nНажми 'Перейти к оплате'"
    await callback.message.edit_text(text, reply_markup=add_more_keyboard())
    await callback.answer("✅ Заказ добавлен в корзину!")


@dp.message(F.text == "❌ Очистить корзину")
async def clear_cart(message: types.Message):
    user_id = message.from_user.id
    user_orders[user_id] = []
    await message.answer("🗑️ Корзина очищена!", reply_markup=main_menu())


@dp.message(F.text == "💳 Перейти к оплате")
async def start_payment(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    orders = user_orders.get(user_id, [])
    if not orders:
        await message.answer("Корзина пуста! Сначала добавь шаурму.", reply_markup=main_menu())
        return
    total = sum(item["price"] for item in orders)
    points = loyalty_points.get(user_id, 0)
    bonus_text = f"\n🎁 Ваши бонусы: {points} баллов" if points > 0 else ""
    await state.update_data(total=total)
    await state.set_state(OrderState.waiting_phone)
    text = (
        f"💳 <b>Оплата заказа</b>\n\n"
        f"Сумма к оплате: <b>{total}₽</b>{bonus_text}\n\n"
        f"⚠️ <b>Важно:</b>\n"
        f"1. Оплати точную сумму\n"
        f"2. Отправь скриншот или чек оплаты\n"
        f"3. После проверки заказ пойдёт в работу\n\n"
        f"📞 Для начала введи номер телефона:"
    )
    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
        resize_keyboard=True
    )
    await message.answer(text, reply_markup=kb)


@dp.message(OrderState.waiting_phone, F.contact)
async def get_phone_payment(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    await ask_comment(message, state)


@dp.message(OrderState.waiting_phone)
async def get_phone_text_payment(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await ask_comment(message, state)


async def ask_comment(message: types.Message, state: FSMContext):
    await state.set_state(OrderState.waiting_comment)
    await message.answer("📝 Комментарий к заказу? (макс. 100 символов)\n\nНапиши 'Нет' если не нужно:", reply_markup=types.ReplyKeyboardRemove())


@dp.message(OrderState.waiting_comment)
async def get_comment(message: types.Message, state: FSMContext):
    comment = message.text
    if len(comment) > 100:
        await message.answer(f"❌ Слишком длинный комментарий ({len(comment)} символов)\nМаксимум 100 символов. Попробуй ещё раз:")
        return
    if comment == "Нет":
        comment = "Без комментария"
    await state.update_data(comment=comment)
    await ask_time(message, state)


async def ask_time(message: types.Message, state: FSMContext):
    await state.set_state(OrderState.waiting_time)
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Как можно скорее")],
            [types.KeyboardButton(text="Через 15 минут")],
            [types.KeyboardButton(text="Через 30 минут")],
            [types.KeyboardButton(text="Через 1 час")],
        ],
        resize_keyboard=True
    )
    await message.answer("⏰ К какому времени приготовить?", reply_markup=kb)


@dp.message(OrderState.waiting_time)
async def show_payment_options(message: types.Message, state: FSMContext):
    time_str = message.text
    await state.update_data(time=time_str)
    await state.set_state(OrderState.waiting_screenshot)
    data = await state.get_data()
    total = data["total"]
    text = f"💳 <b>Оплата {total}₽</b>\n\nВыбери способ оплаты:\n📱 По номеру телефона\n"
    if QRCODE_AVAILABLE:
        text += "🤖 QR-код - сканируй и плати\n"
    await message.answer(text, reply_markup=payment_keyboard())


@dp.message(OrderState.waiting_screenshot, F.text == "📱 Оплата по номеру телефона")
async def show_phone_payment(message: types.Message, state: FSMContext):
    data = await state.get_data()
    total = data["total"]
    text = (
        f"📱 <b>Оплата по номеру телефона</b>\n\n"
        f"💰 Сумма: <b>{total}₽</b>\n\n"
        f"📞 Номер для перевода:\n<code>{PHONE_NUMBER}</code>\n\n"
        f"🏦 Банк: {BANK_NAME}\n\n"
        f"📋 <b>Как оплатить:</b>\n"
        f"1. Откройте приложение банка\n"
        f"2. Выберите «Перевод по номеру телефона»\n"
        f"3. Вставьте номер выше\n"
        f"4. Введите сумму: {total}₽\n"
        f"5. Подтвердите перевод\n\n"
        f"📸 <b>После оплаты отправьте скриншот сюда</b>"
    )
    await message.answer(text, reply_markup=types.ReplyKeyboardRemove())


@dp.message(OrderState.waiting_screenshot, F.text == "🤖 Оплата по QR-коду")
async def show_qr_payment(message: types.Message, state: FSMContext):
    if not QRCODE_AVAILABLE:
        await message.answer("❌ QR-коды временно недоступны\n\nВоспользуйтесь оплатой по номеру телефона:", reply_markup=payment_keyboard())
        return
    data = await state.get_data()
    total = data["total"]
    try:
        processing_msg = await message.answer("⚙️ <i>Генерирую QR-код...</i>", reply_markup=types.ReplyKeyboardRemove())
        qr_image = await generate_payment_qr(total)
        await processing_msg.delete()
        await message.answer_photo(
            photo=types.BufferedInputFile(qr_image.getvalue(), filename="payment_qr.png"),
            caption=(
                f"🤖 <b>Оплата по QR-коду</b>\n\n"
                f"💰 Сумма: <b>{total}₽</b>\n\n"
                f"📱 <b>Как оплатить:</b>\n"
                f"1. Откройте приложение банка\n"
                f"2. Выберите «Оплата по QR-коду»\n"
                f"3. Наведите камеру на код\n"
                f"4. Проверьте сумму и подтвердите\n\n"
                f"✅ После оплаты отправьте скриншот сюда\n\n"
                f"⚡ <i>Самый быстрый способ!</i>"
            )
        )
    except Exception as e:
        logging.error(f"Ошибка при показе QR-кода: {e}")
        await message.answer(
            f"❌ Не удалось создать QR-код\n\n📱 <b>По телефону:</b>\n<code>{PHONE_NUMBER}</code>\n💰 Сумма: <b>{total}₽</b>",
            reply_markup=types.ReplyKeyboardRemove()
        )


@dp.message(OrderState.waiting_screenshot, F.photo)
async def receive_screenshot(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    user = message.from_user
    orders = user_orders.get(user_id, [])
    total = data["total"]
    phone = data.get("phone", "Не указан")
    comment = data.get("comment", "Без комментария")
    time_str = data.get("time", "Как можно скорее")
    
    cook_text = (
        f"🔔 <b>НОВЫЙ ЗАКАЗ - ПРОВЕРКА ОПЛАТЫ</b>\n\n"
        f"👤 Клиент: {user.full_name}\n🆔 ID: {user.id}\n"
        f"📞 Телефон: {phone}\n⏰ Время: {time_str}\n"
        f"📅 {datetime.now().strftime('%H:%M')}\n\n<b>Заказ:</b>\n"
    )
    for i, item in enumerate(orders, 1):
        cook_text += f"\n{i}. <b>{item['item']}</b> ({item['size']})\n   🥫 {item['sauce']}\n"
        if item['addons']:
            cook_text += f"   ➕ {', '.join(item['addons'])}\n"
        cook_text += f"   💰 {item['price']}₽\n"
    cook_text += f"\n💰 <b>СУММА К ОПЛАТЕ: {total}₽</b>\n📝 {comment}\n\nПроверь скриншот оплаты выше ↑"
    
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{user_id}"),
            types.InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{user_id}")
        ],
        [types.InlineKeyboardButton(text="⚠️ Нет в наличии", callback_data=f"outofstock_{user_id}")]
    ])
    
    sent = False
    try:
        await bot.send_photo(chat_id=COOK_CHAT_ID, photo=message.photo[-1].file_id, caption=cook_text, reply_markup=kb)
        sent = True
    except Exception as e:
        print(f"Ошибка отправки в группу: {e}")
    
    if not sent:
        try:
            await bot.send_photo(chat_id=1136519770, photo=message.photo[-1].file_id, caption=cook_text + "\n\n⚠️ (Не удалось отправить в группу)", reply_markup=kb)
            sent = True
        except Exception as e:
            print(f"Ошибка отправки в личку: {e}")
    
    if sent:
        await message.answer("✅ Скриншот получен!\n\n⏳ Ожидай подтверждения оплаты...\nПосле проверки заказ пойдёт в работу", reply_markup=types.ReplyKeyboardRemove())
        pending_payments[user_id] = {
            "orders": orders, "phone": phone, "time": time_str, "comment": comment,
            "total": total, "user": user, "chat_id": message.chat.id, "cook_message_id": None
        }
    else:
        await message.answer(f"⚠️ Не удалось отправить скриншот повару.\nПозвони для подтверждения: {PHONE_NUMBER}", reply_markup=main_menu())
        await state.clear()


# ===== ОБРАБОТЧИКИ "НЕТ В НАЛИЧИИ" =====
@dp.callback_query(F.data.startswith("outofstock_"))
async def out_of_stock(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    payment_data = pending_payments.get(user_id)
    if not payment_data:
        await callback.answer("Заказ не найден")
        return
    orders = payment_data["orders"]
    if len(orders) == 1:
        has_addons = bool(orders[0]['addons'])
        await callback.message.edit_caption(caption=callback.message.caption + "\n\n⚠️ <b>ВЫБЕРИТЕ, ЧЕГО НЕТ В НАЛИЧИИ:</b>", reply_markup=out_of_stock_keyboard(user_id, 0, has_addons))
    else:
        kb = types.InlineKeyboardMarkup(inline_keyboard=[])
        for i, item in enumerate(orders):
            kb.inline_keyboard.append([types.InlineKeyboardButton(text=f"{i+1}. {item['item']} ({item['size']})", callback_data=f"select_item_oos_{user_id}_{i}")])
        kb.inline_keyboard.append([types.InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel_{user_id}")])
        await callback.message.edit_caption(caption=callback.message.caption + "\n\n⚠️ <b>ВЫБЕРИТЕ ПОЗИЦИЮ:</b>", reply_markup=kb)
    await callback.answer("Выберите отсутствующий товар")


@dp.callback_query(F.data.startswith("select_item_oos_"))
async def select_item_out_of_stock(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    user_id = int(parts[3])
    order_index = int(parts[4])
    payment_data = pending_payments.get(user_id)
    if not payment_data:
        await callback.answer("Заказ не найден")
        return
    has_addons = bool(payment_data["orders"][order_index]['addons'])
    await callback.message.edit_caption(caption=callback.message.caption + f"\n\nПозиция {order_index + 1}", reply_markup=out_of_stock_keyboard(user_id, order_index, has_addons))
    await callback.answer("Выберите что отсутствует")


@dp.callback_query(F.data.startswith("no_item_"))
async def no_item_available(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    user_id = int(parts[2])
    order_index = int(parts[3])
    payment_data = pending_payments.get(user_id)
    if not payment_data:
        await callback.answer("Заказ не найден")
        return
    chat_id = payment_data["chat_id"]
    item = payment_data["orders"][order_index]
    await bot.send_message(chat_id=chat_id, text=f"⚠️ <b>Внимание!</b>\n\nК сожалению, <b>{item['item']}</b> ({item['size']}) сейчас нет в наличии.\n\n🥫 Соус: {item['sauce']}\n➕ Добавки: {', '.join(item['addons']) if item['addons'] else 'нет'}\n💰 Стоимость: {item['price']}₽\n\nВы можете изменить заказ или отменить его.", reply_markup=client_edit_keyboard())
    pending_payments[user_id]["editing_index"] = order_index
    pending_payments[user_id]["editing_type"] = "item"
    await callback.message.edit_caption(caption=callback.message.caption + f"\n\n❌ <b>ШАУРМА '{item['item']}' НЕТ В НАЛИЧИИ</b>\nОжидаем реакции клиента...", reply_markup=None)
    await callback.answer("Клиент уведомлён")


@dp.callback_query(F.data.startswith("no_sauce_"))
async def no_sauce_available(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    user_id = int(parts[2])
    order_index = int(parts[3])
    payment_data = pending_payments.get(user_id)
    if not payment_data:
        await callback.answer("Заказ не найден")
        return
    chat_id = payment_data["chat_id"]
    item = payment_data["orders"][order_index]
    await bot.send_message(chat_id=chat_id, text=f"⚠️ <b>Внимание!</b>\n\nК сожалению, соус <b>{item['sauce']}</b> для {item['item']} ({item['size']}) сейчас нет в наличии.\n\nВы можете выбрать другой соус или отменить заказ.", reply_markup=client_edit_keyboard())
    pending_payments[user_id]["editing_index"] = order_index
    pending_payments[user_id]["editing_type"] = "sauce"
    await callback.message.edit_caption(caption=callback.message.caption + f"\n\n❌ <b>СОУС '{item['sauce']}' НЕТ В НАЛИЧИИ</b>\nОжидаем реакции клиента...", reply_markup=None)
    await callback.answer("Клиент уведомлён")


@dp.callback_query(F.data.startswith("no_addon_"))
async def no_addon_available(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    user_id = int(parts[2])
    order_index = int(parts[3])
    payment_data = pending_payments.get(user_id)
    if not payment_data:
        await callback.answer("Заказ не найден")
        return
    chat_id = payment_data["chat_id"]
    item = payment_data["orders"][order_index]
    if not item['addons']:
        await callback.answer("У клиента нет добавок!")
        return
    addons_text = "\n".join([f"• {a}" for a in item['addons']])
    await bot.send_message(chat_id=chat_id, text=f"⚠️ <b>Внимание!</b>\n\nК сожалению, следующие добавки для {item['item']} ({item['size']}) сейчас нет в наличии:\n\n{addons_text}\n\nВы можете изменить добавки или отменить заказ.", reply_markup=client_edit_keyboard())
    pending_payments[user_id]["editing_index"] = order_index
    pending_payments[user_id]["editing_type"] = "addons"
    await callback.message.edit_caption(caption=callback.message.caption + f"\n\n❌ <b>ДОБАВКИ НЕТ В НАЛИЧИИ</b>\nОжидаем реакции клиента...", reply_markup=None)
    await callback.answer("Клиент уведомлён")


@dp.callback_query(F.data == "edit_order")
async def client_edit_order(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    payment_data = pending_payments.get(user_id)
    if not payment_data:
        await callback.answer("Данные заказа не найдены")
        return
    editing_type = payment_data.get("editing_type")
    order_index = payment_data.get("editing_index", 0)
    item = payment_data["orders"][order_index]
    await callback.answer("Начинаем изменение...")
    
    if editing_type == "item":
        await state.set_state(EditState.selecting_replacement)
        await state.update_data(editing_index=order_index, old_item=item['item'], old_size=item['size'], old_sauce=item['sauce'], old_addons=item['addons'], old_price=item['price'])
        await callback.message.delete()
        await callback.message.answer(f"🔄 <b>Замена шаурмы</b>\n\nБыло: <b>{item['item']}</b> ({item['size']}) - {item['price']}₽\n\nВыбери другую шаурму:", reply_markup=menu_keyboard())
    elif editing_type == "sauce":
        await state.set_state(EditState.selecting_new_sauce)
        await state.update_data(editing_index=order_index)
        await callback.message.delete()
        await callback.message.answer(f"🔄 <b>Замена соуса</b>\n\nБыло: <b>{item['sauce']}</b> для {item['item']} ({item['size']})\n\nВыбери другой соус:", reply_markup=sauce_keyboard())
    elif editing_type == "addons":
        await state.set_state(EditState.selecting_new_addons)
        await state.update_data(editing_index=order_index, new_addons=[], new_addons_price=0)
        await callback.message.delete()
        await callback.message.answer(f"🔄 <b>Замена добавок</b>\n\nБыло: {', '.join(item['addons']) if item['addons'] else 'нет'}\n\nВыбери новые добавки:", reply_markup=addons_list_keyboard())


@dp.message(EditState.selecting_replacement, F.text.in_(MENU.keys()))
async def select_replacement_item(message: types.Message, state: FSMContext):
    await state.update_data(new_item=message.text)
    await state.set_state(EditState.selecting_replacement_size)
    await message.answer(f"🌯 <b>{message.text}</b>\n\n{MENU[message.text]['desc']}\n\nВыбери размер:", reply_markup=size_keyboard(message.text))


@dp.message(EditState.selecting_replacement_size, F.text.contains(" - "))
async def select_replacement_size(message: types.Message, state: FSMContext):
    size = message.text.split(" - ")[0]
    data = await state.get_data()
    price = MENU[data["new_item"]]["prices"][size]
    await state.update_data(new_size=size, new_base_price=price)
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=f"🥫 Оставить {data.get('old_sauce')}", callback_data="keep_sauce"),
         types.InlineKeyboardButton(text="🔄 Другой соус", callback_data="change_sauce")]
    ])
    await message.answer(f"✅ <b>{data['new_item']}</b> ({size}) - {price}₽\n\nОставить соус <b>{data.get('old_sauce')}</b> или выбрать другой?", reply_markup=kb)


@dp.callback_query(F.data == "keep_sauce")
async def keep_sauce(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    old_addons = data.get("old_addons", [])
    new_price = data["new_base_price"] + sum(ADDONS.get(a, 0) for a in old_addons)
    user_id = callback.from_user.id
    payment_data = pending_payments[user_id]
    item = payment_data["orders"][data["editing_index"]]
    item.update({"item": data["new_item"], "size": data["new_size"], "sauce": data["old_sauce"], "addons": old_addons, "price": new_price})
    new_total = sum(i["price"] for i in payment_data["orders"])
    payment_data["total"] = new_total
    text = "🛒 <b>Заказ обновлён:</b>\n\n"
    for i, o in enumerate(payment_data["orders"], 1):
        text += f"{i}. <b>{o['item']}</b> ({o['size']})\n   🥫 {o['sauce']}\n"
        if o['addons']: text += f"   ➕ {', '.join(o['addons'])}\n"
        text += f"   💰 {o['price']}₽\n\n"
    text += f"<b>НОВАЯ СУММА: {new_total}₽</b>\n\nОтправь скриншот оплаты на новую сумму!"
    await callback.message.delete()
    await callback.message.answer(text, reply_markup=main_menu())
    await state.clear()
    try:
        await bot.send_message(chat_id=COOK_CHAT_ID, text=f"🔄 <b>ЗАКАЗ ИЗМЕНЁН</b>\n👤 Клиент ID: {user_id}\n💰 Новая сумма: {new_total}₽\nОжидаем новый скриншот...")
    except: pass


@dp.callback_query(F.data == "change_sauce")
async def change_sauce(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(EditState.selecting_new_sauce)
    await callback.message.delete()
    await callback.message.answer("Выбери новый соус:", reply_markup=sauce_keyboard())


@dp.message(EditState.selecting_new_sauce, F.text.in_(SAUCES))
async def select_new_sauce(message: types.Message, state: FSMContext):
    sauce = message.text
    data = await state.get_data()
    user_id = message.from_user.id
    payment_data = pending_payments[user_id]
    payment_data["orders"][data["editing_index"]]["sauce"] = sauce
    new_total = sum(i["price"] for i in payment_data["orders"])
    payment_data["total"] = new_total
    text = "🛒 <b>Заказ обновлён:</b>\n\n"
    for i, o in enumerate(payment_data["orders"], 1):
        text += f"{i}. <b>{o['item']}</b> ({o['size']})\n   🥫 {o['sauce']}\n"
        if o['addons']: text += f"   ➕ {', '.join(o['addons'])}\n"
        text += f"   💰 {o['price']}₽\n\n"
    text += f"<b>СУММА: {new_total}₽</b> (без изменений)\n\nВсё в порядке! Отправь скриншот оплаты."
    await message.answer(text, reply_markup=main_menu())
    await state.clear()
    try:
        await bot.send_message(chat_id=COOK_CHAT_ID, text=f"🔄 <b>ЗАКАЗ ИЗМЕНЁН</b>\n👤 Клиент ID: {user_id}\n🥫 Новый соус: {sauce}\n💰 Сумма: {new_total}₽")
    except: pass


@dp.message(EditState.selecting_new_addons, F.text.contains(" - ") & ~F.text.contains("Готово"))
async def toggle_new_addon(message: types.Message, state: FSMContext):
    addon_name = message.text.replace("✅ ", "").split(" - ")[0].strip()
    if addon_name not in ADDONS: return
    data = await state.get_data()
    addons = data.get("new_addons", [])
    addons_price = data.get("new_addons_price", 0)
    if addon_name in addons:
        addons.remove(addon_name)
        addons_price -= ADDONS[addon_name]
    else:
        addons.append(addon_name)
        addons_price += ADDONS[addon_name]
    await state.update_data(new_addons=addons, new_addons_price=addons_price)
    await message.answer("Добавки обновлены:", reply_markup=addons_list_keyboard(addons))


@dp.message(EditState.selecting_new_addons, F.text == "✅ Готово")
async def finish_new_addons(message: types.Message, state: FSMContext):
    data = await state.get_data()
    new_addons = data.get("new_addons", [])
    new_addons_price = data.get("new_addons_price", 0)
    user_id = message.from_user.id
    payment_data = pending_payments[user_id]
    item = payment_data["orders"][data["editing_index"]]
    old_addons_price = sum(ADDONS.get(a, 0) for a in item.get("addons", []))
    item["addons"] = new_addons
    item["price"] = item["price"] - old_addons_price + new_addons_price
    new_total = sum(i["price"] for i in payment_data["orders"])
    payment_data["total"] = new_total
    text = "🛒 <b>Заказ обновлён:</b>\n\n"
    for i, o in enumerate(payment_data["orders"], 1):
        text += f"{i}. <b>{o['item']}</b> ({o['size']})\n   🥫 {o['sauce']}\n"
        if o['addons']: text += f"   ➕ {', '.join(o['addons'])}\n"
        text += f"   💰 {o['price']}₽\n\n"
    text += f"<b>НОВАЯ СУММА: {new_total}₽</b>\n\nОтправь скриншот оплаты на новую сумму!"
    await message.answer(text, reply_markup=main_menu())
    await state.clear()
    try:
        await bot.send_message(chat_id=COOK_CHAT_ID, text=f"🔄 <b>ЗАКАЗ ИЗМЕНЁН</b>\n👤 Клиент ID: {user_id}\n➕ Новые добавки: {', '.join(new_addons) if new_addons else 'нет'}\n💰 Новая сумма: {new_total}₽")
    except: pass


@dp.callback_query(F.data == "cancel_client_order")
async def client_cancel_order(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if pending_payments.get(user_id):
        user_orders[user_id] = []
        pending_payments.pop(user_id, None)
        await callback.message.delete()
        await callback.message.answer("❌ <b>Заказ отменён</b>\n\nВаша кор Activity capacity reached. Temporarily unable to generate complete response. Please try again.
        @dp.callback_query(F.data == "cancel_client_order")
async def client_cancel_order(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if pending_payments.get(user_id):
        user_orders[user_id] = []
        pending_payments.pop(user_id, None)
        await callback.message.delete()
        await callback.message.answer(
            "❌ <b>Заказ отменён</b>\n\nВаша корзина очищена.\nНачните новый заказ через /start",
            reply_markup=main_menu()
        )
        try:
            await bot.send_message(chat_id=COOK_CHAT_ID, text=f"❌ Заказ клиента {user_id} отменён клиентом")
        except: pass
    else:
        await callback.message.delete()
        await callback.message.answer("Заказ не найден. Начните заново /start", reply_markup=main_menu())
    await callback.answer("Заказ отменён")


@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_payment(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    payment_data = pending_payments.get(user_id)
    if not payment_data:
        await callback.answer("Заказ не найден")
        return
    
    orders = payment_data["orders"]
    total = payment_data["total"]
    chat_id = payment_data["chat_id"]
    
    user_id_str = str(user_id)
    if user_id_str not in orders_history:
        orders_history[user_id_str] = []
    orders_history[user_id_str].append({
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "items": orders,
        "total": total
    })
    if len(orders_history[user_id_str]) > 20:
        orders_history[user_id_str] = orders_history[user_id_str][-20:]
    save_orders_history()
    
    bonus = math.floor(total / 100)
    loyalty_points[user_id] = loyalty_points.get(user_id, 0) + bonus
    
    try:
        await bot.send_message(chat_id=chat_id, text=(
            f"✅ <b>Оплата подтверждена!</b>\n💰 {total}₽\n⏰ {payment_data['time']}\n\n"
            f"🍳 Заказ принят в работу!\n🎁 Начислено бонусов: +{bonus}\n"
            f"📜 Заказ сохранён в истории\n\nПриходите вовремя!"
        ), reply_markup=main_menu())
    except: pass
    
    await callback.message.edit_caption(caption=callback.message.caption + "\n\n✅ <b>ОПЛАТА ПОДТВЕРЖДЕНА</b>", reply_markup=None)
    await callback.answer("Заказ подтверждён")
    user_orders[user_id] = []
    pending_payments.pop(user_id, None)


@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_payment(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    payment_data = pending_payments.get(user_id)
    if not payment_data:
        await callback.answer("Заказ не найден")
        return
    
    total = payment_data["total"]
    chat_id = payment_data["chat_id"]
    try:
        await bot.send_message(chat_id=chat_id, text=(
            f"❌ <b>Оплата не подтверждена</b>\nСумма оплаты не соответствует заказу\n\n"
            f"💰 Требовалось: {total}₽\n\n📞 Перезвони для уточнения: {PHONE_NUMBER}\n"
            f"Или начни новый заказ /start"
        ), reply_markup=main_menu())
    except: pass
    
    await callback.message.edit_caption(caption=callback.message.caption + "\n\n❌ <b>ОПЛАТА ОТКЛОНЕНА</b>", reply_markup=None)
    await callback.answer("Заказ отменён")
    pending_payments.pop(user_id, None)


@dp.message(OrderState.waiting_screenshot)
async def no_screenshot(message: types.Message):
    await message.answer("Пожалуйста, отправь скриншот оплаты (фото)")


@dp.message(F.text == "🔙 Назад")
async def go_back(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state in [OrderState.waiting_phone.state, OrderState.waiting_comment.state, OrderState.waiting_time.state, OrderState.waiting_screenshot.state]:
        await state.clear()
        await message.answer("Главное меню:", reply_markup=main_menu())
    else:
        await state.clear()
        await message.answer("Главное меню:", reply_markup=main_menu())


async def main():
    load_orders_history()
    print("=" * 50)
    print("🚀 Shawarma Sheikh запускается...")
    print(f"👨‍🍳 Заказы в группу: {COOK_CHAT_ID}")
    print("📜 История заказов загружена")
    if QRCODE_AVAILABLE:
        print("🤖 QR-коды доступны")
    print("=" * 50)
    
    try:
        web_runner = await web_server()
        print("🌐 Веб-сервер активен")
    except Exception as e:
        logging.error(f"Ошибка запуска веб-сервера: {e}")
    
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Бот работает!")
    print("📍 Бот: @Shawarma_Sheikh_bot")
    print("=" * 50)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
