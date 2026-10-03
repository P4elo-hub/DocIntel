"""Рендеринг стрима событий в Telegram-сообщение.

Native streaming через `sendMessageDraft`: бот шлёт серию «драфтов» с
общим draft_id (Telegram анимирует приращение текста), а в конце
фиксирует ответ полноценным `send_message`. Драфт — ephemeral preview
на ~30 секунд, поэтому финальный send_message обязателен.

Backend стримит уже dict-события `{"type":"token","delta":"..."}` и
однократно `{"type":"message_saved","message_id":"<uuid>"}`. Если id
известен — финальный send_message получает inline-клавиатуру feedback,
привязанную к этому message_id. Если backend старый или message_id
не пришёл — кнопок нет.

sendMessageDraft — private-chat only. Если бот когда-нибудь окажется в группе,
вызов упадёт; на этот случай оставлен узкий AttributeError-fallback (на
старых версиях aiogram без метода) — он переключает рендер на edit_text-тротлинг.
"""

import logging
import uuid
from collections.abc import AsyncIterable
from time import monotonic
from uuid import UUID

import telegramify_markdown
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import Message

from bot.keyboards.inline import feedback_kb

log = logging.getLogger(__name__)

# Лимит Telegram на одно сообщение. MarkdownV2-эскейп раздувает текст,
# поэтому режем с запасом; при plain-fallback используем полный лимит.
TG_MAX_MESSAGE_LEN = 4096
TG_SAFE_CHUNK_LEN = 3500


def _chunk_text(text: str, limit: int = TG_SAFE_CHUNK_LEN) -> list[str]:
    """Режет длинный ответ на куски ≤ limit, по возможности по абзацам."""
    text = text or ""
    if len(text) <= limit:
        return [text] if text else []

    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break
        cut = rest.rfind("\n\n", 0, limit)
        if cut < limit // 3:
            cut = rest.rfind("\n", 0, limit)
        if cut < limit // 3:
            cut = limit
        piece = rest[:cut].rstrip()
        if not piece:
            piece = rest[:limit]
            cut = limit
        chunks.append(piece)
        rest = rest[cut:].lstrip("\n")
    return chunks


def _format_sources_footer(sources: list[dict]) -> str:
    """Компактный блок «Источники» под ответом: [1] file.md, [2] file.md.

    Цитаты [n] уже стоят в тексте ответа; футер расшифровывает номера в имена
    файлов из базы знаний."""
    if not sources:
        return ""
    lines = ["", "", "📚 Источники:"]
    for s in sources:
        sid = s.get("id")
        name = s.get("file_name") or "unknown"
        page = s.get("page")
        suffix = f", стр. {page}" if page else ""
        lines.append(f"[{sid}] {name}{suffix}")
    return "\n".join(lines)


def _to_tg_markdown(text: str) -> str:
    """GitHub-Markdown от LLM → Telegram MarkdownV2 с эскейпом спецсимволов.

    LLM возвращает обычный Markdown (`**bold**`, `# header`, `- list`), а
    Telegram парсит свой MarkdownV2 (требует эскейпа `.`, `-`, `(`, `)`, ...).
    `telegramify-markdown` делает конвертацию и эскейп.
    """
    try:
        return telegramify_markdown.markdownify(text)
    except Exception:
        # На любую ошибку конвертации — отдаём текст как есть; парсер Telegram
        # на это вернёт ошибку, и мы упадём в fallback без parse_mode.
        return text

# Минимальный интервал между sendMessageDraft вызовами на один draft.
# Telegram flood-control режет ~30 вызовов/сек суммарно; на длинном LLM-стриме
# (десятки токенов в секунду) без тротлинга мгновенно ловим TelegramRetryAfter.
# 0.7 сек даёт плавную анимацию и оставляет запас под другие сообщения бота.
DRAFT_MIN_INTERVAL_SEC = 0.7


async def stream_to_chat(
    message: Message,
    events: AsyncIterable[dict],
    chat_id: UUID | None = None,
) -> str:
    """Стримит через sendMessageDraft с общим draft_id. Финальный send_message
    фиксирует ответ в чате и крепит feedback-кнопки, если backend отдал
    message_id."""
    draft_id = uuid.uuid4().int & 0xFFFFFFFF or 1  # ensure non-zero
    buffer = ""
    assistant_message_id: str | None = None
    sources: list[dict] = []
    last_draft_at = 0.0

    # Первый кадр — пустой draft-плейсхолдер. Если метод недоступен (старая
    # aiogram) — graceful fallback на edit_text.
    try:
        await message.bot.send_message_draft(
            chat_id=message.chat.id, draft_id=draft_id, text="",
        )
        last_draft_at = monotonic()
    except AttributeError:
        return await _stream_via_edit_text(message, events, chat_id)
    except TelegramRetryAfter as e:
        log.warning("draft flood on init, falling back to edit_text: retry_after=%s", e.retry_after)
        return await _stream_via_edit_text(message, events, chat_id)

    async for event in events:
        etype = event.get("type")
        if etype == "error":
            await message.answer(
                event.get("message", "Что-то пошло не так. Попробуйте ещё раз."),
            )
            return ""
        if etype == "token":
            buffer += event.get("delta", "")
            if not buffer.strip():
                continue
            now = monotonic()
            if now - last_draft_at < DRAFT_MIN_INTERVAL_SEC:
                continue   # тротлим — финальный send_message покажет полный текст
            try:
                # Draft тоже ограничен лимитом Telegram — шлём хвост буфера.
                draft_text = buffer if len(buffer) <= TG_MAX_MESSAGE_LEN else buffer[-TG_MAX_MESSAGE_LEN:]
                await message.bot.send_message_draft(
                    chat_id=message.chat.id,
                    draft_id=draft_id,
                    text=draft_text,
                )
                last_draft_at = now
            except TelegramRetryAfter as e:
                # Telegram сам сказал «подожди N сек» — пропускаем draft'ы
                # на это окно. Финальный send_message всё равно отрисует ответ.
                last_draft_at = now + e.retry_after
            except TelegramBadRequest:
                # draft expired / message_not_modified — игнорируем,
                # доберём финальным send_message.
                pass
        elif etype == "message_saved":
            assistant_message_id = event.get("message_id")
        elif etype == "sources":
            sources = event.get("sources", [])

    if buffer:
        reply_markup = (
            feedback_kb(assistant_message_id) if assistant_message_id else None
        )
        await _send_final(message, buffer + _format_sources_footer(sources), reply_markup)
    return buffer


async def _send_final(message: Message, text: str, reply_markup) -> None:
    """Шлёт финальный ответ; длинные документы режет на несколько сообщений.

    Telegram лимит — 4096 символов. Документация фичи часто длиннее.
    Feedback-клавиатура вешается только на последнее сообщение.
    """
    chunks = _chunk_text(text, TG_SAFE_CHUNK_LEN)
    if not chunks:
        return
    total = len(chunks)
    for index, chunk in enumerate(chunks):
        markup = reply_markup if index == total - 1 else None
        suffix = f"\n\n({index + 1}/{total})" if total > 1 else ""
        await _send_one_chunk(message, chunk + suffix, markup)


async def _send_plain(message: Message, text: str, reply_markup) -> None:
    """Plain-текст без parse_mode.

    У бота DefaultBotProperties(parse_mode=HTML) — если не сбросить явно,
    Telegram пытается парсить `<include …>` / PlantUML / XML из документации
    и падает с «Unsupported start tag».
    """
    await message.bot.send_message(
        chat_id=message.chat.id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=None,
    )


async def _send_one_chunk(message: Message, text: str, reply_markup) -> None:
    """Один кусок: MarkdownV2, при ошибке/длине — plain (при необходимости ещё режем)."""
    md = _to_tg_markdown(text)
    if len(md) <= TG_MAX_MESSAGE_LEN:
        try:
            await message.bot.send_message(
                chat_id=message.chat.id,
                text=md,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return
        except TelegramBadRequest as e:
            log.warning("MarkdownV2 parse failed, fallback to plain: %s", e)
    else:
        log.warning(
            "MarkdownV2 too long after escape (%s chars), fallback to plain",
            len(md),
        )

    plain_chunks = _chunk_text(text, TG_MAX_MESSAGE_LEN)
    for index, part in enumerate(plain_chunks):
        markup = reply_markup if index == len(plain_chunks) - 1 else None
        try:
            await _send_plain(message, part, markup)
        except TelegramBadRequest as e:
            log.error("plain send failed even after chunking: %s", e)
            # На крайний случай вычищаем угловые скобки (псевдо-HTML/XML в доках).
            safe = (
                part[: TG_MAX_MESSAGE_LEN - 40]
                .replace("<", "‹")
                .replace(">", "›")
                + "\n…(обрезано)"
            )
            try:
                await _send_plain(message, safe, markup)
            except TelegramBadRequest as e2:
                log.error("sanitized plain send also failed: %s", e2)
            break


async def _stream_via_edit_text(
    message: Message,
    events: AsyncIterable[dict],
    chat_id: UUID | None = None,
) -> str:
    """Fallback: edit_text-тротлинг 1 сек/кадр + finalize с feedback-кнопками."""
    sent = await message.answer("…")
    buffer = ""
    assistant_message_id: str | None = None
    sources: list[dict] = []
    last_edit = monotonic()

    async for event in events:
        etype = event.get("type")
        if etype == "error":
            await message.answer(
                event.get("message", "Что-то пошло не так. Попробуйте ещё раз."),
            )
            return ""
        if etype == "token":
            buffer += event.get("delta", "")
            if monotonic() - last_edit >= 1.0:
                try:
                    await sent.edit_text(buffer)
                    last_edit = monotonic()
                except TelegramRetryAfter as e:
                    last_edit = monotonic() + e.retry_after
                except TelegramBadRequest:
                    last_edit = monotonic()
        elif etype == "message_saved":
            assistant_message_id = event.get("message_id")
        elif etype == "sources":
            sources = event.get("sources", [])

    if buffer:
        reply_markup = (
            feedback_kb(assistant_message_id) if assistant_message_id else None
        )
        full = buffer + _format_sources_footer(sources)
        chunks = _chunk_text(full, TG_SAFE_CHUNK_LEN)
        first = chunks[0] if chunks else full
        md = _to_tg_markdown(first)
        try:
            if len(md) <= TG_MAX_MESSAGE_LEN:
                await sent.edit_text(
                    md,
                    reply_markup=reply_markup if len(chunks) <= 1 else None,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            else:
                await sent.edit_text(
                    first[:TG_MAX_MESSAGE_LEN],
                    reply_markup=reply_markup if len(chunks) <= 1 else None,
                    parse_mode=None,
                )
        except TelegramBadRequest:
            try:
                await sent.edit_text(
                    first[:TG_MAX_MESSAGE_LEN],
                    reply_markup=reply_markup if len(chunks) <= 1 else None,
                    parse_mode=None,
                )
            except (TelegramBadRequest, TelegramRetryAfter):
                pass
        except TelegramRetryAfter:
            pass
        # Остаток длинного ответа — отдельными сообщениями.
        if len(chunks) > 1:
            for index, chunk in enumerate(chunks[1:], start=2):
                markup = reply_markup if index == len(chunks) else None
                await _send_one_chunk(
                    message,
                    chunk + f"\n\n({index}/{len(chunks)})",
                    markup,
                )
    return buffer
