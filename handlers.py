import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    BotCommand,
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton as IKB,
    InlineKeyboardMarkup,
    Message,
)
from dotenv import load_dotenv

from libs import answer_user_message, summarize_dialog_history
from memory_store import clear_user_memory, get_user_memory, init_db, upsert_user_memory
from prompts import SYSTEM_PROMPT
from speech_local import synthesize_speech, transcribe_audio_file

load_dotenv()

router = Router()
subscribed_users: set[int] = set()
last_reminder_slot: dict[int, str] = {}
reminder_task: asyncio.Task | None = None

USERS_FILE = Path(os.getenv("SUBSCRIBERS_FILE", "subscribed_users.json"))
try:
    REMINDER_TZ = ZoneInfo("Europe/Moscow")
except ZoneInfoNotFoundError:
    REMINDER_TZ = timezone(timedelta(hours=3))

QUIET_HOUR_START = 1
QUIET_HOUR_END = 8
RECENT_DIALOG_MAX_CHARS = 7000
RECENT_DIALOG_KEEP_CHARS = 2500


def load_subscribed_users() -> set[int]:
    if not USERS_FILE.exists():
        return set()
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {int(user_id) for user_id in data}
    except Exception:
        logging.exception("Не удалось загрузить список подписчиков")
    return set()


def save_subscribed_users() -> None:
    try:
        USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        USERS_FILE.write_text(
            json.dumps(sorted(subscribed_users), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        logging.exception("Не удалось сохранить список подписчиков")


def register_user(user_id: int) -> None:
    if user_id not in subscribed_users:
        subscribed_users.add(user_id)
        save_subscribed_users()


def unregister_user(user_id: int) -> None:
    if user_id in subscribed_users:
        subscribed_users.remove(user_id)
        save_subscribed_users()


async def reminder_loop(bot: Bot) -> None:
    while True:
        try:
            now = datetime.now(REMINDER_TZ)
            hour = now.hour

            if QUIET_HOUR_START <= hour < QUIET_HOUR_END:
                await asyncio.sleep(60)
                continue

            if hour % 2 == 0 and now.minute < 5:
                slot = now.strftime("%Y-%m-%d %H")
                for user_id in list(subscribed_users):
                    if last_reminder_slot.get(user_id) == slot:
                        continue
                    try:
                        await bot.send_message(
                            user_id,
                            "Напоминание: выпейте воды и напишите, пожалуйста, что вы съели за последние часы.",
                        )
                        last_reminder_slot[user_id] = slot
                    except Exception:
                        logging.exception("Не удалось отправить напоминание пользователю %s", user_id)

            await asyncio.sleep(60)
        except asyncio.CancelledError:
            break
        except Exception:
            logging.exception("Ошибка в reminder_loop()")
            await asyncio.sleep(60)


def kb_clear_memory() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[IKB(text="Очистить память", callback_data="clear_memory")]]
    )


async def clear_memory(tg_id: int) -> None:
    try:
        clear_user_memory(tg_id)
        logging.info("Очищена история переписки для %s", tg_id)
    except Exception:
        logging.exception("clear_memory()")


async def generate_assistant_reply(user_id: int, user_text: str) -> str:
    summary, recent_dialog = get_user_memory(user_id)
    history = (
        f"Сводка прошлых диалогов:\n{summary}\n\nНедавняя переписка:\n{recent_dialog}"
        if summary
        else recent_dialog
    )

    response_text = await answer_user_message(
        SYSTEM_PROMPT,
        f"История переписки:\n{history}\n\nЗапрос:\n{user_text}",
    )

    updated_recent_dialog = recent_dialog + (
        f"\n\nЗапрос пользователя: {user_text}"
        f"\n\nОтвет:\n{response_text}"
    )

    updated_summary = summary
    if len(updated_recent_dialog) > RECENT_DIALOG_MAX_CHARS:
        updated_summary = await summarize_dialog_history(summary, updated_recent_dialog)
        updated_recent_dialog = updated_recent_dialog[-RECENT_DIALOG_KEEP_CHARS:]

    upsert_user_memory(user_id, updated_summary, updated_recent_dialog)
    return response_text


@router.callback_query(F.data == "clear_memory")
async def handle_clear_callback(callback: CallbackQuery) -> None:
    await clear_memory(callback.from_user.id)
    if callback.message:
        await callback.message.delete()
    await callback.answer("Память очищена")


@router.startup()
async def set_menu_button(bot: Bot) -> None:
    main_menu_commands = [
        BotCommand(command="/start", description="Start"),
        BotCommand(command="/reminders", description="reminders on|off"),
    ]
    await bot.set_my_commands(main_menu_commands)


@router.startup()
async def init_persistent_memory(bot: Bot) -> None:
    init_db()
    logging.info("SQLite память инициализирована")


@router.startup()
async def start_reminders(bot: Bot) -> None:
    global reminder_task
    if reminder_task is None or reminder_task.done():
        reminder_task = asyncio.create_task(reminder_loop(bot))
        logging.info("Фоновая задача напоминаний запущена")


@router.shutdown()
async def stop_reminders(bot: Bot) -> None:
    global reminder_task
    if reminder_task and not reminder_task.done():
        reminder_task.cancel()
        try:
            await reminder_task
        except asyncio.CancelledError:
            pass
    reminder_task = None
    logging.info("Фоновая задача напоминаний остановлена")


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    user_id = message.from_user.id
    register_user(user_id)
    await clear_memory(user_id)
    await message.answer(
        "Привет. Я помогу вам худеть спокойно и устойчиво. "
        "Напишите, как проходит день, что ели или что сейчас чувствуете."
    )


@router.message(Command("reminders"))
async def cmd_reminders(message: Message) -> None:
    user_id = message.from_user.id
    parts = (message.text or "").strip().split()
    mode = parts[1].lower() if len(parts) > 1 else ""

    if mode == "on":
        register_user(user_id)
        await message.answer(
            "Напоминания включены. Буду писать каждые 2 часа, кроме периода 01:00-08:00."
        )
        return

    if mode == "off":
        unregister_user(user_id)
        await message.answer("Напоминания отключены.")
        return

    await message.answer(
        "Используйте команду так:\n"
        "/reminders on - включить\n"
        "/reminders off - отключить"
    )


@router.message(F.voice | F.audio)
async def handle_voice_dialog(message: Message, bot: Bot) -> None:
    user_id = message.from_user.id
    register_user(user_id)

    media = message.voice or message.audio
    if media is None:
        await message.answer("Не удалось обработать голосовое сообщение.")
        return

    suffix = ".ogg" if message.voice else ".mp3"
    temp_path: str | None = None

    await message.answer("Принял голосовое, распознаю...")
    try:
        tg_file = await bot.get_file(media.file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            temp_path = tmp.name

        await bot.download_file(tg_file.file_path, destination=temp_path)
        try:
            user_text = await asyncio.to_thread(transcribe_audio_file, temp_path)
        except Exception:
            logging.exception("STT ошибка при обработке голосового")
            await message.answer(
                "Не смог распознать голос. Попробуйте еще раз через 10-20 секунд или отправьте текстом."
            )
            return
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)

    if not user_text:
        await message.answer("Не смог распознать речь. Попробуйте записать голос чуть четче.")
        return

    logging.info("handle_voice_dialog() - Запрос от %s: %s", user_id, user_text)

    response = await generate_assistant_reply(user_id, user_text)
    try:
        audio_bytes, filename, is_voice = await asyncio.to_thread(synthesize_speech, response)
        file_to_send = BufferedInputFile(audio_bytes, filename=filename)

        if is_voice:
            await message.answer_voice(file_to_send)
        else:
            await message.answer_audio(file_to_send, caption="Голосовой ответ")
    except Exception:
        logging.exception("TTS ошибка, отправляю текстовый ответ")
        await message.answer("Не смог озвучить ответ локально, отправляю текстом.")
        await message.answer(response)


@router.message(F.text)
async def handle_dialog(message: Message) -> None:
    user_id = message.from_user.id
    user_text = message.text or ""
    register_user(user_id)

    logging.info("handle_dialog() - Запрос от %s: %s", user_id, user_text)

    response = await generate_assistant_reply(user_id, user_text)

    await message.answer(response)
    await message.answer(
        "Задайте уточняющий вопрос или очистите память перед следующим запросом",
        reply_markup=kb_clear_memory(),
    )


subscribed_users = load_subscribed_users()

