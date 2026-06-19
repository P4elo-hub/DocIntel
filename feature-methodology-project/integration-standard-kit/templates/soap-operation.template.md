# SOAP операция: [OperationName]

## Назначение

[Что делает операция и кто ее вызывает.]

## WSDL и endpoint

| Параметр | Значение |
|---|---|
| WSDL | [url/path] |
| Endpoint | [url/path] |
| Namespace | [namespace] |
| SOAPAction | [soap action] |
| Producer | [service] |
| Consumer | [client/service] |
| Аутентификация | WS-Security / UsernameToken / X.509 / SAML |

## HTTP headers

| Заголовок | Обязат. | Описание | Пример |
|---|---|---|---|
| Content-Type | Да | MIME-тип SOAP сообщения | `text/xml; charset=utf-8` |
| SOAPAction | Да | URI операции | `"urn:example:Operation"` |
| X-Request-ID | Да | Идентификатор запроса | `7c9e6679-7425-40de-944b-e07fc1f90ae7` |

## SOAP Header

| Элемент | Обязат. | Описание | Пример |
|---|---|---|---|
| wsse:Security | Да | WS-Security block | `<wsse:BinarySecurityToken>...</wsse:BinarySecurityToken>` |
| trc:RequestId | Да | ID запроса | `7c9e6679-7425-40de-944b-e07fc1f90ae7` |

## XSD types

```xml
<xs:complexType name="[RequestType]">
  <xs:sequence>
    <xs:element name="entityId" type="xs:string" minOccurs="1" maxOccurs="1">
      <xs:annotation>
        <xs:documentation>UUID сущности</xs:documentation>
      </xs:annotation>
    </xs:element>
  </xs:sequence>
</xs:complexType>
```

## Request parameters

| Параметр | Тип XSD | minOccurs | maxOccurs | Описание | Ограничения | Пример |
|---|---|---:|---|---|---|---|
| entityId | xs:string | 1 | 1 | UUID сущности | `minLength: 36, maxLength: 36` | `550e8400-e29b-41d4-a716-446655440000` |

## Response parameters

| Параметр | Тип XSD | minOccurs | maxOccurs | Описание | Ограничения | Пример |
|---|---|---:|---|---|---|---|
| result | xs:string | 1 | 1 | Результат операции | — | `OK` |

## Пример SOAP запроса

```xml
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ex="urn:example:v1">
  <soap:Header>
    <trc:RequestId>7c9e6679-7425-40de-944b-e07fc1f90ae7</trc:RequestId>
  </soap:Header>
  <soap:Body>
    <ex:OperationRequest>
      <ex:entityId>550e8400-e29b-41d4-a716-446655440000</ex:entityId>
    </ex:OperationRequest>
  </soap:Body>
</soap:Envelope>
```

## Пример SOAP ответа

```xml
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ex="urn:example:v1">
  <soap:Body>
    <ex:OperationResponse>
      <ex:result>OK</ex:result>
    </ex:OperationResponse>
  </soap:Body>
</soap:Envelope>
```

## SOAP Fault

| faultcode | errorCode | faultstring | Условие |
|---|---|---|---|
| soap:Client | VALIDATION_ERROR | Validation error | Невалидный request |
| soap:Server | INTERNAL_ERROR | Internal error | Ошибка сервиса |
