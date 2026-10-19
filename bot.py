"""Telegram bot for home brewery — stock, orders, and admin management.

All member interactions happen via inline buttons (no typing required).
The group should have "Send Messages" disabled for regular members.
Admin commands work in private chat with the bot.
Language: Ukrainian
"""

import os
import uuid
from datetime import datetime

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatJoinRequest
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    ChatMemberHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
CREDS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

if SHEET_ID and SHEET_ID != "your_spreadsheet_id_here" and os.path.exists(CREDS_FILE):
    from sheets import SheetsDB
    db = SheetsDB(CREDS_FILE, SHEET_ID)
    print("📊 Using Google Sheets for storage")
else:
    from local_db import LocalDB
    db = LocalDB()
    print("📁 Using local JSON file for storage (Google Sheets not configured)")

ADD_NAME, ADD_STYLE, ADD_ABV, ADD_IBU, ADD_BOTTLES, ADD_PRICE = range(6)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# --- Main menu (posted in group, members interact via buttons) ---

def build_main_menu():
    buttons = [
        [InlineKeyboardButton("🍺 Наявне пиво", callback_data="menu_stock")],
        [InlineKeyboardButton("🛒 Зробити замовлення", callback_data="menu_order")],
        [InlineKeyboardButton("📋 Мої замовлення", callback_data="menu_myorders")],
    ]
    return InlineKeyboardMarkup(buttons)


async def post_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🍺 *Lake62 Brewing*\n\nОберіть дію:",
        reply_markup=build_main_menu(),
        parse_mode="Markdown",
    )
    try:
        await msg.pin(disable_notification=True)
    except Exception:
        pass


# --- Button handlers ---

async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id
    user_id = query.from_user.id

    # Track personal messages per user so we edit THEIR message, not the pinned menu
    msg_key = f"msg_{user_id}"

    if data == "menu_stock":
        await send_or_edit_personal(query, context, msg_key, *build_stock_content())
    elif data == "menu_order":
        await send_or_edit_personal(query, context, msg_key, *build_order_content(query, context))
    elif data == "menu_myorders":
        await send_or_edit_personal(query, context, msg_key, *build_myorders_content(query))
    elif data == "back_to_menu":
        context.bot_data.pop(f"cart_{user_id}", None)
        context.bot_data.pop(f"stock_{user_id}", None)
        context.bot_data.pop(f"selected_{user_id}", None)
        await safe_edit(query, "🍺 *Lake62 Brewing*\n\nОберіть дію:", build_main_menu())
    elif data.startswith("pick_"):
        await handle_pick_item(query, context)
    elif data.startswith("qty_"):
        await handle_pick_qty(query, context)
    elif data == "add_more":
        text, markup = build_order_content(query, context)
        await safe_edit(query, text, markup)
    elif data == "confirm_yes":
        await handle_confirm_order(query, context)
    elif data == "cancel_order":
        context.bot_data.pop(f"cart_{user_id}", None)
        context.bot_data.pop(f"stock_{user_id}", None)
        context.bot_data.pop(f"selected_{user_id}", None)
        await safe_edit(query, "❌ Замовлення скасовано.\n\n🍺 *Lake62 Brewing*\n\nОберіть дію:", build_main_menu())


async def safe_edit(query, text, reply_markup=None):
    """Edit the message that the button belongs to. If it's the pinned menu, send a new one instead."""
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception:
        await query.message.chat.send_message(text, reply_markup=reply_markup, parse_mode="Markdown",
                                              disable_notification=True)


async def send_or_edit_personal(query, context, msg_key, text, reply_markup):
    """For first interaction from pinned menu: send new message. After that: edit user's personal message."""
    chat_id = query.message.chat.id
    user_id = query.from_user.id

    # Check if the button was pressed on the pinned menu (not on a personal message)
    stored_msg_id = context.bot_data.get(msg_key)
    is_pinned = (stored_msg_id is None or query.message.message_id != stored_msg_id)

    if is_pinned:
        # Send a NEW message, don't edit the pinned menu
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="Markdown",
            disable_notification=True,
        )
        context.bot_data[msg_key] = sent.message_id
    else:
        # Edit the user's own personal message
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        except Exception:
            sent = await context.bot.send_message(
                chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode="Markdown",
                disable_notification=True,
            )
            context.bot_data[msg_key] = sent.message_id


def build_stock_content():
    items = db.get_stock()
    if not items:
        text = "Наразі нічого немає в наявності. Перевірте пізніше!"
    else:
        lines = ["🍺 *Наявне пиво:*\n"]
        for i, item in enumerate(items, 1):
            lines.append(
                f"{i}. *{item['Name']}* — {item['Style']}\n"
                f"   ABV: {item.get('ABV', '?')}% | IBU: {item.get('IBU', '?')}\n"
                f"   Залишок: {item.get('Bottles', '?')} пл. (0.33л)\n"
                f"   Ціна: {item['Price']} грн/пл."
            )
        text = "\n".join(lines)
    buttons = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]]
    return text, InlineKeyboardMarkup(buttons)


def build_order_content(query, context):
    items = db.get_stock()
    if not items:
        buttons = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]]
        return "Наразі нічого немає в наявності. Перевірте пізніше!", InlineKeyboardMarkup(buttons)

    user_id = query.from_user.id
    context.bot_data[f"stock_{user_id}"] = items

    lines = ["🛒 *Оберіть пиво:*\n"]
    buttons = []
    for i, item in enumerate(items):
        lines.append(
            f"*{i+1}. {item['Name']}* — {item['Style']}\n"
            f"    ABV: {item.get('ABV', '?')}% | IBU: {item.get('IBU', '?')} | {item['Price']} грн/пл."
        )
        buttons.append([InlineKeyboardButton(f"{i+1}. {item['Name']}", callback_data=f"pick_{i}")])
    buttons.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel_order")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def build_myorders_content(query):
    username = query.from_user.username or str(query.from_user.id)
    orders = db.get_orders_by_user(username)

    if not orders:
        text = "У вас ще немає замовлень. Натисніть 🛒 щоб зробити перше!"
    else:
        lines = ["📋 *Ваші замовлення:*\n"]
        for o in orders[-10:]:
            lines.append(f"• {o['Item']} x{o['Qty']} пл. — _{o['Status']}_ ({o['Date']})")
        text = "\n".join(lines)
    buttons = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]]
    return text, InlineKeyboardMarkup(buttons)



async def handle_pick_item(query, context):
    user_id = query.from_user.id
    idx = int(query.data.replace("pick_", ""))
    items = context.bot_data.get(f"stock_{user_id}", [])

    if idx >= len(items):
        await query.edit_message_text(
            "Помилка: товар не знайдено. Спробуйте ще раз.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]]),
        )
        return

    context.bot_data[f"selected_{user_id}"] = items[idx]

    buttons = [
        [InlineKeyboardButton(str(n), callback_data=f"qty_{n}") for n in range(1, 7)],
        [InlineKeyboardButton(str(n), callback_data=f"qty_{n}") for n in range(7, 13)],
        [InlineKeyboardButton("❌ Скасувати", callback_data="cancel_order")],
    ]

    await query.edit_message_text(
        f"Обрано: *{items[idx]['Name']}*\n"
        f"Ціна: {items[idx]['Price']} грн/пл. (0.33л)\n\n"
        f"Скільки пляшок?",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


async def handle_pick_qty(query, context):
    user_id = query.from_user.id
    qty = int(query.data.replace("qty_", ""))
    item = context.bot_data.get(f"selected_{user_id}")

    if not item:
        await query.edit_message_text(
            "Помилка: сесія закінчилась. Почніть спочатку.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]]),
        )
        return

    # Add to cart
    cart = context.bot_data.get(f"cart_{user_id}", [])
    cart.append({"name": item["Name"], "style": item["Style"], "price": item["Price"], "qty": qty})
    context.bot_data[f"cart_{user_id}"] = cart

    # Show cart summary
    await show_cart(query, context, user_id)


async def show_cart(query, context, user_id):
    cart = context.bot_data.get(f"cart_{user_id}", [])

    lines = ["🛒 *Ваш кошик:*\n"]
    grand_total = 0
    for i, entry in enumerate(cart, 1):
        try:
            item_total = float(entry["price"]) * entry["qty"]
            grand_total += item_total
            lines.append(f"{i}. {entry['name']} — {entry['qty']} пл. × {entry['price']} грн = {item_total:.0f} грн")
        except (ValueError, TypeError):
            lines.append(f"{i}. {entry['name']} — {entry['qty']} пл. × {entry['price']} грн")

    if grand_total > 0:
        lines.append(f"\n*Разом: {grand_total:.0f} грн*")

    buttons = [
        [InlineKeyboardButton("➕ Додати ще", callback_data="add_more")],
        [InlineKeyboardButton("✅ Підтвердити замовлення", callback_data="confirm_yes")],
        [InlineKeyboardButton("❌ Скасувати", callback_data="cancel_order")],
    ]

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown",
    )


async def handle_confirm_order(query, context):
    user_id = query.from_user.id
    cart = context.bot_data.get(f"cart_{user_id}", [])

    if not cart:
        await query.edit_message_text(
            "Помилка: кошик порожній. Почніть спочатку.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]]),
        )
        return

    user = query.from_user
    username = user.username or str(user.id)
    fullname = user.full_name

    order_id = str(uuid.uuid4())[:8].upper()
    date = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Save each cart item as a separate order line
    order_lines = []
    grand_total = 0
    for entry in cart:
        db.place_order(order_id, date, fullname, username, entry["name"], entry["qty"])
        try:
            item_total = float(entry["price"]) * entry["qty"]
            grand_total += item_total
            order_lines.append(f"• {entry['name']} — {entry['qty']} пл. ({item_total:.0f} грн)")
        except (ValueError, TypeError):
            order_lines.append(f"• {entry['name']} — {entry['qty']} пл.")

    # Clean up
    context.bot_data.pop(f"cart_{user_id}", None)
    context.bot_data.pop(f"stock_{user_id}", None)
    context.bot_data.pop(f"selected_{user_id}", None)

    total_text = f"\nРазом: {grand_total:.0f} грн" if grand_total > 0 else ""
    items_text = "\n".join(order_lines)

    await query.edit_message_text(
        f"✅ *Замовлення прийнято!*\n\n"
        f"Номер: `{order_id}`\n\n"
        f"{items_text}\n"
        f"{total_text}\n\n"
        f"Пивовар зв'яжеться з вами щодо отримання.\n\n"
        f"🍺 *Lake62 Brewing*",
        reply_markup=build_main_menu(),
        parse_mode="Markdown",
    )

    # Notify admins
    admin_lines = "\n".join(order_lines)
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"🆕 *Нове замовлення!*\n"
                f"Від: {fullname} (@{username})\n"
                f"Номер: `{order_id}`\n\n"
                f"{admin_lines}\n{total_text}",
                parse_mode="Markdown",
            )
        except Exception:
            pass


async def show_my_orders(query, context):
    username = query.from_user.username or str(query.from_user.id)
    orders = db.get_orders_by_user(username)

    if not orders:
        text = "У вас ще немає замовлень. Натисніть 🛒 щоб зробити перше!"
    else:
        lines = ["📋 *Ваші замовлення:*\n"]
        for o in orders[-10:]:
            lines.append(f"• {o['Item']} x{o['Qty']} пл. — _{o['Status']}_ ({o['Date']})")
        text = "\n".join(lines)

    buttons = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


# --- Join request approval ---

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    join_request: ChatJoinRequest = update.chat_join_request
    user = join_request.from_user

    buttons = [
        [
            InlineKeyboardButton("✅ Прийняти", callback_data=f"approve_{user.id}_{join_request.chat.id}"),
            InlineKeyboardButton("❌ Відхилити", callback_data=f"decline_{user.id}_{join_request.chat.id}"),
        ]
    ]

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"🚪 *Запит на вступ*\n"
                f"Користувач: {user.full_name} (@{user.username or 'без username'})\n"
                f"ID: `{user.id}`",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode="Markdown",
            )
        except Exception:
            pass


async def handle_join_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    data = query.data
    parts = data.split("_")
    action = parts[0]
    user_id = int(parts[1])
    chat_id = int(parts[2])

    try:
        if action == "approve":
            await context.bot.approve_chat_join_request(chat_id, user_id)
            await query.edit_message_text(f"✅ Користувач {user_id} прийнятий.")
        else:
            await context.bot.decline_chat_join_request(chat_id, user_id)
            await query.edit_message_text(f"❌ Користувач {user_id} відхилений.")
    except Exception as e:
        await query.edit_message_text(f"Помилка: {e}")


async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send brief welcome in group when a new member joins."""
    if update.chat_member is None:
        return

    new_status = update.chat_member.new_chat_member.status
    old_status = update.chat_member.old_chat_member.status

    if new_status == "member" and old_status in ("left", "kicked"):
        user = update.chat_member.new_chat_member.user
        chat_id = update.chat_member.chat.id

        msg = await context.bot.send_message(
            chat_id,
            f"🍺 Вітаємо, *{user.full_name}*! Натисніть на закріплене повідомлення вище ☝️",
            parse_mode="Markdown",
            disable_notification=True,
        )
        # Auto-delete welcome after 30 seconds to keep group clean
        import asyncio
        await asyncio.sleep(30)
        try:
            await msg.delete()
        except Exception:
            pass


# --- Admin commands (work in private chat with bot) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private" and is_admin(update.effective_user.id):
        await update.message.reply_text(
            "🍺 *Панель адміністратора*\n\n"
            "Команди:\n"
            "/menu — Опублікувати меню в групі\n"
            "/addstock — Додати нове пиво\n"
            "/editqty <кількість> <назва> — Змінити залишок\n"
            "/remove <назва> — Видалити пиво\n"
            "/allstock — Переглянути всі позиції\n"
            "/orders — Переглянути замовлення\n"
            "/backup — Завантажити бекап бази даних\n",
            parse_mode="Markdown",
        )
    elif update.effective_chat.type == "private":
        await update.message.reply_text(
            "🍺 Вітаю! Цей бот працює в групі пивоварні.\n"
            "Зверніться до адміна за посиланням для вступу."
        )


async def admin_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    context.user_data.clear()
    await update.message.reply_text(
        "Додавання нового пива. Надішліть /cancel щоб скасувати.\n\n"
        "Введіть назву пива:"
    )
    return ADD_NAME


async def admin_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_name"] = update.message.text
    await update.message.reply_text("Введіть стиль (напр. IPA, Stout, Lager, Wheat):")
    return ADD_STYLE


async def admin_add_style(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_style"] = update.message.text
    await update.message.reply_text("Введіть ABV (% алкоголю, напр. 5.2):")
    return ADD_ABV


async def admin_add_abv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_abv"] = update.message.text
    await update.message.reply_text("Введіть IBU (гіркота, напр. 35):")
    return ADD_IBU


async def admin_add_ibu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_ibu"] = update.message.text
    await update.message.reply_text("Скільки пляшок (0.33л) в наявності?")
    return ADD_BOTTLES


async def admin_add_bottles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_bottles"] = update.message.text
    await update.message.reply_text("Введіть ціну за пляшку (грн):")
    return ADD_PRICE


async def admin_add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = context.user_data["new_name"]
    style = context.user_data["new_style"]
    abv = context.user_data["new_abv"]
    ibu = context.user_data["new_ibu"]
    bottles = context.user_data["new_bottles"]
    price = update.message.text

    db.add_stock_item(name, style, abv, ibu, bottles, price)
    await update.message.reply_text(
        f"✅ Додано:\n"
        f"*{name}* ({style})\n"
        f"ABV: {abv}% | IBU: {ibu}\n"
        f"Кількість: {bottles} пл. | Ціна: {price} грн/пл.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def admin_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    args = context.args
    if not args:
        await update.message.reply_text("Використання: /remove <назва пива>")
        return

    name = " ".join(args)
    if db.remove_stock_item(name):
        await update.message.reply_text(f"✅ *{name}* видалено з наявності.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ '{name}' не знайдено.")


async def admin_editqty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            "Використання: /editqty <кількість> <назва пива>\n"
            "Приклад: /editqty 24 Summer Haze"
        )
        return

    new_qty = args[0]
    name = " ".join(args[1:])

    if db.update_stock_qty(name, new_qty):
        await update.message.reply_text(f"✅ *{name}* — залишок оновлено: {new_qty} пл.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ '{name}' не знайдено.")


async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    orders = db.get_all_orders()
    if not orders:
        await update.message.reply_text("Замовлень поки немає.")
        return

    # Show last 20 orders, newest first
    recent = orders[-20:][::-1]
    lines = ["📦 *Останні замовлення:*\n"]
    for o in recent:
        username = o.get('Username', '?')
        user_display = f"@{username}" if not username.isdigit() else f"ID:{username}"
        lines.append(
            f"• `{o.get('Order ID', '?')}` — {o.get('Item', '?')} x{o.get('Qty', '?')} пл.\n"
            f"  Від: {o.get('User', '?')} ({user_display})\n"
            f"  {o.get('Date', '?')} — _{o.get('Status', '?')}_"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def admin_allstock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    items = db.get_all_stock()
    if not items:
        await update.message.reply_text("Склад порожній.")
        return

    lines = ["📦 *Весь склад:*\n"]
    for item in items:
        status = "✅" if str(item.get("Available", "")).lower() in ("yes", "1", "true", "+") else "❌"
        lines.append(
            f"{status} *{item['Name']}* ({item['Style']})\n"
            f"   ABV: {item.get('ABV', '?')}% | IBU: {item.get('IBU', '?')}\n"
            f"   Пляшок: {item.get('Bottles', '?')} | Ціна: {item['Price']} грн"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Скасовано.")
    return ConversationHandler.END


async def admin_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    filepath = db.get_data_file_path()
    if not os.path.exists(filepath):
        await update.message.reply_text("❌ Файл бази даних не знайдено.")
        return

    date = datetime.now().strftime("%Y%m%d_%H%M")
    await update.message.reply_document(
        document=open(filepath, "rb"),
        filename=f"brewery_backup_{date}.json",
        caption=f"📦 Бекап бази даних — {date}",
    )


def main():
    app = Application.builder().token(TOKEN).build()

    add_conv = ConversationHandler(
        entry_points=[CommandHandler("addstock", admin_add_start)],
        states={
            ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_name)],
            ADD_STYLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_style)],
            ADD_ABV: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_abv)],
            ADD_IBU: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_ibu)],
            ADD_BOTTLES: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_bottles)],
            ADD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_price)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("addstock", admin_add_start),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", post_menu))
    app.add_handler(add_conv)
    app.add_handler(CommandHandler("remove", admin_remove))
    app.add_handler(CommandHandler("editqty", admin_editqty))
    app.add_handler(CommandHandler("orders", admin_orders))
    app.add_handler(CommandHandler("backup", admin_backup))
    app.add_handler(CommandHandler("allstock", admin_allstock))
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    app.add_handler(ChatMemberHandler(handle_new_member, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CallbackQueryHandler(handle_join_decision, pattern=r"^(approve|decline)_"))
    app.add_handler(CallbackQueryHandler(handle_menu_buttons))

    print("🍺 Brewery bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
