# Архитектура Data Pipeline: AI-ассистент для службы поддержки ERP

## Схема архитектуры данных

```mermaid
flowchart TD
    subgraph Sources["Источники"]
        ERP["ERP SM<br/>(oData API)"] -->|"Daily polling<br/>LastModifiedDateTime"| ETL["ETL Worker<br/>Python"]
        Admin["Администратор<br/>(Thymeleaf)"] -->|"CRUD<br/>HTTP REST"| AdminAPI["Admin API<br/>FastAPI"]
    end

    subgraph Bronze["Bronze: Raw Data"]
        ETL -->|"Трансформация,<br/>валидация"| Raw[("PostgreSQL<br/>raw_requests")]
        AdminAPI -->|"Вставка / обновление"| Raw
    end

    subgraph Silver["Silver: Cleansed + Embedded"]
        Raw -->|"Очистка,<br/>нормализация"| Embedding["Embedding Service<br/>Python + Qwen"]
        Embedding -->|"Генерация<br/>эмбеддингов"| Qdrant[("Qdrant<br/>requests +<br/>solution_chunks")]
        Embedding -->|"Дедупликация<br/>(cosine threshold)"| DupCheck{{"Дубликат?"}}
        DupCheck -->|"Да"| Pending[("PostgreSQL<br/>pending_validations")]
        DupCheck -->|"Нет"| Qdrant
    end

    subgraph Gold["Gold: Serving Index"]
        Qdrant -->|"ANN search<br/>top_k"| SearchOrch["Search Orchestrator<br/>Python"]
        SearchOrch -->|"Ранжирование,<br/>cosine scoring"| Ranked{{"Результаты<br/>ранжирования"}}
        Ranked -->|"LLM генерация"| LLM["LLM Response<br/>Qwen"]
        Ranked -->|"degraded fallback"| Fallback["Raw results<br/>without LLM"]
    end

    subgraph Cache["Cache Layer"]
        SearchOrch <-->|"check / store<br/>TTL 24h/4h"| Redis[("Redis<br/>query_cache")]
    end

    subgraph Serving["Response Pipeline"]
        LLM -->|"Структурированный<br/>ответ"| Response["Gateway → ERP"]
        Fallback -->|"degraded ответ"| Response
        Response -->|"Async:<br/>audit + metrics"| Audit["Audit & Metrics<br/>PostgreSQL + Prometheus"]
    end

    classDef storage fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    class Raw,Qdrant,Redis,Pending storage;
    classDef service fill:#f3e5f5,stroke:#4a148c,stroke-width:2px;
    class ETL,Embedding,SearchOrch,LLM,AdminAPI service;
    classDef decision fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    class DupCheck,Ranked decision;
```

---

## Текстовое описание потока

### Обзор

Архитектура реализует **RAG-пайплайн** (Retrieval-Augmented Generation) с разделением на два независимых потока:

1. **Offline ETL Pipeline** — пополнение базы знаний из ERP по расписанию (1 раз/сутки)
2. **Online Query Pipeline** — обработка запросов пользователей в реальном времени

### Описание компонентов

#### 1. ETL Worker (Python)

Оркестрирует загрузку данных из ERP SM через штатный oData-интерфейс.

| Параметр | Значение |
|----------|----------|
| Протокол | oData REST API |
| Расписание | Daily (cron) |
| Фильтр | `LastModifiedDateTime > last_sync`, `Status = Closed` |
| Идемпотентность | Upsert по `RequestID` |
| Retry | Exponential backoff, max 3 attempts |
| Circuit Breaker | Отключение при >5 ошибок подряд, восстановление через 5 мин |

**Поток:**
```
oData ERP → ETL Worker → PostgreSQL (raw_requests) → Embedding Service → Qdrant
```

Этапы:
1. **Polling**: Запрос новых/изменённых обращений через oData с фильтром по дате модификации
2. **Трансформация**: Нормализация полей, валидация обязательных атрибутов
3. **Загрузка**: Вставка/обновление в PostgreSQL (`raw_requests`)

#### 2. Embedding Service (Python + Qwen)

Генерирует векторные представления и проверяет дубликаты.

| Параметр | Значение |
|----------|----------|
| Модель эмбеддинга | Qwen-embedding (on-prem) |
| Размерность | ~1024 (зависит от модели) |
| Чанкинг | Разбиение решений на чанки по ~500 токенов |
| Порог дедупликации | cosine similarity > 0.92 |

**Поток дедупликации:**
```
raw_requests → Генерация эмбеддинга запроса → Qdrant (top-1 search)
   → cosine similarity > threshold → duplicate → pending_validations
   → cosine similarity ≤ threshold → уникальное → solution_chunks в Qdrant
```

**Хранилища Qdrant:**
- `requests` — эмбеддинги полных текстов обращений
- `solution_chunks` — эмбеддинги чанков решений (с payload: request_id, chunk_text, direction)

#### 3. Search Orchestrator (Python)

Основной RAG-пайплайн для обработки запросов.

**Поток:**
```
Query → Redis cache check
   → [cache miss] → Embedding (Qwen) → Qdrant search (requests + solution_chunks)
   → Ranking (cosine scoring + dedup) → LLM generation (Qwen)
   → Response → Redis cache update → async Audit
   → [cache hit] → Cached response
```

**Ранжирование:**
- Поиск по коллекции `requests` (полные обращения) → top_k results
- Поиск по коллекции `solution_chunks` (чанки решений) → top_k results
- Если чанк принадлежит `solution`, которое уже есть среди полных решений → пропуск дубликата
- Финальный скор: `cosine_similarity × weight` (полные обращения × 1.0, чанки × 0.8)
- Фильтрация по `similarity_threshold`

**Fallback:**
- LLM timeout/error → возврат raw результатов векторного поиска с `status: degraded`
- Qdrant пуст → `status: empty`

#### 4. Cache Manager (Redis)

| Параметр | Значение |
|----------|----------|
| TTL (точное совпадение) | 24 часа |
| TTL (семантически похожий) | 4 часа |
| Key | SHA256(query + metadata_filters + config) |
| Value | Сериализованный JSON-ответ |
| Инвалидация | TTL + автоматическая при обновлении БД + ручная через Admin API |

#### 5. Audit & Metrics

Асинхронная запись метаданных после формирования ответа (не блокирует ответ пользователю).

| Метрика | Описание |
|---------|----------|
| request_latency_ms | Время обработки запроса |
| cache_hit_ratio | Доля попаданий в кэш |
| llm_latency_ms | Время генерации LLM |
| vector_search_latency_ms | Время векторного поиска |
| dedup_rejected_count | Количество отклонённых дубликатов |
| dedup_pending_count | Количество дубликатов на ручной валидации |

---

## Потоки данных

### Поток 1: Offline ETL (пополнение базы знаний)

```
┌─────────┐    oData     ┌──────────┐   SQL    ┌────────────┐
│ ERP SM  │ ──────────►  │ ETL      │ ──────► │ PostgreSQL │
│ (source)│   polling    │ Worker   │         │ raw_requests│
└─────────┘              └──────────┘         └─────┬──────┘
                                                     │
                                                     │ trigger
                                                     ▼
                                            ┌────────────────┐
                                            │ Embedding      │
                                            │ Service        │
                                            └───┬────────┬───┘
                                                │        │
                                    ┌───────────┘        └──────────┐
                                    ▼                               ▼
                           ┌─────────────┐               ┌──────────────────┐
                           │   Qdrant    │               │ pending_validations│
                           │ (requests + │               │ (дубликаты)       │
                           │  chunks)    │               └──────────────────┘
                           └─────────────┘
```

### Поток 2: Online Query (обработка запроса)

```
┌──────────┐  REST   ┌──────────┐  HTTP   ┌──────────┐
│ Gateway  │ ──────► │ AI       │ ◄─────► │ Redis    │
│          │         │ Service  │  cache  │(TTL 24h/4h)│
└──────────┘         └────┬─────┘         └──────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
       ┌──────────┐ ┌──────────┐ ┌──────────┐
       │ Qwen     │ │ Qdrant   │ │ Qwen     │
       │ Embedding│ │ ANN      │ │ LLM      │
       └──────────┘ │ Search   │ └────┬─────┘
                    └──────────┘      │
                                      ▼
                               ┌──────────┐
                               │ Response │
                               │ → ERP    │
                               └──────────┘
```

### Поток 3: Admin CRUD (управление базой знаний)

```
┌──────────────┐  Thymeleaf  ┌──────────────┐  REST  ┌──────────────┐
│ Администратор│ ──────────► │ Admin API    │ ──────► │ AI Service   │
│              │             │ (Spring Boot)│         │ (FastAPI)    │
└──────────────┘             └──────────────┘         └──────┬───────┘
                                                             │
                                                    ┌────────┼────────┐
                                                    ▼        ▼        ▼
                                              ┌──────┐ ┌─────────┐ ┌───────┐
                                              │PG    │ │ Qdrant  │ │ Redis │
                                              │      │ │         │ │       │
                                              └──────┘ └─────────┘ └───────┘
```