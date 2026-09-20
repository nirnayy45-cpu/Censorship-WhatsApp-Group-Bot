"""Telegram control bot for the WhatsApp URL/keyword auto-delete filter."""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)


BASE_DIR = Path(__file__).resolve().parent
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GROUPS_FILE = Path(os.getenv("GROUPS_FILE", str(BASE_DIR / "groups.json")))
FILTERS_FILE = Path(os.getenv("FILTERS_FILE", str(BASE_DIR / "filters.json")))
QR_FILE = Path(
    os.getenv(
        "QR_FILE",
        str(BASE_DIR / "whatsapp_pairing_qr.png"),
    )
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("whatsapp-url-filter-bot")


def allowed_user_ids() -> set[int]:
    raw_ids = os.getenv("ALLOWED_USER_IDS", "")
    if not raw_ids.strip():
        return set()
    ids: set[int] = set()
    for raw_id in raw_ids.split(","):
        try:
            ids.add(int(raw_id.strip()))
        except ValueError:
            logger.warning("Ignoring invalid ALLOWED_USER_IDS entry: %r", raw_id)
    return ids


ALLOWED_USERS = allowed_user_ids()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set.")

bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher(storage=MemoryStorage())
router = Router()
dispatcher.include_router(router)

DEFAULT_FILTERS = {"enabled_groups": [], "url_filter": True, "keywords": []}


def load_filters() -> dict[str, Any]:
    if not FILTERS_FILE.exists():
        return dict(DEFAULT_FILTERS)
    try:
        data = json.loads(FILTERS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_FILTERS)
    return {
        "enabled_groups": data.get("enabled_groups", []),
        "url_filter": bool(data.get("url_filter", True)),
        "keywords": data.get("keywords", []),
    }


def save_filters(data: dict[str, Any]) -> None:
    temporary_file = FILTERS_FILE.with_suffix(".json.tmp")
    temporary_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temporary_file.replace(FILTERS_FILE)


def load_groups() -> list[dict[str, str]]:
    if not GROUPS_FILE.exists():
        return []
    try:
        content: Any = json.loads(GROUPS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        logger.error("Could not read %s: %s", GROUPS_FILE, error)
        return []
    if not isinstance(content, list):
        return []
    return [
        {"name": group["name"].strip(), "jid": group["jid"].strip()}
        for group in content
        if isinstance(group, dict)
        and isinstance(group.get("name"), str)
        and isinstance(group.get("jid"), str)
    ]


def is_allowed(message: Message) -> bool:
    if not ALLOWED_USERS:
        return True
    return bool(message.from_user and message.from_user.id in ALLOWED_USERS)


async def reject_if_not_allowed(message: Message) -> bool:
    if is_allowed(message):
        return False
    await message.answer("This bot is private.")
    return True


class Flow(StatesGroup):
    adding_keyword = State()


def groups_keyboard(
    groups: list[dict[str, str]], enabled: list[str]
) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=("✅ " if group["jid"] in enabled else "⬜ ") + group["name"],
                callback_data=f"togglegrp:{group['jid']}",
            )
        ]
        for group in groups
    ]
    buttons.append(
        [InlineKeyboardButton(text="Done", callback_data="groupsdone")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def settings_summary(
    filters_data: dict[str, Any], groups: list[dict[str, str]]
) -> str:
    enabled_names = [
        group["name"]
        for group in groups
        if group["jid"] in filters_data["enabled_groups"]
    ]
    return "\n".join(
        [
            "Current filter settings:",
            "",
            f"Groups: {', '.join(enabled_names) if enabled_names else '(none selected)'}",
            f"URL filter: {'ON' if filters_data['url_filter'] else 'OFF'}",
            f"Keywords: {', '.join(filters_data['keywords']) if filters_data['keywords'] else '(none)'}",
        ]
    )


@router.message(Command("start"))
async def command_start(message: Message, state: FSMContext) -> None:
    if await reject_if_not_allowed(message):
        return
    await state.clear()
    await message.answer(
        "WhatsApp URL/Keyword Auto-Delete Bot\n\n"
        "/link — link WhatsApp by scanning a QR code\n"
        "/groups — choose groups where the filter runs\n"
        "/urlfilter — turn URL detection on or off\n"
        "/keywords — manage optional keyword filters\n"
        "/status — view current settings\n\n"
        "The WhatsApp account must be an admin in filtered groups."
    )


@router.message(Command("link"))
async def command_link(message: Message, state: FSMContext) -> None:
    if await reject_if_not_allowed(message):
        return
    if GROUPS_FILE.exists() and load_groups():
        await message.answer("WhatsApp is already linked. Use /groups.")
        return
    if not QR_FILE.exists():
        await message.answer(
            "QR abhi ready nahi hai. 5 seconds wait karke /link dobara bhejo."
        )
        return

    await message.answer_photo(
        photo=FSInputFile(QR_FILE),
        caption=(
            "QR ready hai. Isko WhatsApp app se scan karo:\n"
            "Settings → Linked devices → Link a device"
        ),
    )


@router.message(Command("groups"))
async def command_groups(message: Message) -> None:
    if await reject_if_not_allowed(message):
        return
    groups = load_groups()
    if not groups:
        await message.answer("No groups found. Link WhatsApp first with /link.")
        return
    filters_data = load_filters()
    await message.answer(
        "Choose the groups where the filter should run:",
        reply_markup=groups_keyboard(groups, filters_data["enabled_groups"]),
    )


@router.callback_query(F.data.startswith("togglegrp:"))
async def toggle_group(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return
    jid = callback.data.split("togglegrp:", 1)[1]
    filters_data = load_filters()
    enabled = filters_data["enabled_groups"]
    if jid in enabled:
        enabled.remove(jid)
    else:
        enabled.append(jid)
    filters_data["enabled_groups"] = enabled
    save_filters(filters_data)
    await callback.message.edit_reply_markup(
        reply_markup=groups_keyboard(load_groups(), enabled)
    )
    await callback.answer()


@router.callback_query(F.data == "groupsdone")
async def groups_done(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return
    await callback.message.edit_text(
        settings_summary(load_filters(), load_groups())
    )
    await callback.answer()


@router.message(Command("urlfilter"))
async def command_urlfilter(message: Message) -> None:
    if await reject_if_not_allowed(message):
        return
    filters_data = load_filters()
    filters_data["url_filter"] = not filters_data["url_filter"]
    save_filters(filters_data)
    await message.answer(
        f"URL filter is now {'ON' if filters_data['url_filter'] else 'OFF'}."
    )


@router.message(Command("keywords"))
async def command_keywords(message: Message) -> None:
    if await reject_if_not_allowed(message):
        return
    filters_data = load_filters()
    buttons = [
        [InlineKeyboardButton(text="Add keyword", callback_data="kwadd")]
    ]
    buttons.extend(
        [
            [
                InlineKeyboardButton(
                    text=f"Remove '{keyword}'", callback_data=f"kwdel:{keyword}"
                )
            ]
            for keyword in filters_data["keywords"]
        ]
    )
    await message.answer(
        "Current keywords: "
        + (", ".join(filters_data["keywords"]) or "(none)"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data == "kwadd")
async def keyword_add_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        await callback.answer()
        return
    await state.set_state(Flow.adding_keyword)
    await callback.message.answer("Send the new keyword.")
    await callback.answer()


@router.message(Flow.adding_keyword, F.text)
async def keyword_add_received(message: Message, state: FSMContext) -> None:
    if await reject_if_not_allowed(message):
        return
    keyword = message.text.strip()
    if not keyword:
        await message.answer("The keyword cannot be empty.")
        return
    filters_data = load_filters()
    if keyword.lower() not in [item.lower() for item in filters_data["keywords"]]:
        filters_data["keywords"].append(keyword)
        save_filters(filters_data)
    await message.answer(f"Keyword '{keyword}' added.")
    await state.clear()


@router.callback_query(F.data.startswith("kwdel:"))
async def keyword_delete(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return
    keyword = callback.data.split("kwdel:", 1)[1]
    filters_data = load_filters()
    filters_data["keywords"] = [
        item for item in filters_data["keywords"] if item != keyword
    ]
    save_filters(filters_data)
    await callback.message.edit_text(f"Keyword '{keyword}' removed.")
    await callback.answer()


@router.message(Command("status"))
async def command_status(message: Message) -> None:
    if await reject_if_not_allowed(message):
        return
    await message.answer(settings_summary(load_filters(), load_groups()))


async def main() -> None:
    if not FILTERS_FILE.exists():
        save_filters(dict(DEFAULT_FILTERS))
    logger.info("Telegram control bot is starting")
    if ALLOWED_USERS:
        logger.info("User allowlist enabled for %d Telegram user(s)", len(ALLOWED_USERS))
    else:
        logger.warning("ALLOWED_USER_IDS is empty; anyone who finds the bot can use it")
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())