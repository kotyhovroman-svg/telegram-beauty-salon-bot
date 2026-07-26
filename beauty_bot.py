import os
import telebot
from telebot import types
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()

TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')
SPREADSHEET_NAME = os.getenv('SPREADSHEET_NAME')

bot = telebot.TeleBot(TOKEN)
booking_data = {}


# --- НАСТРОЙКА GOOGLE SHEETS ---
def append_to_sheet(row_data):
    """Авторизация через OAuth Client ID (Desktop App)"""
    try:
        # Бот будет искать файл client_secret.json и создаст рядом authorized_user.json
        client = gspread.oauth(
            credentials_filename='client_secret.json',
            authorized_user_filename='authorized_user.json'
        )
        sheet = client.open(SPREADSHEET_NAME).sheet1
        sheet.append_row(row_data)
    except Exception as e:
        print(f"Ошибка при записи в Google Таблицу: {e}")


# --- ХЕНДЛЕРЫ БОТА ---
@bot.message_handler(commands=['start'])
def start_message(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("💅 Записаться на маникюр"))
    bot.send_message(
        message.chat.id,
        "Добро пожаловать в студию **Nail Studio**! ✨\nНажмите кнопку ниже для записи:",
        reply_markup=markup,
        parse_mode="Markdown"
    )


@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.text == "💅 Записаться на маникюр":
        chat_id = message.chat.id
        booking_data[chat_id] = {}

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Маникюр с покрытием (2 200 ₽)", callback_data="service_manicure"))
        markup.add(types.InlineKeyboardButton("Педикюр (3 000 ₽)", callback_data="service_pedicure"))

        bot.send_message(chat_id, "Выберите услугу:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = call.message.chat.id
    if chat_id not in booking_data:
        booking_data[chat_id] = {}

    if call.data.startswith("service_"):
        services = {
            "service_manicure": "Маникюр с покрытием",
            "service_pedicure": "Педикюр"
        }
        booking_data[chat_id]['service'] = services[call.data]

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Завтра 12:00", callback_data="time_1200"))
        markup.add(types.InlineKeyboardButton("Завтра 15:00", callback_data="time_1500"))

        bot.edit_message_text("Выберите удобное время:", chat_id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("time_"):
        times = {"time_1200": "Завтра в 12:00", "time_1500": "Завтра в 15:00"}
        booking_data[chat_id]['time'] = times[call.data]

        bot.delete_message(chat_id, call.message.message_id)
        msg = bot.send_message(chat_id, "Напишите ваше **Имя**:")
        bot.register_next_step_handler(msg, process_name_step)


def process_name_step(message):
    chat_id = message.chat.id
    booking_data[chat_id]['name'] = message.text

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton(text="📱 Отправить номер телефона", request_contact=True))

    msg = bot.send_message(chat_id, f"Приятно познакомиться, {message.text}! Отправьте номер телефона:",
                           reply_markup=markup)
    bot.register_next_step_handler(msg, process_phone_step)


def process_phone_step(message):
    chat_id = message.chat.id
    phone = message.contact.phone_number if message.contact else message.text
    booking_data[chat_id]['phone'] = phone

    data = booking_data[chat_id]

    # 1. Отправляем данные в Google Таблицу
    row = [data['time'], data['name'], phone, data['service'], "Любой мастер"]
    append_to_sheet(row)

    # 2. Подтверждение клиенту
    bot.send_message(
        chat_id,
        f"🎉 **Вы успешно записаны!**\n\n"
        f"• Услуга: {data['service']}\n"
        f"• Время: {data['time']}\n"
        f"• Имя: {data['name']}\n"
        f"• Телефон: {phone}",
        parse_mode="Markdown",
        reply_markup=types.ReplyKeyboardRemove()
    )

    # 3. Уведомление администратору
    if ADMIN_CHAT_ID:
        admin_text = f"🔔 **Новая запись!**\nИмя: {data['name']}\nТел: {phone}\nУслуга: {data['service']}\nВремя: {data['time']}"
        bot.send_message(ADMIN_CHAT_ID, admin_text, parse_mode="Markdown")


if __name__ == '__main__':
    bot.infinity_polling()