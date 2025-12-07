# Progress Report

# 30-nov-2025 4:15 pm - Multi-Language Analysis 

## Files Created
- `backend/app/services/lizard_analyzer.py` - LizardAnalyzer class for JS/TS/other languages

## Files Modified
- `backend/pyproject.toml` - Added lizard dependency
- `backend/app/services/repo_analyzer.py` - Added `_detect_languages()`, `analyze_with_lizard()`, `_merge_complexity_results()`, updated `analyze()`
- `frontend/components/analysis-metrics.tsx` - Added "By Language" card, `getLanguageIcon()` helper, updated TypeScript interface
- `frontend/app/playground/page.tsx` - Updated ScanResult interface with by_language
- `docs/architecture.md` - Added "Code Complexity Analysis Tools" section with tool selection rationale
- `docs/glossary.md` - Added definitions: by_language, Cyclomatic Complexity, lizard, radon

## What Was Done
Multi-language code complexity analysis using lizard for JS/TS/Java/Go/etc alongside radon for Python. Results are merged with weighted averages, combined top functions, and per-language breakdown displayed in UI.


# 01-dec-2025 12:21 pm - Frontend Modernization & Behavioral Analysis

## Files Created
- `frontend/hooks/use-analysis-stream.ts` - Custom hook encapsulating SSE analysis logic

## Files Modified
- `frontend/app/globals.css` - Updated `primary` color to Brand Green, added `hover-lift` utility
- `frontend/app/page.tsx` - Standardized button colors to use semantic theme
- `frontend/app/dashboard/page.tsx` - Standardized button colors
- `frontend/components/run-analysis-button.tsx` - Refactored to use `useAnalysisStream`, reduced complexity
- `frontend/components/repositories-table.tsx` - Fixed TypeScript errors, resolved unique key warnings

## What Was Done
Standardized the frontend design by enforcing the Brand Green color globally. Modernized the codebase by extracting complex SSE logic into a reusable custom hook. Implemented and then reverted a collapsible row feature based on feedback, while retaining micro-interaction improvements.


# 02-dec-2025 3:23 pm - Vector-Based Semantic Analysis

## Files Created
- `backend/app/api/v1/semantic.py` - 9 semantic API endpoints (search, clusters, outliers, similar code, etc.)
- `backend/app/services/cluster_analyzer.py` - HDBSCAN clustering for architecture health analysis
- `backend/scripts/generate_repo_embeddings.py` - Utility script for manual embedding generation
- `backend/scripts/migrate_qdrant_v2.py` - Qdrant schema migration with new indexes
- `backend/tests/test_semantic_api.py` - 17 integration tests for semantic endpoints
- `frontend/components/semantic-search.tsx` - Natural language code search UI
- `frontend/components/architecture-health.tsx` - Cluster visualization with health scores
- `frontend/components/similar-code.tsx` - Duplicate code detection panel
- `frontend/components/tech-debt-heatmap.tsx` - Technical debt hotspots visualization
- `frontend/components/cluster-map.tsx` - Visual code organization map
- `frontend/lib/semantic-api.ts` - API client for semantic endpoints
- `docs/vector_tasks.md` - Task tracking for vector implementation

## Files Modified
- `backend/app/workers/analysis.py` - Fixed bug: collect files for embeddings before temp dir cleanup
- `backend/app/workers/embeddings.py` - Enhanced payload with hierarchical metadata (level, qualified_name, complexity)
- `backend/app/services/code_chunker.py` - Added hierarchical chunking with complexity metrics
- `backend/app/services/llm_gateway.py` - Auto-detection of embedding provider (Azure/OpenAI/Gemini)
- `backend/app/core/config.py` - Added Azure embedding deployment settings
- `.env.example` - Documented all LLM provider configuration options

## What Was Done
Implemented complete vector-based code understanding system using semantic embeddings. Features include: natural language code search, HDBSCAN cluster analysis for architecture health (47/100 score), outlier detection for dead/misplaced code, similar code detection, refactoring suggestions, and technical debt heatmap. Fixed Qdrant collection dimension mismatch (1536→3072 for Azure text-embedding-3-large). Generated 74 embeddings for test repository with 8 clusters and 20 outliers detected.


# 02-dec-2025 6:30 pm - Bug Fixes & Mobile Responsive Dashboard

## Files Created
- `frontend/app/dashboard/layout.tsx` - Dashboard layout with session validation before render

## Files Modified
- `backend/app/workers/scheduled.py` - Fixed timezone-aware datetime (replaced `utcnow()` with `now(timezone.utc)`)
- `frontend/lib/session.ts` - Added `validateSession()` and `getValidatedSession()` for backend token validation
- `frontend/app/actions/repository.ts` - Added `handleUnauthorized()` for 401 handling with session cleanup
- `frontend/app/login/page.tsx` - Added friendly "session expired" message
- `frontend/app/dashboard/repository/[id]/page.tsx` - Complete bento grid layout rewrite, mobile responsive
- `frontend/components/vci-score-card.tsx` - Mobile responsive sizing and padding
- `frontend/components/analysis-metrics.tsx` - Mobile responsive grid, cards, and table layouts
- `frontend/components/semantic-analysis-section.tsx` - Compact mobile tabs, removed duplicate headers
- `docs/fix_progress/02-dec-2025-fix.md` - Documented fixes

## What Was Done
Fixed two critical bugs: (1) Celery scheduled tasks failing with "can't subtract offset-naive and offset-aware datetimes" error by using timezone-aware datetimes, (2) Dashboard showing empty state with 401 errors by validating session tokens against backend before rendering. Completely redesigned repository detail page with proper bento-style grid layout. Made entire dashboard mobile responsive with adaptive padding, text sizes, and component layouts that work from 320px mobile to 1600px desktop.


# 03-dec-2025 - Balanced Architecture Filter

## Files Created
- `backend/app/services/architecture_filter.py` - Import analysis, boilerplate detection, architectural context, test evaluation, and confidence scoring modules
- `backend/tests/test_architecture_filter.py` - Property-based tests (17 tests) for all filter modules

## Files Modified
- `backend/app/services/cluster_analyzer.py` - Updated OutlierInfo dataclass with confidence/tier fields, integrated balanced confidence scoring in _find_outliers
- `backend/app/api/v1/semantic.py` - Updated OutlierInfoResponse with confidence, confidence_factors, and tier fields
- `frontend/lib/semantic-api.ts` - Added confidence, confidence_factors, and tier to OutlierInfo interface
- `frontend/components/architecture-health.tsx` - Added tier badges (critical/recommended/informational), confidence percentage display, expandable confidence factors

## What Was Done
Implemented balanced architecture filter to reduce false positives in outlier detection. Features include: import relationship analysis (Python/JS/TS), boilerplate detection (dunder methods, framework conventions, utility patterns), architectural layer context, test file relationship evaluation, and multi-factor confidence scoring. Outliers are now filtered by confidence (≥0.4), assigned tiers, sorted by confidence, and limited to 15 results. Frontend displays tier-colored badges and confidence factors for transparency.


# 03-dec-2025 - Commit Selector MVP

## Files Created
- `frontend/components/commit-timeline.tsx` - CommitTimeline component with branch selector, commit list, and analysis triggers
- `backend/tests/test_commit_schemas.py` - Property-based tests for commit schema validation
- `backend/tests/test_github_service.py` - Unit tests for GitHubService branch/commit methods

## Files Modified
- `backend/app/services/github.py` - Added `list_branches()`, `list_commits()` methods with error handling
- `backend/app/api/v1/repositories.py` - Added `/branches` and `/commits` endpoints
- `backend/app/schemas/repository.py` - Added BranchResponse, CommitResponse, CommitListResponse schemas
- `frontend/lib/api.ts` - Added Branch/Commit types and branchApi/commitApi clients
- `frontend/app/dashboard/repository/[id]/page.tsx` - Integrated CommitTimeline component in bento grid

## What Was Done
Implemented Commit Selector MVP allowing users to view commit history per branch, see which commits have been analyzed (with VCI scores), and trigger analysis on any historical commit. Backend includes GitHubService extensions for branch/commit listing with proper error handling (rate limits, permissions), API endpoints with analysis enrichment, and property-based tests. Frontend features a CommitTimeline component with branch selector, timeline visualization, relative timestamps, and polling for analysis status updates.


# 04-dec-2025 - Progress Tracking Refactor (PostgreSQL-Based State)

## Files Created
- `backend/alembic/versions/007_add_embeddings_tracking.py` - Migration adding embeddings_status, embeddings_progress, embeddings_stage, embeddings_message, embeddings_error, embeddings_started_at, embeddings_completed_at, vectors_count, semantic_cache_status, state_updated_at columns with CHECK constraints and indexes
- `backend/app/services/analysis_state.py` - AnalysisStateService with state transition validation, convenience methods, and Redis event publishing
- `backend/tests/test_analysis_state_service.py` - Property tests for state transitions, progress bounds, timestamp updates
- `backend/tests/test_analysis_state_constraints.py` - Property test for database constraint enforcement
- `backend/tests/test_embeddings_workflow.py` - Integration test for full embeddings workflow
- `backend/tests/test_full_status_api.py` - Unit tests for /analyses/{id}/full-status endpoint
- `backend/tests/test_state_persistence.py` - Property tests for state persistence across restarts and Redis independence
- `frontend/lib/hooks/use-analysis-status.ts` - React Query hook with smart polling for analysis status
- `frontend/__tests__/hooks/use-analysis-status.test.ts` - Unit tests for useAnalysisStatus hook

## Files Modified
- `backend/app/models/analysis.py` - Added embeddings tracking columns, semantic_cache_status, state_updated_at to Analysis model
- `backend/app/schemas/analysis.py` - Added AnalysisFullStatusResponse schema with computed fields (overall_progress, overall_stage, is_complete)
- `backend/app/api/v1/analyses.py` - Added GET /analyses/{id}/full-status endpoint
- `backend/app/api/v1/semantic.py` - Updated GET /repositories/{id}/embedding-status for backward compatibility (reads from PostgreSQL)
- `backend/app/workers/embeddings.py` - Refactored to use AnalysisStateService, separated semantic cache into dedicated task
- `backend/app/workers/analysis.py` - Updated to mark embeddings pending via state service
- `backend/app/core/redis.py` - Added publish_analysis_event function for non-blocking event publishing
- `backend/app/core/config.py` - Added use_postgres_embeddings_state feature flag
- `frontend/components/semantic-analysis-section.tsx` - Refactored to use useAnalysisStatus hook
- `frontend/components/vci-section-client.tsx` - Refactored to use shared useAnalysisStatus hook
- `frontend/hooks/use-analysis-stream.ts` - Removed embeddings task creation, invalidates React Query cache on analysis complete

## What Was Done
Major architecture shift from Redis-only to PostgreSQL-based state management for embeddings and semantic cache progress tracking. State is now persisted in PostgreSQL with proper constraints, enabling recovery after restarts and eliminating Redis dependency for critical state. Features include: validated state transitions (pending→processing→completed/failed), progress tracking with stage information, automatic semantic cache task queuing on embeddings completion, Redis event publishing for real-time updates, backward-compatible legacy endpoint, and feature flag for gradual rollout. Frontend uses React Query with smart polling intervals that stop when is_complete is true. All 7 phases completed with property-based tests validating state persistence, transitions, progress bounds, and event publishing.


# 05-dec-2025 - AI Scan Integration

## Files Created
- `backend/alembic/versions/006_add_ai_scan_cache.py` - Migration adding ai_scan_cache JSONB column to analyses table
- `backend/app/schemas/ai_scan.py` - AIScanRequest, AIScanIssue, AIScanCacheResponse, CandidateIssue schemas with validation
- `backend/app/services/repo_view_generator.py` - RepoViewGenerator for LLM-friendly markdown with token budgeting and file prioritization
- `backend/app/services/broad_scan_agent.py` - BroadScanAgent for multi-model parallel scanning (Gemini 3 Pro + Claude Sonnet 4.5)
- `backend/app/services/issue_merger.py` - IssueMerger for deduplication, confidence boosting, and unique ID generation
- `backend/app/services/issue_investigator.py` - IssueInvestigator tool-calling agent for deep-diving high-severity issues
- `backend/app/workers/ai_scan.py` - Celery task for AI scan pipeline orchestration
- `backend/app/api/v1/ai_scan.py` - POST trigger, GET results, SSE streaming endpoints
- `backend/tests/test_ai_scan_cache.py` - Property tests for cache round-trip serialization
- `backend/tests/test_ai_scan_schemas.py` - Property tests for schema validation
- `backend/tests/test_repo_view_generator.py` - Property tests for token budget, file prioritization, large file truncation
- `backend/tests/test_ai_scan_worker.py` - Property tests for commit SHA consistency, results persistence, cost tracking
- `backend/tests/test_issue_investigator.py` - Property tests for investigation output completeness
- `frontend/lib/ai-scan-api.ts` - triggerAIScan, getAIScanResults, streamAIScanProgress API client
- `frontend/components/ai-insights-panel.tsx` - AI Insights panel with issue display, severity grouping, SSE progress

## Files Modified
- `backend/app/models/analysis.py` - Added ai_scan_cache JSONB field
- `backend/app/api/v1/__init__.py` - Registered ai_scan router
- `backend/app/core/config.py` - Added AI_SCAN_MAX_COST_PER_SCAN setting
- `backend/app/services/llm_gateway.py` - Added extra_headers support for Claude 1M context beta
- `frontend/app/dashboard/repository/[id]/page.tsx` - Integrated AIInsightsPanel in bento grid

## What Was Done
Implemented full AI-powered code analysis as the third analysis method in n9r. Pipeline includes: RepoViewGenerator creating LLM-friendly markdown within 800K token budget with smart file prioritization (entry points → configs → core logic → API routes), BroadScanAgent running parallel scans across Gemini 3 Pro and Claude Sonnet 4.5 with model-specific configs (1M context windows), IssueMerger deduplicating issues with 0.8 similarity threshold and boosting confidence when found by multiple models, optional IssueInvestigator for tool-calling validation of critical/high severity issues. Results cached in PostgreSQL JSONB with cost tracking. Frontend displays issues grouped by severity with expandable details and evidence snippets. Property-based tests cover 19 correctness properties including token budgets, deduplication, cost limits, and cache round-trips.


# 05-dec-2025 - AI Scan Orchestration & Unified Progress

## Files Created
- `backend/alembic/versions/008_add_ai_scan_tracking.py` - Migration adding ai_scan_status, ai_scan_progress, ai_scan_stage, ai_scan_message, ai_scan_error, ai_scan_started_at, ai_scan_completed_at columns
- `backend/tests/test_ai_scan_state_transitions.py` - Property tests for AI scan state transitions, automatic chaining, failure isolation
- `frontend/__tests__/stores/analysis-progress-store.test.ts` - Tests for ai_scan task type in progress store
- `frontend/__tests__/components/ai-insights-panel.test.tsx` - Tests for AI Insights panel rendering states

## Files Modified
- `backend/app/models/analysis.py` - Added AI scan tracking columns (status, progress, stage, message, error, timestamps)
- `backend/app/services/analysis_state.py` - Extended with AI_SCAN_TRANSITIONS, mark_ai_scan_pending, start_ai_scan, complete_ai_scan, fail_ai_scan, skip_ai_scan, update_ai_scan_progress methods
- `backend/app/workers/embeddings.py` - Modified compute_semantic_cache to auto-queue AI scan on completion
- `backend/app/workers/ai_scan.py` - Refactored to use AnalysisStateService for PostgreSQL-backed state management
- `backend/app/schemas/analysis.py` - Added AIScanStatus enum, extended AnalysisFullStatusResponse with AI scan fields, updated compute_overall_progress (80-100% for AI scan phase)
- `backend/app/api/v1/analyses.py` - Extended full-status endpoint with AI scan state
- `backend/app/core/config.py` - Added ai_scan_enabled setting for skip behavior
- `frontend/lib/stores/analysis-progress-store.ts` - Added 'ai_scan' task type and getAIScanTaskId helper
- `frontend/lib/hooks/use-analysis-status.ts` - Extended AnalysisFullStatus interface, added AI scan polling logic and progress store sync
- `frontend/components/ai-insights-panel.tsx` - Simplified to use unified progress system, removed inline SSE streaming

## What Was Done
Integrated AI Scan into the unified analysis pipeline architecture with PostgreSQL as single source of truth. Features include: automatic chaining from semantic cache completion to AI scan (following same pattern as embeddings → semantic cache), validated state transitions via AnalysisStateService, extended Full Status API with AI scan fields, updated overall progress calculation (Static 0-30%, Embeddings 30-60%, Semantic Cache 60-80%, AI Scan 80-100%), frontend progress store extended with 'ai_scan' task type, smart polling intervals for AI scan states, and skip behavior when ai_scan_enabled=False. Property-based tests validate 10 correctness properties including state transitions, automatic chaining, failure isolation, retry capability, and PostgreSQL as SSOT.


# 07-dec-2025 - Parallel Analysis Pipeline

## Files Created
- `backend/app/workers/helpers.py` - Shared helpers: `_get_repo_url`, `_collect_files_for_embedding` extracted for reuse
- `backend/tests/test_parallel_embeddings.py` - Property tests for independent cloning with commit_sha
- `backend/tests/test_parallel_dispatch.py` - Property tests for parallel task dispatch from API
- `backend/tests/test_parallel_progress.py` - Property tests for parallel progress calculation (3-track weighted average)
- `backend/tests/test_semantic_cache_chain.py` - Property tests for Embeddings → Semantic Cache chain (no AI Scan dispatch)
- `backend/tests/test_parallel_pipeline_integration.py` - Integration tests for full parallel pipeline and partial failures

## Files Modified
- `backend/app/api/v1/analyses.py` - Orchestrator now dispatches all 3 tasks in parallel, sets all statuses to "pending"
- `backend/app/workers/analysis.py` - Removed embeddings dispatch, Static Analysis only calculates VCI
- `backend/app/workers/embeddings.py` - Added `generate_embeddings_parallel` task with independent repo cloning
- `backend/app/workers/ai_scan.py` - Removed `analysis.status != "completed"` blocker
- `backend/app/services/analysis_state.py` - Removed AI Scan auto-trigger from `complete_semantic_cache`
- `backend/app/schemas/analysis.py` - New `compute_overall_progress_parallel` (33% per track), updated `compute_overall_stage` with bullet separators, updated `compute_is_complete` for 3-track terminal detection
- `backend/tests/test_ai_scan_worker.py` - Updated tests for parallel execution
- `backend/tests/test_analysis_state_service.py` - Updated tests for new parallel behavior
- `backend/tests/test_full_status_api.py` - Updated tests for new progress calculation

## What Was Done
Transformed sequential analysis pipeline (Analysis → Embeddings → Semantic Cache → AI Scan) into fully parallel execution where Static Analysis, Embeddings, and AI Scan all start simultaneously. Each track clones the repository independently using the same commit_sha. Semantic Cache still chains from Embeddings completion. New progress calculation uses 33% weight per track, capped at 95% until all tracks reach terminal states. Partial failures handled gracefully (e.g., VCI + AI insights without semantic if Embeddings fails). Reduces total analysis time by 50-60%.
