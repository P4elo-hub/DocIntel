---
name: integration-analysis
description: Analyzes and documents system integrations using source evidence. Use when describing REST, gRPC, GraphQL, SOAP, Kafka, RabbitMQ, synchronous or asynchronous integrations, API contracts, request/response mappings, retries, timeouts, and integration scenarios.
disable-model-invocation: true
---

# Integration Analysis

## Purpose

Use this skill when an agent must analyze or write documentation for integrations. The skill defines the workflow. The required output format is defined by the protocol specs, templates, canonical examples and quality gates in this kit.

This skill is not a substitute for evidence. Do not invent runtime URLs, SLA, timeout, retry, fallback, delivery guarantee, auth rules, field mappings or error behavior.

## Required Files

Before writing an integration artifact, read the relevant files:

| Protocol | Spec | Template | Canonical example | Quality gate |
|---|---|---|---|---|
| General | `spec-kit/integration-page.schema.yaml` | `templates/integration-page.template.md` | protocol-specific example | `quality-gates/integration-review.yaml` |
| REST | `spec-kit/rest-api.schema.yaml` | `templates/rest-endpoint.template.md` | `examples/rest-integration-example.md` | `quality-gates/rest-review.yaml` |
| gRPC | `spec-kit/grpc-service.schema.yaml` | `templates/grpc-service.template.md` | `examples/grpc-service-example.md` | `quality-gates/grpc-review.yaml` |
| GraphQL | `spec-kit/graphql-operation.schema.yaml` | `templates/graphql-operation.template.md` | `examples/graphql-operation-example.md` | `quality-gates/graphql-review.yaml` |
| SOAP | `spec-kit/soap-operation.schema.yaml` | `templates/soap-operation.template.md` | `examples/soap-operation-example.md` | `quality-gates/soap-review.yaml` |
| Async / event | `spec-kit/async-message.schema.yaml` | `templates/async-message.template.md` | `examples/async-message-example.md` | `quality-gates/async-review.yaml` |

## Instructions

1. Classify the integration.
   - Identify source system, target system, direction, type and protocol.
   - Choose exactly one protocol-specific spec/gate for the main artifact.
   - If several protocols are involved, split the artifact or add subsections with separate gates.

2. Collect evidence before writing.
   - REST: OpenAPI, controller, route config, SOWA/gateway config, request/response DTOs, tests.
   - gRPC: `.proto`, generated service/client, service implementation, metadata handling, tests.
   - GraphQL: SDL schema, resolver, query/mutation/subscription, variables schema, tests.
   - SOAP: WSDL, XSD, SOAPAction, client/server stubs, SOAP Fault handling, tests.
   - Async: topic/queue config, producer, consumer, schema registry, headers, retry/DLQ config, tests.

3. Ask clarification questions for critical gaps before writing the final artifact.
   - If the user's task is too short to identify the integration boundary, do not draft immediately.
   - First identify missing protocol, source system, target system, direction, operation/endpoint/topic name, request/response/event fields, requiredness, validation, examples, mapping and error behavior.
   - Ask focused questions only for gaps that affect the contract shape, integration boundary or reader-facing correctness.
   - Do not ask infrastructure or production policy questions unless the user needs a production-ready contract.
   - If the user explicitly asks for a quick draft, keep non-critical unknowns as gaps and do not invent values.
   - If multiple gaps exist, group questions by category: boundary, protocol contract, fields, mapping, errors and runtime behavior.

4. Use the canonical example as the target level of detail.
   - Match section order unless the project has a documented exception.
   - Match table granularity: general info, headers/metadata, parameters, response, errors, examples.
   - Include boundary cases where the canonical example includes them.
   - Use realistic example values, not placeholders like `"string"` or `"123"`.

5. Apply protocol-specific requirements.
   - REST: request/response headers, path/query parameters, enum tables, response body, error codes, empty collection behavior.
   - gRPC: request metadata, response/trailing metadata, proto definition, request/response params, enum tables, JSON Schema request/response, gRPC statuses.
   - GraphQL: headers, schema definition, arguments, response fields, Relay pagination for list queries, JSON Schema variables/response, GraphQL errors.
   - SOAP: HTTP headers and SOAP Header separately, WSDL/endpoint/namespace/SOAPAction, XSD schema, request/response params, SOAP Fault, empty collection behavior.
   - Async: general topic info, consumer info, Kafka headers, envelope, metadata, payload, conditional fields, enums, partition key, JSON/Avro schema, retry/DLQ.

6. Preserve evidence and uncertainty.
   - Every meaningful current-state claim must be traceable to analytics, code, contract, schema, config, migration, test or DB export.
   - If evidence is missing, record a gap in the working layer.
   - If sources conflict, record a conflict and do not silently choose a winner.
   - Permanent reader pages must not contain unresolved markers, raw traceability tables or internal claim IDs unless the project explicitly requires it.

7. Run quality gates.
   - Always run `quality-gates/integration-review.yaml`.
   - Then run the protocol-specific gate.
   - If any blocking check fails, do not mark the artifact as done.

## Clarification Triggers

Ask the user follow-up questions when any of these are unknown and the answer affects the integration artifact:

- Integration boundary: source system, target system, direction, producer, consumer.
- Protocol: REST, gRPC, GraphQL, SOAP, Kafka, RabbitMQ, file, batch or another transport.
- Operation identity: endpoint, method, RPC, query, mutation, SOAP operation, topic or event name.
- Contract shape: request fields, response fields, event envelope, payload, headers or metadata.
- Field semantics: type, requiredness, nullable behavior, default value, enum values, units, currency, precision or scale.
- Validation: format, min/max, pattern, allowed values, empty collection behavior or conditional requiredness.
- Mapping: source field, target field, transformation rule, defaulting rule, aggregation or filtering rule.
- Examples: realistic request, response, event payload, headers and error examples.
- Error behavior: protocol status, business error, validation error, technical error, retryable/non-retryable status.
- Async behavior: producer, consumer, partition key, ordering, idempotency, duplicate handling, DLQ or retry policy.
- Runtime behavior: timeout, retry, fallback, SLA, auth, rate limit or endpoint only when required for the requested artifact.

Prefer one compact grouped question block before drafting. Example:

```text
Нужно уточнить интеграционный контракт:

1. Boundary: какая система producer/source и какая consumer/target?
2. Contract: какие поля обязательные, nullable и какие есть примеры значений?
3. Mapping: из каких source fields формируются target fields?
4. Errors: какие ошибки возвращаются/публикуются при validation, business и technical failures?
5. Async: если это Kafka, какой event/topic, partition key и что делать при duplicate/timeout?
```

If the user cannot answer or asks to proceed, keep the remaining unknowns as explicit gaps. Do not turn gaps into confident claims.

## Output Discipline

For each integration artifact, produce or update:

1. Working-layer evidence pack or traceability entry.
2. Reader-facing integration page using the relevant template.
3. Review status based on general and protocol-specific quality gates.

Use Russian for reader-facing explanations by default. Keep protocol names, paths, class names, method names, fields, endpoints, source IDs and technical identifiers in their original spelling.

## Forbidden Without Evidence

- SLA, SLO, p95/p99, throughput, rate limit.
- Timeout, retry count, backoff, fallback.
- Delivery guarantee, retention, partition count, replication factor.
- Runtime endpoint, target URL, queue/topic name.
- Auth mechanism and required headers/metadata.
- Field-level mapping and validation.
- Error/status behavior.

If the canonical example contains such fields but the project evidence does not, do not invent them. Keep the section narrower and record the gap in the working layer.
