# Дашборд Grafana: AI-ассистент для службы поддержки ERP

> Спецификация виджетов для мониторинга RAG-системы в Grafana.

---

## Row 1: Обзор системы (Overview)

### 1. Request Rate
- **Тип:** Time series graph
- **Описание:** RPS по эндпоинтам AI Service, разбивка по статусам ответа (ok / degraded / empty)
- **Query (пример):** `sum(rate(ai_service_requests_total[5m])) by (endpoint, status)`
- **Алерт:** error rate > 5% в течение 5 минут

### 2. Latency Distribution
- **Тип:** Heatmap или time series с percentile-линиями
- **Описание:** p50 / p95 / p99 времени обработки запроса. Раздельные линии для каждого этапа: embedding, vector_search, LLM generation, total
- **Query (пример):**
  - `histogram_quantile(0.95, rate(ai_service_request_duration_seconds_bucket[5m]))`
  - `histogram_quantile(0.95, rate(ai_service_embedding_duration_seconds_bucket[5m]))`
  - `histogram_quantile(0.95, rate(ai_service_vector_search_duration_seconds_bucket[5m]))`
  - `histogram_quantile(0.95, rate(ai_service_llm_duration_seconds_bucket[5m]))`
- **Алерт:** p95 total > 5 сек

### 3. Top Slow Queries
- **Тип:** Table
- **Описание:** Топ-20 самых медленных запросов за последний час с указанием trace_id, latency, endpoint, cache_hit. Помогает быстро выявить «тяжёлые» запросы
- **Query (пример):** `topk(20, ai_service_request_duration_seconds{quantile="0.95"})` или SQL-запрос к query_log
- **Алерт:** —

### 4. Error Rate by Component
- **Тип:** Time series graph
- **Описание:** Процент ошибок по компонентам (Gateway, AI Service, Qdrant, Qwen Embedding, Qwen LLM). Threshold-линии на 1% и 5%
- **Query (пример):** `sum(rate(ai_service_errors_total[5m])) by (component) / sum(rate(ai_service_requests_total[5m])) by (component) * 100`
- **Алерт:** error rate > 5% по любому компоненту

### 5. Active Pod Count
- **Тип:** Stat panel
- **Описание:** Количество запущенных подов по каждому сервису (Gateway, AI Service, ETL Worker, Embedding Service)
- **Query (пример):** `count(kube_pod_info{namespace="ai-support"}) by (deployment)`

---

## Row 2: AI-метрики (AI Quality & Cost)

### 6. Failed Cases Distribution
- **Тип:** Bar chart + time series
- **Описание:** Количество неудачных ответов по причинам (hallucination, irrelevant, incomplete, toxic, pii_leak, outdated) + тренд по неделям
- **Query (пример):** `sum(failed_cases_total) by (failure_reason)`
- **Алерт:** рост > 20% week-of-week по любой причине

### 7. Dedup Metrics
- **Тип:** Gauge + time series
- **Описание:** Gauge — текущие Dedup Precision, Recall, F1. Time series — тренд по неделям
- **Query (пример):** `dedup_precision`, `dedup_recall`, `dedup_f1_score`
- **Алерт:** Dedup F1 < 0.85

### 8. Token Usage per Request
- **Тип:** Time series graph + stat
- **Описание:** Среднее количество токенов (input + output) на запрос по эндпоинтам. Отдельные линии для embedding-запросов и LLM-запросов
- **Query (пример):**
  - `rate(ai_service_tokens_total{type="input"}[5m]) / rate(ai_service_requests_total[5m])`
  - `rate(ai_service_tokens_total{type="output"}[5m]) / rate(ai_service_requests_total[5m])`
- **Алерт:** output tokens > 2000 в среднем (возможная проблема с промптом)

### 9. Cost per Request
- **Тип:** Time series graph + stat
- **Описание:** Средняя стоимость запроса в условных единицах (на основе потребления GPU-time или кастомной формулы). Разбивка: embedding cost + LLM cost
- **Query (пример):**
  - `rate(ai_service_cost_credits_total[5m]) / rate(ai_service_requests_total[5m])`
- **Алерт:** cost > baseline × 2 за день

---

## Row 3: Инфраструктура (Infrastructure)

### 10. Qdrant Collection Stats
- **Тип:** Stat panel + time series
- **Описание:** Количество векторов в коллекциях (requests, solution_chunks), используемая память, индексный размер
- **Query (пример):** `qdrant_collection_info{collection=~"requests|solution_chunks"}`
- **Алерт:** использование памяти > 80%

### 11. Redis Cache Performance
- **Тип:** Time series + stat
- **Описание:** Hit/miss ratio, eviction rate, used memory, connected clients
- **Query (пример):**
  - `redis_keyspace_hits_total / (redis_keyspace_hits_total + redis_keyspace_misses_total)`
  - `redis_memory_used_bytes`
  - `redis_evicted_keys_total`
- **Алерт:** hit ratio < 30%, memory > 80%

### 12. Cache Hit Ratio by Request Type
- **Тип:** Time series + bar chart
- **Описание:** Доля cache hit/miss в разбивке по типам запросов (unique queries vs repeated). Распределение TTL — сколько запросов с каким TTL попадают в кэш. Помогает оптимизировать TTL и размер кэша
- **Query (пример):**
  - `sum(rate(ai_service_cache_hits_total{hit="true"}[5m])) by (query_type) / sum(rate(ai_service_requests_total[5m])) by (query_type)`
  - `histogram_quantile(0.5, rate(ai_service_cache_ttl_seconds_bucket[5m]))`
- **Алерт:** hit ratio < 30%

### 13. PostgreSQL Health
- **Тип:** Stat + time series
- **Описание:** Active connections, query latency p95, последний ETL sync (records_synced, errors_count, статус), slow queries count
- **Query (пример):**
  - `pg_stat_activity_count{state="active"}`
  - `pg_stat_statements_mean_time`
  - `etl_state_records_synced`, `etl_state_errors_count`
- **Алерт:** active connections > 80% max, slow queries > 10/min

### 14. Node CPU & RAM Usage
- **Тип:** Time series graph
- **Описание:** Средняя загрузка CPU и RAM по нодам Kubernetes. Отдельные линии для нод с Qwen (embedding + LLM serving) и остальных
- **Query (пример):**
  - `instance:node_cpu_utilisation:rate5m`
  - `instance:node_memory_utilisation:ratio`

### 15. Pod RAM Usage
- **Тип:** Time series graph
- **Описание:** Использование RAM по подам в разбивке по сервисам (AI Service, Embedding, Qwen Embedding, Qwen LLM, ETL Worker). Отображается в MB/GB
- **Query (пример):**
  - `sum(container_memory_working_set_bytes{namespace="ai-support"}) by (pod)`
  - `sum(kube_pod_container_resource_requests{resource="memory", namespace="ai-support"}) by (pod)` — лимит запроса
  - `sum(kube_pod_container_resource_limits{resource="memory", namespace="ai-support"}) by (pod)` — лимит
- **Алерт:** использование > 85% от лимита

---

## Row 4: ETL Pipeline

### 16. ETL Sync Status
- **Тип:** Time series + stat
- **Описание:** Количество синхронизированных записей за запуск, количество ошибок, время выполнения, статус последнего запуска (success / partial / failed)
- **Query (пример):** `etl_records_synced`, `etl_errors_count`, `etl_duration_seconds`
- **Алерт:** статус = failed, errors > 0

### 17. Circuit Breaker Status
- **Тип:** Stat panel
- **Описание:** Текущее состояние circuit breaker для каждого внешнего сервиса (oData ERP, Qwen Embedding, Qwen LLM, Qdrant). Значения: closed (норма), open (открыт), half-open (восстановление)
- **Query (пример):** `circuit_breaker_state{service=~"oData|qwen_embedding|qwen_llm|qdrant"}`
- **Алерт:** состояние = open

---

## Row 5: Security

### 18. Guardrail Blocks
- **Тип:** Bar chart + time series
- **Описание:** Количество срабатываний guardrails по типам: toxicity, PII leak, prompt injection, format violation. Тренд по дням
- **Query (пример):** `sum(guardrail_blocks_total) by (type)`
- **Алерт:** prompt injection > 0, toxicity > 10/day

### 19. Auth & Security Failures
- **Тип:** Time series + stat
- **Описание:** Количество неудачных аутентификаций на Gateway (RBAC denied, mTLS failures), rate limit exceeded
- **Query (пример):** `gateway_auth_failures_total{reason=~"rbac|mtls|rate_limit"}`
- **Алерт:** rbac failures > 20/hour (возможная атака)

---

## Row 6: Инфраструктурное здоровье (Infrastructure Health)

### 20. Pod Restarts & OOMKilled
- **Тип:** Stat + time series
- **Описание:** Количество рестартов подов по сервисам. Отдельный индикатор для OOMKilled —terminated reason подов
- **Query (пример):**
  - `increase(kube_pod_container_status_restarts_total{namespace="ai-support"}[1h])`
  - `kube_pod_container_status_last_terminated_reason{namespace="ai-support"}`
- **Алерт:** restarts > 3 за час, OOMKilled > 0

### 21. CPU Throttling
- **Тип:** Time series graph
- **Описание:** Процент времени CPU throttling по подам. Throttling = periods_throttled / periods_total
- **Query (пример):**
  - `rate(container_cpu_cfs_throttled_periods_total{namespace="ai-support"}[5m]) / rate(container_cpu_cfs_periods_total{namespace="ai-support"}[5m])`
- **Алерт:** throttle ratio > 50% за 5 мин

### 22. Disk Usage
- **Тип:** Gauge + time series
- **Описание:** Свободное место на дисках нод (особенно ноды с Qwen моделями). В GB и % от общего
- **Query (пример):**
  - `node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"} * 100`
- **Алерт:** < 15% свободного места

---

## Row 7: Критичные AI-метрики (Critical AI Metrics)

### 23. Hallucination Rate Trend
- **Тип:** Time series graph
- **Описание:** Доля ответов с галлюцинациями (ответ не подтверждён контекстом). Данные из monthly LLM-as-Judge проверок и.failed_cases. Целевая линия ≤ 15%
- **Query (пример):** `hallucination_rate`
- **Алерт:** > 0.20 за день

### 24. Faithfulness Trend
- **Тип:** Time series graph
- **Описание:** Тренд Faithfulness (доля ответов, основанных на контексте) по дням/неделям. Данные из failed_cases и LLM-as-Judge. Целевая линия ≥ 0.85
- **Query (пример):** `faithfulness_score_daily`
- **Алерт:**
  - Warning: < 0.85
  - Critical: < 0.70 за 2 прогона подряд
  - Trend: падение > 10% за неделю

### 25. Answer Relevancy Trend
- **Тип:** Time series graph
- **Описание:** Тренд Answer Relevancy с целевой линией (≥ 0.80). Данные из failed_cases и LLM-as-Judge
- **Query (пример):** `answer_relevancy_score_daily`
- **Алерт:** < 0.80 за день

---

## Рекомендуемые переменные дашборда

| Переменная | Описание | Пример |
|------------|----------|--------|
| `$namespace` | Kubernetes namespace | `ai-support` |
| `$service` | Фильтр по сервису | `ai-service`, `embedding-service`, `etl-worker` |
| `$time_range` | Временной диапазон | `1h`, `24h`, `7d`, `30d` |
| `$interval` | Интервал агрегации | `1m`, `5m`, `1h` |

---

## Рекомендуемые алерты (Alert Rules)

### Инфраструктура

| Алерт | Условие | Severity | Доставка |
|-------|---------|----------|----------|
| High Error Rate | error_rate > 5% за 5 мин | Critical | Telegram + PagerDuty |
| Latency Degraded | p95 > 5 сек за 10 мин | Warning | Telegram |
| Qdrant Unavailable | circuit_breaker = open | Critical | Telegram + PagerDuty |
| LLM Degraded | llm_errors > 10% за 5 мин | Error | Telegram |
| ETL Failed | etl_status = failed | Warning | Telegram |
| RAM Critical | pod RAM > 85% лимита | Warning | Telegram |
| RAM OOM Risk | pod RAM > 95% лимита | Critical | Telegram + PagerDuty |
| CPU Throttling | cpu_throttled_seconds > 0.5/sec за 5 мин | Warning | Telegram |
| Pod Restarts | kube_pod_container_status_restarts_total > 3 за 1 час | Warning | Telegram |
| OOMKilled | kube_pod_container_status_last_terminated_reason = OOMKilled | Critical | Telegram + PagerDuty |
| Disk Pressure | node_filesystem_avail_bytes < 15% на нодах с Qwen | Warning | Telegram |
| Network Errors | rate(network_errors_total[5m]) > 10/sec | Warning | Telegram |
| Cost Spike | cost_per_request > baseline × 2 за день | Error | Telegram |

### Безопасность (PII и Guardrails)

| Алерт | Условие | Severity | Доставка |
|-------|---------|----------|----------|
| PII Leakage | guardrail_blocks_total{type="pii_leak"} > 0 | Critical | Telegram + PagerDuty |
| Prompt Injection | guardrail_blocks_total{type="injection"} > 0 | Critical | Telegram + PagerDuty |
| Toxicity Spike | guardrail_blocks_total{type="toxicity"} > 10 за час | Error | Telegram |
| Format Violation | guardrail_blocks_total{type="format"} > 5% от total requests | Warning | Telegram |
| RBAC Denied Spike | gateway_auth_failures_total{reason="rbac"} > 20 за час | Error | Telegram |
| mTLS Failures | gateway_auth_failures_total{reason="mtls"} > 5 за час | Warning | Telegram |

### AI-метрики (критичные)

| Алерт | Условие | Severity | Доставка |
|-------|---------|----------|----------|
| Faithfulness Drop | faithfulness < 0.85 | Warning | Telegram |
| Faithfulness Critical | faithfulness < 0.70 за 2 прогона подряд | Critical | Telegram + PagerDuty |
| Faithfulness Trend | faithfulness упало > 10% за неделю | Warning | Telegram |
| Answer Relevancy Drop | answer_relevancy < 0.80 | Warning | Telegram |
| Hallucination Rate Spike | hallucination_rate > 0.20 за день | Error | Telegram |
| Dedup F1 Drop | dedup_f1 < 0.85 | Warning | Telegram |
| Dedup Precision Critical | dedup_precision < 0.70 | Error | Telegram |
| Token Usage Spike | avg_tokens_per_request > baseline × 2 | Warning | Telegram |
