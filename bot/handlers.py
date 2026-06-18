import asyncio
import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot import client, state
from bot.config import get_allowed_user_ids, get_public_base_url

logger = logging.getLogger(__name__)
router = Router()

POLL_INTERVAL_SEC = 5


class GenerateStates(StatesGroup):
    waiting_topic = State()
    waiting_format = State()


def _is_allowed(user_id: int) -> bool:
    return user_id in get_allowed_user_ids()


@router.message(CommandStart())
async def cmd_start(message: Message):
    if not _is_allowed(message.from_user.id):
        await message.answer("Доступ запрещён.")
        return
    await message.answer(
        "Привет! Команды:\n"
        "/generate — создать видео\n"
        "/history — последние запросы\n"
        "/cancel — отменить текущий ввод"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state_ctx: FSMContext):
    if not _is_allowed(message.from_user.id):
        await message.answer("Доступ запрещён.")
        return
    await state_ctx.clear()
    await message.answer("Отменено.")


@router.message(Command("generate"))
async def cmd_generate(message: Message, state_ctx: FSMContext):
    if not _is_allowed(message.from_user.id):
        await message.answer("Доступ запрещён.")
        return
    await state_ctx.set_state(GenerateStates.waiting_topic)
    await message.answer("Какая тема видео?")


@router.message(GenerateStates.waiting_topic)
async def on_topic(message: Message, state_ctx: FSMContext):
    topic = (message.text or "").strip()
    if not topic:
        await message.answer("Тема не может быть пустой. Напишите тему видео.")
        return
    await state_ctx.update_data(topic=topic)
    await state_ctx.set_state(GenerateStates.waiting_format)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Short (9:16)", callback_data="format:short"),
                InlineKeyboardButton(text="Long (16:9)", callback_data="format:long"),
            ]
        ]
    )
    await message.answer("Какой формат?", reply_markup=keyboard)


@router.callback_query(GenerateStates.waiting_format, F.data.startswith("format:"))
async def on_format(callback: CallbackQuery, state_ctx: FSMContext, bot: Bot):
    fmt = callback.data.split(":", 1)[1]
    data = await state_ctx.get_data()
    topic = data["topic"]
    await state_ctx.clear()
    await callback.message.edit_reply_markup(reply_markup=None)

    try:
        result = await client.create_video(topic, fmt)
    except Exception:
        logger.exception("create_video failed for topic=%r format=%r", topic, fmt)
        await callback.message.answer("Backend недоступен, попробуйте позже.")
        await callback.answer()
        return

    video_id = result["id"]
    state.add_request(video_id, callback.from_user.id, topic, fmt)
    await callback.message.answer(
        "Генерация запущена (~1-5 мин для short / дольше для long). "
        "Сообщу, когда будет готово."
    )
    await callback.answer()
    asyncio.create_task(_poll_and_notify(bot, callback.message.chat.id, video_id))


async def _poll_and_notify(bot: Bot, chat_id: int, video_id: str):
    base_url = get_public_base_url()
    while True:
        await asyncio.sleep(POLL_INTERVAL_SEC)
        try:
            status_data = await client.get_status(video_id)
        except Exception:
            logger.exception("status poll failed for video_id=%s", video_id)
            continue

        status = status_data["status"]
        if status == "completed":
            await bot.send_message(
                chat_id, f"Готово! Скачать: {base_url}/videos/{video_id}/download"
            )
            return
        if status == "failed":
            await bot.send_message(
                chat_id, f"Не получилось: {status_data.get('error')}"
            )
            return


@router.message(Command("history"))
async def cmd_history(message: Message):
    if not _is_allowed(message.from_user.id):
        await message.answer("Доступ запрещён.")
        return

    requests = state.get_history(message.from_user.id)
    if not requests:
        await message.answer("История пуста.")
        return

    base_url = get_public_base_url()
    lines = []
    for req in requests:
        try:
            status_data = await client.get_status(req["video_id"])
        except Exception:
            lines.append(f"{req['topic']} ({req['format']}) — статус неизвестен")
            continue

        status = status_data["status"]
        if status == "completed":
            lines.append(
                f"{req['topic']} ({req['format']}) — готово: "
                f"{base_url}/videos/{req['video_id']}/download"
            )
        elif status == "failed":
            lines.append(f"{req['topic']} ({req['format']}) — ошибка: {status_data.get('error')}")
        else:
            lines.append(f"{req['topic']} ({req['format']}) — генерируется")

    await message.answer("\n".join(lines))
