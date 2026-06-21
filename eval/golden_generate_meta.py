"""Метаданные methodology (template/spec/gate) для golden_dataset_generate.json."""

from __future__ import annotations

ITEM_METHODOLOGY: dict[str, dict] = {
    "gen_async_001": {
        "shablon_section": "4.1.2",
        "template_ref": "integration-standard-kit/templates/async-message.template.md",
        "spec_ref": "integration-standard-kit/spec-kit/async-message.schema.yaml",
        "gate_ref": "integration-standard-kit/quality-gates/async-review.yaml",
        "gate_blocking_ids": [
            "ASYNC-GATE-001",
            "ASYNC-GATE-002",
            "ASYNC-GATE-003",
            "ASYNC-GATE-011",
            "ASYNC-GATE-012",
        ],
    },
    "gen_rest_001": {
        "shablon_section": "4.1.1",
        "template_ref": "integration-standard-kit/templates/rest-endpoint.template.md",
        "spec_ref": "integration-standard-kit/spec-kit/rest-api.schema.yaml",
        "gate_ref": "integration-standard-kit/quality-gates/rest-review.yaml",
        "gate_blocking_ids": [
            "REST-GATE-001",
            "REST-GATE-002",
            "REST-GATE-003",
            "REST-GATE-008",
            "REST-GATE-009",
        ],
    },
    "gen_grpc_001": {
        "shablon_section": "4.1.1",
        "template_ref": "integration-standard-kit/templates/grpc-service.template.md",
        "spec_ref": "integration-standard-kit/spec-kit/grpc-service.schema.yaml",
        "gate_ref": "integration-standard-kit/quality-gates/grpc-review.yaml",
        "gate_blocking_ids": ["GRPC-GATE-001", "GRPC-GATE-002", "GRPC-GATE-005"],
    },
    "gen_graphql_001": {
        "shablon_section": "4.1.1",
        "template_ref": "integration-standard-kit/templates/graphql-operation.template.md",
        "spec_ref": "integration-standard-kit/spec-kit/graphql-operation.schema.yaml",
        "gate_ref": "integration-standard-kit/quality-gates/graphql-review.yaml",
        "gate_blocking_ids": ["GQL-GATE-001", "GQL-GATE-002", "GQL-GATE-003"],
    },
    "gen_soap_001": {
        "shablon_section": "4.1.1",
        "template_ref": "integration-standard-kit/templates/soap-operation.template.md",
        "spec_ref": "integration-standard-kit/spec-kit/soap-operation.schema.yaml",
        "gate_ref": "integration-standard-kit/quality-gates/soap-review.yaml",
        "gate_blocking_ids": ["SOAP-GATE-001", "SOAP-GATE-002", "SOAP-GATE-003"],
    },
    "gen_uc_001": {
        "shablon_section": "1.2-usecase,1.3-usecase",
        "template_ref": "use-case-standard-kit/templates/use-case.template.md",
        "spec_ref": "use-case-standard-kit/spec-kit/use-case.schema.yaml",
        "gate_ref": "use-case-standard-kit/quality-gates/use-case-review.yaml",
        "gate_blocking_ids": [
            "UC-GATE-002",
            "UC-GATE-006",
            "UC-GATE-012",
            "UC-GATE-014",
            "UC-GATE-008",
        ],
    },
    "gen_req_001": {
        "shablon_section": "1.1,2",
        "template_ref": "requirements-standard-kit/templates/requirements-analysis.template.md",
        "spec_ref": "requirements-standard-kit/spec-kit/requirements-analysis.schema.yaml",
        "gate_ref": "requirements-standard-kit/quality-gates/requirements-review.yaml",
        "gate_blocking_ids": [
            "REQ-GATE-002",
            "REQ-GATE-005",
            "REQ-GATE-006",
            "REQ-GATE-007",
        ],
    },
    "gen_data_001": {
        "shablon_section": "4.2.3",
        "template_ref": "data-standard-kit/templates/data-model.template.md",
        "spec_ref": "data-standard-kit/spec-kit/data-model.schema.yaml",
        "gate_ref": "data-standard-kit/quality-gates/data-model-review.yaml",
        "gate_blocking_ids": [
            "DM-GATE-002",
            "DM-GATE-004",
            "DM-GATE-005",
        ],
    },
    "gen_nfr_perf_001": {
        "shablon_section": "5.2-performance",
        "template_ref": "nfr-standard-kit/templates/performance.template.md",
        "spec_ref": "nfr-standard-kit/spec-kit/performance.schema.yaml",
        "gate_ref": "nfr-standard-kit/quality-gates/performance-review.yaml",
        "gate_blocking_ids": [
            "PERF-GATE-002",
            "PERF-GATE-003",
            "PERF-GATE-007",
        ],
    },
    "gen_nfr_rel_001": {
        "shablon_section": "5.2-reliability",
        "template_ref": "nfr-standard-kit/templates/reliability.template.md",
        "spec_ref": "nfr-standard-kit/spec-kit/reliability.schema.yaml",
        "gate_ref": "nfr-standard-kit/quality-gates/reliability-review.yaml",
        "gate_blocking_ids": ["REL-GATE-001", "REL-GATE-002"],
    },
    "gen_nfr_config_001": {
        "shablon_section": "5.4",
        "template_ref": "nfr-standard-kit/templates/configuration.template.md",
        "spec_ref": "nfr-standard-kit/spec-kit/configuration.schema.yaml",
        "gate_ref": "nfr-standard-kit/quality-gates/configuration-review.yaml",
        "gate_blocking_ids": ["CONF-GATE-001", "CONF-GATE-002"],
    },
    "gen_nfr_toggles_001": {
        "shablon_section": "5.5",
        "template_ref": "nfr-standard-kit/templates/feature-toggles.template.md",
        "spec_ref": "nfr-standard-kit/spec-kit/feature-toggles.schema.yaml",
        "gate_ref": "nfr-standard-kit/quality-gates/feature-toggles-review.yaml",
        "gate_blocking_ids": ["TOGL-GATE-001", "TOGL-GATE-002"],
    },
    "gen_obs_log_001": {
        "shablon_section": "5.3.1",
        "template_ref": "observability-standard-kit/templates/logging.template.md",
        "spec_ref": "observability-standard-kit/spec-kit/logging.schema.yaml",
        "gate_ref": "observability-standard-kit/quality-gates/logging-review.yaml",
        "gate_blocking_ids": [
            "LOG-GATE-001",
            "LOG-GATE-002",
            "LOG-GATE-005",
        ],
    },
    "gen_obs_metrics_001": {
        "shablon_section": "5.3.2",
        "template_ref": "observability-standard-kit/templates/metrics.template.md",
        "spec_ref": "observability-standard-kit/spec-kit/metrics.schema.yaml",
        "gate_ref": "observability-standard-kit/quality-gates/metrics-review.yaml",
        "gate_blocking_ids": [
            "METR-GATE-001",
            "METR-GATE-002",
            "METR-GATE-005",
        ],
    },
    "gen_full_kafka_001": {
        "shablon_section": "1.1,1.2-usecase,1.3-usecase,2,4.1.2,5.3.1,5.3.2",
        "template_ref": "integration-standard-kit/templates/async-message.template.md",
        "spec_ref": "integration-standard-kit/spec-kit/async-message.schema.yaml",
        "gate_ref": "integration-standard-kit/quality-gates/async-review.yaml",
        "quality_gates": [
            {
                "gate_ref": "integration-standard-kit/quality-gates/async-review.yaml",
                "blocking_ids": ["ASYNC-GATE-001", "ASYNC-GATE-003", "ASYNC-GATE-012"],
            },
            {
                "gate_ref": "observability-standard-kit/quality-gates/logging-review.yaml",
                "blocking_ids": ["LOG-GATE-002", "LOG-GATE-005"],
            },
            {
                "gate_ref": "observability-standard-kit/quality-gates/metrics-review.yaml",
                "blocking_ids": ["METR-GATE-001", "METR-GATE-002"],
            },
        ],
    },
}

NEW_FOCUS_ITEMS: list[dict] = [
    {
        "id": "gen_gate_async_focus",
        "feature_brief": (
            "Событие PaymentCompleted в Kafka topic payments.completed. "
            "Consumer groups Order/Notification, DLQ, Schema Registry BACKWARD."
        ),
        "feature_name": "PaymentCompleted Kafka (gate focus)",
        "protocol": "Async",
        "question": "Gate-focus: async-message по ASYNC-GATE blocking checks",
        "expected_answer": (
            "Документ 4.1.2 проходит async-review: topic, headers, consumer/DLQ, envelope, пример события."
        ),
        "expected_keywords": [
            "payments.completed",
            "X-Message-Id",
            "consumer group",
            "DLQ",
            "metadata",
            "payload",
        ],
        "must_not_contain": ["Пакет методологии", "# INTERNAL", "> **Kit"],
        "methodology_ref": "integration-standard-kit/examples/async-message-example.md",
        "kit": "integration-standard-kit",
        "tool": "write_integration",
        "category": "code_gen",
        "difficulty": "hard",
        "source": "methodology_gate",
        "shablon_section": "4.1.2",
        "template_ref": "integration-standard-kit/templates/async-message.template.md",
        "spec_ref": "integration-standard-kit/spec-kit/async-message.schema.yaml",
        "gate_ref": "integration-standard-kit/quality-gates/async-review.yaml",
        "gate_blocking_ids": [
            "ASYNC-GATE-001",
            "ASYNC-GATE-002",
            "ASYNC-GATE-003",
            "ASYNC-GATE-004",
            "ASYNC-GATE-011",
            "ASYNC-GATE-012",
        ],
    },
    {
        "id": "gen_gate_metrics_focus",
        "feature_brief": (
            "Метрики Prometheus для переводов между счетами: latency histogram, "
            "error counters, business KPI, consumer lag Kafka."
        ),
        "feature_name": "Metrics gate focus — переводы",
        "question": "Gate-focus: metrics по METR-GATE blocking checks",
        "expected_answer": (
            "Раздел 5.3.2 с technical/error/business metrics, labels, GAP-OBS/status."
        ),
        "expected_keywords": [
            "5.3.2",
            "Prometheus",
            "histogram",
            "error",
            "business",
            "GAP-OBS",
        ],
        "must_not_contain": ["Пакет методологии"],
        "methodology_ref": "observability-standard-kit/examples/account-transfer-metrics-example.md",
        "kit": "observability-standard-kit",
        "tool": "write_observability",
        "category": "code_gen",
        "difficulty": "hard",
        "source": "methodology_gate",
        "shablon_section": "5.3.2",
        "template_ref": "observability-standard-kit/templates/metrics.template.md",
        "spec_ref": "observability-standard-kit/spec-kit/metrics.schema.yaml",
        "gate_ref": "observability-standard-kit/quality-gates/metrics-review.yaml",
        "gate_blocking_ids": [
            "METR-GATE-001",
            "METR-GATE-002",
            "METR-GATE-003",
            "METR-GATE-005",
        ],
    },
    {
        "id": "gen_gate_uc_focus",
        "feature_brief": (
            "Use Case: оформить перевод между счетами в мобильном банке. "
            "BR-01…BR-06, альтернативы 3a/3b/3c, ЕСЛИ/ТО/ИНАЧЕ."
        ),
        "feature_name": "Use Case gate focus — перевод между счетами",
        "question": "Gate-focus: use case по UC-GATE blocking checks",
        "expected_answer": (
            "Use Case с предусловиями, BR-id, main scenario ЕСЛИ/ТО/ИНАЧЕ, альтернативы с возвратом."
        ),
        "expected_keywords": [
            "Use Case",
            "BR-01",
            "ЕСЛИ",
            "ИНАЧЕ",
            "альтернатив",
            "Предуслов",
        ],
        "must_not_contain": ["Пакет методологии", "СТД-", "TODO"],
        "methodology_ref": "use-case-standard-kit/examples/transfer-between-accounts-use-case-example.md",
        "kit": "use-case-standard-kit",
        "tool": "write_use_case_to_be",
        "category": "code_gen",
        "difficulty": "hard",
        "source": "methodology_gate",
        "shablon_section": "1.2-usecase,1.3-usecase",
        "template_ref": "use-case-standard-kit/templates/use-case.template.md",
        "spec_ref": "use-case-standard-kit/spec-kit/use-case.schema.yaml",
        "gate_ref": "use-case-standard-kit/quality-gates/use-case-review.yaml",
        "gate_blocking_ids": [
            "UC-GATE-002",
            "UC-GATE-008",
            "UC-GATE-012",
            "UC-GATE-014",
            "UC-GATE-017",
            "UC-GATE-019",
        ],
    },
]
