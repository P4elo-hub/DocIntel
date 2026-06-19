"""Политики GAP / DESIGN по kit-tool — как в standard kits."""

from __future__ import annotations

_GAP_COMMON = [
    "Правило evidence-first: в brief **нет** факта → не выдумывай; пометь поле маркером GAP/DESIGN по kit.",
    "Запрещено: «требует уточнения», «не указано», «TBD», голый `GAP-*` без номера — только `GAP-<KIT>-NNN`.",
    "Каждый маркер GAP/DESIGN в теле **обязан** иметь строку в таблице **Gaps и допущения** (или «Gaps не выявлены», если их нет).",
    "Если значение **спроектировано** без подтверждения пользователя — `DESIGN-<KIT>-NNN` + строка в Gaps (тип Design/Assumption).",
    "Цифры (%, RPS, p85, timeout, retention), ссылки Jira, имена eventType/метрик без evidence → GAP или DESIGN, не «уверенный» текст.",
]

_TOOL_GAP_POLICIES: dict[str, list[str]] = {
    "write_requirements": [
        "Kit: **requirements-standard-kit** | префикс: `GAP-REQ-001`, `GAP-REQ-002`, …",
        "Применяй GAP в: SMART (особенно Measurable/Time-bound), Jira/источник, стейкхолдеры, метрики цели, CN/ограничения.",
        "В конце `### 1.1` и/или `## 2` — таблица **Gaps и допущения** по шаблону kit (колонки: ID, Тип, Где, Что не хватает, Как закрыть).",
    ],
    "write_use_case_as_is": [
        "Kit: **use-case-standard-kit** | для неизвестных шагов/правил: `GAP-UC-001` (или `GAP-REQ-NNN`, если gap в бизнес-правиле).",
        "Не выдумывай акторов, таймауты, коды ошибок, лимиты — помечай GAP в шаге сценария или в таблице Use Case.",
        "Если альтернативный сценарий не следует из brief — опиши минимально и добавь GAP на детали ветвления.",
    ],
    "write_use_case_to_be": [
        "Kit: **use-case-standard-kit** | `GAP-UC-001`, … для неизвестных TO BE деталей.",
        "Таблица «Изменения относительно AS IS»: неизвестный тип изменения → GAP в ячейке.",
        "Kafka/outbox/retry: только то, что в brief; остальное — GAP в шагах или Gaps и допущения.",
    ],
    "write_integration": [
        "Kit: **integration-standard-kit** | префикс: `GAP-INT-001`, …",
        "Поля контракта без evidence (auth, rate limit, timeout, retry, версия API, optional headers) → `GAP-INT-NNN` в таблице.",
        "Поля события в brief заданы явно — заполни; остальные атрибуты схемы → GAP-INT, не placeholder «…».",
        "В конце раздела 4.x — **Gaps и допущения** для всех GAP-INT из таблиц.",
    ],
    "write_data_model": [
        "Kit: **data-standard-kit** | префикс: `GAP-DATA-001`, `DESIGN-DATA-001`, …",
        "Не invent сущности/колонки без evidence; пустые attribute tables → GAP-DATA в СУБД/полях.",
        "Обязательна таблица **Gaps и допущения** из template.",
    ],
    "write_nfr": [
        "Kit: **nfr-standard-kit** | префикс: `GAP-NFR-001`, `DESIGN-NFR-001`, `ASM-NFR-001`.",
        "p85, RPS, CCU, breaker, SLO, toggle-зависимости без evidence → GAP-NFR или DESIGN-NFR (колонка «Статус»).",
        "Каждый NFR-подраздел из скелета: таблица **Gaps и допущения** внизу подраздела.",
    ],
    "write_observability": [
        "Kit: **observability-standard-kit** | префикс: `GAP-OBS-001`, `DESIGN-OBS-001` (три цифры: 001, не 1).",
        "eventType, exSystem, labels метрик, пороги алёртов без evidence → GAP-OBS/DESIGN-OBS в ячейке и в **Gaps и допущения**.",
        "Колонка «Статус» в таблицах logging/metrics: `Подтверждено` / `GAP-OBS-NNN` / `DESIGN-OBS-NNN`.",
        "Отдельная таблица **Gaps и допущения** в 5.3.1 и 5.3.2 (или одна общая в конце блока 5.3).",
    ],
}


def gap_instructions_for_tool(tool_name: str) -> list[str]:
    """Общие + kit-specific инструкции по GAP для section package и промптов."""
    specific = _TOOL_GAP_POLICIES.get(tool_name, [
        f"Префикс GAP для `{tool_name}`: помечай неизвестное явно; таблица Gaps и допущения обязательна.",
    ])
    return [*_GAP_COMMON, *specific]


def extract_gap_excerpt_from_skill(skill: str, *, max_chars: int = 1800) -> str:
    """Вырезка из SKILL.md: строки про GAP/DESIGN/evidence (для справки в пакете)."""
    if not skill or skill.startswith("[файл не найден"):
        return ""
    keywords = (
        "gap-",
        "gaps и допущ",
        "design-",
        "asm-",
        "не выдум",
        "неизвест",
        "evidence",
        "требует уточн",
        "mark missing",
        "gap policy",
    )
    picked: list[str] = []
    for line in skill.splitlines():
        lower = line.lower()
        if any(keyword in lower for keyword in keywords):
            picked.append(line)
    if not picked:
        return ""
    text = "\n".join(picked)
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}\n\n...[обрезано]"
