"""Загрузка shablon.md и standard kits для write_feature_doc."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_KIT_SECTION_RE = re.compile(r"<!--\s*kit-section\s+(.*?)-->", re.DOTALL)
_ATTR_RE = re.compile(r'(\w+)=["\']([^"\']*)["\']')
_CONTRACT_RE = re.compile(
    r"## Контракт выходного документа.*?\n\n(.*?)\n\n---",
    re.DOTALL,
)

_PROTOCOL_FILES: dict[str, dict[str, str]] = {
    "REST": {
        "template": "integration-standard-kit/templates/rest-endpoint.template.md",
        "spec": "integration-standard-kit/spec-kit/rest-api.schema.yaml",
        "example": "integration-standard-kit/examples/rest-integration-example.md",
        "gate": "integration-standard-kit/quality-gates/rest-review.yaml",
    },
    "gRPC": {
        "template": "integration-standard-kit/templates/grpc-service.template.md",
        "spec": "integration-standard-kit/spec-kit/grpc-service.schema.yaml",
        "example": "integration-standard-kit/examples/grpc-service-example.md",
        "gate": "integration-standard-kit/quality-gates/grpc-review.yaml",
    },
    "GraphQL": {
        "template": "integration-standard-kit/templates/graphql-operation.template.md",
        "spec": "integration-standard-kit/spec-kit/graphql-operation.schema.yaml",
        "example": "integration-standard-kit/examples/graphql-operation-example.md",
        "gate": "integration-standard-kit/quality-gates/graphql-review.yaml",
    },
    "SOAP": {
        "template": "integration-standard-kit/templates/soap-operation.template.md",
        "spec": "integration-standard-kit/spec-kit/soap-operation.schema.yaml",
        "example": "integration-standard-kit/examples/soap-operation-example.md",
        "gate": "integration-standard-kit/quality-gates/soap-review.yaml",
    },
    "Async": {
        "template": "integration-standard-kit/templates/async-message.template.md",
        "spec": "integration-standard-kit/spec-kit/async-message.schema.yaml",
        "example": "integration-standard-kit/examples/async-message-example.md",
        "gate": "integration-standard-kit/quality-gates/async-review.yaml",
    },
}

_SECTION_KEYWORDS: dict[str, list[str]] = {
    "1.1": ["цель", "бизнес", "smart", "стейкхолдер", "требован", "br"],
    "1.2-usecase": ["as is", "asis", "сейчас", "проблем", "синхрон", "было", "текущ"],
    "1.3-usecase": ["use case", "сценарий", "tobe", "to be", "процесс", "целев", "диаграмм", "uml"],
    "4.1.1": ["rest", "grpc", "graphql", "soap", "endpoint", "синхрон", "https"],
    "4.1.2": ["kafka", "событие", "async", "очередь", "topic", "rabbit", "асинхрон"],
    "4.2.2": ["алгоритм", "обработк", "операц"],
    "4.2.3": ["модель данных", "бд", "entity", "таблиц", "er", "миграц", "postgresql", "хранилищ"],
    "5.1": ["безопасност", "auth", "oauth", "rbac", "шифрован"],
    "5.2-performance": ["производительност", "latency", "rps", "p85", "нагрузк", "кэш"],
    "5.2-reliability": ["надежност", "slo", "sla", "degradation", "fallback"],
    "5.3.1": ["логирован", "logging", "журнал", "eventtype", "логи"],
    "5.3.2": ["метрик", "prometheus", "мониторинг"],
    "5.4": ["конфигурац", "config", "configmap", "параметр"],
    "5.5": ["toggle", "тогл", "feature flag", "раскатк"],
}

# Ядро полного документа: AS IS + TO BE всегда при full
_FULL_DOCUMENT_CORE = [
    "1.1",
    "1.2-usecase",
    "1.3-usecase",
    "2",
]

_SECTION_HEADINGS: dict[str, str] = {
    "1.1": "### 1.1. Цель",
    "1.2-usecase": "### 1.2. Процесс/Сервис AS IS",
    "1.3-usecase": "### 1.3. Процесс/Сервис TO BE",
    "1.3-diagram": "### 1.3. Диаграмма TO BE",
    "2": "## 2. Ограничения и допущения",
    "4.1.1": "#### 4.1.1. Сервис [Название сервиса]",
    "4.1.2": "#### 4.1.2. Асинхронное событие [EventName]",
    "4.2.2": "#### 4.2.2. Алгоритм обработки запроса [Название операции]",
    "4.2.3": "#### 4.2.3. Модель данных (при изменении БД)",
    "5.1": "### 5.1. Требования безопасности",
    "5.2-performance": "#### Время отклика / Пропускная способность",
    "5.2-reliability": "#### Надёжность",
    "5.3.1": "#### 5.3.1. Требования к логированию",
    "5.3.2": "#### 5.3.2. Требования к мониторингу",
    "5.4": "### 5.4. Требования к настройкам",
    "5.5": "#### Feature Toggles",
}


@dataclass
class KitSection:
    id: str
    attrs: dict[str, str] = field(default_factory=dict)
    skeleton: str = ""


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zа-яё0-9]+", text.lower()) if len(token) > 2}


def _parse_attrs(raw: str) -> dict[str, str]:
    return {key: value for key, value in _ATTR_RE.findall(raw)}


def _read_file(base: Path, relative: str, max_chars: int = 10_000) -> str:
    if not relative:
        return ""
    path = base / relative
    if not path.is_file():
        return f"[файл не найден: {relative}]"
    text = path.read_text(encoding="utf-8")
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}\n\n...[обрезано: {len(text)} символов всего]"


def _load_output_contract(shablon_path: Path) -> str:
    content = shablon_path.read_text(encoding="utf-8")
    match = _CONTRACT_RE.search(content)
    if match:
        return match.group(1).strip()
    return "Следуй структуре shablon.md: разделы 1.1, 1.2 AS IS, 1.3 TO BE, 2, 4.x, 5.x."


def _is_kit_metadata_line(line: str) -> bool:
    if not line.startswith("> "):
        return False
    markers = (
        "**Kit",
        "**Skill",
        "**Template",
        "**Spec",
        "**Example",
        "**Gate",
        "**Entrypoint",
        "**Kit skill",
        "**Покрывает стандарты",
        "**Источник стандарта",
        "**Заполнение",
    )
    return any(marker in line for marker in markers)


def _strip_kit_metadata(skeleton: str) -> str:
    """Убрать служебные blockquote-строки kits из скелета (не для финального документа)."""
    lines = [line for line in skeleton.splitlines() if not _is_kit_metadata_line(line)]
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines).strip()


_PAIRED_SECTIONS: dict[str, str] = {
    "1.2-usecase": "1.2-diagram",
    "1.3-usecase": "1.3-diagram",
}


def _merge_paired_sections(sections: dict[str, KitSection]) -> dict[str, KitSection]:
    """Если usecase-скелет пуст (два kit-section подряд в shablon), подтянуть тело из *-diagram."""
    for usecase_id, diagram_id in _PAIRED_SECTIONS.items():
        usecase = sections.get(usecase_id)
        diagram = sections.get(diagram_id)
        if usecase is None:
            continue
        if not usecase.skeleton.strip() and diagram and diagram.skeleton.strip():
            usecase.skeleton = diagram.skeleton
    return sections


def parse_shablon(shablon_path: Path) -> dict[str, KitSection]:
    content = shablon_path.read_text(encoding="utf-8")
    sections: dict[str, KitSection] = {}
    matches = list(_KIT_SECTION_RE.finditer(content))

    for index, match in enumerate(matches):
        attrs = _parse_attrs(match.group(1))
        section_id = attrs.get("id", f"section-{index}")
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        skeleton = content[start:end].strip()
        skeleton = _strip_kit_metadata(skeleton)
        sections[section_id] = KitSection(id=section_id, attrs=attrs, skeleton=skeleton)

    return _merge_paired_sections(sections)


def _section_sort_key(section_id: str) -> tuple[int, str]:
    base = section_id.split("-")[0]
    parts = base.split(".")
    numbers = [int(part) for part in parts if part.isdigit()]
    while len(numbers) < 4:
        numbers.append(0)
    return (*numbers[:4], section_id)


def _keyword_sections(brief: str) -> set[str]:
    tokens = _tokenize(brief)
    chosen: set[str] = set()
    for section_id, keywords in _SECTION_KEYWORDS.items():
        keyword_tokens: set[str] = set()
        for keyword in keywords:
            keyword_tokens |= _tokenize(keyword)
        if tokens & keyword_tokens:
            chosen.add(section_id)
    return chosen


def infer_sections(feature_brief: str, explicit: str | None = None) -> list[str]:
    if explicit and explicit.lower() != "full":
        return sorted(
            [part.strip() for part in explicit.split(",") if part.strip()],
            key=_section_sort_key,
        )

    chosen = set(_FULL_DOCUMENT_CORE)
    chosen |= _keyword_sections(feature_brief)

    # Миграция / доработка — AS IS обязателен
    migration_markers = _tokenize("сейчас синхронно было текущ перевести миграция as is")
    if _tokenize(feature_brief) & migration_markers:
        chosen.add("1.2-usecase")

    # Kafka/async — событие, не модель данных по умолчанию
    if "4.1.2" in chosen:
        chosen.discard("4.2.3")

    # Логи/метрики из brief
    observability = _tokenize("логирование логи метрики мониторинг producer consumer")
    if _tokenize(feature_brief) & observability:
        chosen.add("5.3.1")
        chosen.add("5.3.2")

    return sorted(chosen, key=_section_sort_key)


def _resolve_kit_paths(section: KitSection, protocol: str | None) -> dict[str, str]:
    attrs = section.attrs
    paths: dict[str, str] = {}

    for key in ("skill", "kit_skill", "template", "spec", "example", "gate"):
        if key in attrs:
            paths[key] = attrs[key]

    for key in ("page_template", "page_spec", "page_gate"):
        if key in attrs:
            paths[key.replace("page_", "")] = attrs[key]

    if section.id in {"4.1.1", "4.1.2"} and protocol:
        proto_key = protocol.strip().upper()
        if proto_key in ("KAFKA", "ASYNC", "EVENT"):
            proto_key = "Async"
        proto_files = _PROTOCOL_FILES.get(proto_key, {})
        paths.update(proto_files)

    if section.id == "4.1.2" and "template" not in paths:
        paths.update(_PROTOCOL_FILES["Async"])

    return paths


def load_kit_bundle(
    methodology_dir: Path,
    section: KitSection,
    protocol: str | None = None,
) -> dict[str, str]:
    paths = _resolve_kit_paths(section, protocol)
    bundle: dict[str, str] = {
        "section_id": section.id,
        "kit": section.attrs.get("kit", "none"),
        "heading": _SECTION_HEADINGS.get(section.id, f"## Раздел {section.id}"),
    }

    limits = {
        "skill": 5_000,
        "kit_skill": 5_000,
        "template": 8_000,
        "spec": 4_000,
        "example": 4_000,
        "gate": 3_000,
    }

    for role, relative in paths.items():
        bundle[role] = _read_file(methodology_dir, relative, limits.get(role, 5_000))

    bundle["skeleton"] = section.skeleton
    return bundle


def _build_document_skeleton(
    sections: dict[str, KitSection],
    target_sections: list[str],
    feature_name: str,
) -> str:
    lines = [f"# {feature_name}", ""]

    if any(sid.startswith("1.") for sid in target_sections):
        lines.append("## 1. Бизнес-требования")
        lines.append("")

    for sid in target_sections:
        heading = _SECTION_HEADINGS.get(sid, f"## Раздел {sid}")
        if sid == "2":
            lines.extend(["", heading, ""])
        elif sid.startswith("1."):
            lines.extend([heading, ""])
        elif sid.startswith("4."):
            if lines and lines[-1] != "## 4. Функциональные требования":
                lines.extend(["", "## 4. Функциональные требования", ""])
            lines.extend([heading, ""])
        elif sid.startswith("5."):
            if lines and lines[-1] != "## 5. Нефункциональные требования":
                lines.extend(["", "## 5. Нефункциональные требования", ""])
            lines.extend([heading, ""])

        section = sections.get(sid)
        if section and section.skeleton:
            lines.append(section.skeleton)
        lines.append("")

    return "\n".join(lines).strip()


def build_write_package(
    methodology_dir: Path,
    shablon_path: Path,
    feature_brief: str,
    section_id: str | None = None,
    protocol: str | None = None,
    feature_name: str | None = None,
) -> str:
    if not shablon_path.is_file():
        return "Ошибка: shablon.md не найден. Проверьте SUPPORT_METHODOLOGY_DIR."

    sections = parse_shablon(shablon_path)
    target_sections = infer_sections(feature_brief, section_id)
    name = feature_name or "Новая фича"
    contract = _load_output_contract(shablon_path)
    doc_skeleton = _build_document_skeleton(sections, target_sections, name)

    parts = [
        "# INTERNAL: пакет для ассистента (не отдавать пользователю как есть)",
        "",
        "## Описание от пользователя",
        feature_brief.strip(),
        "",
        f"## Разделы shablon для заполнения: {', '.join(target_sections)}",
        "",
        "## Контракт выходного документа",
        contract,
        "",
        "## Инструкция (обязательно)",
        "1. Верни **один** Markdown-документ фичи — заполни **Скелет итогового документа** ниже.",
        "2. Сохрани заголовки: `### 1.2. Процесс/Сервис AS IS`, `### 1.3. Процесс/Сервис TO BE` и др.",
        "3. **Запрещено** в ответе: «Пакет методологии», «Раздел X | kit», строки `> **Kit` / `> **Skill` / `> **Покрывает стандарты`, обёртка ```markdown.",
        "4. AS IS = как работает сейчас; TO BE = целевое после фичи.",
        "5. GAP-* для неизвестных полей; не выдумывай факты.",
        "6. **Язык финального документа — русский.** Английские skill/template — только справка; не включай их в ответ.",
        "7. **Use Case обязателен** в `### 1.2 AS IS` и `### 1.3 TO BE`: таблица Use Case, предусловия, постусловия, основной сценарий (нумерованные шаги), минимум 1 альтернативный сценарий. Нельзя заменять одним абзацем. Диаграмма plantuml — по желанию.",
        "",
        "## Скелет итогового документа (заполни и верни пользователю)",
        "",
        doc_skeleton,
        "",
        "## Справка по kits (для заполнения скелета)",
        "",
    ]

    for sid in target_sections:
        section = sections.get(sid)
        if section is None:
            continue

        bundle = load_kit_bundle(methodology_dir, section, protocol)
        parts.extend([
            f"### Справка: {sid} | kit `{bundle.get('kit', 'none')}`",
            "",
        ])
        if bundle.get("template"):
            parts.extend(["**Template:**", "```markdown", bundle["template"], "```", ""])
        if bundle.get("skill"):
            parts.extend(["**Skill (кратко):**", "```markdown", bundle["skill"][:3000], "```", ""])

    return "\n".join(parts)
