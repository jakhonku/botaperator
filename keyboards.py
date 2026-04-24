from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_USER_CONNECT = "📞 Operator bilan bog'lanish"
BTN_USER_END     = "❌ Suhbatni yakunlash"

BTN_OP_ONLINE    = "🟢 Ishga kirishish"
BTN_OP_OFFLINE   = "🔴 Ishdan chiqish"
BTN_OP_END       = "✅ Suhbatni yakunlash"


def _kb(rows: list[list[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=True,
    )


def user_start_kb() -> ReplyKeyboardMarkup:
    return _kb([[BTN_USER_CONNECT]])


def user_in_chat_kb() -> ReplyKeyboardMarkup:
    return _kb([[BTN_USER_END]])


def operator_offline_kb() -> ReplyKeyboardMarkup:
    return _kb([[BTN_OP_ONLINE]])


def operator_online_kb() -> ReplyKeyboardMarkup:
    return _kb([[BTN_OP_OFFLINE]])


def operator_in_chat_kb() -> ReplyKeyboardMarkup:
    return _kb([[BTN_OP_END]])
