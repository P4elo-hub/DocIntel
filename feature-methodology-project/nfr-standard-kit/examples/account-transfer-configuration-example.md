#### NFR — Переводы между счетами (Конфигурация)

### Настройки и конфигурация

| Параметр | Тип | Уровень | Частота | Область | Хранение | По умолчанию | Описание | Валидация | Влияние при изменении | Процедура отката |
|----------|-----|---------|---------|---------|----------|-------------|----------|-----------|----------------------|------------------|
| `transfer.daily.limit` | integer | public | dynamic | global | ConfigMap | 500 000 | Дневной лимит переводов (₽) | min: 1 000, max: 10 000 000 | Изменение лимита для всех пользователей; снижение может заблокировать текущие переводы | Установить предыдущее значение в ConfigMap, применить через rollout restart |
| `transfer.single.max` | integer | public | dynamic | global | ConfigMap | 1 000 000 | Макс. сумма одного перевода (₽) | min: 1 000, max: 50 000 000 | Ограничивает максимальную сумму одной операции | Установить предыдущее значение в ConfigMap |
| `transfer.aml.threshold` | integer | internal | dynamic | global | ConfigMap | 15 000 | Порог AML-проверки (₽) | min: 0, max: 1 000 000 | Снижение → рост нагрузки на Compliance Service; повышение → пропуск проверок | Откат ConfigMap + мониторинг error rate Compliance Service |
| `transfer.2fa.threshold` | integer | internal | dynamic | global | ConfigMap | 50 000 | Порог 2FA-подтверждения (₽) | min: 0, max: 10 000 000 | Снижение → больше 2FA-запросов; повышение → снижение безопасности | Установить предыдущее значение в ConfigMap |
| `db.pool.size` | integer | internal | static | env | ConfigMap | 20 | Размер пула соединений | min: 5, max: 50 | Увеличение → больше соединений к PostgreSQL; уменьшение → отказы при нагрузке | Требует перезапуска pod'ов. Откат: предыдущий ConfigMap + rollout restart |
| `redis.cache.ttl.transfer` | integer | internal | dynamic | global | ConfigMap | 300 | TTL кэша перевода (сек) | min: 10, max: 3 600 | Снижение → больше запросов к БД; повышение → устаревшие данные в кэше | Установить предыдущее значение в ConfigMap |
| `circuit.compliance.threshold` | float | internal | dynamic | global | ConfigMap | 0.5 | Порог Circuit Breaker для AML | min: 0.1, max: 1.0 | Снижение → Circuit Breaker срабатывает чаще; повышение → позднее обнаружение отказа | Установить предыдущее значение, проверить состояние Circuit Breaker |
| `feature.p2p.instantTransfer.enabled` | boolean | public | runtime | env | БД | false | Мгновенные P2P-переводы | true / false | ON → мгновенные переводы через СБП; OFF → возврат к T+1 | Установить false в БД (эффект мгновенный, без перезапуска) |
