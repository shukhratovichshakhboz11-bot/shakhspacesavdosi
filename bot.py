import os
import asyncio
import sqlite3
import re
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup


# ============================================================
# SOZLAMALAR
# ============================================================

# MUHIM:
# @BotFather orqali YANGI token oling va shu yerga yozing.
TOKEN = "8058135143:AAHo4AK9u4z_8tfz3AqYZJfxEVLMci9KM7U"

ADMIN_ID = 8167713251
ADMIN_USERNAME = "@shaxbozshuxratovich11"

# Bir nechta admin bo'lishi mumkin — shu ro'yxatga qo'shiladi.
ADMIN_IDS = [
    8167713251,       # shaxbozshuxratovich11
    1676736186,       # @FaRRuX_Samiyev_01_28
]

CHANNEL_USERNAME = "@shaxatovarlar"
INSTAGRAM_USERNAME = "Shaxa_storeshop"

CARD_NUMBER = "5614682764532182"
CARD_NAME = "Munojat"

# Kanal postlaridagi $/USD narxlarni so'mga aylantirish uchun kurs.
# Kerak bo'lsa shu raqamni o'zgartiring.
USD_TO_UZS = 12500


# ============================================================
# BOT
# ============================================================

bot = Bot(TOKEN)
dp = Dispatcher()

DB = sqlite3.connect("shaxatovarlar.db")
DB.row_factory = sqlite3.Row

# Admin qaysi rejimda ekanini eslab turadi:
# True  -> hozir ADMIN PANELda
# False -> hozir MIJOZ PANELda (admin o'zini mijoz sifatida sinamoqda)
# Faqat /admin va "👤 Mijoz paneli" tugmalari shu qiymatni o'zgartiradi.
admin_mode = {}


# ============================================================
# DATABASE
# ============================================================

def column_exists(table_name, column_name):
    cur = DB.cursor()

    cur.execute(f"PRAGMA table_info({table_name})")

    columns = [row["name"] for row in cur.fetchall()]

    return column_name in columns


def db_init():
    cur = DB.cursor()

    # USERS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            full_name TEXT DEFAULT '',
            balance INTEGER DEFAULT 0
        )
    """)

    # Eski database bo'lsa full_name yo'q bo'lishi mumkin.
    if not column_exists("users", "username"):
        try:
            cur.execute(
                "ALTER TABLE users ADD COLUMN username TEXT DEFAULT ''"
            )
        except sqlite3.OperationalError:
            pass

    if not column_exists("users", "full_name"):
        try:
            cur.execute(
                "ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT ''"
            )
        except sqlite3.OperationalError:
            pass

    if not column_exists("users", "balance"):
        try:
            cur.execute(
                "ALTER TABLE users ADD COLUMN balance INTEGER DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass

    # TRANSACTIONS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount INTEGER,
            status TEXT,
            created_at TEXT
        )
    """)

    # ORDERS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            products TEXT,
            amount INTEGER DEFAULT 0,
            address TEXT,
            phone TEXT,
            message TEXT,
            status TEXT,
            created_at TEXT
        )
    """)

    if not column_exists("orders", "amount"):
        try:
            cur.execute(
                "ALTER TABLE orders ADD COLUMN amount INTEGER DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass

    DB.commit()


# ============================================================
# USER
# ============================================================

def add_user(user):
    cur = DB.cursor()

    cur.execute(
        "SELECT id FROM users WHERE id = ?",
        (user.id,)
    )

    row = cur.fetchone()

    username = user.username or ""
    full_name = user.full_name or ""

    if not row:
        cur.execute(
            """
            INSERT INTO users
            (id, username, full_name, balance)
            VALUES (?, ?, ?, 0)
            """,
            (
                user.id,
                username,
                full_name,
            )
        )
    else:
        cur.execute(
            """
            UPDATE users
            SET username = ?,
                full_name = ?
            WHERE id = ?
            """,
            (
                username,
                full_name,
                user.id
            )
        )

    DB.commit()


def get_balance(user_id):
    cur = DB.cursor()

    cur.execute(
        "SELECT balance FROM users WHERE id = ?",
        (user_id,)
    )

    row = cur.fetchone()

    if not row:
        return 0

    return row["balance"]


def change_balance(user_id, amount):
    cur = DB.cursor()

    cur.execute(
        """
        UPDATE users
        SET balance = balance + ?
        WHERE id = ?
        """,
        (
            amount,
            user_id
        )
    )

    DB.commit()


def add_transaction(user_id, tx_type, amount, status):
    cur = DB.cursor()

    cur.execute(
        """
        INSERT INTO transactions
        (user_id, type, amount, status, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_id,
            tx_type,
            amount,
            status,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )

    DB.commit()


def add_order(
    user_id,
    products,
    amount,
    address,
    phone,
    message,
    status="pending"
):
    cur = DB.cursor()

    cur.execute(
        """
        INSERT INTO orders
        (user_id, products, amount, address, phone, message, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            products,
            amount,
            address,
            phone,
            message,
            status,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )

    DB.commit()

    return cur.lastrowid


# ============================================================
# NARXNI KANAL POSTIDAN ANIQLASH
# ============================================================

def parse_number(value):
    value = value.strip().replace(" ", "")
    if not value:
        return None
    if "." in value and "," in value:
        # Masalan 200,000.50
        if value.rfind(".") > value.rfind(","):
            value = value.replace(",", "")
        else:
            value = value.replace(".", "").replace(",", ".")
    elif "," in value or "." in value:
        sep = "," if "," in value else "."
        parts = value.split(sep)
        if len(parts) == 2 and len(parts[1]) <= 2:
            # USD kabi 140.50
            try:
                return float(value.replace(",", "."))
            except ValueError:
                return None
        value = value.replace(",", "").replace(".", "")
    try:
        return float(value)
    except ValueError:
        return None


def extract_price(text):
    if not text:
        return None

    # Dollar: $140 / 140$ / 140 USD
    usd_patterns = [
        r"\$\s*([0-9][0-9\s,\.]*)",
        r"([0-9][0-9\s,\.]*)\s*(?:USD|usd|\$)"
    ]
    for pattern in usd_patterns:
        m = re.search(pattern, text)
        if m:
            number = parse_number(m.group(1))
            if number is not None:
                return int(round(number * USD_TO_UZS))

    # So'm / UZS / сум narxi. NARXI: 200 000 SO'M formatini ham oladi.
    uzs_patterns = [
        r"(?:NARXI|NARX|PRICE)\s*[:\-]?\s*([0-9][0-9\s,\.]*)\s*(?:SO['’ʻ`]?M|SUM|UZS|СУМ)?",
        r"([0-9][0-9\s,\.]*)\s*(?:SO['’ʻ`]?M|SUM|UZS|СУМ)"
    ]
    for pattern in uzs_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            number = parse_number(m.group(1))
            if number is not None:
                return int(round(number))

    return None


def charge_order(user_id, amount):
    cur = DB.cursor()
    cur.execute(
        """
        UPDATE users
        SET balance = balance - ?
        WHERE id = ? AND balance >= ?
        """,
        (amount, user_id, amount)
    )
    if cur.rowcount != 1:
        DB.rollback()
        return False
    DB.commit()
    return True


def refund_order(user_id, amount):
    change_balance(user_id, amount)

# ============================================================
# HOLATLAR
# ============================================================

class OrderState(StatesGroup):
    products = State()
    address_region = State()
    address_city = State()
    full_address = State()
    phone = State()
    message = State()
    confirm = State()


class DepositState(StatesGroup):
    receipt = State()
    amount = State()
    message = State()
    confirm = State()


class WithdrawState(StatesGroup):
    information = State()
    confirm = State()


class CustomerState(StatesGroup):
    message = State()


class AdminState(StatesGroup):
    reply = State()
    reject_reason = State()
    deposit_reject_reason = State()
    withdraw_reject_reason = State()


# ============================================================
# MIJOZ PANEL
# ============================================================

def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🛒 Buyurtma berish"),
                KeyboardButton(text="👤 Mening hisobim"),
            ],
            [
                KeyboardButton(text="📦 Buyurtmalarim"),
                KeyboardButton(text="❓ FAQ"),
            ],
            [
                KeyboardButton(text="🏪 Biz haqimizda"),
                KeyboardButton(text="💬 Adminga xabar"),
            ],
        ],
        resize_keyboard=True
    )


def back_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔙 Orqaga")
            ]
        ],
        resize_keyboard=True
    )


def order_channel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📢 Kanalga o'tish")
            ],
            [
                KeyboardButton(text="🔙 Orqaga")
            ]
        ],
        resize_keyboard=True
    )


def yes_no_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="👍 Ha"),
                KeyboardButton(text="🚫 Shart emas")
            ],
            [
                KeyboardButton(text="❌ Bekor qilish")
            ]
        ],
        resize_keyboard=True
    )


def confirm_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="✅ Yuborish"),
                KeyboardButton(text="❌ Bekor qilish")
            ]
        ],
        resize_keyboard=True
    )


def account_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="💳 Depozit"),
                KeyboardButton(text="💸 Yechib olish"),
            ],
            [
                KeyboardButton(text="📋 To'lov tarixi"),
                KeyboardButton(text="🔙 Orqaga"),
            ]
        ],
        resize_keyboard=True
    )


def faq_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🛒 Qanday buyurtma beraman"),
            ],
            [
                KeyboardButton(text="💰 Qanday balansga pul o'tkazaman"),
            ],
            [
                KeyboardButton(text="💸 Qanday balansdan pul yechaman"),
            ],
            [
                KeyboardButton(text="❌ Buyurtmani bekor qilsa bo'ladimi"),
            ],
            [
                KeyboardButton(text="🚚 Dostavka qayerga ishlaydi"),
            ],
            [
                KeyboardButton(text="💳 Qanday depozit qilaman"),
            ],
            [
                KeyboardButton(text="🔙 Orqaga")
            ]
        ],
        resize_keyboard=True
    )


def about_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📸 Instagram sahifa",
                    url="https://instagram.com/Shaxa_storeshop"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📢 Telegram kanal",
                    url="https://t.me/shaxatovarlar"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👨‍💼 Admin",
                    url="https://t.me/shaxbozshuxratovich11"
                )
            ]
        ]
    )


# ============================================================
# ADMIN PANEL
# ============================================================

def admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="💰 Balansni boshqarish"),
            ],
            [
                KeyboardButton(text="📥 Depozitlar"),
                KeyboardButton(text="📤 Yechib olishlar"),
            ],
            [
                KeyboardButton(text="🛒 Buyurtmalar"),
            ],
            [
                KeyboardButton(text="👥 Mijozlar"),
            ],
            [
                KeyboardButton(text="👤 Mijoz paneli"),
            ],
        ],
        resize_keyboard=True
    )


# ============================================================
# HUDUDLAR
# ============================================================

QASHQADARYO = [
    "🏙️ Qarshi shahri",
    "🏙️ Shahrisabz shahri",
    "📍 Qarshi tumani",
    "📍 Shahrisabz tumani",
    "📍 Chiroqchi tumani",
    "📍 Dehqonobod tumani",
    "📍 G'uzor tumani",
    "📍 Kasbi tumani",
    "📍 Kitob tumani",
    "📍 Koson tumani",
    "📍 Ko'kdala tumani",
    "📍 Mirishkor tumani",
    "📍 Muborak tumani",
    "📍 Nishon tumani",
    "📍 Qamashi tumani",
    "📍 Yakkabog' tumani",
]


def regions_keyboard():
    regions = [
        "📍 Andijon viloyati",
        "📍 Buxoro viloyati",
        "📍 Jizzax viloyati",
        "📍 Qashqadaryo viloyati",
        "📍 Navoiy viloyati",
        "📍 Namangan viloyati",
        "📍 Samarqand viloyati",
        "📍 Sirdaryo viloyati",
        "📍 Surxondaryo viloyati",
        "📍 Toshkent viloyati",
        "📍 Farg'ona viloyati",
        "📍 Xorazm viloyati",
        "📍 Toshkent shahri",
        "📍 Qoraqalpog'iston Respublikasi",
    ]

    rows = []

    for i in range(0, len(regions), 2):
        row = [
            KeyboardButton(text=regions[i])
        ]

        if i + 1 < len(regions):
            row.append(
                KeyboardButton(text=regions[i + 1])
            )

        rows.append(row)

    rows.append(
        [
            KeyboardButton(text="🔙 Orqaga")
        ]
    )

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True
    )


def cities_keyboard():
    rows = []

    for i in range(0, len(QASHQADARYO), 2):

        row = [
            KeyboardButton(text=QASHQADARYO[i])
        ]

        if i + 1 < len(QASHQADARYO):
            row.append(
                KeyboardButton(text=QASHQADARYO[i + 1])
            )

        rows.append(row)

    rows.append(
        [
            KeyboardButton(text="🔙 Orqaga")
        ]
    )

    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True
    )


# ============================================================
# START
# ============================================================

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):

    await state.clear()

    add_user(message.from_user)

    # /start bosilganda admin ham mijoz rejimida boshlanadi.
    admin_mode[message.from_user.id] = False

    name = message.from_user.first_name or "mijoz"

    await message.answer(
        f"👋 Assalomu alaykum, {name}! 🛍️\n\n"
        "🏪 SHAKH SPACE rasmiy botiga xush kelibsiz!\n\n"
        "🛒 Bu bot orqali mahsulotlarga buyurtma berishingiz mumkin.\n"
        "💰 Balansingizni boshqarishingiz mumkin.\n"
        "📦 Buyurtmalaringizni ko'rishingiz mumkin.\n"
        "💬 Admin bilan bog'lanishingiz mumkin.\n\n"
        "🛍️ Bizda:\n"
        "⌨️ Klaviaturalar\n"
        "🖱️ Mishkalar\n"
        "🎧 Quloqchinlar\n"
        "🔌 Kabellar\n"
        "🧹 Tozalash vositalari\n"
        "📦 Boshqa aksessuarlar\n\n"
        "📢 Yangiliklar va mahsulotlar kanalimizda.\n\n"
        "👇 Kerakli bo'limni tanlang.",
        reply_markup=main_keyboard()
    )


# ============================================================
# ADMIN COMMAND
# ============================================================

@dp.message(Command("admin"))
async def admin_command(message: Message, state: FSMContext):

    if message.from_user.id not in ADMIN_IDS:
        await message.answer(
            "❌ Sizda admin paneliga kirish huquqi yo'q."
        )
        return

    await state.clear()

    admin_mode[message.from_user.id] = True

    await message.answer(
        "👨‍💼 ADMIN PANEL\n\n"
        "🏪 SHAKH SPACE boshqaruv markazi.\n\n"
        "💰 Balanslarni boshqaring.\n"
        "📥 Depozitlarni tekshiring.\n"
        "📤 Yechib olishlarni ko'ring.\n"
        "🛒 Buyurtmalarni boshqaring.\n"
        "👥 Mijozlarni ko'ring.\n"
        "💬 Mijozlarga javob bering.",
        reply_markup=admin_keyboard()
    )


# ============================================================
# MIJOZ PANELIGA O'TISH
# ============================================================

@dp.message(F.text == "👤 Mijoz paneli")
async def customer_panel(message: Message, state: FSMContext):

    if message.from_user.id not in ADMIN_IDS:
        return

    await state.clear()

    admin_mode[message.from_user.id] = False

    await message.answer(
        "👤 MIJOZ PANELI\n\n"
        "🛍️ Oddiy mijoz sifatida botdan foydalanishingiz mumkin.",
        reply_markup=main_keyboard()
    )


# ============================================================
# BUYURTMA BOSHLASH
# ============================================================

@dp.message(F.text == "🛒 Buyurtma berish")
async def order_start(message: Message, state: FSMContext):

    # MUHIM O'ZGARISH: buyurtma berish uchun balansda pul bo'lishi shart.
    balance = get_balance(message.from_user.id)

    if balance <= 0:

        await message.answer(
            "❌ BUYURTMA BERIB BO'LMAYDI\n\n"
            "💰 Buyurtma berish uchun hisobingizda "
            "mablag' bo'lishi kerak.\n\n"
            f"💳 Hozirgi balansingiz: {balance:,} so'm\n\n"
            "👤 Mening hisobim → 💳 Depozit orqali "
            "hisobingizni to'ldiring.",
            reply_markup=main_keyboard()
        )

        return

    await state.clear()

    await state.set_state(OrderState.products)

    await message.answer(
        "🛒 BUYURTMA BERISH 📦\n\n"
        f"💳 Balansingiz: {balance:,} so'm\n\n"
        "📢 Pastdagi tugma orqali SHAKH SPACE kanaliga o'ting.\n\n"
        "🔎 Kerakli mahsulotni toping.\n"
        "📦 Mahsulot xabarini shu botga forward qiling.\n\n"
        "👇 Avval kanalga o'ting.",
        reply_markup=order_channel_keyboard()
    )


# ============================================================
# KANAL
# ============================================================

@dp.message(
    OrderState.products,
    F.text == "📢 Kanalga o'tish"
)
async def channel(message: Message, state: FSMContext):

    await message.answer(
        "📢 SHAKH SPACE KANALI 🏪\n\n"
        "👇 Kanalga o'tish uchun quyidagi tugmani bosing.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📢 SHAKH SPACE kanaliga o'tish",
                        url="https://t.me/shaxatovarlar"
                    )
                ]
            ]
        )
    )


# ============================================================
# BUYURTMA ORQAGA
# ============================================================

@dp.message(
    OrderState.products,
    F.text == "🔙 Orqaga"
)
async def order_back(message: Message, state: FSMContext):

    await state.clear()

    await message.answer(
        "🏠 Bosh menyu 🏪",
        reply_markup=main_keyboard()
    )


# ============================================================
# YANA MAHSULOT ("👍 Ha")
# ============================================================
# MUHIM: bu handler (va pastdagi "🚫 Shart emas" / "❌ Bekor qilish"
# handlerlari) pastdagi umumiy `product_forward` catch-all handleridan
# OLDIN turishi SHART. Aks holda catch-all ular ham "forward emas"
# deb ushlab qolib, tugmalar ishlamay qoladi (aynan shu bug bor edi).

@dp.message(
    OrderState.products,
    F.text == "👍 Ha"
)
async def more_product(message: Message, state: FSMContext):

    await message.answer(
        "📦 Yana bir mahsulot xabarini "
        "SHAKH SPACE kanalidan forward qiling.\n\n"
        "👇 Keyingi mahsulotni yuboring.",
        reply_markup=order_channel_keyboard()
    )


# ============================================================
# SHART EMAS
# ============================================================

@dp.message(
    OrderState.products,
    F.text == "🚫 Shart emas"
)
async def finish_products(message: Message, state: FSMContext):

    data = await state.get_data()

    products = data.get("products", [])

    if not products:
        await message.answer(
            "❌ Hali mahsulot tanlanmagan.\n\n"
            "📦 Avval kanalimizdan mahsulot xabarini "
            "forward qiling."
        )
        return

    await state.set_state(
        OrderState.address_region
    )

    await message.answer(
        "✅ Mahsulotlar tanlandi! 📦\n\n"
        "📍 Endi manzilingiz joylashgan "
        "viloyatni tanlang.\n\n"
        "🚚 Hozircha faqat Qashqadaryo viloyatiga "
        "dostavka mavjud.",
        reply_markup=regions_keyboard()
    )


# ============================================================
# ORDER CANCEL
# ============================================================

@dp.message(
    OrderState.products,
    F.text == "❌ Bekor qilish"
)
async def cancel_order_products(
    message: Message,
    state: FSMContext
):

    await state.clear()

    await message.answer(
        "❌ Buyurtma bekor qilindi.\n\n"
        "🏠 Bosh menyuga qaytdingiz.",
        reply_markup=main_keyboard()
    )


# ============================================================
# PRODUCT FORWARD (CATCH-ALL — shu state uchun ENG OXIRIDA turishi kerak)
# ============================================================

@dp.message(OrderState.products)
async def product_forward(message: Message, state: FSMContext):

    # Ha / shart emas / bekor qilish / kanalga o'tish / orqaga — bularning
    # barchasi yuqorida alohida handlerlar bilan ushlab olinadi, shuning
    # uchun bu yerga faqat forward yoki noto'g'ri xabar keladi.

    if not message.forward_from_chat:

        await message.answer(
            "📦 Mahsulotni SHAKH SPACE kanalidan "
            "forward qilib yuboring.\n\n"
            "📢 Kanalga o'tish uchun tugmani bosing.",
            reply_markup=order_channel_keyboard()
        )

        return

    data = await state.get_data()

    products = data.get("products", [])

    forwarded_text = message.text or message.caption or ""
    price = extract_price(forwarded_text)

    if price is None:
        await message.answer(
            "❌ Mahsulot narxini aniqlab bo'lmadi.\n\n"
            "📌 Kanal postida `NARXI: 200 000 SO'M` yoki `$140` kabi narx bo'lishi kerak.\n"
            "🔄 Shu postni qaytadan forward qiling."
        )
        return

    products.append(
        {
            "chat_id": message.forward_from_chat.id,
            "message_id": message.forward_from_message_id,
            "price": price
        }
    )

    await state.update_data(
        products=products
    )

    await message.answer(
        "✅ Mahsulot qabul qilindi! 📦\n\n"
        f"🛒 Hozircha {len(products)} ta mahsulot tanlandi.\n\n"
        "➕ Yana mahsulot kerak bo'lsa — 👍 Ha.\n"
        "✅ Buyurtmani davom ettirish uchun — 🚫 Shart emas.",
        reply_markup=yes_no_keyboard()
    )


# ============================================================
# VILOYAT
# ============================================================

@dp.message(OrderState.address_region)
async def choose_region(
    message: Message,
    state: FSMContext
):

    if message.text == "🔙 Orqaga":

        await state.clear()

        await message.answer(
            "🏠 Bosh menyu",
            reply_markup=main_keyboard()
        )

        return

    if message.text != "📍 Qashqadaryo viloyati":

        await message.answer(
            "🚚 Afsuski, bu hududga hozircha "
            "dostavka mavjud emas.\n\n"
            "📍 Faqat Qashqadaryo viloyatiga "
            "dostavka mavjud.",
            reply_markup=regions_keyboard()
        )

        return

    await state.update_data(
        region="Qashqadaryo viloyati"
    )

    await state.set_state(
        OrderState.address_city
    )

    await message.answer(
        "📍 Qashqadaryo viloyati tanlandi! ✅\n\n"
        "🏙️ Endi shahar yoki tumanni tanlang.",
        reply_markup=cities_keyboard()
    )


# ============================================================
# SHAHAR
# ============================================================

@dp.message(OrderState.address_city)
async def choose_city(
    message: Message,
    state: FSMContext
):

    if message.text == "🔙 Orqaga":

        await state.set_state(
            OrderState.address_region
        )

        await message.answer(
            "📍 Viloyatni tanlang.",
            reply_markup=regions_keyboard()
        )

        return

    if message.text not in QASHQADARYO:

        await message.answer(
            "❌ Iltimos tugmalardan birini tanlang.",
            reply_markup=cities_keyboard()
        )

        return

    await state.update_data(
        city=message.text
    )

    await state.set_state(
        OrderState.full_address
    )

    await message.answer(
        "🏠 TO'LIQ MANZIL 📍\n\n"
        "Ko'cha nomi, uy raqami va mo'ljalni yozing.\n\n"
        "💡 Masalan:\n"
        "Mustaqillik ko'chasi, 25-uy, "
        "maktab yonida.",
        reply_markup=back_keyboard()
    )


# ============================================================
# MANZIL
# ============================================================

@dp.message(OrderState.full_address)
async def full_address(
    message: Message,
    state: FSMContext
):

    if message.text == "🔙 Orqaga":

        await state.set_state(
            OrderState.address_city
        )

        await message.answer(
            "🏙️ Shahar yoki tumanni tanlang.",
            reply_markup=cities_keyboard()
        )

        return

    await state.update_data(
        address=message.text
    )

    await state.set_state(
        OrderState.phone
    )

    await message.answer(
        "📱 TELEFON RAQAMI ☎️\n\n"
        "🇺🇿 O'zbekiston raqamingizni kiriting.\n\n"
        "Masalan:\n"
        "919292901\n"
        "yoki\n"
        "+998919292901",
        reply_markup=back_keyboard()
    )


# ============================================================
# TELEFON
# ============================================================

@dp.message(OrderState.phone)
async def phone(
    message: Message,
    state: FSMContext
):

    if message.text == "🔙 Orqaga":

        await state.set_state(
            OrderState.full_address
        )

        await message.answer(
            "🏠 To'liq manzilingizni kiriting.",
            reply_markup=back_keyboard()
        )

        return

    phone_number = (
        message.text
        .replace("+", "")
        .replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )

    if phone_number.startswith("998"):

        if (
            len(phone_number) != 12
            or not phone_number.isdigit()
        ):
            await message.answer(
                "❌ Telefon raqami noto'g'ri.\n\n"
                "🇺🇿 Masalan:\n"
                "+998919292901"
            )

            return

    elif (
        len(phone_number) != 9
        or not phone_number.isdigit()
    ):

        await message.answer(
            "❌ Telefon raqami noto'g'ri.\n\n"
            "🇺🇿 Masalan:\n"
            "919292901"
        )

        return

    if len(phone_number) == 9:
        phone_number = "+998" + phone_number
    else:
        phone_number = "+" + phone_number

    await state.update_data(
        phone=phone_number
    )

    await state.set_state(
        OrderState.message
    )

    await message.answer(
        "💬 BUYURTMA XABARI 📝\n\n"
        "Admin bilishi kerak bo'lgan qo'shimcha "
        "ma'lumot bo'lsa yozing.\n\n"
        "Masalan: rang, model yoki boshqa istak.",
        reply_markup=back_keyboard()
    )


# ============================================================
# BUYURTMA XABARI
# ============================================================

@dp.message(OrderState.message)
async def order_message(
    message: Message,
    state: FSMContext
):

    if message.text == "🔙 Orqaga":

        await state.set_state(
            OrderState.phone
        )

        await message.answer(
            "📱 Telefon raqamingizni kiriting.",
            reply_markup=back_keyboard()
        )

        return

    await state.update_data(
        customer_message=message.text
    )

    await state.set_state(
        OrderState.confirm
    )

    data = await state.get_data()

    products = data.get(
        "products",
        []
    )
    total_amount = sum(int(p.get("price", 0)) for p in products)

    await state.update_data(total_amount=total_amount)

    await message.answer(
        "🧾 BUYURTMA TEKSHIRUVI 📦\n\n"
        f"📦 Mahsulotlar: {len(products)} ta\n"
        f"💰 Jami narx: {total_amount:,} so'm\n"
        f"📍 Viloyat: {data.get('region')}\n"
        f"🏙️ Shahar/tuman: {data.get('city')}\n"
        f"🏠 Manzil: {data.get('address')}\n"
        f"📱 Telefon: {data.get('phone')}\n"
        f"💬 Xabar: {data.get('customer_message')}\n\n"
        "✅ Hammasi to'g'rimi?",
        reply_markup=confirm_keyboard()
    )


# ============================================================
# BUYURTMA BEKOR
# ============================================================

@dp.message(
    OrderState.confirm,
    F.text == "❌ Bekor qilish"
)
async def cancel_order(
    message: Message,
    state: FSMContext
):

    await state.clear()

    await message.answer(
        "❌ Buyurtma bekor qilindi.",
        reply_markup=main_keyboard()
    )


# ============================================================
# BUYURTMA YUBORISH
# ============================================================

@dp.message(
    OrderState.confirm,
    F.text == "✅ Yuborish"
)
async def send_order(
    message: Message,
    state: FSMContext
):

    data = await state.get_data()
    products = data.get("products", [])
    total_amount = int(data.get("total_amount", 0))

    if not products or total_amount <= 0:
        await state.clear()
        await message.answer(
            "❌ Buyurtma ma'lumotlari topilmadi.",
            reply_markup=main_keyboard()
        )
        return

    balance = get_balance(message.from_user.id)

    if balance < total_amount:
        missing = total_amount - balance
        await state.clear()
        await message.answer(
            "❌ BUYURTMA BERIB BO'LMAYDI\n\n"
            f"💰 Mahsulotlar jami: {total_amount:,} so'm\n"
            f"💳 Balansingiz: {balance:,} so'm\n"
            f"⚠️ Yetishmayapti: {missing:,} so'm\n\n"
            "👤 Mening hisobim → 💳 Depozit orqali balansni to'ldiring.",
            reply_markup=main_keyboard()
        )
        return

    if not charge_order(message.from_user.id, total_amount):
        await state.clear()
        await message.answer(
            "❌ Balansingiz yetarli emas yoki balans o'zgargan.\n\n"
            "💳 Iltimos balansingizni tekshiring.",
            reply_markup=main_keyboard()
        )
        return

    order_id = add_order(
        message.from_user.id,
        str(len(products)),
        total_amount,
        data.get("address", ""),
        data.get("phone", ""),
        data.get("customer_message", "")
    )

    add_transaction(
        message.from_user.id,
        "order",
        total_amount,
        "confirmed"
    )

    username = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else "Username yo'q"
    )

    admin_markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Qabul qilish",
                    callback_data=f"order_yes:{order_id}:{message.from_user.id}"
                ),
                InlineKeyboardButton(
                    text="❌ Rad etish",
                    callback_data=f"order_no:{order_id}:{message.from_user.id}"
                )
            ]
        ]
    )

    # Adminlardan biriga yuborishda xato chiqsa ham mijozga
    # "buyurtma yuborildi" xabari albatta boradi.
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                "🆕 YANGI BUYURTMA 📦\n\n"
                f"🆔 Buyurtma: #{order_id}\n"
                f"👤 ID: {message.from_user.id}\n"
                f"👤 Username: {username}\n\n"
                f"📦 Mahsulotlar: {len(products)} ta\n"
                f"💰 Jami narx: {total_amount:,} so'm\n"
                f"📍 Viloyat: {data.get('region')}\n"
                f"🏙️ Shahar/tuman: {data.get('city')}\n"
                f"🏠 Manzil: {data.get('address')}\n"
                f"📱 Telefon: {data.get('phone')}\n"
                f"💬 Xabar: {data.get('customer_message')}",
                reply_markup=admin_markup
            )
        except Exception as e:
            print(f"Buyurtmani admin {admin_id} ga yuborishda xato: {e}")

    for product in products:
        for admin_id in ADMIN_IDS:
            try:
                await bot.forward_message(
                    admin_id,
                    product["chat_id"],
                    product["message_id"]
                )
            except Exception:
                pass

    await state.clear()

    # Mijozdagi "Yuborish/Bekor qilish" tugmalarini majburan yopamiz.
    await message.answer(
        "✅ BUYURTMANGIZ YUBORILDI! 📦\n\n"
        f"💰 {total_amount:,} so'm balansingizdan yechildi.\n"
        "👨‍💼 Admin buyurtmangizni tekshiradi.\n"
        "⏳ Tez orada sizga xabar beramiz.",
        reply_markup=ReplyKeyboardRemove()
    )

    await message.answer(
        "🏠 BOSH MENYU\n\n"
        "👇 Kerakli bo'limni tanlang.",
        reply_markup=main_keyboard()
    )


# ============================================================
# ADMIN BUYURTMANI QABUL QILISH
# ============================================================

@dp.callback_query(
    F.data.startswith("order_yes:")
)
async def order_yes(
    callback: CallbackQuery
):

    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Siz admin emassiz.", show_alert=True)
        return

    _, order_id, user_id = callback.data.split(":")
    order_id = int(order_id)
    user_id = int(user_id)

    cur = DB.cursor()
    cur.execute("SELECT status FROM orders WHERE id = ?", (order_id,))
    row = cur.fetchone()

    if not row:
        await callback.answer("❌ Buyurtma topilmadi.", show_alert=True)
        return

    if row["status"] != "pending":
        await callback.answer("⚠️ Bu buyurtma allaqachon ko'rib chiqilgan.", show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    cur.execute(
        "UPDATE orders SET status = 'accepted' WHERE id = ? AND status = 'pending'",
        (order_id,)
    )
    DB.commit()

    await bot.send_message(
        user_id,
        "✅ BUYURTMANGIZ TASDIQLANDI! 📦\n\n"
        "👨‍💼 Buyurtmangiz admin tomonidan qabul qilindi.\n"
        "⏳ Tez orada sizga xabar beramiz.",
        reply_markup=main_keyboard()
    )

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.answer("✅ Buyurtma tasdiqlandi.")


# ============================================================
# ADMIN BUYURTMANI RAD ETISH
# ============================================================

@dp.callback_query(
    F.data.startswith("order_no:")
)
async def order_no(
    callback: CallbackQuery,
    state: FSMContext
):

    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer(
            "❌ Siz admin emassiz.",
            show_alert=True
        )
        return

    _, order_id, user_id = (
        callback.data.split(":")
    )

    await state.clear()

    await state.update_data(
        reject_order_id=int(order_id),
        reject_user_id=int(user_id)
    )

    await state.set_state(
        AdminState.reject_reason
    )

    await callback.message.answer(
        "❌ BUYURTMANI RAD ETISH\n\n"
        "📝 Rad etish sababini yozing."
    )

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.answer()


@dp.message(AdminState.reject_reason)
async def order_reject_reason(
    message: Message,
    state: FSMContext
):

    if message.from_user.id not in ADMIN_IDS:
        return

    data = await state.get_data()

    order_id = data["reject_order_id"]
    user_id = data["reject_user_id"]

    cur = DB.cursor()

    cur.execute(
        """
        UPDATE orders
        SET status = 'rejected'
        WHERE id = ?
        """,
        (order_id,)
    )

    DB.commit()

    await bot.send_message(
        user_id,
        "❌ BUYURTMANGIZ RAD ETILDI 📦\n\n"
        f"📝 Sababi:\n{message.text}\n\n"
        "💬 Savol bo'lsa admin bilan bog'laning."
    )

    await message.answer(
        "✅ Buyurtma rad etildi.",
        reply_markup=admin_keyboard()
    )

    await state.clear()


# ============================================================
# MENING HISOBIM
# ============================================================

@dp.message(F.text == "👤 Mening hisobim")
async def account(message: Message):

    add_user(message.from_user)

    balance = get_balance(
        message.from_user.id
    )

    await message.answer(
        "👤 MENING HISOBIM 💳\n\n"
        f"🆔 ID: {message.from_user.id}\n"
        f"👤 Username: "
        f"@{message.from_user.username or 'yo‘q'}\n\n"
        f"💰 BALANS: {balance:,} so'm\n\n"
        "👇 Kerakli amalni tanlang.",
        reply_markup=account_keyboard()
    )


# ============================================================
# DEPOZIT BOSHLASH
# ============================================================

@dp.message(F.text == "💳 Depozit")
async def deposit_start(
    message: Message,
    state: FSMContext
):

    await state.clear()

    await state.set_state(
        DepositState.receipt
    )

    await message.answer(
        "💳 DEPOZIT 💰\n\n"
        f"💳 Karta: {CARD_NUMBER}\n"
        f"👤 Hisob nomi: {CARD_NAME}\n\n"
        "💰 To'lovni ushbu kartaga amalga oshiring.\n\n"
        "🧾 Keyin chekni rasm yoki PDF shaklida yuboring.\n\n"
        "⚠️ Chek yuborilmasa depozit tasdiqlanmaydi.",
        reply_markup=back_keyboard()
    )


# ============================================================
# DEPOZIT CHEK
# ============================================================

@dp.message(DepositState.receipt)
async def deposit_receipt(
    message: Message,
    state: FSMContext
):

    if message.text == "🔙 Orqaga":

        await state.clear()

        await message.answer(
            "👤 Mening hisobim",
            reply_markup=account_keyboard()
        )

        return

    if not message.photo and not message.document:

        await message.answer(
            "🧾 Iltimos chekni rasm yoki PDF shaklida yuboring."
        )

        return

    if message.photo:

        receipt_type = "photo"
        receipt_id = message.photo[-1].file_id

    else:

        receipt_type = "document"
        receipt_id = message.document.file_id

    await state.update_data(
        receipt_type=receipt_type,
        receipt_id=receipt_id
    )

    await state.set_state(
        DepositState.amount
    )

    await message.answer(
        "💰 Qancha so'm to'laganingizni yozing.\n\n"
        "🔢 Faqat raqam.\n\n"
        "Masalan: 50000",
        reply_markup=back_keyboard()
    )


# ============================================================
# DEPOZIT SUMMA
# ============================================================

@dp.message(DepositState.amount)
async def deposit_amount(
    message: Message,
    state: FSMContext
):

    if message.text == "🔙 Orqaga":

        await state.set_state(
            DepositState.receipt
        )

        await message.answer(
            "🧾 Chekni yuboring.",
            reply_markup=back_keyboard()
        )

        return

    amount_text = (
        message.text
        .replace(" ", "")
        .replace(",", "")
        .replace(".", "")
    )

    if not amount_text.isdigit():

        await message.answer(
            "❌ Miqdor noto'g'ri.\n\n"
            "💰 Masalan: 50000"
        )

        return

    amount = int(amount_text)

    if amount <= 0:

        await message.answer(
            "❌ Miqdor 0 dan katta bo'lishi kerak."
        )

        return

    await state.update_data(
        amount=amount
    )

    await state.set_state(
        DepositState.message
    )

    await message.answer(
        "💬 Depozit haqida xabar yozing.\n\n"
        "Masalan: karta orqali to'ladim.",
        reply_markup=back_keyboard()
    )


# ============================================================
# DEPOZIT XABAR
# ============================================================

@dp.message(DepositState.message)
async def deposit_message(
    message: Message,
    state: FSMContext
):

    if message.text == "🔙 Orqaga":

        await state.set_state(
            DepositState.amount
        )

        await message.answer(
            "💰 Miqdorni kiriting.",
            reply_markup=back_keyboard()
        )

        return

    await state.update_data(
        customer_message=message.text
    )

    await state.set_state(
        DepositState.confirm
    )

    data = await state.get_data()

    await message.answer(
        "🧾 DEPOZIT TEKSHIRUVI 💳\n\n"
        f"💰 Miqdor: {data['amount']:,} so'm\n"
        f"🆔 ID: {message.from_user.id}\n"
        f"👤 Username: "
        f"@{message.from_user.username or 'yo‘q'}\n"
        f"💬 Xabar: {data['customer_message']}\n\n"
        "🧾 Chek yuborilgan.\n\n"
        "✅ Ma'lumotlar to'g'rimi?",
        reply_markup=confirm_keyboard()
    )


# ============================================================
# DEPOZIT CANCEL
# ============================================================

@dp.message(
    DepositState.confirm,
    F.text == "❌ Bekor qilish"
)
async def deposit_cancel(
    message: Message,
    state: FSMContext
):

    await state.clear()

    await message.answer(
        "❌ Depozit bekor qilindi.",
        reply_markup=account_keyboard()
    )


# ============================================================
# DEPOZIT YUBORISH
# ============================================================

@dp.message(
    DepositState.confirm,
    F.text == "✅ Yuborish"
)
async def deposit_send(
    message: Message,
    state: FSMContext
):

    data = await state.get_data()

    amount = data["amount"]

    add_transaction(
        message.from_user.id,
        "deposit",
        amount,
        "pending"
    )

    username = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else "Username yo'q"
    )

    admin_text = (
        "💳 YANGI DEPOZIT 📥\n\n"
        f"💰 Miqdor: {amount:,} so'm\n"
        f"🆔 ID: {message.from_user.id}\n"
        f"👤 Username: {username}\n"
        f"💬 Xabar: {data['customer_message']}"
    )

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Tasdiqlash",
                    callback_data=(
                        f"dep_yes:"
                        f"{message.from_user.id}:"
                        f"{amount}"
                    )
                ),
                InlineKeyboardButton(
                    text="❌ Rad etish",
                    callback_data=(
                        f"dep_no:"
                        f"{message.from_user.id}:"
                        f"{amount}"
                    )
                )
            ]
        ]
    )

    # Adminlarga yuborish mijozning javobini to'xtatib qo'ymasligi uchun
    # har bir admin alohida tekshiriladi.
    for admin_id in ADMIN_IDS:
        try:
            if data["receipt_type"] == "photo":
                await bot.send_photo(
                    admin_id,
                    data["receipt_id"],
                    caption=admin_text,
                    reply_markup=markup
                )
            else:
                await bot.send_document(
                    admin_id,
                    data["receipt_id"],
                    caption=admin_text,
                    reply_markup=markup
                )
        except Exception as e:
            print(f"Depozitni admin {admin_id} ga yuborishda xato: {e}")

    await state.clear()

    # Eski "Yuborish/Bekor qilish" klaviaturasini majburan olib tashlaymiz.
    await message.answer(
        "✅ BALANS TO'LDIRISH ARIZANGIZ YUBORILDI! 💳\n\n"
        "👨‍💼 Admin chekni tekshiradi.\n"
        "⏳ Tasdiqlangandan keyin balansingiz to'ldiriladi.",
        reply_markup=ReplyKeyboardRemove()
    )

    # Keyingi xabarda faqat asosiy menyu chiqadi.
    await message.answer(
        "🏠 BOSH MENYU\n\n"
        "👇 Kerakli bo'limni tanlang.",
        reply_markup=main_keyboard()
    )


# ============================================================
# DEPOZIT TASDIQLASH
# ============================================================
# MUHIM O'ZGARISH (BUG FIX):
# Ilgari bu yerda admin "✅ Tasdiqlash" bosishi bilanoq
# change_balance() chaqirilib, balansga AVTOMATIK pul qo'shilardi.
# Endi bu yerda balans AVTOMATIK o'zgarmaydi — faqat depozit
# "tasdiqlandi" deb belgilanadi va mijozga xabar boriladi.
# Balansni admin o'zi qo'lda /addbalance buyrug'i orqali qo'shadi.

@dp.callback_query(
    F.data.startswith("dep_yes:")
)
async def deposit_yes(
    callback: CallbackQuery
):

    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer(
            "❌ Siz admin emassiz.",
            show_alert=True
        )
        return

    _, user_id, amount = (
        callback.data.split(":")
    )

    user_id = int(user_id)
    amount = int(amount)

    # Bir xil ariza ikki marta tasdiqlanmasin
    cur = DB.cursor()

    cur.execute(
        """
        SELECT id
        FROM transactions
        WHERE user_id = ?
        AND type = 'deposit'
        AND amount = ?
        AND status = 'pending'
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            user_id,
            amount
        )
    )

    tx = cur.fetchone()

    if not tx:

        await callback.answer(
            "⚠️ Bu depozit allaqachon ko'rib chiqilgan.",
            show_alert=True
        )

        return

    tx_id = tx["id"]

    # ❌ ENDI BU YERDA change_balance() CHAQIRILMAYDI.
    # Balansni admin o'zi /addbalance orqali qo'lda qo'shadi.

    cur.execute(
        """
        UPDATE transactions
        SET status = 'confirmed'
        WHERE id = ?
        """,
        (tx_id,)
    )

    DB.commit()

    await bot.send_message(
        user_id,
        "✅ DEPOZITINGIZ TASDIQLANDI! 💳\n\n"
        f"💰 Miqdor: {amount:,} so'm\n\n"
        "⏳ Balansingiz admin tomonidan tez orada "
        "qo'lda qo'shiladi."
    )

    await callback.message.answer(
        "✅ Depozit tasdiqlandi (chek to'g'ri).\n\n"
        "⚠️ ESLATMA: balans AVTOMATIK qo'shilmadi.\n"
        "💰 Balansni qo'shish uchun buyruqdan foydalaning:\n"
        f"/addbalance {user_id} {amount}"
    )

    try:
        await callback.message.edit_reply_markup(
            reply_markup=None
        )
    except Exception:
        pass

    await callback.answer(
        "✅ Tasdiqlandi (balans hali qo'shilmadi)."
    )


# ============================================================
# DEPOZIT RAD
# ============================================================

@dp.callback_query(
    F.data.startswith("dep_no:")
)
async def deposit_no(
    callback: CallbackQuery,
    state: FSMContext
):

    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer(
            "❌ Siz admin emassiz.",
            show_alert=True
        )
        return

    _, user_id, amount = (
        callback.data.split(":")
    )

    await state.clear()

    await state.update_data(
        deposit_user_id=int(user_id),
        deposit_amount=int(amount)
    )

    await state.set_state(
        AdminState.deposit_reject_reason
    )

    await callback.message.answer(
        "❌ DEPOZITNI RAD ETISH\n\n"
        "📝 Rad etish sababini yozing."
    )

    await callback.answer()


@dp.message(
    AdminState.deposit_reject_reason
)
async def deposit_reject_reason(
    message: Message,
    state: FSMContext
):

    if message.from_user.id not in ADMIN_IDS:
        return

    data = await state.get_data()

    user_id = data["deposit_user_id"]
    amount = data["deposit_amount"]

    cur = DB.cursor()

    cur.execute(
        """
        SELECT id
        FROM transactions
        WHERE user_id = ?
        AND type = 'deposit'
        AND amount = ?
        AND status = 'pending'
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            user_id,
            amount
        )
    )

    tx = cur.fetchone()

    if tx:

        cur.execute(
            """
            UPDATE transactions
            SET status = 'rejected'
            WHERE id = ?
            """,
            (tx["id"],)
        )

        DB.commit()

    await bot.send_message(
        user_id,
        "❌ DEPOZIT RAD ETILDI 💳\n\n"
        f"📝 Sababi:\n{message.text}"
    )

    await message.answer(
        "✅ Depozit rad etildi.",
        reply_markup=admin_keyboard()
    )

    await state.clear()


# ============================================================
# YECHIB OLISH
# ============================================================

@dp.message(F.text == "💸 Yechib olish")
async def withdraw_start(
    message: Message,
    state: FSMContext
):

    balance = get_balance(
        message.from_user.id
    )

    if balance <= 0:

        await message.answer(
            "❌ Balansingizda pul mavjud emas.",
            reply_markup=account_keyboard()
        )

        return

    await state.clear()

    await state.set_state(
        WithdrawState.information
    )

    await message.answer(
        "💸 YECHIB OLISH 💰\n\n"
        f"💰 Hozirgi balans: {balance:,} so'm\n\n"
        "📝 Quyidagi ma'lumotlarni yuboring:\n\n"
        "💳 Hisob raqami\n"
        "👤 Hisob nomi\n"
        "💰 Miqdor\n"
        "📝 Sababi\n\n"
        "💡 Masalan:\n"
        "Hisob raqami: 8600...\n"
        "Hisob nomi: Ali\n"
        "Miqdor: 50000\n"
        "Sababi: Buyurtma",
        reply_markup=back_keyboard()
    )


@dp.message(WithdrawState.information)
async def withdraw_information(
    message: Message,
    state: FSMContext
):

    if message.text == "🔙 Orqaga":

        await state.clear()

        await message.answer(
            "👤 Mening hisobim",
            reply_markup=account_keyboard()
        )

        return

    await state.update_data(
        information=message.text
    )

    await state.set_state(
        WithdrawState.confirm
    )

    await message.answer(
        "💸 YECHIB OLISH TEKSHIRUVI\n\n"
        f"{message.text}\n\n"
        "✅ Ma'lumotlaringiz to'g'rimi?",
        reply_markup=confirm_keyboard()
    )


# ============================================================
# WITHDRAW CANCEL
# ============================================================

@dp.message(
    WithdrawState.confirm,
    F.text == "❌ Bekor qilish"
)
async def withdraw_cancel(
    message: Message,
    state: FSMContext
):

    await state.clear()

    await message.answer(
        "❌ Yechib olish bekor qilindi.",
        reply_markup=account_keyboard()
    )


# ============================================================
# WITHDRAW SEND
# ============================================================

@dp.message(
    WithdrawState.confirm,
    F.text == "✅ Yuborish"
)
async def withdraw_send(
    message: Message,
    state: FSMContext
):

    data = await state.get_data()

    information = data["information"]

    for admin_id in ADMIN_IDS:

        await bot.send_message(
            admin_id,
            "💸 YANGI YECHIB OLISH ARIZASI 📤\n\n"
            f"🆔 ID: {message.from_user.id}\n"
            f"👤 Username: "
            f"@{message.from_user.username or 'yo‘q'}\n\n"
            f"📝 MA'LUMOT:\n{information}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Tasdiqlash",
                            callback_data=(
                                f"with_yes:"
                                f"{message.from_user.id}"
                            )
                        ),
                        InlineKeyboardButton(
                            text="❌ Rad etish",
                            callback_data=(
                                f"with_no:"
                                f"{message.from_user.id}"
                            )
                        )
                    ]
                ]
            )
        )

    await state.clear()

    await message.answer(
        "✅ YECHIB OLISH ARIZASI YUBORILDI! 💸\n\n"
        "👨‍💼 Admin tekshiradi.",
        reply_markup=account_keyboard()
    )


# ============================================================
# WITHDRAW YES
# ============================================================

@dp.callback_query(
    F.data.startswith("with_yes:")
)
async def withdraw_yes(
    callback: CallbackQuery
):

    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer(
            "❌ Siz admin emassiz.",
            show_alert=True
        )
        return

    _, user_id = callback.data.split(":")

    user_id = int(user_id)

    await bot.send_message(
        user_id,
        "✅ YECHIB OLISH ARIZANGIZ TASDIQLANDI! 💸\n\n"
        "💳 Admin to'lovni amalga oshiradi.\n"
        "⏳ To'lov amalga oshirilgandan keyin "
        "balans admin tomonidan yangilanadi."
    )

    await callback.message.edit_reply_markup(
        reply_markup=None
    )

    await callback.message.answer(
        "✅ Yechib olish tasdiqlandi.\n\n"
        "⚠️ Pulni foydalanuvchiga o'tkazgandan keyin "
        "admin paneldagi balansni ayiring."
    )

    await callback.answer(
        "✅ Tasdiqlandi."
    )


# ============================================================
# WITHDRAW NO
# ============================================================

@dp.callback_query(
    F.data.startswith("with_no:")
)
async def withdraw_no(
    callback: CallbackQuery,
    state: FSMContext
):

    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer(
            "❌ Siz admin emassiz.",
            show_alert=True
        )
        return

    _, user_id = callback.data.split(":")

    await state.clear()

    await state.update_data(
        withdraw_user_id=int(user_id)
    )

    await state.set_state(
        AdminState.withdraw_reject_reason
    )

    await callback.message.answer(
        "❌ YECHIB OLISHNI RAD ETISH\n\n"
        "📝 Rad etish sababini yozing."
    )

    await callback.answer()


@dp.message(
    AdminState.withdraw_reject_reason
)
async def withdraw_reject_reason(
    message: Message,
    state: FSMContext
):

    if message.from_user.id not in ADMIN_IDS:
        return

    data = await state.get_data()

    user_id = data["withdraw_user_id"]

    await bot.send_message(
        user_id,
        "❌ YECHIB OLISH ARIZANGIZ RAD ETILDI 💸\n\n"
        f"📝 Sababi:\n{message.text}"
    )

    await message.answer(
        "✅ Ariza rad etildi.",
        reply_markup=admin_keyboard()
    )

    await state.clear()


# ============================================================
# TO'LOV TARIXI
# ============================================================

@dp.message(F.text == "📋 To'lov tarixi")
async def payment_history(
    message: Message
):

    cur = DB.cursor()

    cur.execute(
        """
        SELECT type, amount, status, created_at
        FROM transactions
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 20
        """,
        (message.from_user.id,)
    )

    rows = cur.fetchall()

    if not rows:

        await message.answer(
            "📋 TO'LOV TARIXI 📋\n\n"
            "Hozircha tarix mavjud emas.",
            reply_markup=account_keyboard()
        )

        return

    text = "📋 TO'LOV TARIXI 💳\n\n"

    for row in rows:

        if row["type"] == "deposit":
            icon = "💰"
            name = "Depozit"
        elif row["type"] == "order":
            icon = "🛒"
            name = "Buyurtma uchun to'lov"
        elif row["type"] == "order_refund":
            icon = "↩️"
            name = "Buyurtma puli qaytarildi"
        else:
            icon = "💸"
            name = "Yechib olish"

        text += (
            f"{icon} {name}\n"
            f"💵 {row['amount']:,} so'm\n"
            f"📌 Holat: {row['status']}\n"
            f"🕐 {row['created_at']}\n\n"
        )

    await message.answer(
        text,
        reply_markup=account_keyboard()
    )


# ============================================================
# BUYURTMALARIM
# ============================================================

@dp.message(F.text == "📦 Buyurtmalarim")
async def my_orders(
    message: Message
):

    cur = DB.cursor()

    cur.execute(
        """
        SELECT id,
               products,
               amount,
               address,
               phone,
               status,
               created_at
        FROM orders
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 20
        """,
        (message.from_user.id,)
    )

    rows = cur.fetchall()

    if not rows:

        await message.answer(
            "📦 BUYURTMALARIM\n\n"
            "Hozircha buyurtmalaringiz yo'q.",
            reply_markup=main_keyboard()
        )

        return

    text = "📦 BUYURTMALARIM 🛒\n\n"

    for row in rows:

        text += (
            f"🛒 Buyurtma #{row['id']}\n"
            f"📦 Mahsulotlar: {row['products']} ta\n"
            f"📍 Manzil: {row['address']}\n"
            f"📱 Telefon: {row['phone']}\n"
            f"📌 Holat: {row['status']}\n"
            f"🕐 {row['created_at']}\n\n"
        )

    await message.answer(
        text,
        reply_markup=main_keyboard()
    )


# ============================================================
# FAQ
# ============================================================

@dp.message(F.text == "❓ FAQ")
async def faq(message: Message):

    await message.answer(
        "❓ FAQ 📚\n\n"
        "👇 Qiziqtirgan savolingizni tanlang.",
        reply_markup=faq_keyboard()
    )


@dp.message(
    F.text == "🛒 Qanday buyurtma beraman"
)
async def faq_order(message: Message):

    await message.answer(
        "🛒 QANDAY BUYURTMA BERAMAN? 📦\n\n"
        "1️⃣ 🛒 Buyurtma berish tugmasini bosing.\n"
        "2️⃣ 📢 SHAKH SPACE kanaliga o'ting.\n"
        "3️⃣ 📦 Mahsulot xabarini botga forward qiling.\n"
        "4️⃣ 👍 Yana mahsulot kerak bo'lsa Ha.\n"
        "5️⃣ 🚫 Tugatish uchun Shart emas.\n"
        "6️⃣ 📍 Manzilni kiriting.\n"
        "7️⃣ 📱 Telefonni kiriting.\n"
        "8️⃣ 💬 Xabarni yozing.\n"
        "9️⃣ ✅ Buyurtmani yuboring.\n\n"
        "👨‍💼 Admin buyurtmani ko'rib chiqadi."
    )


@dp.message(
    F.text == "💰 Qanday balansga pul o'tkazaman"
)
async def faq_balance_add(message: Message):

    await message.answer(
        "💰 BALANSGA QANDAY PUL O'TKAZAMAN?\n\n"
        "👤 Mening hisobim → 💳 Depozit.\n\n"
        f"💳 Karta: {CARD_NUMBER}\n"
        f"👤 Hisob nomi: {CARD_NAME}\n\n"
        "🧾 To'lov qiling.\n"
        "📸 Chekni yuboring.\n"
        "💰 Miqdorni kiriting.\n"
        "💬 Xabar yozing.\n"
        "✅ Yuboring.\n\n"
        "👨‍💼 Admin tekshiradi va balansingizga qo'shadi."
    )


@dp.message(
    F.text == "💸 Qanday balansdan pul yechaman"
)
async def faq_balance_withdraw(
    message: Message
):

    await message.answer(
        "💸 BALANSDAN QANDAY PUL YECHAMAN?\n\n"
        "👤 Mening hisobim → 💸 Yechib olish.\n\n"
        "💳 Hisob raqamini yozing.\n"
        "👤 Hisob nomini yozing.\n"
        "💰 Miqdorni yozing.\n"
        "📝 Sababni yozing.\n\n"
        "👨‍💼 Admin arizani tekshiradi."
    )


@dp.message(
    F.text == "❌ Buyurtmani bekor qilsa bo'ladimi"
)
async def faq_cancel_order(
    message: Message
):

    await message.answer(
        "❌ BUYURTMANI BEKOR QILISH\n\n"
        "📦 Buyurtma yuborilishidan oldin "
        "❌ Bekor qilish tugmasidan foydalanishingiz mumkin.\n\n"
        "⏳ Yuborilgan buyurtma bo'yicha "
        "💬 Admin bilan bog'laning."
    )


@dp.message(
    F.text == "🚚 Dostavka qayerga ishlaydi"
)
async def faq_delivery(
    message: Message
):

    await message.answer(
        "🚚 DOSTAVKA 📦\n\n"
        "📍 Hozircha Qashqadaryo viloyatiga mavjud.\n\n"
        "❌ Boshqa viloyatlarga hozircha mavjud emas."
    )


@dp.message(
    F.text == "💳 Qanday depozit qilaman"
)
async def faq_deposit(
    message: Message
):

    await message.answer(
        "💳 DEPOZIT QILISH 💰\n\n"
        f"💳 Karta: {CARD_NUMBER}\n"
        f"👤 Hisob nomi: {CARD_NAME}\n\n"
        "🧾 To'lov qiling.\n"
        "📸 Chekni yuboring.\n"
        "💰 Miqdorni kiriting.\n"
        "💬 Xabar yozing.\n"
        "✅ Yuboring.\n\n"
        "👨‍💼 Admin tekshirib chiqqach, balansni "
        "qo'lda qo'shadi."
    )


# ============================================================
# BIZ HAQIMIZDA
# ============================================================

@dp.message(F.text == "🏪 Biz haqimizda")
async def about(message: Message):

    await message.answer(
        "🏪 SHAKH SPACE HAQIDA 🛍️\n\n"
        "👋 SHAKH SPACE — siz uchun turli toifadagi arzon, foydali va zamonaviy mahsulotlarni taklif qiluvchi onlayn do'kon.\n\n"
        "👗 Ayollar uchun kiyimlar va foydali buyumlar\n"
        "👔 Erkaklar uchun foydali mahsulotlar\n"
        "🧸 Bolalar uchun mahsulotlar\n"
        "📱 Telefon g'iloflari va aksessuarlari\n"
        "💻 Kompyuter va texnika aksessuarlari\n"
        "🏠 Uy va kundalik hayot uchun mahsulotlar\n"
        "📦 Va boshqa ko'plab kerakli mahsulotlar\n\n"
        "🇨🇳 Xitoydan mahsulotlarni siz uchun tanlab, buyurtma qilish va yetkazib berish xizmatini taqdim etamiz.\n\n"
        "🚚 Yetkazib berish: Qashqadaryo viloyati bo'ylab.\n\n"
        "📢 Yangi mahsulotlar, aksiyalar va e'lonlar rasmiy Telegram kanalimizda.\n\n"
        "💬 Savollaringiz bo'lsa, admin bilan bog'lanishingiz mumkin.",
        reply_markup=about_keyboard()
    )


# ============================================================
# MIJOZ → ADMIN XABAR
# ============================================================

@dp.message(F.text == "💬 Adminga xabar")
async def customer_message_start(
    message: Message,
    state: FSMContext
):

    await state.clear()

    await state.set_state(
        CustomerState.message
    )

    await message.answer(
        "💬 ADMINGA XABAR 📩\n\n"
        "📝 Muammo, savol yoki taklifingizni yozing.\n\n"
        "👨‍💼 Xabaringiz admin paneliga yuboriladi.\n"
        "⏳ Admin javob berganda shu bot orqali olasiz.",
        reply_markup=back_keyboard()
    )


@dp.message(CustomerState.message)
async def customer_message_send(
    message: Message,
    state: FSMContext
):

    if message.text == "🔙 Orqaga":

        await state.clear()

        await message.answer(
            "🏠 Bosh menyu",
            reply_markup=main_keyboard()
        )

        return

    username = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else "Username yo'q"
    )

    for admin_id in ADMIN_IDS:

        await bot.send_message(
            admin_id,
            "📩 YANGI MIJOZ XABARI\n\n"
            f"🆔 ID: {message.from_user.id}\n"
            f"👤 Username: {username}\n"
            f"👤 Ism: {message.from_user.full_name}\n\n"
            f"💬 XABAR:\n{message.text}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💬 Javob qaytarish",
                            callback_data=(
                                f"reply:"
                                f"{message.from_user.id}"
                            )
                        )
                    ]
                ]
            )
        )

    await state.clear()

    await message.answer(
        "✅ XABARINGIZ YUBORILDI! 📩\n\n"
        "👨‍💼 Admin xabaringizni ko'radi.\n"
        "⏳ Javob shu bot orqali keladi.",
        reply_markup=main_keyboard()
    )


# ============================================================
# ADMIN → MIJOZ JAVOB
# ============================================================

@dp.callback_query(
    F.data.startswith("reply:")
)
async def admin_reply_start(
    callback: CallbackQuery,
    state: FSMContext
):

    if callback.from_user.id not in ADMIN_IDS:

        await callback.answer(
            "❌ Siz admin emassiz.",
            show_alert=True
        )

        return

    _, user_id = callback.data.split(":")

    await state.clear()

    await state.update_data(
        reply_user_id=int(user_id)
    )

    await state.set_state(
        AdminState.reply
    )

    await callback.message.answer(
        "💬 MIJOZGA JAVOB 👤\n\n"
        f"🆔 Mijoz ID: {user_id}\n\n"
        "✍️ Endi mijozga yubormoqchi "
        "bo'lgan javobingizni yozing.",
        reply_markup=back_keyboard()
    )

    await callback.answer()


@dp.message(AdminState.reply)
async def admin_reply_send(
    message: Message,
    state: FSMContext
):

    if message.from_user.id not in ADMIN_IDS:
        return

    if message.text == "🔙 Orqaga":

        await state.clear()

        await message.answer(
            "👨‍💼 ADMIN PANEL",
            reply_markup=admin_keyboard()
        )

        return

    data = await state.get_data()

    user_id = data.get(
        "reply_user_id"
    )

    if not user_id:

        await state.clear()

        await message.answer(
            "❌ Mijoz topilmadi.",
            reply_markup=admin_keyboard()
        )

        return

    try:

        await bot.send_message(
            user_id,
            "👨‍💼 ADMIN JAVOBI 📩\n\n"
            f"💬 {message.text}\n\n"
            "🏪 SHAKH SPACE"
        )

        await message.answer(
            "✅ JAVOB MIJOZGA YUBORILDI! 📩\n\n"
            f"🆔 Mijoz ID: {user_id}",
            reply_markup=admin_keyboard()
        )

    except Exception:

        await message.answer(
            "❌ Mijozga xabar yuborib bo'lmadi.\n\n"
            "⚠️ Mijoz botni bloklagan bo'lishi "
            "yoki bot bilan chat boshlamagan bo'lishi mumkin.",
            reply_markup=admin_keyboard()
        )

    await state.clear()


# ============================================================
# ADMIN BALANS
# ============================================================

@dp.message(F.text == "💰 Balansni boshqarish")
async def admin_balance(
    message: Message
):

    if message.from_user.id not in ADMIN_IDS:
        return

    await message.answer(
        "💰 BALANSNI BOSHQARISH\n\n"
        "➕ Balansga qo'shish:\n"
        "/addbalance ID MIQDOR\n\n"
        "➖ Balansdan ayirish:\n"
        "/removebalance ID MIQDOR\n\n"
        "📌 Misol:\n"
        "/addbalance 123456789 50000\n\n"
        "/removebalance 123456789 20000\n\n"
        "👤 ID ni '👥 Mijozlar' bo'limidan olishingiz mumkin."
    )


# ============================================================
# ADD BALANCE
# ============================================================

@dp.message(
    F.text.startswith("/addbalance")
)
async def admin_add_balance(
    message: Message
):

    if message.from_user.id not in ADMIN_IDS:
        return

    parts = message.text.split()

    if len(parts) != 3:

        await message.answer(
            "❌ Format noto'g'ri.\n\n"
            "Masalan:\n"
            "/addbalance 123456789 50000"
        )

        return

    try:

        user_id = int(parts[1])
        amount = int(parts[2])

    except ValueError:

        await message.answer(
            "❌ ID yoki miqdor noto'g'ri."
        )

        return

    if amount <= 0:

        await message.answer(
            "❌ Miqdor 0 dan katta bo'lishi kerak."
        )

        return

    cur = DB.cursor()

    cur.execute(
        "SELECT id FROM users WHERE id = ?",
        (user_id,)
    )

    if not cur.fetchone():

        await message.answer(
            "❌ Bu ID bilan mijoz topilmadi.\n\n"
            "👥 Avval mijoz botga /start bosgan bo'lishi kerak."
        )

        return

    change_balance(
        user_id,
        amount
    )

    add_transaction(
        user_id,
        "deposit",
        amount,
        "admin_added"
    )

    new_balance = get_balance(
        user_id
    )

    await message.answer(
        "✅ BALANS TO'LDIRILDI 💰\n\n"
        f"🆔 ID: {user_id}\n"
        f"➕ Qo'shildi: {amount:,} so'm\n"
        f"💳 Yangi balans: {new_balance:,} so'm"
    )

    try:

        await bot.send_message(
            user_id,
            "💰 BALANSINGIZ TO'LDIRILDI!\n\n"
            f"➕ Qo'shildi: {amount:,} so'm\n"
            f"💳 Yangi balans: {new_balance:,} so'm"
        )

    except Exception:
        pass


# ============================================================
# REMOVE BALANCE
# ============================================================

@dp.message(
    F.text.startswith("/removebalance")
)
async def admin_remove_balance(
    message: Message
):

    if message.from_user.id not in ADMIN_IDS:
        return

    parts = message.text.split()

    if len(parts) != 3:

        await message.answer(
            "❌ Format noto'g'ri.\n\n"
            "Masalan:\n"
            "/removebalance 123456789 50000"
        )

        return

    try:

        user_id = int(parts[1])
        amount = int(parts[2])

    except ValueError:

        await message.answer(
            "❌ ID yoki miqdor noto'g'ri."
        )

        return

    if amount <= 0:

        await message.answer(
            "❌ Miqdor noto'g'ri."
        )

        return

    balance = get_balance(
        user_id
    )

    if balance < amount:

        await message.answer(
            "❌ Balansda yetarli pul yo'q.\n\n"
            f"💳 Hozirgi balans: {balance:,} so'm"
        )

        return

    change_balance(
        user_id,
        -amount
    )

    add_transaction(
        user_id,
        "withdraw",
        amount,
        "admin_removed"
    )

    new_balance = get_balance(
        user_id
    )

    await message.answer(
        "✅ BALANSDAN AYIRILDI 💸\n\n"
        f"🆔 ID: {user_id}\n"
        f"➖ Ayirildi: {amount:,} so'm\n"
        f"💳 Yangi balans: {new_balance:,} so'm"
    )

    try:

        await bot.send_message(
            user_id,
            "💸 BALANSINGIZDAN PUL AYIRILDI\n\n"
            f"➖ Summa: {amount:,} so'm\n"
            f"💳 Qolgan balans: {new_balance:,} so'm"
        )

    except Exception:
        pass


# ============================================================
# ADMIN DEPOZITLAR
# ============================================================

@dp.message(F.text == "📥 Depozitlar")
async def admin_deposits(
    message: Message
):

    if message.from_user.id not in ADMIN_IDS:
        return

    cur = DB.cursor()

    cur.execute(
        """
        SELECT user_id,
               amount,
               status,
               created_at
        FROM transactions
        WHERE type = 'deposit'
        ORDER BY id DESC
        LIMIT 30
        """
    )

    rows = cur.fetchall()

    if not rows:

        await message.answer(
            "📥 DEPOZITLAR\n\n"
            "Hozircha depozitlar yo'q."
        )

        return

    text = "📥 DEPOZITLAR 💳\n\n"

    for row in rows:

        text += (
            f"🆔 ID: {row['user_id']}\n"
            f"💰 Summa: {row['amount']:,} so'm\n"
            f"📌 Holat: {row['status']}\n"
            f"🕐 {row['created_at']}\n\n"
        )

    await message.answer(
        text,
        reply_markup=admin_keyboard()
    )


# ============================================================
# ADMIN WITHDRAWS
# ============================================================

@dp.message(F.text == "📤 Yechib olishlar")
async def admin_withdraws(
    message: Message
):

    if message.from_user.id not in ADMIN_IDS:
        return

    cur = DB.cursor()

    cur.execute(
        """
        SELECT user_id,
               amount,
               status,
               created_at
        FROM transactions
        WHERE type = 'withdraw'
        ORDER BY id DESC
        LIMIT 30
        """
    )

    rows = cur.fetchall()

    if not rows:

        await message.answer(
            "📤 YECHIB OLISHLAR\n\n"
            "Hozircha ma'lumot yo'q."
        )

        return

    text = "📤 YECHIB OLISHLAR 💸\n\n"

    for row in rows:

        text += (
            f"🆔 ID: {row['user_id']}\n"
            f"💰 Summa: {row['amount']:,} so'm\n"
            f"📌 Holat: {row['status']}\n"
            f"🕐 {row['created_at']}\n\n"
        )

    await message.answer(
        text,
        reply_markup=admin_keyboard()
    )


# ============================================================
# ADMIN ORDERS
# ============================================================

@dp.message(F.text == "🛒 Buyurtmalar")
async def admin_orders(
    message: Message
):

    if message.from_user.id not in ADMIN_IDS:
        return

    cur = DB.cursor()

    cur.execute(
        """
        SELECT id,
               user_id,
               products,
               amount,
               address,
               phone,
               message,
               status,
               created_at
        FROM orders
        ORDER BY id DESC
        LIMIT 30
        """
    )

    rows = cur.fetchall()

    if not rows:

        await message.answer(
            "🛒 BUYURTMALAR\n\n"
            "Hozircha buyurtmalar yo'q."
        )

        return

    for row in rows:

        await message.answer(
            "🛒 BUYURTMA 📦\n\n"
            f"🆔 Buyurtma: #{row['id']}\n"
            f"👤 Mijoz ID: {row['user_id']}\n"
            f"📦 Mahsulotlar: {row['products']} ta\n"
            f"💰 Jami: {row['amount']:,} so'm\n"
            f"🏠 Manzil: {row['address']}\n"
            f"📱 Telefon: {row['phone']}\n"
            f"💬 Xabar: {row['message']}\n"
            f"📌 Holat: {row['status']}\n"
            f"🕐 {row['created_at']}",
            reply_markup=admin_keyboard()
        )


# ============================================================
# ADMIN USERS
# ============================================================

@dp.message(F.text == "👥 Mijozlar")
async def admin_users(
    message: Message
):

    if message.from_user.id not in ADMIN_IDS:
        return

    cur = DB.cursor()

    cur.execute(
        """
        SELECT id,
               username,
               full_name,
               balance
        FROM users
        ORDER BY id DESC
        LIMIT 50
        """
    )

    rows = cur.fetchall()

    if not rows:

        await message.answer(
            "👥 MIJOZLAR\n\n"
            "Hozircha mijozlar yo'q."
        )

        return

    text = "👥 MIJOZLAR 👤\n\n"

    for row in rows:

        text += (
            f"🆔 ID: {row['id']}\n"
            f"👤 Ism: {row['full_name'] or 'yo‘q'}\n"
            f"📱 Username: "
            f"@{row['username'] or 'yo‘q'}\n"
            f"💰 Balans: {row['balance']:,} so'm\n\n"
        )

    await message.answer(
        text,
        reply_markup=admin_keyboard()
    )


# ============================================================
# ADMIN ORQAGA
# ============================================================

@dp.message(F.text == "🔙 Orqaga")
async def global_back(
    message: Message,
    state: FSMContext
):

    await state.clear()

    # Admin uchun ham, faqat hozir ADMIN PANEL rejimida bo'lsagina
    # admin menyusi ko'rsatiladi. Aks holda (mijoz rejimida bo'lsa)
    # oddiy mijoz menyusiga qaytariladi.
    if message.from_user.id in ADMIN_IDS and admin_mode.get(message.from_user.id, False):

        await message.answer(
            "👨‍💼 ADMIN PANEL ⚙️\n\n"
            "👇 Kerakli bo'limni tanlang.",
            reply_markup=admin_keyboard()
        )

    else:

        await message.answer(
            "🏠 BOSH MENYU 🏪\n\n"
            "👇 Kerakli bo'limni tanlang.",
            reply_markup=main_keyboard()
        )


# ============================================================
# UNKNOWN ADMIN TEXT
# ============================================================

@dp.message()
async def unknown_message(
    message: Message
):

    if message.from_user.id in ADMIN_IDS and admin_mode.get(message.from_user.id, False):

        await message.answer(
            "👨‍💼 ADMIN PANEL ⚙️\n\n"
            "👇 Tugmalardan birini tanlang.",
            reply_markup=admin_keyboard()
        )

    else:

        await message.answer(
            "🏠 SHAKH SPACE 🏪\n\n"
            "👇 Tugmalardan birini tanlang.",
            reply_markup=main_keyboard()
        )


# ============================================================
# ISHGA TUSHIRISH
# ============================================================

async def main():

    db_init()

    print(
        "===================================="
    )
    print(
        " SHAKH SPACE BOT ISHLAYAPTI..."
    )
    print(
        "===================================="
    )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())