"""Lexical search_kb: FE-композит и окно обрезки по теме запроса."""

from __future__ import annotations

from pathlib import Path

from app.tools.search_kb.handler import (
    SearchKbHandler,
    _clip_contract_window,
    _query_wants_detail_card,
    _query_wants_feed_screen,
    _query_wants_frontend_composite,
    _source_is_be_operations_blob,
    _source_is_frontend_composite,
    _tokenize,
)


def test_clip_prefers_tax_over_first_json() -> None:
    buy = (
        '```json\n{"type": "transaction_buy", "deals": [{"id": "1"}]}\n```\n'
    )
    # Много «шума» до налога, как в огромном FE-файле.
    padding = ("прочая операция funds_input\n" * 400) + buy * 3
    tax = (
        "\nНалоги\n"
        "Списание налога при выводе\n"
        'Данный вид операций имеет тип (operationType) tax\n'
        '```json\n{"operationType": "tax", "title": {"text": "Удержание налога"}}\n```\n'
    )
    text = padding + tax
    clipped = _clip_contract_window(
        text,
        query="пример ответа деталка по налогам на фронт композит",
        limit=3_000,
    )
    assert "tax" in clipped.lower()
    assert "удержание налога" in clipped.lower() or "списание налога" in clipped.lower()
    assert "transaction_buy" not in clipped


def test_frontend_composite_path_helpers() -> None:
    fe = "SIHIST/SIHIST_markdown_front/Фронт Композит/Композит_деталка_(FE).md"
    be = "SIHIST/SIHIST_markdown_back/[SIHIST-1740]_веб_СБОЛ_get_all.md"
    assert _source_is_frontend_composite(fe)
    assert not _source_is_frontend_composite(be)
    assert _query_wants_frontend_composite("деталка композит налог на фронт")
    assert _source_is_be_operations_blob(
        be,
        "operation/v2/get_all параметры ответа\n" + ("x" * 13_000) + "transaction_buy",
    )


def test_score_boosts_fe_detail_over_be_get_all(tmp_path: Path) -> None:
    fe_dir = tmp_path / "SIHIST" / "SIHIST_markdown_front" / "Фронт Композит"
    fe_dir.mkdir(parents=True)
    be_dir = tmp_path / "SIHIST" / "SIHIST_markdown_back"
    be_dir.mkdir(parents=True)

    (fe_dir / "Композит_деталка_(FE).md").write_text(
        "# FE\n\n## Описание\n\n"
        "Налоги\noperationType tax\n"
        '```json\n{"operationType": "tax"}\n```\n',
        encoding="utf-8",
    )
    (be_dir / "SIHIST-1740_get_all.md").write_text(
        "# BE\n\n## Параметры ответа operation/v2/get_all\n\n"
        + ("| field | type |\n| --- | --- |\n" * 200)
        + '```json\n{"type": "transaction_buy", "deals": []}\n```\n',
        encoding="utf-8",
    )

    kb = SearchKbHandler(docs_dir=tmp_path)
    query = "пример композитного ответа на фронт деталка по налогам"
    q_tokens = _tokenize(query)
    scored = [
        (
            SearchKbHandler._score_chunk(
                ch, q_tokens, [], True, query=query
            ),
            ch.source,
        )
        for ch in kb._chunks
    ]
    scored.sort(reverse=True)
    assert scored
    assert "Композит_деталка_(FE)" in scored[0][1]
    assert scored[0][0] > scored[-1][0]


def test_search_kb_returns_tax_from_fe_file(tmp_path: Path) -> None:
    fe_dir = tmp_path / "SIHIST" / "SIHIST_markdown_front" / "Фронт Композит"
    fe_dir.mkdir(parents=True)
    be_dir = tmp_path / "SIHIST" / "SIHIST_markdown_back"
    be_dir.mkdir(parents=True)

    noise = '```json\n{"type": "transaction_buy", "deals": [1]}\n```\n' + (
        "funds_input пример\n" * 500
    )
    tax = (
        "Налоги\nСписание налога\n"
        'тип (operationType) tax\n'
        '```json\n{"operationType": "tax", "instrumentName": "Списание налога"}\n```\n'
    )
    (fe_dir / "Композит_деталка_(FE).md").write_text(
        "# FE\n\n## Описание выполняемых доработок:\n\n" + noise + tax,
        encoding="utf-8",
    )
    (be_dir / "get_all_ops.md").write_text(
        "# BE\n\n## Параметры ответа\n\n"
        "operation/v2/get_all\n"
        + ("| a | b |\n" * 300)
        + '```json\n{"type": "transaction_buy"}\n```\n',
        encoding="utf-8",
    )

    kb = SearchKbHandler(docs_dir=tmp_path)
    hit = kb.search_kb(
        "пример ответа на фронт деталка композит по налогам JSON"
    )
    assert "tax" in hit.lower()
    assert "списание налога" in hit.lower()
    # Не должен утащить чужой пример как единственный смысл.
    assert hit.lower().index("tax") < hit.lower().rfind("transaction_buy") or (
        "transaction_buy" not in hit
    )


def test_detail_vs_feed_and_nfr_ranking(tmp_path: Path) -> None:
    fe = tmp_path / "SIHIST" / "SIHIST_markdown_front" / "Фронт Композит"
    fe.mkdir(parents=True)

    (fe / "Композит_деталка_(FE).md").write_text(
        "# FE detail\n\n"
        "## Нефункциональные требования » Требования к сопровождению\n\n"
        "Логирование и мониторинг.\n\n"
        "## Функциональные требования » Описание выполняемых доработок:\n\n"
        "Налоги\n"
        '```json\n{"screenData": {"type": "operationDetails"}, '
        '"operationType": "tax"}\n```\n',
        encoding="utf-8",
    )
    (fe / "Композит_экран_ленты_(FE).md").write_text(
        "# FE feed\n\n## Функциональные требования » Описание выполняемых доработок:\n\n"
        "Налоги в ленте\n"
        '```json\n{"screenData": {"type": "operationsHistory"}, '
        '"type": "tax"}\n```\n',
        encoding="utf-8",
    )
    (fe / "Отмены_деталка_(FE).md").write_text(
        "# Cancel\n\n## Функциональные требования » Пример cancellationDetails\n\n"
        '```json\n{"action": "cancelOperation"}\n```\n',
        encoding="utf-8",
    )

    kb = SearchKbHandler(docs_dir=tmp_path)
    query = "Пример ответа для налога в карточке детальной информации (деталка)"
    assert _query_wants_detail_card(query)
    assert not _query_wants_feed_screen(query)

    hit = kb.search_kb(query)
    assert "operationDetails" in hit or "operationdetails" in hit.lower()
    assert "Композит_деталка_(FE)" in hit
    # Не отмены и не NFR-сопровождение как главный смысл.
    assert "cancelOperation" not in hit
    assert "сопровождению" not in hit.lower()

    feed_q = "пример ответа налог на ленте композит экран ленты"
    assert _query_wants_feed_screen(feed_q)
    feed_hit = kb.search_kb(feed_q)
    assert "operationsHistory" in feed_hit or "operationshistory" in feed_hit.lower()
    assert "Композит_экран_ленты_(FE)" in feed_hit

    # «Ленты» в названии папки ≠ запрос про экран ленты, если есть деталка.
    pathish = "Пример ответа для налога с деталкой из файла Композит, Экран, Ленты, ФЕ"
    assert _query_wants_detail_card(pathish)
    assert not _query_wants_feed_screen(pathish)
    path_hit = kb.search_kb(pathish)
    assert "Композит_деталка_(FE)" in path_hit
    assert "operationDetails" in path_hit or "operationdetails" in path_hit.lower()
    assert "operationsHistory" not in path_hit and "operationshistory" not in path_hit.lower()
