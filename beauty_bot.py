import os
import telebot
from telebot import types
import gspread
import datetime
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')
SPREADSHEET_NAME = os.getenv('SPREADSHEET_NAME')

bot = telebot.TeleBot(BOT_TOKEN)

# Словарь для временного хранения данных клиентов в процессе записи
booking_data = {}


# --- ФУНКЦИИ РАБОТЫ С GOOGLE ТАБЛИЦАМИ ---

def get_gspread_client():
    """Помощник для авторизации, чтобы не писать этот код в каждой функции"""
    return gspread.oauth(
        credentials_filename='client_secret.json',
        authorized_user_filename='authorized_user.json'
    )


def update_schedule_with_dates(days_ahead=7):
    """Генерация расписания: дописывает отсутствующие дни на X дней вперед"""
    try:
        client = get_gspread_client()
        sheet = client.open(SPREADSHEET_NAME).worksheet("Расписание")
        records = sheet.get_all_records()

        # Собираем даты, которые уже есть в таблице
        existing_dates = set([str(row['Дата']) for row in records if 'Дата' in row])

        working_hours = ["09:00–11:00", "11:00–13:00", "13:00–15:00", "15:00–17:00", "17:00–19:00"]
        services = ["Маникюр", "Педикюр"]
        today = datetime.date.today()
        rows_to_add = []

        for i in range(days_ahead):
            target_date = today + datetime.timedelta(days=i)
            date_str = target_date.strftime("%d.%m.%Y")

            # Если даты нет в таблице — добавляем слоты
            if date_str not in existing_dates:
                for hour in working_hours:
                    for service in services:
                        rows_to_add.append([date_str, hour, service, "Свободно", "", ""])

        if rows_to_add:
            sheet.append_rows(rows_to_add)
            print(f"✅ Расписание обновлено: добавлено {len(rows_to_add)} слотов (на новые даты).")
        else:
            print("📋 Расписание актуально. Новых дат для добавления нет.")

    except Exception as e:
        print(f"❌ Ошибка при автогенерации расписания: {e}")


def get_available_days(selected_service):
    """Ищет доступные даты для выбранной услуги"""
    try:
        client = get_gspread_client()
        sheet = client.open(SPREADSHEET_NAME).worksheet("Расписание")
        records = sheet.get_all_records()

        available_days = []
        for row in records:
            if row.get('Услуга') == selected_service and row.get('Статус') == 'Свободно':
                day = str(row['Дата'])
                if day not in available_days:
                    available_days.append(day)
        return available_days
    except Exception as e:
        print(f"❌ Ошибка при получении дней: {e}")
        return []


def get_available_hours(selected_service, selected_day):
    """Ищет свободное время на конкретный день для услуги"""
    try:
        client = get_gspread_client()
        sheet = client.open(SPREADSHEET_NAME).worksheet("Расписание")
        records = sheet.get_all_records()

        available_hours = []
        for row in records:
            if row.get('Услуга') == selected_service and str(row.get('Дата')) == selected_day and row.get(
                    'Статус') == 'Свободно':
                available_hours.append(str(row['Время']))
        return available_hours
    except Exception as e:
        print(f"❌ Ошибка при получении часов: {e}")
        return []


def book_schedule_slot(date, time, service, user):
    """Меняет статус конкретного окна на 'Занято' и записывает данные клиента"""
    try:
        client = get_gspread_client()
        sheet = client.open(SPREADSHEET_NAME).worksheet("Расписание")
        records = sheet.get_all_records()

        user_id = str(user.id)
        user_name = f"@{user.username}" if user.username else user.first_name

        for i, row in enumerate(records, start=2):
            if str(row.get('Дата')) == date and str(row.get('Время')) == time and row.get('Услуга') == service:
                sheet.update_cell(i, 4, "Занято")
                sheet.update_cell(i, 5, user_id)
                sheet.update_cell(i, 6, user_name)
                print(f"🔒 Окно {date} {time} ({service}) успешно забронировано за {user_name}.")
                break
    except Exception as e:
        print(f"❌ Ошибка при бронировании слота: {e}")


def append_to_sheet(row_data):
    """Добавляет готовую запись на главный лист (Лист1)"""
    try:
        client = get_gspread_client()
        sheet = client.open(SPREADSHEET_NAME).sheet1
        sheet.append_row(row_data)
        print(f"📊 Новая запись клиента добавлена на главный лист!")
    except Exception as e:
        print(f"❌ Ошибка при записи на главный лист: {e}")


# --- ЛОГИКА ИНТЕРФЕЙСА БОТА ---

def get_main_keyboard():
    """Главная клавиатура бота"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("💅 Записаться на маникюр")
    btn2 = types.KeyboardButton("👣 Записаться на педикюр")
    btn3 = types.KeyboardButton("📋 Мои записи")
    keyboard.add(btn1, btn2)
    keyboard.add(btn3)
    return keyboard


@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(
        message.chat.id,
        "Добро пожаловать в студию Nail Studio! ✨\nВыберите действие в меню ниже:",
        reply_markup=get_main_keyboard()
    )


@bot.message_handler(func=lambda message: message.text == "📋 Мои записи")
def show_my_bookings(message):
    try:
        user_id = str(message.from_user.id)
        client = get_gspread_client()
        sheet = client.open(SPREADSHEET_NAME).worksheet("Расписание")
        all_rows = sheet.get_all_values()

        user_bookings = []
        # Пробегаем по строкам (пропуская заголовок)
        for index, row in enumerate(all_rows[1:], start=2):
            if len(row) >= 5 and row[4] == user_id and row[3] == "Занято":
                user_bookings.append({
                    'row': index,
                    'date': row[0],
                    'time': row[1],
                    'service': row[2]
                })

        if not user_bookings:
            bot.send_message(message.chat.id, "У вас пока нет активных записей.", reply_markup=get_main_keyboard())
            return

        bot.send_message(message.chat.id, "<b>Ваши текущие записи:</b>", parse_mode="HTML")

        # Отправляем карточку с кнопкой "Отменить"
        for item in user_bookings:
            text = f"📅 <b>Дата:</b> {item['date']}\n⏰ <b>Время:</b> {item['time']}\n💅 <b>Услуга:</b> {item['service']}"
            keyboard = types.InlineKeyboardMarkup()
            btn_cancel = types.InlineKeyboardButton("❌ Отменить запись", callback_data=f"cancel_{item['row']}")
            keyboard.add(btn_cancel)
            bot.send_message(message.chat.id, text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        bot.send_message(message.chat.id, "Произошла ошибка при поиске записей.")
        print(f"Ошибка в Мои записи: {e}")


@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_"))
def cancel_booking_callback(call):
    try:
        row_number = int(call.data.split("_")[1])
        client = get_gspread_client()
        sheet = client.open(SPREADSHEET_NAME).worksheet("Расписание")

        # Очищаем данные в Google Таблице
        sheet.update_cell(row_number, 4, "Свободно")
        sheet.update_cell(row_number, 5, "")
        sheet.update_cell(row_number, 6, "")

        bot.answer_callback_query(call.id, "Запись успешно отменена!")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="❌ <b>Запись отменена.</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        bot.answer_callback_query(call.id, "Ошибка при отмене.")
        print(f"Ошибка отмены: {e}")


@bot.message_handler(func=lambda message: message.text in ["💅 Записаться на маникюр", "👣 Записаться на педикюр"])
def start_booking(message):
    chat_id = message.chat.id
    if chat_id not in booking_data:
        booking_data[chat_id] = {}

    chosen_service = "Маникюр" if "маникюр" in message.text.lower() else "Педикюр"
    booking_data[chat_id]['service'] = chosen_service

    days = get_available_days(chosen_service)

    if not days:
        bot.send_message(chat_id, f"К сожалению, свободных окон на {chosen_service.lower()} пока нет 😔")
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    for d in days:
        markup.add(types.InlineKeyboardButton(text=d, callback_data=f"day_{d}"))

    bot.send_message(chat_id, "Выберите удобный день:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("day_") or call.data.startswith("time_"))
def callback_handler(call):
    chat_id = call.message.chat.id
    if chat_id not in booking_data:
        booking_data[chat_id] = {}

    # Выбрали дату -> Показываем часы
    if call.data.startswith("day_"):
        chosen_day = call.data[4:]
        booking_data[chat_id]['date'] = chosen_day

        current_service = booking_data[chat_id].get('service', 'Маникюр')
        hours = get_available_hours(current_service, chosen_day)

        markup = types.InlineKeyboardMarkup(row_width=2)
        for h in hours:
            markup.add(types.InlineKeyboardButton(text=h, callback_data=f"time_{h}"))

        bot.edit_message_text(f"Свободное время на {chosen_day} ({current_service}):", chat_id, call.message.message_id,
                              reply_markup=markup)

    # Выбрали время -> Спрашиваем имя
    elif call.data.startswith("time_"):
        chosen_time = call.data[5:]
        booking_data[chat_id]['time'] = chosen_time

        bot.delete_message(chat_id, call.message.message_id)
        msg = bot.send_message(chat_id, "Отлично! Напишите ваше **Имя**:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_name_step)


def process_name_step(message):
    chat_id = message.chat.id
    booking_data[chat_id]['name'] = message.text

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    button_phone = types.KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)
    markup.add(button_phone)

    msg = bot.send_message(chat_id, "Остался последний шаг! Поделитесь номером телефона:", reply_markup=markup)
    bot.register_next_step_handler(msg, process_phone_step)


def process_phone_step(message):
    chat_id = message.chat.id
    phone = message.contact.phone_number if message.contact else message.text
    booking_data[chat_id]['phone'] = phone

    data = booking_data.get(chat_id, {})

    if not all(k in data for k in ("date", "time", "service", "name")):
        bot.send_message(chat_id, "Произошла ошибка при записи. Пожалуйста, начните заново.",
                         reply_markup=get_main_keyboard())
        return

    full_time_info = f"{data['date']} в {data['time']}"
    row = [full_time_info, data['name'], phone, data['service'], "Любой мастер"]

    # 1. Запись на главный лист
    append_to_sheet(row)

    # 2. Блокировка времени в расписании (передаем message.from_user для ID)
    book_schedule_slot(data['date'], data['time'], data['service'], message.from_user)

    # 3. Сообщения
    bot.send_message(
        chat_id,
        f"🎉 **Вы успешно записаны!**\n\n"
        f"• Услуга: {data['service']}\n"
        f"• Дата: {data['date']}\n"
        f"• Время: {data['time']}\n"
        f"• Имя: {data['name']}\n"
        f"• Телефон: {phone}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()  # Возвращаем главное меню вместо скрытия кнопок
    )

    if ADMIN_CHAT_ID:
        admin_text = f"🔔 **Новая запись!**\nИмя: {data['name']}\nТел: {phone}\nУслуга: {data['service']}\nВремя: {full_time_info}"
        try:
            bot.send_message(ADMIN_CHAT_ID, admin_text, parse_mode="Markdown")
        except Exception as e:
            print(f"Не удалось отправить уведомление администратору: {e}")

    booking_data.pop(chat_id, None)


# --- ЗАПУСК БОТА ---

if __name__ == '__main__':
    print("Проверка расписания...")
    update_schedule_with_dates(days_ahead=7)
    print("✅ Бот успешно запущен и готов к работе!")
    bot.infinity_polling()