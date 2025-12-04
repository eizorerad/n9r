# План внедрения: Исправление системы прогресса

## 🎯 Два варианта решения

### Вариант A: Quick Fixes (1-2 дня, низкий риск)
Минимальные изменения для устранения критических проблем.

### Вариант B: Полный рефакторинг (5-7 дней, средний риск)
Системное решение с правильной архитектурой.

---

## 🚀 Вариант A: Quick Fixes (РЕКОМЕНДУЕТСЯ СНАЧАЛА)

### Цель
Исправить критические проблемы минимальными изменениями, чтобы система работала стабильно.

### Fix #1: Не добавлять embeddings task преждевременно

**Файл:** `frontend/hooks/use-analysis-stream.ts`
**Строки:** 302-311
**Действие:** Удалить блок кода, который добавляет embeddings task

```typescript
// УДАЛИТЬ весь этот блок:
const embeddingsTaskId = `embeddings-${repositoryId}`
console.log('[Analysis Complete] Adding embeddings task:', embeddingsTaskId)
addTask({
  id: embeddingsTaskId,
  type: 'embeddings',
  repositoryId,
  status: 'pending',
  progress: 0,
  stage: 'waiting',
  message: 'Waiting for embeddings to start...',
})
console.log('[Analysis Complete] Embeddings task added')
```

**Почему:** Task будет добавлен автоматически в semantic-analysis-section когда polling увидит РЕАЛЬНЫЙ status='running' от backend.

**Результат:** Прогресс-бар не будет показывать "ghost" embeddings task который сразу исчезает.

**Время:** 30 минут

---

### Fix #2: Backend возвращает "unknown" когда не уверен

**Файл:** `backend/app/api/v1/semantic.py`
**Строки:** 1169-1207
**Действие:** Изменить логику fallback

Вместо попытки угадать состояние по Qdrant векторам, честно возвращать "unknown" когда:
- Нет Redis state
- В Qdrant есть векторы
- НО semantic_cache = NULL (значит ещё вычисляется)

**Код изменения:**

```python
# Когда нет Redis state но есть векторы в Qdrant:
if count.count > 0:
    # Попытка найти analysis с готовым semantic_cache
    from app.models.analysis import Analysis
    
    last_cached = await db.execute(
        select(Analysis)
        .where(
            Analysis.repository_id == repository_id,
            Analysis.semantic_cache.isnot(None),
        )
        .order_by(Analysis.created_at.desc())
        .limit(1)
    )
    cached_analysis = last_cached.scalar_one_or_none()
    
    if cached_analysis and cached_analysis.semantic_cache:
        # Есть готовый cache - можем вернуть completed
        return EmbeddingStatusResponse(
            repository_id=str(repository_id),
            status="completed",
            stage="completed",
            progress=100,
            message=f"{count.count} vectors available",
            chunks_processed=count.count,
            vectors_stored=count.count,
            analysis_id=str(cached_analysis.id),
        )
    else:
        # Векторы есть, но cache НЕ готов - возвращаем unknown
        return EmbeddingStatusResponse(
            repository_id=str(repository_id),
            status="unknown",
            stage="computing",
            progress=50,
            message="Vectors exist, computing semantic analysis...",
            chunks_processed=count.count,
            vectors_stored=count.count,
            analysis_id=None,
        )
```

**Результат:** Frontend не будет видеть ложный "completed" пока semantic_cache действительно не готов.

**Время:** 1 час

---

### Fix #3: Frontend обрабатывает "unknown" status

**Файл:** `frontend/components/semantic-analysis-section.tsx`
**Строки:** 214
**Действие:** Добавить обработку unknown status

```typescript
const isNone = data.status === 'none'
const isUnknown = data.status === 'unknown'

// После проверки isStaleStatus, добавить:
if (isUnknown) {
  console.log('[SemanticAnalysis] Backend computing state, continue polling')
  if (taskExists) {
    updateTask(taskId, {
      status: 'running',
      stage: 'computing',
      message: 'Computing semantic analysis...',
      progress: 50,
    })
  }
  return // Продолжаем polling
}
```

**Результат:** Frontend корректно обрабатывает неопределённое состояние.

**Время:** 15 минут

---

### Fix #4: Увеличить polling intervals

**Файл:** `frontend/components/semantic-analysis-section.tsx`
**Строки:** 432-439
**Действие:** Изменить интервалы polling

```typescript
// Более консервативные интервалы:
const shouldPollFast = isNowInProgress && pollCount <= 20
const shouldPollMedium = taskExists || isNone || pollCount <= 30
const shouldPollSlow = isNowCompleted || pollCount > 30

const newInterval = shouldPollSlow ? 10000 : 
                   (shouldPollFast ? 2000 : 5000)
```

**Результат:** Меньше нагрузка на backend, меньше лишних UI updates.

**Время:** 10 минут

---

### Fix #5: Debounce semantic cache refresh

**Файл:** `frontend/components/semantic-analysis-section.tsx`
**Строки:** 385-391
**Действие:** Добавить debouncing с cancellation

```typescript
// Добавить ref для timeout:
const refreshTimeoutRef = useRef<NodeJS.Timeout>()

// В cleanup effect:
useEffect(() => {
  return () => {
    if (refreshTimeoutRef.current) {
      clearTimeout(refreshTimeoutRef.current)
    }
  }
}, [])

// В логике refresh:
if (needsRefresh) {
  console.log('[SemanticAnalysis] Triggering cache refresh after delay...')
  
  // Cancel previous timeout если есть
  if (refreshTimeoutRef.current) {
    clearTimeout(refreshTimeoutRef.current)
  }
  
  // Schedule new refresh с увеличенной задержкой
  refreshTimeoutRef.current = setTimeout(() => {
    console.log('[SemanticAnalysis] Executing cache refresh now')
    setRefreshKey(k => k + 1)
    refreshTimeoutRef.current = undefined
  }, 2000)  // Увеличено с 500ms до 2000ms
}
```

**Результат:** Cache успевает сгенерироваться до первого fetch, меньше лишних запросов.

**Время:** 20 минут

---

## 📊 Итого Quick Fixes

| Fix | Файл | Время | Приоритет |
|-----|------|-------|-----------|
| #1 | use-analysis-stream.ts | 30 мин | 🔴 Критический |
| #2 | semantic.py | 1 час | 🔴 Критический |
| #3 | semantic-analysis-section.tsx | 15 мин | 🔴 Критический |
| #4 | semantic-analysis-section.tsx | 10 мин | 🟡 Высокий |
| #5 | semantic-analysis-section.tsx | 20 мин | 🟡 Высокий |

**Общее время: 2-3 часа**

**Ожидаемый результат:**
- ✅ Прогресс-бар не "мигает" (не появляется/исчезает)
- ✅ Не показывает ложный "completed"
- ✅ Меньше нагрузка на backend (меньше polling)
- ✅ UI меньше дёргается
- ⚠️ Всё ещё могут быть редкие edge cases

---

## 🏗️ Вариант B: Полный рефакторинг (долгосрочное решение)

### Зачем нужен полный рефакторинг?

Quick fixes решают 80-90% проблем, но:
- Остаются edge cases когда Redis TTL истекает
- Архитектура всё ещё сложная (multiple sources of truth)
- Трудно добавлять новые features
- Трудно дебажить проблемы

### Ключевые изменения

#### 1. PostgreSQL как единственный source of truth

**Новые поля в Analysis table:**
```sql
embeddings_status VARCHAR(20) DEFAULT 'none'
embeddings_progress INTEGER DEFAULT 0  
embeddings_message TEXT
embeddings_started_at TIMESTAMP
embeddings_completed_at TIMESTAMP
embeddings_vectors_count INTEGER DEFAULT 0
```

**Преимущества:**
- Permanent storage (не теряется при restart)
- Можно query точное состояние любого analysis
- Redis используется только для live updates (optional)

#### 2. Добавить analysis_id в Qdrant векторы

**Новая структура payload:**
```json
{
  "repository_id": "499bb544-36bb-45dd-823e-fbf4d45abd4b",
  "commit_sha": "16e04f9afdd886b5cfc51862deb8f169d203cbff",
  "analysis_id": "6aa4e309-7f82-4a26-a9cf-2652d1862b19",
  "file_path": "backend/app/main.py",
  "language": "python",
  "chunk_type": "function",
  "name": "analyze_code",
  "content": "def analyze_code():\n    pass"
}
```

**Миграция существующих векторов:**
- Script который находит analysis по repository_id + commit_sha
- Обновляет payload каждого вектора

#### 3. Embeddings worker обновляет PostgreSQL

**При старте:**
```python
UPDATE analyses 
SET embeddings_status = 'running',
    embeddings_started_at = NOW(),
    embeddings_progress = 0
WHERE id = analysis_id
```

**При прогрессе:**
```python
UPDATE analyses
SET embeddings_progress = 45,
    embeddings_message = 'Embedding batch 10/20...',
    embeddings_vectors_count = 500
WHERE id = analysis_id
```

**При завершении:**
```python
UPDATE analyses
SET embeddings_status = 'completed',
    embeddings_completed_at = NOW(),
    embeddings_progress = 100,
    embeddings_vectors_count = 1025
WHERE id = analysis_id
```

#### 4. Новый упрощённый API endpoint

```
GET /analyses/{analysis_id}/embeddings-status
```

Возвращает:
```json
{
  "analysis_id": "6aa4e309-...",
  "embeddings_status": "running",
  "embeddings_progress": 45,
  "embeddings_message": "Embedding batch 10/20...",
  "embeddings_vectors_count": 500,
  "semantic_cache_ready": false
}
```

**Логика:** Просто читает из PostgreSQL. Никаких fallbacks, никаких угадываний.

#### 5. Frontend упрощение

**БЫЛО:** Manual polling с сложной логикой
**СТАЛО:** React Query с auto-refetch

```typescript
const { data: embeddingsStatus } = useQuery({
  queryKey: ['embeddings', selectedAnalysisId],
  queryFn: () => api.getEmbeddingsStatus(selectedAnalysisId),
  enabled: !!selectedAnalysisId,
  refetchInterval: (data) => {
    // Refetch только когда нужно
    if (data?.embeddings_status === 'running') return 2000
    if (data?.embeddings_status === 'completed' && !data?.semantic_cache_ready) return 5000
    return false // Остановить polling
  },
})

// Sync с progress store:
useEffect(() => {
  if (!embeddingsStatus) return
  
  if (embeddingsStatus.embeddings_status === 'running') {
    if (!hasTask(taskId)) {
      addTask({id: taskId, type: 'embeddings', ...embeddingsStatus})
    } else {
      updateTask(taskId, embeddingsStatus)
    }
  } else if (embeddingsStatus.embeddings_status === 'completed') {
    if (hasTask(taskId)) {
      updateTask(taskId, {status: 'completed', progress: 100})
      setTimeout(() => removeTask(taskId), 2000)
    }
  }
}, [embeddingsStatus])
```

---

## 📋 Детальный план рефакторинга

### Фаза 1: Backend Foundation (2-3 дня)

#### Task 1.1: Database migration (2 часа)

**Создать:** `backend/alembic/versions/007_embeddings_tracking.py`

```python
"""Add embeddings tracking to Analysis table

Revision ID: 007
Revises: 006
Create Date: 2025-12-04
"""

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('analyses', 
        sa.Column('embeddings_status', sa.String(20), 
                 server_default='none', nullable=False))
    op.add_column('analyses',
        sa.Column('embeddings_progress', sa.Integer, 
                 server_default='0', nullable=False))
    op.add_column('analyses',
        sa.Column('embeddings_message', sa.Text, nullable=True))
    op.add_column('analyses',
        sa.Column('embeddings_started_at', sa.DateTime, nullable=True))
    op.add_column('analyses',
        sa.Column('embeddings_completed_at', sa.DateTime, nullable=True))
    op.add_column('analyses',
        sa.Column('embeddings_vectors_count', sa.Integer, 
                 server_default='0', nullable=False))
    
    op.create_index('ix_analyses_embeddings_status', 
                   'analyses', ['embeddings_status'])

def downgrade():
    op.drop_index('ix_analyses_embeddings_status')
    op.drop_column('analyses', 'embeddings_status')
    op.drop_column('analyses', 'embeddings_progress')
    op.drop_column('analyses', 'embeddings_message')
    op.drop_column('analyses', 'embeddings_started_at')
    op.drop_column('analyses', 'embeddings_completed_at')
    op.drop_column('analyses', 'embeddings_vectors_count')
```

**Запустить:** `cd backend && alembic upgrade head`

---

#### Task 1.2: Update Analysis model (30 мин)

**Файл:** `backend/app/models/analysis.py`

Добавить новые поля в класс Analysis:

```python
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer, Text, DateTime

class Analysis(Base):
    __tablename__ = "analyses"
    
    # Existing fields here
    
    # Embeddings tracking
    embeddings_status: Mapped[str] = mapped_column(String(20), default="none")
    embeddings_progress: Mapped[int] = mapped_column(Integer, default=0)
    embeddings_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    embeddings_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    embeddings_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    embeddings_vectors_count: Mapped[int] = mapped_column(Integer, default=0)
```

---

#### Task 1.3: Qdrant migration script (3 часа)

**Создать:** `backend/scripts/migrate_qdrant_add_analysis_id.py`

Скрипт который:
1. Читает все векторы из Qdrant
2. Группирует по repository_id + commit_sha
3. Находит соответствующий Analysis в PostgreSQL
4. Обновляет payload.analysis_id для каждого вектора

**Запустить после деплоя:** `python backend/scripts/migrate_qdrant_add_analysis_id.py`

---

#### Task 1.4: Обновить embeddings worker (4 часа)

**Файл:** `backend/app/workers/embeddings.py`

**Изменение #1:** При старте обновлять PostgreSQL

```python
def generate_embeddings(self, repository_id: str, commit_sha: str,
                       files: list[dict], analysis_id: str) -> dict:
    
    logger.info(f"Generating embeddings for repository {repository_id}")
    
    # UPDATE PostgreSQL ПРИ СТАРТЕ
    from app.core.database import get_sync_session
    from app.models.analysis import Analysis
    
    with get_sync_session() as db:
        analysis = db.get(Analysis, UUID(analysis_id))
        if analysis:
            analysis.embeddings_status = 'running'
            analysis.embeddings_started_at = datetime.utcnow()
            analysis.embeddings_progress = 0
            analysis.embeddings_message = 'Starting embeddings...'
            db.commit()
            logger.info(f"Updated analysis {analysis_id} embeddings_status to 'running'")
    
    # Helper function для progress updates
    def publish_progress(stage: str, progress: int, message: str | None = None,
                        status: str = "running", chunks: int = 0, vectors: int = 0):
        # Update PostgreSQL
        with get_sync_session() as db:
            analysis = db.get(Analysis, UUID(analysis_id))
            if analysis:
                analysis.embeddings_progress = progress
                analysis.embeddings_message = message
                analysis.embeddings_vectors_count = vectors
                db.commit()
        
        # OPTIONAL: Publish to Redis для real-time updates
        publish_embedding_progress(
            repository_id=repository_id,
            stage=stage,
            progress=progress,
            message=message,
            status=status,
            chunks_processed=chunks,
            vectors_stored=vectors,
            analysis_id=analysis_id,
        )
        
        self.update_state(state="PROGRESS", meta={"stage": stage, "progress": progress})
    
    try:
        publish_progress("initializing", 5, "Starting embedding generation...")
        
        chunker = get_code_chunker()
        from app.services.llm_gateway import get_llm_gateway
        llm = get_llm_gateway()
        qdrant = get_qdrant_client()
        
        # Generate chunks and embeddings (existing logic)
        
        # CREATE POINTS with analysis_id
        for chunk, embedding in chunk_embedding_pairs:
            point_id = f"{repository_id}_{chunk.file_path}_{chunk.line_start}".replace("/", "_").replace(".", "_")
            
            points.append(PointStruct(
                id=hash(point_id) % (2**63),
                vector=embedding,
                payload={
                    "repository_id": repository_id,
                    "commit_sha": commit_sha,
                    "analysis_id": analysis_id,  # ДОБАВИТЬ analysis_id!
                    "file_path": chunk.file_path,
                    "language": chunk.language,
                    "chunk_type": chunk.chunk_type,
                    "name": chunk.name,
                    "line_start": chunk.line_start,
                    "line_end": chunk.line_end,
                    "parent_name": chunk.parent_name,
                    "docstring": chunk.docstring,
                    "content": chunk.content[:2000],
                    "token_estimate": chunk.token_estimate,
                    "level": chunk.level,
                    "qualified_name": chunk.qualified_name,
                    "cyclomatic_complexity": chunk.cyclomatic_complexity,
                    "line_count": chunk.line_count,
                    "cluster_id": None,
                }
            ))
        
        logger.info(f"Generated {len(points)} embedding vectors")
        publish_progress("indexing", 85, "Storing vectors in Qdrant...", 
                        chunks=len(all_chunks), vectors=len(points))
        
        # Store in Qdrant (existing logic)
        
        # Compute semantic cache (existing logic)
        semantic_cache = None
        if analysis_id and len(points) >= 5:
            publish_progress("semantic_analysis", 92, "Computing semantic analysis...",
                           chunks=len(all_chunks), vectors=len(points))
            try:
                semantic_cache = _compute_and_store_semantic_cache(
                    repository_id=repository_id,
                    analysis_id=analysis_id,
                )
            except Exception as e:
                logger.warning(f"Failed to compute semantic cache: {e}")
        
        # UPDATE PostgreSQL ПРИ ЗАВЕРШЕНИИ
        with get_sync_session() as db:
            analysis = db.get(Analysis, UUID(analysis_id))
            if analysis:
                analysis.embeddings_status = 'completed'
                analysis.embeddings_completed_at = datetime.utcnow()
                analysis.embeddings_progress = 100
                analysis.embeddings_vectors_count = len(points)
                db.commit()
                logger.info(f"Updated analysis {analysis_id} embeddings_status to 'completed'")
        
        # Publish completion
        publish_progress("completed", 100, f"Generated {len(points)} embeddings",
                        status="completed", chunks=len(all_chunks), vectors=len(points))
        
        return {
            "repository_id": repository_id,
            "commit_sha": commit_sha,
            "chunks_processed": len(all_chunks),
            "vectors_stored": len(points),
            "status": "completed",
            "semantic_cache_computed": semantic_cache is not None,
        }
        
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        
        # UPDATE PostgreSQL ON ERROR
        with get_sync_session() as db:
            analysis = db.get(Analysis, UUID(analysis_id))
            if analysis:
                analysis.embeddings_status = 'error'
                analysis.embeddings_message = str(e)[:500]
                db.commit()
        
        publish_embedding_progress(
            repository_id=repository_id,
            stage="error",
            progress=0,
            message=str(e),
            status="error",
            analysis_id=analysis_id,
        )
        raise
```

---

#### Task 1.5: Новый API endpoint (1 час)

**Файл:** `backend/app/api/v1/analyses.py`

Добавить новый endpoint:

```python
class EmbeddingsStatusResponse(BaseModel):
    analysis_id: str
    embeddings_status: str
    embeddings_progress: int
    embeddings_message: str | None
    embeddings_vectors_count: int
    semantic_cache_ready: bool
    started_at: str | None
    completed_at: str | None

@router.get("/analyses/{analysis_id}/embeddings-status")
async def get_analysis_embeddings_status(
    analysis_id: UUID,
    db: DbSession,
    user: CurrentUser,
) -> EmbeddingsStatusResponse:
    """Get embeddings status for specific analysis.
    
    Source of truth: PostgreSQL Analysis table.
    No fallbacks, no guessing - just return exact state.
    """
    result = await db.execute(
        select(Analysis)
        .join(Repository)
        .where(
            Analysis.id == analysis_id,
            Repository.owner_id == user.id,
        )
    )
    analysis = result.scalar_one_or_none()
    
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    
    return EmbeddingsStatusResponse(
        analysis_id=str(analysis.id),
        embeddings_status=analysis.embeddings_status or 'none',
        embeddings_progress=analysis.embeddings_progress or 0,
        embeddings_message=analysis.embeddings_message,
        embeddings_vectors_count=analysis.embeddings_vectors_count or 0,
        semantic_cache_ready=analysis.semantic_cache is not None,
        started_at=analysis.embeddings_started_at.isoformat() if analysis.embeddings_started_at else None,
        completed_at=analysis.embeddings_completed_at.isoformat() if analysis.embeddings_completed_at else None,
    )
```

---

### Фаза 2: Frontend Refactoring (2 дня)

#### Task 2.1: Переключиться на новый endpoint (1 час)

**Файл:** `frontend/components/semantic-analysis-section.tsx`

Изменить fetchStatus чтобы использовать новый endpoint:

```typescript
const fetchStatus = async (): Promise<EmbeddingStatus | null> => {
  if (!selectedAnalysisId) return null
  
  try {
    const response = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/analyses/${selectedAnalysisId}/embeddings-status`,
      { headers: { 'Authorization': `Bearer ${token}` } }
    )
    
    if (response.ok) {
      const data = await response.json()
      return {
        repository_id: repositoryId,
        status: data.embeddings_status,
        stage: data.embeddings_status,
        progress: data.embeddings_progress,
        message: data.embeddings_message,
        chunks_processed: data.embeddings_vectors_count,
        vectors_stored: data.embeddings_vectors_count,
        analysis_id: data.analysis_id,
      }
    }
  } catch (error) {
    console.error('Failed to fetch status:', error)
  }
  return null
}
```

#### Task 2.2: Упростить polling logic (3 часа)

**Файл:** `frontend/components/semantic-analysis-section.tsx`

Убрать всю сложную логику с isStaleStatus, taskExists checks.

Новая упрощённая логика:

```typescript
const poll = async () => {
  if (!isMounted) return
  
  const data = await fetchStatus()
  if (!isMounted || !data) return
  
  setEmbeddingStatus(data)
  
  // Простая логика на основе status
  const status = data.status
  const taskExists = hasTask(taskId)
  
  if (status === 'running') {
    if (!taskExists) {
      addTask({
        id: taskId,
        type: 'embeddings',
        repositoryId,
        status: 'running',
        progress: data.progress,
        stage: data.stage,
        message: data.message,
      })
    } else {
      updateTask(taskId, {
        status: 'running',
        progress: data.progress,
        stage: data.stage,
        message: data.message,
      })
    }
  } else if (status === 'completed') {
    if (taskExists) {
      updateTask(taskId, {
        status: 'completed',
        progress: 100,
        stage: 'completed',
        message: `${data.vectors_stored} vectors available`,
      })
      setTimeout(() => removeTask(taskId), 2000)
    }
    
    // Refresh cache если не готов
    if (!semanticCache?.is_cached) {
      setTimeout(() => setRefreshKey(k => k + 1), 2000)
    } else {
      // Cache готов - остановить polling
      if (intervalId) {
        clearInterval(intervalId)
        intervalId = null
      }
      return
    }
  }
  
  // Остановить polling если всё готово
  const allDone = status === 'completed' && semanticCache?.is_cached
  if (allDone && intervalId) {
    clearInterval(intervalId)
    intervalId = null
  }
}
```

#### Task 2.3: Опционально - React Query (4 часа)

**Файл:** `frontend/components/semantic-analysis-section.tsx`

Полностью заменить manual polling на React Query для более чистого кода.

---

### Фаза 3: Testing & Rollout (1 день)

#### Task 3.1: Integration tests (3 часа)

Тесты для:
- Полный цикл: analysis → embeddings → clustering → cache ready
- Edge case: Redis TTL истекает во время embeddings
- Edge case: Server restart во время embeddings
- Multiple analyses параллельно

#### Task 3.2: Manual testing (2 часа)

- Запустить 5-10 analyses подряд
- Проверить прогресс-бар на всех этапах
- Проверить что semantic cache появляется
- Проверить что нет "ghost" tasks

#### Task 3.3: Production rollout (2 часа)

1. Deploy backend с миграцией
2. Запустить Qdrant migration script
3. Deploy frontend
4. Мониторинг в течение часа

---

## 📊 Метрики успеха

После внедрения измерить:

### Quick Fixes (Вариант A):
- ✅ Прогресс-бар не "мигает" (появляется/исчезает)
- ✅ Не показывает ложный "completed" в начале
- ✅ Polling requests < 20 за время embeddings (было 30-50)
- ✅ UI renders < 50 за время embeddings (было 100+)

### Полный рефакторинг (Вариант B):
- ✅ Все вышеперечисленное +
- ✅ Time to semantic_cache ready < 15 сек (было 20-40 сек)
- ✅ Zero false "completed" events
- ✅ Работает после Redis TTL expiry
- ✅ Работает после server restart
- ✅ Можно запускать multiple analyses параллельно

---

## ⚠️ Риски

### Quick Fixes (низкий риск):
- Могут остаться редкие edge cases
- Не решает фундаментальную архитектурную проблему

### Полный рефакторинг (средний риск):
- Требует координированного deploy backend + frontend
- Qdrant migration может занять время на production
- Нужен rollback план если что-то пойдёт не так

---

## 🎬 Рекомендуемая последовательность

### Неделя 1 (Quick Wins):

**День 1:**
- ✅ Fix #1: Убрать preemptive task (30 мин)
- ✅ Fix #2: Return "unknown" (1 час)
- ✅ Fix #3: Handle "unknown" (15 мин)
- ✅ Deploy и тестирование (2 часа)

**День 2:**
- ✅ Fix #4: Увеличить intervals (10 мин)
- ✅ Fix #5: Debounce refresh (20 мин)
- ✅ Testing и monitoring (3 часа)

**Результат:** Система работает стабильно на 90%

### Неделя 2 (Если нужна идеальная архитектура):

**День 3-4:**
- Database migration
- Analysis model update
- Embeddings worker update
- Qdrant migration script

**День 5-6:**
- Новый API endpoint
- Frontend переключение
- Упрощение polling logic

**День 7:**
- Integration testing
- Production rollout
- Мониторинг

---

## 📝 Для передачи разработчику

### Что было сделано (НЕ помогло полностью):

1. **Увеличен Qdrant timeout** → убрал timeout errors ✅
2. **Исправлен cache endpoint** → убрал 404 ошибки ✅
3. **Stale status detection** → частично работает ⚠️
4. **Qdrant fallback logic** → создал новые проблемы ❌
5. **Commit timeline race fix** → помог немного ⚠️

### Корневая причина:

**Проблема:** Qdrant не хранит analysis_id в векторах. Когда Redis TTL истекает или сервер перезагружается, backend не может определить какому analysis принадлежат векторы. Он пытается угадать → возвращает неправильный status → frontend показывает ложный "completed" → прогресс-бар мигает.

### Что делать:

**Немедленно (сегодня):** Сделать Quick Fixes #1-3 (2 часа) - это решит 80% проблем.

**На этой неделе:** Сделать Quick Fixes #4-5 (30 мин) - улучшит UX.

**На следующей неделе (по желанию):** Полный рефакторинг с PostgreSQL tracking и analysis_id в Qdrant - это сделает архитектуру правильной и расширяемой.

### Критические файлы:

Backend:
- `backend/app/api/v1/semantic.py` - embedding-status endpoint с проблемной fallback логикой
- `backend/app/workers/embeddings.py` - worker который не обновляет PostgreSQL
- `backend/app/models/analysis.py` - нужны новые поля для tracking

Frontend:
- `frontend/hooks/use-analysis-stream.ts` - preemptive task creation (строка 302)
- `frontend/components/semantic-analysis-section.tsx` - сложный polling (строки 162-453)

### Документы:
- `ARCHITECTURE_ANALYSIS.md` - детальный анализ проблем и архитектуры
- `IMPLEMENTATION_PLAN.md` - этот план с пошаговыми инструкциями