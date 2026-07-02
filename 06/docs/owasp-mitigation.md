# Решение по митигации OWASP LLM Top 10

## Матрица соответствия угроз и компонентов

| OWASP ID | Угроза | Компонент митигации | Слой |
|----------|--------|---------------------|------|
| LLM01 | Direct Prompt Injection | Input Guardrails + LLM Guardrail | Входной фильтр |
| LLM01 | Indirect Prompt Injection | Input Guardrails + LLM Guardrail | Входной фильтр |
| LLM02 | PII Leakage | PII Sanitizer + Output Validator | Обработка данных |
| LLM02 | Sensitive Business Data Disclosure | Output Validator | Выходной фильтр |
| LLM07 | Exposure of Sensitive Functionality | Access Controller | Контроль доступа |
| LLM08 | Behavior Alteration | RAG Data Validator + Search Orchestrator | Валидация данных |
| LLM08 | Data Poisoning Attacks | RAG Data Validator | Валидация данных |
| LLM09 | Factual Inaccuracies | Fact Checker + Output Validator | Верификация вывода |
| LLM09 | Unsupported Claims | Fact Checker | Верификация вывода |
| LLM10 | Variable-Length Input Flood | Gateway (rate-limit) + Input Length Validator | Входной фильтр |
| LLM10 | Continuous Input Overflow | Gateway (rate-limit) + Input Length Validator | Входной фильтр |

---

## Описание компонентов

### Gateway (SpringBoot Cloud Gateway)

**Угроза:** LLM10 — Unbounded Consumption

**Решение:** Rate limiting и ограничение размера запроса на уровне шлюза. Это первая линия защиты от DoS-атак и перерасхода ресурсов.

**Реализация:**
- Rate limit по IP-адресу и API-ключу (token bucket / sliding window)
- Ограничение максимального размера HTTP body (max-http-message-size)
- Timeouts на уровне соединения
- Блокировка IP при превышении лимита

---

### Input Length Validator (Python)

**Угроза:** LLM10 — Variable-Length Input Flood, Continuous Input Overflow

**Решение:** Валидация длины промпта перед обработкой. Компонент отклоняет входные данные, превышающие допустимый размер.

**Реализация:**
- Максимальная длина промпта: 8192 токена (или заданная конфигурация)
- Проверка на presence oversized-входов (context window overflow)
- Логирование попыток превышения лимита

---

### Input Guardrails (Regex + Semantic Router)

**Угроза:** LLM01 — Prompt Injection (Direct и Indirect)

**Решение:** Многоуровневая фильтрация входящих запросов с обнаружением паттернов инъекций.

**Реализация:**
- Regex-паттерны для обнаружения известных векторов атак:
  - `ignore previous instructions`
  - `you are now`
  - `system prompt`
  - Base64-кодированные payloads
- Semantic Router для классификации намерений запроса
- Фильтрация тематических отклонений (запросы вне контекста задачи)
- Отклонение запросов с обнаруженными паттернами инъекций

---

### LLM Guardrail (LlamaGuard / NeMo Guardrails)

**Угроза:** LLM01 — Prompt Injection (глубокая проверка)

**Решение:** Проверка промптов с использованием специализированной safety-модели перед передачей в основной LLM.

**Реализация:**
- Классификация промпта по категориям риска (LlamaGuard categories)
- Проверка на соответствие политикам контента
- Блокировка промптов с высоким risk score
- NeMo Guardrails для определения allowed/denied topics

---

### Access Controller (Python + RBAC)

**Угроза:** LLM07 — Exposure of Sensitive Functionality

**Решение:** Контроль доступа к чувствительным данным и функциям, предотвращение раскрытия credentials через LLM.

**Реализация:**
- RBAC:的角色-based access control для API-эндпоинтов
- Изоляция credentials от контекста LLM (не передаются в промпт)
- Валидация X-User-Id и проверка прав доступа перед обработкой
- Логирование попыток несанкционированного доступа

---

### Request Handler (Python + FastApi)

**Угроза:** LLM01, LLM07 — общая точка валидации

**Решение:** Центральный компонент обработки запросов с извлечением идентификаторов и маршрутизацией.

**Реализация:**
- Валидация входного запроса (Content-Type, размер, структура)
- Извлечение и валидация X-User-Id из заголовка
- Маршрутизация запроса через пайплайн безопасности
- Логирование всех входящих запросов для аудита

---

### PII Sanitizer (Microsoft Presidio)

**Угроза:** LLM02 — PII Leakage

**Решение:** Маскирование персональных данных (PII) в запросах и ответах для предотвращения утечки.

**Реализация:**
- Распознавание PII: имена, email, телефоны, ИНН, номера карт
- Маскирование перед передачей в LLM (input sanitization)
- Восстановление масок в ответе (output de-sanitization)
- Конфигурируемые правила для разных типов данных

---

### Search Orchestrator (Python)

**Угроза:** LLM08 — Behavior Alteration, Data Poisoning

**Решение:** Оркестрация поиска с валидацией источников и контролем качества данных.

**Реализация:**
- Валидация источников перед использованием в контексте
- Фильтрация по релевантности и trust-score документов
- RBAC-фильтрация по direction (роли пользователя)
- Мониторинг аномалий в результатах поиска

---

### RAG Data Validator (Python)

**Угроза:** LLM08 — Data Poisoning Attacks

**Решение:** Мониторинг целостности данных в векторной базе, обнаружение отравленных записей.

**Реализация:**
- Периодическая проверка хешей документов в Qdrant
- Обнаружение аномалий в распределении эмбеддингов
- Сигнализация при обнаружении подозрительных изменений
- Версионирование данных для отката при инциденте

---

### LLM & Response Builder (Python)

**Угроза:** LLM09 — Misinformation (частичная митигация)

**Решение:** Генерация текста с проверкой groundness на этапе сборки ответа.

**Реализация:**
- Формирование промпта с ограничениями (system prompt с role-based instructions)
- Проверка контекста перед генерацией
- Встраивание цитат и ссылок на источники в ответ
- Логирование сгенерированных ответов для аудита

---

### Fact Checker (Python + RAG Triad)

**Угроза:** LLM09 — Factual Inaccuracies, Unsupported Claims

**Решение:** Верификация фактов в ответах LLM с использованием RAG Triad.

**Реализация:**
- **Context Relevance**: проверка, что контекст релевантен вопросу
- **Groundedness**: проверка, что ответ подтверждается найденными источниками
- **Answer Relevance**: проверка, что ответ соответствует вопросу
- Оценка confidence score для каждого ответа
- Блокировка или пометка ответов с низким confidence

---

### Output Validator (DLP + Toxicity)

**Угроза:** LLM02 — Sensitive Business Data Disclosure, LLM09 — Misinformation

**Решение:** Финальная проверка ответа перед отдачей пользователю.

**Реализация:**
- Проверка на токсичность и вредоносный контент
- DLP-фильтрация для обнаружения утечки чувствительных данных
- Валидация формата ответа
- Обнаружение галлюцинаций (сравнение с источниками)
- Блокировка или замена ответа при нарушении политик

---

## Потоки данных

### Основной пайплайн обработки запроса

```
Gateway (rate-limit)
    ↓
Input Length Validator (LLM10)
    ↓
Input Guardrails (LLM01)
    ↓
LLM Guardrail (LLM01)
    ↓
Request Handler (LLM01/LLM07) ← Access Controller (LLM07)
    ↓
PII Sanitizer (LLM02)
    ↓
Search Orchestrator (LLM08) ←→ Vector DB ← RAG Data Validator (LLM08)
    ↓
LLM & Response Builder (LLM09) ←→ Model Serving
    ↓
Output Validator (LLM02/LLM09) ← Fact Checker (LLM09)
    ↓
Gateway → пользователь
```

### Побочный пайплайн: аудит и метрики

```
Request Handler / LLM & Response Builder
    ↓
Audit & Metrics (Async SQL + Prometheus)
    ↓
SQL DB (хранилище логов)
Prometheus (метрики)
```

---

## Ключевые решения

1. **Defense in Depth**: Каждая угроза покрыта минимум двумя компонентами на разных уровнях
2. **Zero Trust**: Все входные данные проходят валидацию независимо от источника
3. **Least Privilege**: Access Controller ограничивает права LLM и расширений
4. **Separation of Duties**: Security-компоненты (оранжевые) изолированы от business-компонентов
5. **Observability**: Все запросы логируются, метрики экспортируются в Prometheus
6. **Graceful Degradation**: При обнаружении атаки запрос отклоняется, а не обрабатывается частично
