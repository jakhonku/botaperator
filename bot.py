from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from config import load_config
from database import Database
from keyboards import (
    BTN_OP_END, BTN_OP_OFFLINE, BTN_OP_ONLINE,
    BTN_USER_CONNECT, BTN_USER_END,
    operator_in_chat_kb, operator_offline_kb, operator_online_kb,
    user_in_chat_kb, user_start_kb,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
log = logging.getLogger("bot")

config = load_config()
bot = Bot(
    token=config.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
db = Database(config.db_path)

# Operatorlarni topish/biriktirish bir vaqtda bo'lmasligi uchun
_match_lock = asyncio.Lock()


# ---------- Yordamchi funksiyalar ----------

def is_admin(tg_id: int) -> bool:
    return tg_id in config.admin_ids


def display_name(msg: Message) -> str:
    u = msg.from_user
    assert u is not None
    name = u.full_name or (u.username or f"User{u.id}")
    if u.username:
        name = f"{name} (@{u.username})"
    return name


async def safe_send(chat_id: int, text: str, **kw) -> None:
    try:
        await bot.send_message(chat_id, text, **kw)
    except Exception as e:
        log.warning("send_message to %s failed: %s", chat_id, e)


async def safe_copy(dst: int, src: int, message_id: int) -> bool:
    try:
        await bot.copy_message(chat_id=dst, from_chat_id=src, message_id=message_id)
        return True
    except Exception as e:
        log.warning("copy_message %s->%s failed: %s", src, dst, e)
        return False


async def try_connect_user(user_tg_id: int, user_name: str, question: str) -> None:
    """Foydalanuvchi uchun chat yaratadi va bo'sh operatorni qidiradi."""
    async with _match_lock:
        existing = await db.get_active_chat_by_user(user_tg_id)
        if existing is None:
            chat_id = await db.create_waiting_chat(user_tg_id, user_name, question)
        else:
            chat_id = existing["id"]
            # agar avvaldan aktiv chat bo'lsa, hech narsa qilmaslik
            if existing["status"] == "active":
                return

        op = await db.find_free_operator()
        if op is None:
            await safe_send(
                user_tg_id,
                "⏳ Hozirda barcha operatorlar band.\n"
                "Iltimos, kuting — birinchi bo'shagan operator siz bilan bog'lanadi.",
                reply_markup=user_in_chat_kb(),
            )
            return

        await db.assign_operator(chat_id, op["tg_id"])

    await safe_send(
        user_tg_id,
        f"✅ Siz <b>{op['full_name']}</b> operatoriga ulandingiz.\n"
        "Endi xabarlaringiz bevosita operatorga yuboriladi.",
        reply_markup=user_in_chat_kb(),
    )
    await safe_send(
        op["tg_id"],
        f"📩 Yangi murojaat — <b>{user_name}</b>\n\n"
        f"<b>Savol:</b> {question}\n\n"
        "Javob yozish uchun xabar yuboring.",
        reply_markup=operator_in_chat_kb(),
    )


async def try_pick_next_for_operator(operator_tg_id: int, operator_name: str) -> bool:
    """Operator bo'shaganda navbatdagi foydalanuvchini biriktiradi."""
    async with _match_lock:
        chat = await db.get_oldest_waiting_chat()
        if chat is None:
            return False
        await db.assign_operator(chat["id"], operator_tg_id)

    await safe_send(
        chat["user_tg_id"],
        f"✅ Siz <b>{operator_name}</b> operatoriga ulandingiz.\n"
        "Endi xabarlaringiz bevosita operatorga yuboriladi.",
        reply_markup=user_in_chat_kb(),
    )
    await safe_send(
        operator_tg_id,
        f"📩 Navbatdagi murojaat — <b>{chat['user_name']}</b>\n\n"
        f"<b>Savol:</b> {chat['user_question'] or '(savol yozilmagan)'}\n\n"
        "Javob yozish uchun xabar yuboring.",
        reply_markup=operator_in_chat_kb(),
    )
    return True


async def end_current_chat(msg: Message) -> None:
    tg_id = msg.from_user.id  # type: ignore[union-attr]
    op = await db.get_operator(tg_id)

    if op:
        chat = await db.get_active_chat_by_operator(tg_id)
        if not chat:
            kb = operator_online_kb() if op["is_online"] else operator_offline_kb()
            await msg.answer("Sizda aktiv suhbat yo'q.", reply_markup=kb)
            return
        await db.end_chat(chat["id"])
        await safe_send(
            chat["user_tg_id"],
            "Suhbat yakunlandi. Xizmatimizdan foydalanganingiz uchun rahmat! 🙏",
            reply_markup=user_start_kb(),
        )
        online = bool(op["is_online"])
        await msg.answer(
            "✅ Suhbat yakunlandi.",
            reply_markup=operator_online_kb() if online else operator_offline_kb(),
        )
        if online:
            await try_pick_next_for_operator(tg_id, op["full_name"])
        return

    # oddiy foydalanuvchi
    chat = await db.get_active_chat_by_user(tg_id)
    if not chat:
        await msg.answer("Sizda aktiv suhbat yo'q.", reply_markup=user_start_kb())
        return

    op_id = chat["operator_tg_id"]
    await db.end_chat(chat["id"])
    await msg.answer(
        "Suhbat yakunlandi. Biz bilan bog'langaningiz uchun rahmat! 🙏",
        reply_markup=user_start_kb(),
    )
    if op_id:
        operator = await db.get_operator(op_id)
        if operator:
            online = bool(operator["is_online"])
            await safe_send(
                op_id,
                "⚠️ Foydalanuvchi suhbatni yakunladi.",
                reply_markup=operator_online_kb() if online else operator_offline_kb(),
            )
            if online:
                await try_pick_next_for_operator(op_id, operator["full_name"])


# ---------- Buyruqlar ----------

@dp.message(CommandStart())
async def cmd_start(msg: Message) -> None:
    tg_id = msg.from_user.id  # type: ignore[union-attr]

    op = await db.get_operator(tg_id)
    if op:
        chat = await db.get_active_chat_by_operator(tg_id)
        if chat:
            await msg.answer(
                f"Sizda aktiv suhbat bor.\nFoydalanuvchi: <b>{chat['user_name']}</b>",
                reply_markup=operator_in_chat_kb(),
            )
            return
        online = bool(op["is_online"])
        await msg.answer(
            f"Assalomu alaykum, <b>{op['full_name']}</b>!\n"
            f"Holat: {'🟢 Onlayn' if online else '🔴 Oflayn'}",
            reply_markup=operator_online_kb() if online else operator_offline_kb(),
        )
        return

    # Foydalanuvchi
    active = await db.get_active_chat_by_user(tg_id)
    if active and active["status"] == "active":
        await msg.answer(
            "💬 Siz hozir operator bilan suhbatdasiz. Xabar yozing.",
            reply_markup=user_in_chat_kb(),
        )
        return
    if active and active["status"] == "waiting":
        await msg.answer(
            "⏳ Siz navbatdasiz — operator bo'shashi bilan ulaymiz.",
            reply_markup=user_in_chat_kb(),
        )
        return

    await msg.answer(
        "Assalomu alaykum! 👋\n\n"
        "Bu yerda savollaringizga bizning operatorlarimiz javob beradi.\n"
        "Savolingizni yozib yuboring — eng yaqin bo'sh operator siz bilan bog'lanadi.",
        reply_markup=user_start_kb(),
    )


@dp.message(Command("myid"))
async def cmd_myid(msg: Message) -> None:
    if not is_admin(msg.from_user.id):  # type: ignore[union-attr]
        return
    await msg.answer(f"Sizning ID: <code>{msg.from_user.id}</code>")  # type: ignore[union-attr]


@dp.message(Command("end"))
async def cmd_end(msg: Message) -> None:
    # Oddiy foydalanuvchilar va operatorlar uchun — suhbatni yakunlash
    tg_id = msg.from_user.id  # type: ignore[union-attr]
    op = await db.get_operator(tg_id)
    user_chat = await db.get_active_chat_by_user(tg_id)
    if not op and not user_chat:
        return  # ruxsatsiz foydalanuvchi — jim
    await end_current_chat(msg)


# ---------- Admin buyruqlari ----------

@dp.message(Command("addoperator"))
async def cmd_add_operator(msg: Message) -> None:
    if not is_admin(msg.from_user.id):  # type: ignore[union-attr]
        return
    parts = (msg.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await msg.answer("Foydalanish: <code>/addoperator &lt;telegram_id&gt; &lt;Ism Familiya&gt;</code>")
        return
    try:
        op_tg = int(parts[1])
    except ValueError:
        await msg.answer("❗ telegram_id raqam bo'lishi kerak")
        return
    name = parts[2].strip()
    added = await db.add_operator(op_tg, name)
    if added:
        await msg.answer(f"✅ Operator qo'shildi: <b>{name}</b> (<code>{op_tg}</code>)")
        await safe_send(
            op_tg,
            "🎉 Siz operator sifatida ro'yxatdan o'tkazildingiz!\n"
            "Ishga kirishish uchun /start ni bosing.",
        )
    else:
        await msg.answer("ℹ️ Bu ID allaqachon operator sifatida mavjud.")


@dp.message(Command("removeoperator"))
async def cmd_remove_operator(msg: Message) -> None:
    if not is_admin(msg.from_user.id):  # type: ignore[union-attr]
        return
    parts = (msg.text or "").split()
    if len(parts) < 2:
        await msg.answer("Foydalanish: <code>/removeoperator &lt;telegram_id&gt;</code>")
        return
    try:
        op_tg = int(parts[1])
    except ValueError:
        await msg.answer("❗ telegram_id raqam bo'lishi kerak")
        return

    chat = await db.get_active_chat_by_operator(op_tg)
    if chat:
        await db.end_chat(chat["id"])
        await safe_send(
            chat["user_tg_id"],
            "⚠️ Suhbat administrator tomonidan yakunlandi.",
            reply_markup=user_start_kb(),
        )

    removed = await db.remove_operator(op_tg)
    if removed:
        await msg.answer("✅ Operator ro'yxatdan chiqarildi.")
        await safe_send(op_tg, "ℹ️ Siz operatorlar ro'yxatidan chiqarildingiz.")
    else:
        await msg.answer("❗ Bunday operator topilmadi.")


@dp.message(Command("operators"))
async def cmd_operators(msg: Message) -> None:
    if not is_admin(msg.from_user.id):  # type: ignore[union-attr]
        return
    ops = await db.list_operators()
    if not ops:
        await msg.answer("Operatorlar ro'yxati bo'sh.")
        return
    lines = [f"<b>Jami:</b> {len(ops)}", ""]
    for o in ops:
        status = "🟢" if o["is_online"] else "🔴"
        lines.append(f"{status} {o['full_name']} — <code>{o['tg_id']}</code>")
    await msg.answer("\n".join(lines))


@dp.message(Command("stats"))
async def cmd_stats(msg: Message) -> None:
    if not is_admin(msg.from_user.id):  # type: ignore[union-attr]
        return
    s = await db.get_stats()
    await msg.answer(
        "📊 <b>Statistika</b>\n\n"
        f"Operatorlar: <b>{s['total_operators']}</b> (onlayn: {s['online_operators']})\n"
        f"Kutayotganlar: <b>{s['waiting']}</b>\n"
        f"Aktiv suhbatlar: <b>{s['active']}</b>\n"
        f"Jami suhbatlar: <b>{s['total_chats']}</b>\n"
        f"Bugun yakunlangan: <b>{s['ended_today']}</b>"
    )


@dp.message(Command("broadcast"))
async def cmd_broadcast(msg: Message) -> None:
    if not is_admin(msg.from_user.id):  # type: ignore[union-attr]
        return
    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await msg.answer("Foydalanish: <code>/broadcast &lt;xabar&gt;</code>")
        return
    content = parts[1]
    ops = await db.list_operators()
    sent = 0
    for o in ops:
        try:
            await bot.send_message(o["tg_id"], f"📢 <b>Xabar (admin)</b>:\n\n{content}")
            sent += 1
        except Exception as e:
            log.warning("broadcast to %s failed: %s", o["tg_id"], e)
    await msg.answer(f"✅ Yuborildi: {sent}/{len(ops)}")


# ---------- Tugmalar ----------

@dp.message(F.text == BTN_OP_ONLINE)
async def btn_op_online(msg: Message) -> None:
    op = await db.get_operator(msg.from_user.id)  # type: ignore[union-attr]
    if not op:
        return
    await db.set_operator_online(op["tg_id"], True)
    await msg.answer(
        "🟢 Siz onlayn holatdasiz. Yangi murojaatlar kutilmoqda...",
        reply_markup=operator_online_kb(),
    )
    await try_pick_next_for_operator(op["tg_id"], op["full_name"])


@dp.message(F.text == BTN_OP_OFFLINE)
async def btn_op_offline(msg: Message) -> None:
    op = await db.get_operator(msg.from_user.id)  # type: ignore[union-attr]
    if not op:
        return
    chat = await db.get_active_chat_by_operator(op["tg_id"])
    if chat:
        await msg.answer(
            "❗ Avval joriy suhbatni yakunlang.",
            reply_markup=operator_in_chat_kb(),
        )
        return
    await db.set_operator_online(op["tg_id"], False)
    await msg.answer("🔴 Siz oflayn holatdasiz.", reply_markup=operator_offline_kb())


@dp.message(F.text.in_({BTN_OP_END, BTN_USER_END}))
async def btn_end(msg: Message) -> None:
    await end_current_chat(msg)


@dp.message(F.text == BTN_USER_CONNECT)
async def btn_user_connect(msg: Message) -> None:
    tg_id = msg.from_user.id  # type: ignore[union-attr]
    existing = await db.get_active_chat_by_user(tg_id)
    if existing:
        if existing["status"] == "active":
            await msg.answer("💬 Siz hozir suhbatdasiz.", reply_markup=user_in_chat_kb())
        else:
            await msg.answer("⏳ Siz navbatdasiz.", reply_markup=user_in_chat_kb())
        return
    await msg.answer(
        "📝 Savolingizni yozib yuboring.",
        reply_markup=user_in_chat_kb(),
    )


# ---------- Xabarlarni uzatish ----------

@dp.message()
async def relay(msg: Message) -> None:
    tg_id = msg.from_user.id  # type: ignore[union-attr]

    # 1) Operatordan foydalanuvchiga
    op = await db.get_operator(tg_id)
    if op:
        chat = await db.get_active_chat_by_operator(tg_id)
        if not chat:
            kb = operator_online_kb() if op["is_online"] else operator_offline_kb()
            await msg.answer("Sizda aktiv suhbat yo'q.", reply_markup=kb)
            return
        ok = await safe_copy(chat["user_tg_id"], tg_id, msg.message_id)
        if not ok:
            await msg.answer("❗ Xabarni foydalanuvchiga yuborib bo'lmadi.")
        return

    # 2) Foydalanuvchidan operatorga
    chat = await db.get_active_chat_by_user(tg_id)
    if chat and chat["status"] == "active":
        ok = await safe_copy(chat["operator_tg_id"], tg_id, msg.message_id)
        if not ok:
            await msg.answer("❗ Xabarni operatorga yuborib bo'lmadi.")
        return
    if chat and chat["status"] == "waiting":
        await msg.answer("⏳ Iltimos kuting — siz navbatdasiz. Xabarlar operator ulangandan keyin yuboriladi.")
        return

    # 3) Chat hali yaratilmagan — birinchi xabar savol hisoblanadi
    name = display_name(msg)
    question = (msg.text or msg.caption or "(media xabar)").strip() or "(bo'sh)"
    await try_connect_user(tg_id, name, question)


# ---------- Ishga tushirish ----------

async def main() -> None:
    await db.init()
    log.info("DB tayyor: %s", config.db_path)
    log.info("Adminlar: %s", config.admin_ids)
    log.info("Bot ishga tushmoqda...")
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot to'xtatildi.")
