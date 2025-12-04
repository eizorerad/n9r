# План исправления системы прогресса - Краткая версия

## 🔴 Критическая проблема

**Симптом:** Прогресс-бар появляется → исчезает → появляется снова. Показывает "completed" хотя embeddings не начались.

**Корневая причина:**
1. Qdrant НЕ хранит analysis_id в векторах
2. Redis TTL истекает или сервер перезагружается
3. Backend не может определить какому analysis принадлежат векторы
4. Пытается угадать → возвращает неправильный status
5. Frontend добавляет task ДО начала работы
6. Task закрывается преждевременно

---

## ⚡ Quick Fixes (2-3 часа, решает 80% проблем)

### Fix 1: Убрать preemptive task creation
**Где:** `frontend/hooks/use-analysis-stream.ts:302-311`
**Что:** Удалить addTask для embeddings - пусть добавляется только когда реально running
**Время:** 30 минут

### Fix 2: Backend возвращает "unknown" вместо "completed"
**Где:** `backend/app/api/v1/semantic.py:1169-1207`
**Что:** Когда нет Redis state и semantic_cache = NULL, вернуть status="unknown"
**Время:** 1 час

### Fix 3: Frontend обрабатывает "unknown"
**Где:** `frontend/components/semantic-analysis-section.tsx:214`
**Что:** Добавить `if (isUnknown) { continue polling }`
**Время:** 15 минут

### Fix 4: Увеличить polling intervals
**Где:** `frontend/components/semantic-analysis-section.tsx:432-439`
**Что:** Изменить с 2000ms на 5000ms или 10000ms в зависимости от состояния
**Время:** 10 минут

### Fix 5: Debounce cache refresh
**Где:** `frontend/components/semantic-analysis-section.tsx:385-391`
**Что:** Добавить debouncing с cancellation, увеличить delay до 2000ms
**Время:** 20 минут

---

## 🏗️ Полный рефакторинг (5-7 дней, правильная архитектура)

### Фаза 1: Backend (2-3 дня)

#### 1.1 Database Migration
Добавить в Analysis table:
- embeddings_status VARCHAR(20)
- embeddings_progress INTEGER
- embeddings_message TEXT
- embeddings_started_at TIMESTAMP
- embeddings_completed_at TIMESTAMP
- embeddings_vectors_count INTEGER

**Файл:** `backend/alembic/versions/007_embeddings_tracking.py`
**Время:** 2 часа

#### 1.2 Update Analysis Model
Добавить новые поля в модель
**Файл:** `backend/app/models/analysis.py`
**Время:** 30 минут

#### 1.3 Qdrant Migration
Script для добавления analysis_id в payload всех существующих векторов
**Файл:** `backend/scripts/migrate_qdrant_add_analysis_id.py`
**Время:** 3 часа

#### 1.4 Update Embeddings Worker
Worker должен:
- При старте: UPDATE Analysis SET embeddings_status='running'
- При прогрессе: UPDATE embeddings_progress, embeddings_message
- При создании векторов: добавлять analysis_id в payload
- При завершении: UPDATE embeddings_status='completed'

**Файл:** `backend/app/workers/embeddings.py`
**Время:** 4 часа

#### 1.5 New API Endpoint
Создать GET /analyses/{id}/embeddings-status
Читает только из PostgreSQL, без fallbacks

**Файл:** `backend/app/api/v1/analyses.py`
**Время:** 1 час

### Фаза 2: Frontend (2 дня)

#### 2.1 Switch to New Endpoint
Изменить fetchStatus для использования нового endpoint
**Файл:** `frontend/components/semantic-analysis-section.tsx`
**Время:** 1 час

#### 2.2 Simplify Polling Logic
Убрать всю сложную логику с isStaleStatus checks
Простая switch по status
**Файл:** `frontend/components/semantic-analysis-section.tsx`
**Время:** 3 часа

#### 2.3 React Query (Optional)
Заменить manual polling на React Query
**Файл:** `frontend/components/semantic-analysis-section.tsx`
**Время:** 4 часа

### Фаза 3: Testing (1 день)

- Integration tests
- Manual testing
- Production rollout
- Monitoring

---

## 🎯 Рекомендация

### Сегодня/завтра - сделать Quick Fixes:
1. Fix #1 (30 мин) - критический
2. Fix #2 (1 час) - критический  
3. Fix #3 (15 мин) - критический

**Итого: 2 часа** → система работает на 80% лучше

### Следующая неделя - полный рефакторинг:
Если нужна идеальная архитектура без костылей

---

## 📝 Для передачи другому разработчику

### Краткое резюме что было сделано:

**Проблема:** Прогресс-бар мигает, показывает ложный completed, semantic analysis не обновляется.

**Что пытались исправить:**
1. Увеличен Qdrant timeout - помогло с timeout errors
2. Исправлен cache endpoint - убрал 404 ошибки
3. Stale status detection - частично работает
4. Qdrant fallback - создал новые проблемы
5. Race condition fixes - помогло немного

**Корневая причина:**
- Qdrant не хранит analysis_id
- Когда Redis state теряется, backend угадывает → неправильный status
- Frontend создаёт task преждевременно → ghost task

**Что нужно сделать:**
- Quick Fix #1-3 (обязательно, 2 часа)
- Quick Fix #4-5 (желательно, 30 минут)
- Полный рефакторинг (опционально, 5-7 дней)

**Критические файлы:**
- `backend/app/api/v1/semantic.py:1087-1220` - fallback logic
- `frontend/hooks/use-analysis-stream.ts:302-311` - preemptive task
- `frontend/components/semantic-analysis-section.tsx:162-453` - polling
- `backend/app/workers/embeddings.py:90-366` - worker

**Документы:**
- `ARCHITECTURE_ANALYSIS.md` - полный анализ
- `REFACTORING_PLAN.md` - этот план
- Console логи - показывают симптомы