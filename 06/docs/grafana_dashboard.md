# Дашборд Grafana: финальный список виджетов и алертов
>Пороговые значения взяты из никаких соображений. Потом установить после пилотного прогона на реальных данных
---

## Golden Signals

### 1. Traffic – Request Rate
- **Тип:** Time series graph
- **Описание:** RPS по эндпоинтам AI Service, разбивка по статусам ответа (ok / degraded / empty)
- **Query:** `sum(rate(ai_service_requests_total[5m])) by (endpoint, status)`

---

### 2. Latency – Heatmap + Percentile Lines
- **Тип:** Heatmap (основной) + наложение p50/p95/p99 линий
- **Описание:** Распределение задержек обработки запроса по этапам (embedding, vector_search, LLM, total). Heatmap показывает выбросы, линии – ключевые перцентили.
- **Queries (для p95):**
  - `histogram_quantile(0.95, rate(ai_service_request_duration_seconds_bucket[5m]))`
  - `histogram_quantile(0.95, rate(ai_service_embedding_duration_seconds_bucket[5m]))`
  - `histogram_quantile(0.95, rate(ai_service_vector_search_duration_seconds_bucket[5m]))`
  - `histogram_quantile(0.95, rate(ai_service_llm_duration_seconds_bucket[5m]))`

---

### 3. Errors – Error Rate by Component
- **Тип:** Time series graph
- **Описание:** Процент ошибок по компонентам (Gateway, AI Service, Qdrant, Qwen Embedding, Qwen LLM) с пороговыми линиями 1% и 5%
- **Query:** `sum(rate(ai_service_errors_total[5m])) by (component) / sum(rate(ai_service_requests_total[5m])) by (component) * 100`

---

### 4. Saturation – Node CPU & RAM Usage
- **Тип:** Time series graph
- **Описание:** Загрузка CPU и RAM по нодам Kubernetes, отдельно для нод с Qwen (embedding + LLM serving) и остальных
- **Queries:**
  - `instance:node_cpu_utilisation:rate5m`
  - `instance:node_memory_utilisation:ratio`

---

### 5. Saturation – Pod RAM Usage
- **Тип:** Time series graph
- **Описание:** Использование RAM по подам (AI Service, Embedding, Qwen, ETL Worker) с отображением лимитов
- **Queries:**
  - `sum(container_memory_working_set_bytes{namespace="ai-support"}) by (pod)`
  - `sum(kube_pod_container_resource_limits{resource="memory", namespace="ai-support"}) by (pod)`

---

## AI-специфичные метрики 

### 6. Token Usage per Request
- **Тип:** Time series + stat
- **Описание:** Среднее количество input и output токенов на запрос по эндпоинтам (embedding vs LLM)
- **Queries:**
  - `rate(ai_service_tokens_total{type="input"}[5m]) / rate(ai_service_requests_total[5m])`
  - `rate(ai_service_tokens_total{type="output"}[5m]) / rate(ai_service_requests_total[5m])`

---

### 7. Average Cost per Request
- **Тип:** Time series + stat
- **Описание:** Средняя стоимость запроса (embedding + LLM) на основе GPU-time или кастомной формулы
- **Query:** `rate(ai_service_cost_credits_total[5m]) / rate(ai_service_requests_total[5m])`

---

### 8. Cache Hit Ratio
- **Тип:** Time series + stat
- **Описание:** Доля попаданий в Redis-кэш по эндпоинтам
- **Query:** `sum(rate(ai_service_cache_hits_total{hit="true"}[5m])) by (endpoint) / sum(rate(ai_service_cache_hits_total[5m])) by (endpoint)`

---

### 9. Guardrail Blocks
- **Тип:** Bar chart + time series
- **Описание:** Количество срабатываний guardrails по типам (toxicity, pii_leak, injection, format)
- **Query:** `sum(guardrail_blocks_total) by (type)`

---

### 10. Faithfulness / Hallucination Rate
- **Тип:** Time series + stat
- **Описание:** Тренд Faithfulness (целевая линия ≥ 0.85) и Hallucination Rate (целевая линия ≤ 0.15)
- **Queries:**
  - `faithfulness_score_daily`
  - `hallucination_rate`

---

### 11. Top Slow Queries
- **Тип:** Table
- **Описание:** Топ-20 самых медленных запросов за последний час с trace_id, latency, endpoint, cache_hit
- **Query:** SQL-запрос к query_log или `topk(20, ai_service_request_duration_seconds{quantile="0.95"})`

---

## переменные дашборда

| Переменная | Описание | Пример |
|------------|----------|--------|
| `$namespace` | Kubernetes namespace | `ai-support` |
| `$service` | Фильтр по сервису | `ai-service`, `embedding-service` |
| `$time_range` | Временной диапазон | `1h`, `24h`, `7d` |
| `$interval` | Интервал агрегации | `1m`, `5m`, `1h` |

---

## Алерты

| Алерт | Условие | Severity | Доставка |
|-------|---------|----------|----------|
| **High Error Rate** | `error_rate > 5%` за 5 мин | Critical | Telegram + PagerDuty |
| **Latency Degraded** | `p95 total > 5 сек` за 10 мин | Warning | Telegram |
| **RAM OOM Risk** | `pod RAM > 95%` лимита | Critical | Telegram + PagerDuty |
| **RAM Warning** | `pod RAM > 85%` лимита | Warning | Telegram |
| **CPU Throttling** | `rate(container_cpu_cfs_throttled_periods_total[5m]) / rate(container_cpu_cfs_periods_total[5m]) > 0.5` | Warning | Telegram |
| **Token Usage Spike** | `avg output tokens per request > 2000` | Warning | Telegram |
| **Cost Spike** | `cost_per_request > baseline × 2` за день | Error | Telegram |
| **Cache Hit Low** | `cache_hit_ratio < 0.30` за 5 мин | Warning | Telegram |
| **Faithfulness Drop** | `faithfulness_score_daily < 0.85` | Warning | Telegram |
| **Faithfulness Critical** | `faithfulness_score_daily < 0.70` за 2 прогона подряд | Critical | Telegram + PagerDuty |
| **Hallucination Spike** | `hallucination_rate > 0.20` за день | Error | Telegram |
| **PII Leakage** | `guardrail_blocks_total{type="pii_leak"} > 0` | Critical | Telegram + PagerDuty |
| **Prompt Injection** | `guardrail_blocks_total{type="injection"} > 0` | Critical | Telegram + PagerDuty |
| **Toxicity Spike** | `guardrail_blocks_total{type="toxicity"} > 10` за час | Error | Telegram |
| **Format Violation** | `guardrail_blocks_total{type="format"} > 5% от total requests` | Warning | Telegram |
| **ETL Stale** | `time() - etl_last_success_timestamp > 86400` (сутки) | Warning | Telegram |
| **ETL Failed** | `etl_status == failed` | Critical | PagerDuty |
| **No Incoming Traffic** | `sum(rate(ai_service_requests_total[10m])) == 0` в рабочие часы | Warning | Telegram |

