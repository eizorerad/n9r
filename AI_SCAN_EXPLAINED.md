# AI Scan Architecture Explained

## Table of Contents
- [Overview](#overview)
- [Parallel vs Sequential Execution](#parallel-vs-sequential-execution)
- [AI Scan Pipeline](#ai-scan-pipeline)
- [Prompts and Agents](#prompts-and-agents)
- [Models and Configuration](#models-and-configuration)
- [State Management](#state-management)
- [Real-Time Progress Updates](#real-time-progress-updates)

---

## Overview

The **AI Scan** is one of three parallel analysis tracks in the Necromancer (n9r) platform that performs AI-powered code analysis to detect security vulnerabilities, code quality issues, and architectural problems using Large Language Models (LLMs).

### Three Parallel Analysis Tracks

When you trigger an analysis, **three independent tasks run in parallel**:

1. **Static Analysis** (`analyze_repository`)
   - Calculates VCI (Vibe-Code Index) score
   - Uses radon, lizard, and tree-sitter for static analysis
   - Analyzes complexity, duplication, maintainability

2. **Embeddings Generation** (`generate_embeddings_parallel`)
   - Creates vector embeddings of code chunks
   - Stores in Qdrant vector database
   - Enables semantic search and clustering

3. **AI Scan** (`run_ai_scan`) 👈 **This document focuses on this track**
   - Uses multiple LLMs to analyze code
   - Detects security issues, bugs, code smells
   - Provides actionable remediation suggestions

All three tracks:
- Start immediately when analysis is triggered
- Clone the repository independently
- Run in separate Celery workers
- Update progress independently
- Use PostgreSQL as the single source of truth for state

---

## Parallel vs Sequential Execution

### Track-Level: **PARALLEL** ✅

The three main analysis tracks (Static Analysis, Embeddings, AI Scan) run **in parallel**:

```python
# File: backend/app/api/v1/analyses.py (lines 236-253)

# All three tasks dispatched simultaneously
analyze_repository.delay(...)           # Task 1: Static Analysis
generate_embeddings_parallel.delay(...) # Task 2: Embeddings  
run_ai_scan.delay(...)                  # Task 3: AI Scan
```

**Benefits:**
- **~50% faster** total analysis time
- Independent failures (one track failing doesn't stop others)
- Better resource utilization

### Within AI Scan: **MIXED** ⚡

The AI Scan itself uses both parallel and sequential execution strategically:

#### Phase 1: Repository Setup (Sequential)
```
Clone Repo → Generate Repo View → Prepare for Scan
```
Must happen in order - you can't generate a view before cloning!

#### Phase 2: Multi-Model Scanning (**PARALLEL**) 🚀
```python
# File: backend/app/services/broad_scan_agent.py (lines 584-588)

# All models scan in parallel using asyncio.gather
tasks = [
    self._scan_with_model(model, repo_view)
    for model in self.models
]
model_results = await asyncio.gather(*tasks)
```

**Multiple LLM models analyze the codebase simultaneously:**
- Gemini 3 Pro (1M context window)
- Claude Sonnet 4.5 on Bedrock (1M context window)

**Benefits:**
- Faster: Both models run at the same time
- Consensus: Issues found by multiple models have higher confidence
- Redundancy: If one model fails, others can still complete

#### Phase 3: Post-Processing (Sequential)
```
Merge Issues → Deduplicate → Investigate (optional) → Cache Results
```

---

## AI Scan Pipeline

Here's the complete step-by-step flow:

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI Scan Task Triggered                        │
│              (Celery task: run_ai_scan)                          │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Initialize (5%)                                          │
│ - Mark scan as "running" in PostgreSQL                          │
│ - Publish progress to Redis for SSE                             │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Load Data (10%)                                          │
│ - Get Analysis record from database                             │
│ - Get Repository and commit_sha                                 │
│ - Get user's GitHub access token (for private repos)            │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Clone Repository (20%)                                   │
│ - Clone repo at specific commit SHA                             │
│ - Independent clone (doesn't interfere with other tracks)       │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: Generate Repository View (35%)                           │
│ - Scan all code files                                           │
│ - Create markdown representation                                │
│ - Include file structure, key code snippets                     │
│ - Estimate token count                                          │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 5: Multi-Model Broad Scan (50%) ⚡ PARALLEL                │
│                                                                  │
│   ┌──────────────────────┐      ┌──────────────────────┐       │
│   │  Gemini 3 Pro        │      │  Claude Sonnet 4.5   │       │
│   │  ----------------    │      │  ------------------  │       │
│   │  • 1M context window │      │  • 1M context window │       │
│   │  • Temp: 1.0         │      │  • Temp: 0.1         │       │
│   │  • Max tokens: 65536 │      │  • Max tokens: 16384 │       │
│   │  • JSON output       │      │  • JSON output       │       │
│   └──────────────────────┘      └──────────────────────┘       │
│            │                              │                     │
│            └──────────┬───────────────────┘                     │
│                       ▼                                         │
│              Both run at same time!                             │
│              (asyncio.gather)                                   │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 6: Merge & Deduplicate Issues (75%)                        │
│ - Combine issues from all models                               │
│ - Remove duplicates (same file/location)                       │
│ - Calculate confidence scores                                  │
│ - Assign consensus severity                                    │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 7: Investigate (80-90%) [OPTIONAL]                         │
│ - Deep dive on high-severity issues                            │
│ - Run IssueInvestigator agent                                  │
│ - Generate suggested fixes                                     │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 8: Cache Results (90%)                                     │
│ - Convert to serializable format                               │
│ - Store in Analysis.ai_scan_cache (PostgreSQL JSONB)           │
│ - Include metadata (models used, tokens, cost)                 │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 9: Complete (100%)                                         │
│ - Mark scan as "completed" in PostgreSQL                       │
│ - Publish final status to Redis                                │
│ - Return summary                                               │
└─────────────────────────────────────────────────────────────────┘
```

### Key Files

| Component | File | Purpose |
|-----------|------|---------|
| **Celery Task** | `backend/app/workers/ai_scan.py` | Main orchestration logic |
| **API Endpoints** | `backend/app/api/v1/ai_scan.py` | Trigger scan, get results, stream progress |
| **Broad Scan Agent** | `backend/app/services/broad_scan_agent.py` | Multi-model LLM orchestration |
| **Issue Merger** | `backend/app/services/issue_merger.py` | Deduplicate and merge issues |
| **Repo View Generator** | `backend/app/services/repo_view_generator.py` | Create markdown repo representation |

---

## Prompts and Agents

### The System Prompt

The AI Scan uses a **single, comprehensive system prompt** that instructs the LLM to act as a code analyst. This prompt is defined in `backend/app/services/broad_scan_agent.py` (lines 130-204):

```python
BROAD_SCAN_SYSTEM_PROMPT = """You are an expert code analyst performing a 
comprehensive security and quality review of a software repository.

Your task is to analyze the provided repository content and identify 
issues across multiple dimensions...
"""
```

#### What the Prompt Requests

The prompt asks the LLM to:

1. **Categorize issues** into dimensions:
   - `security`: Vulnerabilities, secrets, injection risks
   - `db_consistency`: Database schema issues, migrations
   - `api_correctness`: API contracts, validation
   - `code_health`: Dead code, duplication, complexity
   - `other`: Anything else significant

2. **Assign severity levels**:
   - `critical`: Immediate security risk or data loss
   - `high`: Should be addressed soon
   - `medium`: Notable quality issue
   - `low`: Minor improvement suggestion

3. **Rate confidence**:
   - `high`: Clear evidence, definitely an issue
   - `medium`: Likely an issue, needs verification
   - `low`: Possible issue, context-dependent

4. **Return structured JSON**:
   ```json
   {
     "repo_overview": {
       "guessed_project_type": "...",
       "main_languages": [...],
       "frameworks_detected": [...]
     },
     "issues": [
       {
         "id_hint": "sec-001",
         "dimension": "security",
         "severity": "high",
         "files": [{"path": "...", "line_start": 10, "line_end": 15}],
         "summary": "Brief one-line summary",
         "detailed_description": "...",
         "evidence_snippets": ["code snippet"],
         "potential_impact": "...",
         "remediation_idea": "...",
         "confidence": "high"
       }
     ]
   }
   ```

#### Special Context Notes

The prompt includes important context to reduce false positives:

```markdown
- **Database indexes**: Indexes may be defined in migration files rather 
  than ORM models. Check migrations before reporting missing indexes.
  
- **ORM vs Database schema**: Discrepancies between model annotations 
  and migration-defined indexes are documentation issues, not performance issues.
  
- **Foreign key indexes**: Many databases automatically create indexes 
  for foreign keys.
```

### Agents Involved

The AI Scan uses **three types of agents**:

#### 1. **BroadScanAgent** (Primary Agent)

**File:** `backend/app/services/broad_scan_agent.py`

**Purpose:** Orchestrates multi-model scanning

**How it works:**
- Takes repository view (markdown text)
- Sends to multiple LLM models in parallel
- Collects and parses JSON responses
- Aggregates results

**Key methods:**
- `scan(repo_view)`: Main entry point, runs all models in parallel
- `_scan_with_model(model, repo_view)`: Scan with single model
- `_parse_response(response_content, model)`: Parse JSON from LLM

#### 2. **IssueMerger** (Post-Processing Agent)

**File:** `backend/app/services/issue_merger.py`

**Purpose:** Merge and deduplicate issues from multiple models

**How it works:**
- Groups issues by file path and location
- Identifies duplicates across models
- Calculates consensus severity
- Boosts confidence for issues found by multiple models

**Example:**
```python
# Gemini finds: "SQL injection in user_login.py:45"
# Claude finds: "SQL injection in user_login.py:45"
# → Merged into one issue with confidence boosted from "medium" to "high"
```

#### 3. **IssueInvestigator** (Optional Deep-Dive Agent)

**File:** `backend/app/services/issue_investigator.py`

**Purpose:** Investigate high-severity issues in detail

**When used:** Only if `investigate_severity` parameter is provided

**How it works:**
- Reads context around the issue
- Generates suggested fix
- Validates fix (optional)
- Returns investigation result

**Currently:** This is an optional feature, not enabled by default

---

## Models and Configuration

### Default Models

By default, the AI Scan uses **two models in parallel**:

```python
# File: backend/app/services/broad_scan_agent.py (lines 235-238)

DEFAULT_SCAN_MODELS = [
    "gemini/gemini-3-pro-preview",  # Google's Gemini 3 Pro
    "bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0",  # Claude Sonnet 4.5
]
```

### Model-Specific Configurations

Each model has custom configuration for optimal performance:

#### Gemini 3 Pro
```python
{
    "max_tokens": 65536,      # Large output capacity
    "temperature": 1.0,       # Higher temp to avoid loops
    "context": "1M tokens",   # Native 1M context support
    "extra_headers": {}
}
```

#### Claude Sonnet 4.5 (Bedrock)
```python
{
    "max_tokens": 16384,
    "temperature": 0.1,       # Lower temp for precision
    "context": "1M tokens",   # 1M with beta header
    "extra_headers": {
        "anthropic-beta": "context-1m-2025-08-07"
    }
}
```

### Why Two Models?

1. **Consensus:** Issues found by both models are more likely to be real
2. **Coverage:** Each model has different strengths/blind spots
3. **Redundancy:** If one model fails, the other can still complete
4. **Speed:** Running in parallel = faster than sequential

### Cost Management

The system tracks cost and has configurable limits:

```python
# File: backend/app/core/config.py
AI_SCAN_MAX_COST_PER_SCAN = 2.0  # Max $2 per scan
```

If cost exceeds limit, a warning is logged but the scan completes.

### Token Usage

- **Input tokens:** Entire repository view (can be 100K-1M tokens)
- **Output tokens:** JSON response (typically 1K-10K tokens)
- **Total:** Varies by repository size, usually 100K-1M tokens per model

---

## State Management

### PostgreSQL as Single Source of Truth

The AI Scan state is managed through the **AnalysisStateService**, which uses PostgreSQL as the primary state store:

```python
# File: backend/app/workers/ai_scan.py (lines 60-114)

def _update_ai_scan_state(
    analysis_id: str,
    status: str | None = None,
    progress: int | None = None,
    stage: str | None = None,
    message: str | None = None,
    error: str | None = None,
    cache_data: dict[str, Any] | None = None,
) -> None:
    """Update AI scan state in PostgreSQL via AnalysisStateService."""
    state_service = AnalysisStateService(session, publish_events=True)
    
    if status == "running":
        state_service.start_ai_scan(analysis_id)
    elif status == "completed":
        state_service.complete_ai_scan(analysis_id, cache_data)
    elif status == "failed":
        state_service.fail_ai_scan(analysis_id, error)
    elif progress is not None:
        state_service.update_ai_scan_progress(analysis_id, progress, stage, message)
```

### Status Lifecycle

```
pending → running → completed ✅
                 → failed ❌
```

### Database Schema

The `Analysis` table has dedicated fields for AI Scan:

```sql
CREATE TABLE analyses (
    id UUID PRIMARY KEY,
    ai_scan_status VARCHAR,           -- 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
    ai_scan_progress INTEGER,         -- 0-100
    ai_scan_stage VARCHAR,            -- 'cloning' | 'scanning' | 'merging' | etc.
    ai_scan_message TEXT,             -- Human-readable status message
    ai_scan_error TEXT,               -- Error message if failed
    ai_scan_cache JSONB,              -- Complete scan results
    ...
);
```

### Cache Structure

Results are stored in `ai_scan_cache` as JSONB:

```json
{
  "status": "completed",
  "models_used": ["gemini/...", "bedrock/..."],
  "models_succeeded": ["gemini/...", "bedrock/..."],
  "repo_overview": {
    "guessed_project_type": "FastAPI backend",
    "main_languages": ["Python"],
    "frameworks_detected": ["FastAPI", "SQLAlchemy"]
  },
  "issues": [
    {
      "id": "merged-001",
      "dimension": "security",
      "severity": "high",
      "title": "SQL injection vulnerability",
      "summary": "...",
      "files": [{"path": "api.py", "line_start": 45, "line_end": 50}],
      "evidence_snippets": ["db.execute(f'SELECT * FROM users WHERE id={user_id}')"],
      "confidence": "high",
      "found_by_models": ["gemini/...", "bedrock/..."]
    }
  ],
  "computed_at": "2025-12-10T09:45:34Z",
  "total_tokens_used": 156789,
  "total_cost_usd": 0.4521,
  "commit_sha": "abc123..."
}
```

---

## Real-Time Progress Updates

### Two-Layer Architecture

The system uses a **two-layer approach** for progress updates:

```
┌──────────────────────────────────────┐
│  PostgreSQL (Single Source of Truth) │
│  - Persistent state                   │
│  - Survives restarts                  │
│  - Atomic updates                     │
└──────────────────────────────────────┘
                 │
                 │ State changes trigger events
                 ▼
┌──────────────────────────────────────┐
│  Redis Pub/Sub (Real-Time Updates)   │
│  - Ephemeral notifications            │
│  - SSE streaming                      │
│  - Low latency                        │
└──────────────────────────────────────┘
```

### How It Works

#### 1. Worker Updates State

```python
# File: backend/app/workers/ai_scan.py

# Update PostgreSQL (primary)
_update_ai_scan_state(
    analysis_id=analysis_id,
    progress=50,
    stage="scanning",
    message="Running AI scan with 2 models..."
)

# Publish to Redis (real-time)
publish_ai_scan_progress(
    analysis_id=analysis_id,
    stage="scanning",
    progress=50,
    message="Running AI scan with 2 models...",
    status="running"
)
```

#### 2. API Streams to Client

```python
# File: backend/app/api/v1/ai_scan.py (lines 278-460)

@router.get("/{analysis_id}/ai-scan/stream")
async def stream_ai_scan_progress(...):
    """Stream AI scan progress via Server-Sent Events (SSE)."""
    
    # 1. Send last known state from Redis (for late subscribers)
    last_state = await client.get(state_key)
    if last_state:
        yield f"data: {last_state}\n\n"
    
    # 2. Subscribe to real-time updates
    await pubsub.subscribe(channel)
    
    # 3. Stream updates as they arrive
    while True:
        message = await pubsub.get_message()
        if message:
            yield f"data: {message['data']}\n\n"
```

#### 3. Frontend Receives Updates

```typescript
// File: frontend/lib/ai-scan-api.ts

const eventSource = new EventSource(`/api/analyses/${id}/ai-scan/stream`);

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`AI Scan: ${data.stage} (${data.progress}%)`);
  // Update UI with progress
};
```

### Progress Stages

The AI Scan reports these stages:

| Stage | Progress | Description |
|-------|----------|-------------|
| `initializing` | 5% | Starting up |
| `loading` | 10% | Loading analysis data |
| `cloning` | 20% | Cloning repository |
| `generating_view` | 35% | Creating repo view |
| `scanning` | 50% | Running LLM models (parallel) |
| `merging` | 75% | Deduplicating issues |
| `investigating` | 80-90% | Deep dive (optional) |
| `caching` | 90% | Saving results |
| `completed` | 100% | Done! |
| `failed` | 0% | Error occurred |

---

## Summary

### Quick Answers

**Q: Is AI Scan parallel or sequential?**  
A: **Mixed**. The three analysis tracks (Static, Embeddings, AI Scan) run in **parallel**. Within AI Scan, models scan in **parallel**, but setup and post-processing are sequential.

**Q: Are there different prompts?**  
A: **One main prompt** (`BROAD_SCAN_SYSTEM_PROMPT`) used for all models. It's comprehensive and instructs the LLM to act as a code analyst returning structured JSON.

**Q: Are there different agents?**  
A: **Yes, three agents**:
1. **BroadScanAgent** - Orchestrates multi-model scanning
2. **IssueMerger** - Deduplicates and merges issues
3. **IssueInvestigator** - Optional deep-dive on critical issues

**Q: How many models are used?**  
A: **Two by default** (Gemini 3 Pro + Claude Sonnet 4.5), running in **parallel** for faster results and consensus.

**Q: Where are results stored?**  
A: In **PostgreSQL** (`Analysis.ai_scan_cache` JSONB field). Redis is only for real-time progress notifications.

### Architecture Highlights

✅ **Parallel at the top level** - Three independent tracks  
✅ **Parallel within AI Scan** - Multiple models run simultaneously  
✅ **PostgreSQL as source of truth** - Reliable, persistent state  
✅ **Redis for real-time updates** - SSE streaming to frontend  
✅ **Consensus-based detection** - Issues found by multiple models are higher confidence  
✅ **Cost-aware** - Tracks token usage and has configurable cost limits

---

## Related Documentation

- **Main README**: `/README.md` - Overall platform architecture
- **Backend README**: `/backend/README.md` - API and worker details
- **Frontend README**: `/frontend/README.md` - UI implementation

## Code References

Key files to explore:

```
backend/
├── app/
│   ├── api/v1/
│   │   └── ai_scan.py              # API endpoints
│   ├── services/
│   │   ├── broad_scan_agent.py     # Multi-model orchestration
│   │   ├── issue_merger.py         # Issue deduplication
│   │   ├── issue_investigator.py   # Deep-dive analysis
│   │   └── repo_view_generator.py  # Markdown generation
│   ├── workers/
│   │   └── ai_scan.py              # Main Celery task
│   └── schemas/
│       └── ai_scan.py              # Response schemas
```

---

*Last updated: 2025-12-10*
