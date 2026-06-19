#### Пример SOAP операции (согласно стандартам СТД-ИНТ-01, СТД-SOAP-01-09, СТД-СИНХ-ПАР-01-09)

**SOAP операция:** GetCustomerAccounts
**Назначение:** Получение списка банковских счетов клиента с балансами

**Общая информация (СТД-ИНТ-01):**
| Параметр | Значение |
|----------|----------|
| Назначение | Получение списка счетов клиента с балансами |
| Система-источник | CRM System / Back Office |
| Система-получатель | Core Banking System (CBS) |
| Тип интеграции | Синхронная |
| Протокол | SOAP 1.1 (HTTPS) |
| Направление | Однонаправленная (Request → Response) |
| WSDL | https://cbs.bank.com/accounts/v1?wsdl |
| Endpoint | https://cbs.bank.com/accounts/v1 |
| Namespace | urn:bank:cbs:accounts:v1 |
| SOAPAction | urn:bank:cbs:accounts:GetCustomerAccounts |
| Аутентификация | WS-Security (X.509 Certificate) |
| Timeout | 30 секунд |
| Retry Policy | 2 попытки с exponential backoff (2s, 4s) |

**HTTP заголовки транспортного уровня (СТД-ЗАГОЛ-01):**

> В SOAP заголовки делятся на два уровня: **HTTP-заголовки** (транспортный уровень) и **SOAP Header** (уровень протокола, внутри Envelope). Аутентификация в SOAP обычно передаётся через **SOAP Header** (WS-Security), а не через HTTP-заголовки.

| Заголовок | Обязат. | Описание | Пример |
|-----------|---------|----------|--------|
| Content-Type | Да | MIME-тип SOAP сообщения | text/xml; charset=utf-8 |
| SOAPAction | Да | URI операции (для маршрутизации) | "urn:bank:cbs:accounts:GetCustomerAccounts" |
| X-Request-ID | Да | UUID для трассировки | 7c9e6679-7425-40de-944b-e07fc1f90ae7 |

**SOAP Header элементы (СТД-SOAP-02, СТД-SOAP-08):**

> Аутентификация, трассировка и безопасность передаются внутри `<soap:Header>`, а не в HTTP-заголовках. Это отличие от REST/GraphQL.

| Элемент | Обязат. | Описание | Пример |
|---------|---------|----------|--------|
| wsse:Security | Да | WS-Security блок (X.509 Certificate) | `<wsse:BinarySecurityToken>MIIBx...</wsse:BinarySecurityToken>` |
| trc:RequestId | Да | ID запроса для трассировки (дублирует HTTP X-Request-ID) | 7c9e6679-7425-40de-944b-e07fc1f90ae7 |
| trc:Timestamp | Нет | Время отправки запроса | 2026-01-15T10:30:00Z |

**Response Headers:**

> SOAP ответ не использует кастомные HTTP-заголовки для передачи метаданных. Информация о статусе и ошибках передаётся через `<soap:Body>` (успешный ответ) или `<soap:Fault>` (ошибка). Rate-limiting при необходимости реализуется на уровне HTTP (заголовки `X-RateLimit-*`).

| Заголовок | Описание | Пример |
|-----------|----------|--------|
| Content-Type | MIME-тип ответа | text/xml; charset=utf-8 |
| X-Request-ID | Echo request ID | 7c9e6679-7425-40de-944b-e07fc1f90ae7 |

**XSD Schema (СТД-SOAP-03, СТД-SOAP-04, СТД-SOAP-05):**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="urn:bank:cbs:accounts:v1"
           targetNamespace="urn:bank:cbs:accounts:v1">

  <!-- ========== REQUEST ========== -->
  <xs:element name="GetCustomerAccountsRequest"
              type="tns:GetCustomerAccountsRequestType"/>

  <xs:complexType name="GetCustomerAccountsRequestType">
    <xs:sequence>
      <xs:element name="customerId" minOccurs="1" maxOccurs="1">
        <xs:annotation>
          <xs:documentation>UUID клиента</xs:documentation>
        </xs:annotation>
        <xs:simpleType>
          <xs:restriction base="xs:string">
            <xs:minLength value="36"/>
            <xs:maxLength value="36"/>
            <xs:pattern value="[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"/>
          </xs:restriction>
        </xs:simpleType>
      </xs:element>
      <xs:element name="accountType" type="tns:AccountTypeEnum"
                  minOccurs="0" maxOccurs="1">
        <xs:annotation>
          <xs:documentation>Фильтр по типу счёта</xs:documentation>
        </xs:annotation>
      </xs:element>
      <xs:element name="includeBalance" type="xs:boolean"
                  minOccurs="0" maxOccurs="1" default="true">
        <xs:annotation>
          <xs:documentation>Включать балансы в ответ</xs:documentation>
        </xs:annotation>
      </xs:element>
      <xs:element name="currency" minOccurs="0" maxOccurs="1">
        <xs:annotation>
          <xs:documentation>Фильтр по валюте (ISO 4217)</xs:documentation>
        </xs:annotation>
        <xs:simpleType>
          <xs:restriction base="xs:string">
            <xs:minLength value="3"/>
            <xs:maxLength value="3"/>
            <xs:pattern value="[A-Z]{3}"/>
          </xs:restriction>
        </xs:simpleType>
      </xs:element>
    </xs:sequence>
  </xs:complexType>

  <!-- ========== RESPONSE ========== -->
  <xs:element name="GetCustomerAccountsResponse"
              type="tns:GetCustomerAccountsResponseType"/>

  <xs:complexType name="GetCustomerAccountsResponseType">
    <xs:sequence>
      <xs:element name="account" type="tns:AccountType"
                  minOccurs="0" maxOccurs="unbounded"/>
      <xs:element name="totalCount" type="xs:int"
                  minOccurs="1" maxOccurs="1"/>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="AccountType">
    <xs:sequence>
      <xs:element name="accountId" minOccurs="1">
        <xs:simpleType>
          <xs:restriction base="xs:string">
            <xs:minLength value="20"/>
            <xs:maxLength value="34"/>
          </xs:restriction>
        </xs:simpleType>
      </xs:element>
      <xs:element name="accountType" type="tns:AccountTypeEnum" minOccurs="1"/>
      <xs:element name="status" type="tns:AccountStatusEnum" minOccurs="1"/>
      <xs:element name="currency" minOccurs="1">
        <xs:simpleType>
          <xs:restriction base="xs:string">
            <xs:minLength value="3"/>
            <xs:maxLength value="3"/>
            <xs:pattern value="[A-Z]{3}"/>
          </xs:restriction>
        </xs:simpleType>
      </xs:element>
      <xs:element name="balance" type="xs:decimal" minOccurs="0"/>
      <xs:element name="openDate" type="xs:date" minOccurs="1"/>
      <xs:element name="closeDate" type="xs:date" minOccurs="0"/>
    </xs:sequence>
  </xs:complexType>

  <!-- ========== ENUMS ========== -->
  <xs:simpleType name="AccountTypeEnum">
    <xs:restriction base="xs:string">
      <xs:enumeration value="CURRENT"/>   <!-- Текущий счёт -->
      <xs:enumeration value="SAVINGS"/>   <!-- Сберегательный -->
      <xs:enumeration value="DEPOSIT"/>   <!-- Депозит -->
      <xs:enumeration value="LOAN"/>      <!-- Кредитный -->
    </xs:restriction>
  </xs:simpleType>

  <xs:simpleType name="AccountStatusEnum">
    <xs:restriction base="xs:string">
      <xs:enumeration value="ACTIVE"/>    <!-- Активный -->
      <xs:enumeration value="BLOCKED"/>   <!-- Заблокирован -->
      <xs:enumeration value="CLOSED"/>    <!-- Закрыт -->
    </xs:restriction>
  </xs:simpleType>

</xs:schema>
```

**Параметры запроса (СТД-СИНХ-ПАР-01, СТД-СИНХ-ПАР-08):**
| Параметр | Тип XSD | Обязат. | Описание | Валидация | По умолч. | Пример |
|----------|---------|---------|----------|-----------|-----------|--------|
| customerId | xs:string | Да | UUID клиента | minLength: 36, maxLength: 36, pattern: UUID regex | — | 550e8400-e29b-41d4-a716-446655440000 |
| accountType | AccountTypeEnum | Нет | Фильтр по типу счёта | enumeration: [CURRENT, SAVINGS, DEPOSIT, LOAN] | — | SAVINGS |
| includeBalance | xs:boolean | Нет | Включать балансы в ответ | — | true | true |
| currency | xs:string | Условно* | Фильтр по валюте | minLength: 3, maxLength: 3, pattern: `[A-Z]{3}` | — | RUB |

**Условия обязательности:**
| Параметр | Условие обязательности |
|----------|----------------------|
| currency | Обязателен, если includeBalance = true (для конвертации остатков мультивалютных счетов) |

**Параметры ответа (СТД-СИНХ-ПАР-05, СТД-СИНХ-ПАР-08):**
| Параметр | Тип XSD | Обязат. | Описание | Валидация | По умолч. | Пример | Маппинг |
|----------|---------|---------|----------|-----------|-----------|--------|---------|
| account | complexType | 0..* | Массив счетов | maxOccurs: unbounded | — | `<account>` | — |
| ├─ accountId | xs:string | Да | Номер счёта | minLength: 20, maxLength: 34 | — | 40817810099100012345 | CBS → account_num |
| ├─ accountType | AccountTypeEnum | Да | Тип счёта | enumeration: [CURRENT, SAVINGS, DEPOSIT, LOAN] | — | CURRENT | CBS → acct_type |
| ├─ status | AccountStatusEnum | Да | Статус | enumeration: [ACTIVE, BLOCKED, CLOSED] | — | ACTIVE | CBS → acct_status |
| ├─ currency | xs:string | Да | Валюта | minLength: 3, maxLength: 3, pattern: `[A-Z]{3}` | — | RUB | CBS → ccy_code |
| ├─ balance | xs:decimal | Нет | Баланс | minInclusive: 0 | — | 150000.50 | CBS → avail_bal |
| ├─ openDate | xs:date | Да | Дата открытия | format: YYYY-MM-DD | — | 2020-03-15 | CBS → open_dt |
| └─ closeDate | xs:date | Нет | Дата закрытия | format: YYYY-MM-DD | — | — | CBS → close_dt |
| totalCount | xs:int | Да | Кол-во счетов | minInclusive: 0 | — | 3 | COUNT(*) |

**Пример запроса и ответа — Happy Path:**
```xml
<!-- REQUEST -->
<soap:Envelope
  xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
  xmlns:acc="urn:bank:cbs:accounts:v1">
  <soap:Header>
    <wsse:Security xmlns:wsse="...wss-wssecurity-secext-1.0">
      <wsse:BinarySecurityToken
        EncodingType="Base64Binary"
        ValueType="X509v3">MIIBxTCCAW...</wsse:BinarySecurityToken>
    </wsse:Security>
    <trc:RequestId>7c9e6679-7425-40de-944b-e07fc1f90ae7</trc:RequestId>
  </soap:Header>
  <soap:Body>
    <acc:GetCustomerAccountsRequest>
      <acc:customerId>550e8400-e29b-41d4-a716-446655440000</acc:customerId>
      <acc:includeBalance>true</acc:includeBalance>
      <acc:currency>RUB</acc:currency>
    </acc:GetCustomerAccountsRequest>
  </soap:Body>
</soap:Envelope>
```

```xml
<!-- RESPONSE -->
<soap:Envelope xmlns:soap="..." xmlns:acc="urn:bank:cbs:accounts:v1">
  <soap:Body>
    <acc:GetCustomerAccountsResponse>
      <acc:account>
        <acc:accountId>40817810099100012345</acc:accountId>
        <acc:accountType>CURRENT</acc:accountType>
        <acc:status>ACTIVE</acc:status>
        <acc:currency>RUB</acc:currency>
        <acc:balance>150000.50</acc:balance>
        <acc:openDate>2020-03-15</acc:openDate>
      </acc:account>
      <acc:account>
        <acc:accountId>42301810099100067890</acc:accountId>
        <acc:accountType>SAVINGS</acc:accountType>
        <acc:status>ACTIVE</acc:status>
        <acc:currency>RUB</acc:currency>
        <acc:balance>500000.00</acc:balance>
        <acc:openDate>2021-07-01</acc:openDate>
      </acc:account>
      <acc:totalCount>2</acc:totalCount>
    </acc:GetCustomerAccountsResponse>
  </soap:Body>
</soap:Envelope>
```

**Пограничный случай: Нет счетов у клиента:**
```xml
<soap:Envelope xmlns:soap="..." xmlns:acc="...">
  <soap:Body>
    <acc:GetCustomerAccountsResponse>
      <acc:totalCount>0</acc:totalCount>
    </acc:GetCustomerAccountsResponse>
  </soap:Body>
</soap:Envelope>
```
> **Примечание:** При отсутствии счетов элементы `<account>` отсутствуют, `totalCount = 0`. Это НЕ ошибка.

**SOAP Fault коды ошибок (СТД-SOAP-06, СТД-SOAP-07):**
| faultcode | errorCode | Описание |
|-----------|-----------|----------|
| soap:Client | INVALID_CUSTOMER_ID | Невалидный UUID клиента |
| soap:Client | INVALID_ACCOUNT_TYPE | Невалидный тип счёта |
| soap:Client | INVALID_CURRENCY | Невалидный код валюты |
| soap:Client | CUSTOMER_NOT_FOUND | Клиент не найден |
| soap:Client | ACCESS_DENIED | Нет доступа к данным клиента |
| soap:Server | INTERNAL_ERROR | Внутренняя ошибка CBS |
| soap:Server | SERVICE_UNAVAILABLE | CBS недоступен |
| soap:MustUnderstand | SECURITY_HEADER_ERR | Ошибка WS-Security |
