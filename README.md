# **Payment Service — решение вступительного задания**
Сервис для проведения платёжных операций через внешнего провайдера с гарантией идемпотентности и восстановления после сбоев.

## Что делает сервис

-Создаёт платёжные операции с уникальным operationId.

-Отправляет их внешнему провайдеру.

-Принимает callback-квитанции и определяет финальный статус.

-Гарантирует, что для одной операции у провайдера создаётся ровно один платёж.

-Устойчив к потерянным HTTP-ответам, конкурентным запросам и перезапускам.

-Восстанавливает незавершённые операции после перезапуска.

## Запуск приложения:

Клонировать репозиторий 

    git clone https://github.com/FirsovOleg/Entry-task

Перейти в директорию приложения
    
    cd Entry-task

Команда для запуска

    docker compose up --build

Остановка:

    docker compose down

Удаление тома с базой данных:

    docker compose down -v

## Эндпоинты API

| Метод | Маршрут | Назначение |
|-------|---------|------------|
| `GET` | `/health` | Проверка готовности сервиса |
| `POST` | `/operations` | Создание новой операции |
| `POST` | `/operations/{id}/submit` | Отправка операции провайдеру |
| `POST` | `/receipts` | Приём callback-квитанции |
| `GET` | `/operations/{id}` | Получение текущего состояния операции |
| `GET` | `/operations/{id}/events` | Получение истории событий операции |


## Примеры запросов к сервису

### Проверка состояния

GET `/health`

Ответ

```json
{
"status":"ok"
}
```
### Создание операции

POST `/operations`
```json
{
  "operationId": "test-001",
  "amount": "1000.00",
  "currency": "RUB",
  "description": "Оплата заказа"
}
```

Ответ

```json
{
  "operationId": "test-001",
  "amount": "1000.00",
  "currency": "RUB",
  "description": "Оплата заказа",
  "status": "CREATED",
  "providerPaymentId": null
}
```

### Отправка операции

POST `/operations/test-001/submit`

Ответ:

```json
{
  "operationId": "test-001",
  "status": "PROCESSING",
  "providerPaymentId": null
}
```

### Получение состояния операции
GET `/operations/test-001`

Ответ:

```json
{
  "operationId": "test-001",
  "amount": "1000.00",
  "currency": "RUB",
  "description": "Оплата заказа",
  "status": "COMPLETED",
  "providerPaymentId": "aa5b7856-e9f2-4fd5-955b-38b1f28d9c57"
}
```

### Получение истории событий

GET `/operations/test-001/events`

Ответ:

```json
[
  {
    "eventId": 1,
    "type": "CREATED",
    "fromStatus": null,
    "toStatus": "CREATED",
    "message": "Operation created",
    "occurredAt": "2026-08-12T16:30:00Z"
  },
  {
    "eventId": 2,
    "type": "PROCESSING",
    "fromStatus": "CREATED",
    "toStatus": "PROCESSING",
    "message": "Submit requested",
    "occurredAt": "2026-08-12T16:30:05Z"
  },
  {
    "eventId": 3,
    "type": "COMPLETED",
    "fromStatus": "PROCESSING",
    "toStatus": "COMPLETED",
    "message": "Payment completed",
    "occurredAt": "2026-08-12T16:30:08Z"
  }
]
```

## Стек:

-Python 3.14

-FastAPI

-SQLAlchemy

-SQLite

-Uvicorn

-Docker

-GitHub Copilot

## Автор

### Олег Фирсов

[GitHub](https://github.com/FirsovOleg) 

[Email](firsov_olegg@mail.ru)
