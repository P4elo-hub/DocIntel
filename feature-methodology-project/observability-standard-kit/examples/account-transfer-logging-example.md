#### Логирование — Переводы между счетами

### Общие требования к логированию

#### Уровни логирования

| Уровень | Когда использовать | Обязательные поля |
|---------|-------------------|-------------------|
| ERROR | Критические ошибки, сбои интеграции | timestamp, level, message, stackTrace, correlationId, service |
| WARN | Потенциальные проблемы, retry, деградация | timestamp, level, message, correlationId |
| INFO | Бизнес-события, интеграционные вызовы | timestamp, level, message, operation, userId, eventType |
| DEBUG | Отладка (только на dev/staging) | timestamp, level, message, context |

#### Таблица событий для логирования

| Журнал | Уровень | Логируемые параметры | Правила инициализации события |
|--------|---------|---------------------|-------------------------------|
| Интеграционный журнал | INFO | `eventType` = CREATE_TRANSFER / SEND_TRANSFER_RESULT<br>`callType` = IN<br>`exSystem` = API-Gateway | При запросе / ответе создания перевода |
| Интеграционный журнал | INFO | `eventType` = CHECK_AML / SEND_AML_RESULT<br>`callType` = OUT<br>`exSystem` = Compliance | При запросе / ответе AML-проверки |
| Интеграционный журнал | INFO | `eventType` = DEBIT_ACCOUNT / CREDIT_ACCOUNT<br>`callType` = OUT<br>`exSystem` = Account Service | При списании / зачислении средств |
| Интеграционный журнал | INFO | `eventType` = CACHE_WRITE_TRANSFER / CACHE_READ_TRANSFER<br>`callType` = OUT<br>`exSystem` = Redis | При записи / чтении кэша перевода |
| Интеграционный журнал | INFO | `eventType` = PUBLISH_TRANSFER_EVENT<br>`callType` = OUT<br>`exSystem` = Kafka | При публикации события перевода в Kafka |
| Системный журнал | ERROR | Превышено время выполнения транзакции (Global Timeout) | |
| Системный журнал | ERROR | Ошибка компенсации (rollback failed) | |
| Системный журнал | WARN | AML-проверка: Circuit Breaker OPEN | |

#### Структура полей лога (автоматические)

| Атрибут | Описание | Обязательность | Пример | Источник |
|---------|----------|----------------|--------|----------|
| `@timestamp` | Дата-время возникновения события | Да | 2026-02-04T11:56:08.949000Z | Фреймворк |
| `callid` | ID трассировки запроса | Да | B870E7E2-83E8-4BBB-B84C-5C47B2B1FCE3 | Генерируется при входящем запросе |
| `requestId` | ID конкретного запроса/ответа | Да (для ответов) | c7bf5745-e9ab-4e77-8003-dc67d7ac1a84 | Из тела запроса |
| `sessionId` | Клиентская сессия | Да | 91b8d75d42be78c6b0891aafc15eff10 | Из входящего запроса |
| `ucpid` | ID клиента в ЕПК | Да | 1129388786934915284 | Из входящего запроса |
| `service` | Имя сервиса | Да | account-transfer-service | Конфигурация |
| `system` | Код автоматизированной системы | Да | SI | Конфигурация |
| `version` | Версия дистрибутива | Нет | 01.080.00 | Конфигурация |
| `environment` | Среда | Да | prom | Конфигурация |
| `stand` | Стенд | Нет | prom | Конфигурация |
| `datacenter` | ЦОД | Нет | a-tsod | Конфигурация |
| `cluster` | Кластер | Нет | dropApp | Конфигурация |
| `namespace` | K8s namespace | Нет | ci02128305-prom-retail2-b1-atsod | K8s metadata |
| `host` | Hostname | Нет | pvsss-kub002738.sigma.sbrf.ru | K8s metadata |
| `pod` | Имя pod'а | Нет | transfer-svc-bb8455cc4-vjmq5 | K8s metadata |
| `ip` | IP-адрес | Нет | 29.64.18.169 | K8s metadata |
| `block` | Блок | Нет | block-1 | Конфигурация |
| `distrib` | Дистрибутив | Нет | d-01.080.00_5 | Конфигурация |
| `client_name` | Имя клиентского приложения | Нет | sisupp-transfer-svc-k2 | Конфигурация |

#### Структура полей лога (прикладные)

| Атрибут | Описание | Обязательность | Пример | Источник |
|---------|----------|----------------|--------|----------|
| `eventType` | Код события | Да | CREATE_TRANSFER | Код сервиса |
| `callType` | Тип вызова (IN / OUT) | Да | OUT | Код сервиса |
| `exSystem` | Внешняя система | Да | Compliance | Код сервиса |
| `duration` | Время обработки (мс) | Нет | 390 | Код сервиса |
| `kind` | Тип лога | Нет | integration | Код сервиса |
| `level` | Уровень логирования | Да | INFO | Код сервиса |
| `logger` | Имя логгера | Нет | IntegrationLogger | Код сервиса |
| `message` | Описание | Да | Integration log entry | Код сервиса |
| `rqStr` | Тело запроса AS IS | Да (для вызовов) | `{"accountFrom":"...", ...}` | Из тела запроса |
| `rsStr` | Тело ответа AS IS | Да (для ответов) | `{"transferId":"...", ...}` | Из тела ответа |
