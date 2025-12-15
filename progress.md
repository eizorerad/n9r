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


# 08-dec-2025 - Semantic AI Insights Feature & Progress Tracking Fixes

## Files Created
- `backend/alembic/versions/009_add_architecture_findings.py` - Migration for dead_code, file_churn, semantic_ai_insights tables
- `backend/alembic/versions/010_add_generating_insights_status.py` - Migration adding `generating_insights` to semantic_cache_status CHECK constraint
- `backend/app/models/dead_code.py` - DeadCode SQLAlchemy model with dismissal support
- `backend/app/models/file_churn.py` - FileChurn SQLAlchemy model for hot spots
- `backend/app/models/semantic_ai_insight.py` - SemanticAIInsight model for AI recommendations
- `backend/app/schemas/architecture_llm.py` - LLM-ready dataclasses (ArchitectureSummary, DeadCodeFinding, HotSpotFinding, LLMReadyArchitectureData)
- `backend/app/schemas/architecture_findings.py` - API response schemas for architecture findings
- `backend/app/services/call_graph_analyzer.py` - AST-based call graph for dead code detection (Python/JS/TS)
- `backend/app/services/git_analyzer.py` - Git history analysis for code churn metrics
- `backend/app/services/coverage_analyzer.py` - Cobertura XML coverage parsing
- `backend/app/services/semantic_ai_insights.py` - LiteLLM-based insight generation with JSON repair
- `backend/app/services/architecture_findings_service.py` - Service for persisting findings to PostgreSQL
- `backend/app/api/v1/architecture.py` - Architecture findings API endpoints
- `backend/tests/test_call_graph_analyzer.py` - Property tests for call graph analysis
- `backend/tests/test_git_analyzer.py` - Property tests for git churn analysis
- `backend/tests/test_coverage_analyzer.py` - Property tests for coverage parsing
- `backend/tests/test_semantic_ai_insights.py` - Property tests for AI insight generation
- `backend/tests/test_architecture_findings_api.py` - API integration tests
- `frontend/lib/hooks/use-architecture-findings.ts` - TanStack Query hook for architecture findings
- `frontend/components/semantic-ai-insights.tsx` - AI insights display with collapse/expand
- `frontend/components/cluster-graph.tsx` - Force-directed graph visualization (optional)
- `docs/fix_progress/08-dec-2025-fix.md` - Detailed fix documentation

## Files Modified
- `backend/app/services/cluster_analyzer.py` - Added `analyze_for_llm()` method for LLM-ready data generation
- `backend/app/services/analysis_state.py` - Added `generating_insights` status, `start_generating_insights()` method, updated state transitions
- `backend/app/workers/embeddings.py` - Integrated SemanticAIInsightsService, reordered to generate insights BEFORE marking complete
- `backend/app/models/analysis.py` - Added relationships to new finding tables
- `frontend/lib/hooks/use-analysis-status.ts` - Added `generating_insights` to polling, added semantic cache task sync
- `frontend/lib/stores/analysis-progress-store.ts` - Added `semantic_cache` task type and helper
- `frontend/components/analysis-progress-overlay.tsx` - Added semantic cache task display with amber icon
- `frontend/components/semantic-analysis-section.tsx` - Reordered tabs (AI Insights first), added data sync fixes, query invalidation
- `frontend/components/cluster-map.tsx` - Added graph view toggle

## What Was Done
Implemented Semantic AI Insights feature transforming raw architecture metrics into actionable recommendations. Backend includes: CallGraphAnalyzer for AST-based dead code detection, GitAnalyzer for code churn metrics, CoverageAnalyzer for test coverage integration, and SemanticAIInsightsService using LiteLLM directly (separate from AI Scan). All findings persisted to PostgreSQL as SSOT.

Fixed multiple progress tracking issues: (1) JSON repair with multi-strategy fallback for malformed LLM responses, (2) Race condition fix by generating insights BEFORE marking semantic cache complete, (3) New `generating_insights` status in state machine with database migration, (4) Semantic cache tracked as separate task in progress panel with proper polling, (5) Frontend data sync fixes for immediate results without page refresh.

Frontend displays AI insights first in semantic analysis panel with collapse/expand (5 items default), optional force-directed graph visualization, and proper progress tracking showing "Generating AI insights..." during LLM call.


# 08-dec-2025 - Transparent Scoring Formula

## Files Created
- `backend/app/services/scoring.py` - ScoringService with DCI, HSR, AHS formulas, LLM sample selection, color coding
- `backend/alembic/versions/011_add_scoring_columns.py` - Migration adding impact_score to dead_code, risk_score to file_churn
- `backend/tests/test_scoring_service.py` - Property tests for all scoring formulas (7 properties)
- `frontend/components/scoring-formula-dialog.tsx` - Dialog explaining all scoring formulas with weights
- `frontend/__tests__/components/semantic-ai-insights-sorting.test.ts` - Tests for sorting functionality

## Files Modified
- `backend/app/schemas/architecture_llm.py` - Added impact_score to DeadCodeFinding, risk_score to HotSpotFinding
- `backend/app/schemas/architecture_findings.py` - Added impact_score/risk_score fields to API schemas
- `backend/app/models/dead_code.py` - Added impact_score column
- `backend/app/models/file_churn.py` - Added risk_score column
- `backend/app/services/call_graph_analyzer.py` - Integrated ScoringService, sorted findings by impact_score
- `backend/app/services/git_analyzer.py` - Integrated ScoringService, sorted findings by risk_score
- `backend/app/services/semantic_ai_insights.py` - Uses select_llm_samples() for score-based + diversity sampling
- `backend/app/api/v1/architecture.py` - Uses ScoringService for health score calculation
- `frontend/components/semantic-ai-insights.tsx` - Added score badges, sort toggle (score/type/file), info icon with formula dialog
- `frontend/lib/hooks/use-architecture-findings.ts` - Added impact_score/risk_score to types

## What Was Done
Implemented transparent, explainable scoring formulas for all architecture findings. Dead Code Impact Score (DCI) uses weighted formula: Size×0.40 + Location×0.30 + Recency×0.20 + Complexity×0.10. Hot Spot Risk Score (HSR) uses: Churn×0.30 + Coverage×0.30 + Location×0.20 + Volatility×0.20. Architecture Health Score (AHS) calculates penalties capped at 40/30/20 for dead code/hot spots/outliers. LLM sample selection takes top 50% by score + 50% diversity sampling from different directories. Frontend displays color-coded score badges (green/amber/red), sort toggle with 3 options, and info dialog explaining all formulas. Property-based tests validate 7 correctness properties.


# 09-dec-2025 - Call Graph Analyzer Refactoring

## Files Modified
- `backend/app/services/call_graph_analyzer.py` - Major refactoring with AnalyzerConfig dataclass, multi-candidate linking, file-specific indexing, configurable patterns

## Files Created
- None (all changes in existing test file)

## Tests Added
- Property tests for multi-candidate bidirectional linking (Property 1)
- Property tests for same-file priority inclusion (Property 2)
- Property tests for config pattern merge is additive (Property 3)
- Property tests for custom entry point detection (Property 4)
- Property tests for directory exclusion completeness (Property 5)
- Property tests for config round-trip consistency (Property 6)

## What Was Done
Refactored CallGraphAnalyzer to fix critical bugs and improve performance:

1. **Multi-File Same-Name Function Resolution**: Fixed first-match ambiguity bug where function calls were linked to only the first arbitrary match. Now links to ALL candidate functions across files, reducing false positive dead code warnings.

2. **Performance Optimization**: Pre-built file-specific function indexes in `_extract_python_calls` and `_extract_js_calls`. Reduced complexity from O(N*M) to O(F*M) where F = functions per file.

3. **AnalyzerConfig Dataclass**: Replaced hardcoded module-level patterns with structured configuration. Supports entry point patterns (names, decorators, files), callback patterns, async generator patterns, API/worker file patterns, and directory exclusions. Includes compiled regex caching for performance.

4. **Repo-Level Config**: Added support for `.n9r/call_graph.yaml` files allowing repositories to extend default patterns with custom framework detection (additive merge, not replacement).

5. **Expanded Default Exclusions**: Added comprehensive directory exclusions (node_modules, .venv, __pycache__, dist, .next, .git, coverage, etc.) to prevent generated code from polluting dead code detection.

6. **YAML Serialization**: Implemented `to_yaml()` and `from_yaml()` methods for config persistence with round-trip consistency.

All 42 existing tests continue to pass. 6 new property-based tests validate correctness properties.


# 08-09-dec-2025 - IDE UI Refinements & Bug Fixes

## Files Created
- `frontend/app/dashboard/repository/loading.tsx` - Dark themed loading skeleton for repository routes
- `frontend/app/dashboard/(overview)/page.tsx` - Dashboard overview page moved to Route Group
- `frontend/app/dashboard/(overview)/loading.tsx` - Dashboard-specific loading skeleton
- `frontend/app/dashboard/(overview)/repositories-table-server.tsx` - Moved within route group

## Files Modified
- `frontend/components/file-tree.tsx` - Fixed explorer expansion bug (directories now start closed)
- `frontend/components/layout/activity-bar.tsx` - Replaced GitGraph with GitBranch for standard Source Control icon
- `frontend/components/analysis-progress-overlay.tsx` - Removed all colored icons, using muted-foreground for consistency
- `frontend/components/vci-score-card-compact.tsx` - Simplified: removed timeline chart, color-coded grades, trend indicators; added max-width constraint
- `frontend/app/dashboard/repository/[id]/page.tsx` - Made Code Health panel fixed position (top-right corner)

## What Was Done

### Explorer Bug Fix
Fixed file explorer "double-click" bug where folders appeared open but empty on first click. Root cause: directories at level < 1 initialized with `isOpen = true` before children were loaded. First click was actually closing them. Fix: all directories now start closed (`useState(false)`), so first click opens AND triggers data load.

### Loading Skeleton Consistency
Created dedicated dark-themed loading skeleton for repository routes to prevent blue-toned dashboard skeleton from appearing during navigation. Used Next.js Route Groups `(overview)` to isolate dashboard and repository loading states.

### Visual Consistency (Remove Colors)
1. **Progress Overlay**: All task icons changed from colored variants (green, red, purple, amber, emerald, blue) to neutral `text-muted-foreground`. Removed colored backgrounds for completed/failed states.
2. **Code Health Panel**: Removed colored grade badges, timeline chart, and trend indicators. Now displays only numeric score with neutral gray styling. Added `max-w-[160px]` for compact size and fixed positioning in top-right corner.

### Icon Updates
- Activity Bar: Replaced GitGraph with GitBranch for standard Source Control icon (matching VS Code convention)



# 09-dec-2025 - IDE UI Refactoring (VS Code Style)

## What Was Done
Complete UI overhaul to VS Code-style dark theme layout:

1. **VS Code Layout**: Three-panel design with left sidebar (file explorer), center (Monaco editor with tabs), right panel (chat). Dark theme (#1e1e1e background, #252526 sidebars).

2. **File Explorer Fixes**: Fixed "double-click" bug where folders started expanded. Folders now start closed with lazy loading on expand. Branch selector integrated in explorer header.

3. **Route Groups & Loading**: Created dark-themed loading skeletons matching VS Code aesthetic. Proper route group organization for dashboard pages.

4. **Icon Cleanup**: Removed colored icons from progress overlay and Code Health panel. Neutral gray styling throughout. Replaced GitGraph with GitBranch icon for consistency.

5. **Code Health Panel**: Fixed position top-right with max-w-[160px]. Compact display of VCI score and analysis status.

6. **Commit Timeline**: Integrated in sidebar with branch selector. Shows historical commits with VCI scores and analysis status badges.

7. **Analysis Folders Concept**: Analysis results organized by type (AI Scan, Semantic, Static) accessible from the interface.


# 14-dec-2025 - Commit-Aware RAG (Qdrant Vector Filtering)

## Files Created
- `backend/app/services/vector_store.py` - VectorStoreService (368 lines) with stable hashing, filter building, ref resolution, query/scroll/delete operations
- `backend/scripts/migrate_qdrant_commit_aware.py` - Non-destructive migration adding repository_id, commit_sha, file_path indexes
- `backend/scripts/delete_vectors.py` - Admin CLI for manual vector deletion by repo/commit
- `backend/alembic/versions/017_add_analysis_pinned_column.py` - Migration adding pinned boolean to Analysis
- `backend/tests/test_vector_store.py` - 18 test cases covering hashing, filtering, ref resolution

## Files Modified
- `backend/scripts/init_qdrant.py` - Standardized to repository_id, added commit_sha KEYWORD index
- `backend/scripts/recreate_qdrant_collection.py` - Standardized to repository_id, added commit_sha index
- `backend/scripts/init_all.py` - Updated for consistency with new indexes
- `backend/app/workers/embeddings.py` - Deterministic point IDs (blake2b), delete by (repository_id, commit_sha), require concrete commit_sha
- `backend/app/api/v1/chat.py` - Added commit_sha param to _get_rag_context(), Phase 0 commit resolution, SSE context_source events
- `backend/app/api/v1/semantic.py` - Added ref param to all endpoints, _resolve_commit_sha() helper, VectorStoreService queries
- `backend/app/services/cluster_analyzer.py` - Added commit_sha param to analyze(), _fetch_vectors uses VectorStoreService.scroll_vectors
- `backend/app/services/agents/fix.py` - Updated to use VectorStoreService.query_similar_chunks with commit filter
- `backend/app/workers/scheduled.py` - Added cleanup_vector_retention Celery task (daily 3:00 AM)
- `backend/app/core/config.py` - Added vector_retention_max_analyses (20), vector_retention_max_days (90), vector_retention_enabled
- `backend/app/models/analysis.py` - Added pinned boolean column for retention exemption

## What Was Done
Made all vector-backed features (chat RAG, semantic endpoints, cluster analysis, agents) commit-aware so IDE context.ref determines which commit's vectors are queried.

**VectorStoreService**: Centralized vector access with blake2b-based stable point IDs (deterministic across processes), in-memory TTL cache for ref→SHA resolution, async+sync DB paths. Supports 40-hex SHA passthrough, branch name resolution via GitHub API, fallback to latest completed Analysis commit.

**Embeddings Pipeline**: Changed delete filter from repository_id-only to (repository_id, commit_sha), enabling multiple commit snapshots per repo. Point IDs include commit_sha for uniqueness. update_embeddings and delete_embeddings accept optional commit_sha.

**Chat RAG**: Phase 0 commit resolution before RAG queries. SSE emits context_source events showing filter mode (commit vs repo-only). semantic_search tool passes resolved commit to queries.

**Semantic Endpoints**: All vector-backed endpoints (/semantic-search, /related-code, /similar-code, /style-consistency) accept optional ref param. Default is commit-centric (latest completed Analysis) rather than repo-wide.

**Retention**: Configurable policy (N analyses / X days), pinned column for manual retention, cleanup task prunes vectors for old unpinned analyses.

**Telemetry**: Structured logs with `extra={"telemetry": True}` for all vector operations including repository_id, commit_sha, filter_mode, hits, avg_score.


# 15-dec-2025 - Repository Content Cache (MinIO + PostgreSQL)

## Files Created
- `backend/app/models/repo_content_cache.py` - RepoContentCache SQLAlchemy model (status, file_count, total_size_bytes)
- `backend/app/models/repo_content_object.py` - RepoContentObject model (path, object_key, content_hash)
- `backend/app/models/repo_content_tree.py` - RepoContentTree model (JSONB tree structure)
- `backend/alembic/versions/018_add_repo_content_cache.py` - Migration for all three tables with indexes
- `backend/app/services/object_storage.py` - ObjectStorageClient interface + MinIOClient implementation
- `backend/app/services/repo_content.py` - RepoContentService (cache management, file collection, upload, retrieval)
- `backend/app/workers/repo_content_gc.py` - GC worker for cleanup of failed/old caches
- `backend/tests/test_repo_content_cache.py` - Property tests for cache operations
- `backend/tests/test_object_storage.py` - Unit tests for MinIO client
- `backend/tests/test_chat_cache_integration.py` - Integration tests for chat cache usage

## Files Modified
- `backend/app/workers/embeddings.py` - Added cache population after clone (collect files → upload to MinIO → save tree)
- `backend/app/api/v1/chat.py` - Updated `_get_repo_tree_lines` and `_read_repo_file_text` to try cache first, fallback to GitHub API
- `backend/scripts/init_minio.py` - Added `repo-content` bucket creation
- `backend/scripts/init_all.py` - Added `repo-content` bucket to initialization
- `backend/README.md` - Added deployment instructions for MinIO bucket initialization

## What Was Done
Implemented production-grade content cache for repository files using PostgreSQL for metadata and MinIO for file storage. Cache is commit-centric (tied to specific commit SHA) ensuring consistency with analysis results.

**Architecture**: PostgreSQL stores metadata (cache status, file paths, content hashes), MinIO stores actual file bytes with UUID-based object keys. Stable keys avoid path encoding issues and enable efficient storage.

**Cache Population**: During embeddings worker clone phase, files are collected (same filters as embeddings: code extensions, 50B-100KB size), SHA-256 hashed, uploaded to MinIO, and recorded in PostgreSQL. Tree structure saved as JSONB for fast directory listings.

**Chat Integration**: `_get_repo_tree_lines` and `_read_repo_file_text` try cache first (1-10ms latency) before falling back to GitHub API (100-500ms). Content hash verified on retrieval for integrity.

**GC Worker**: Celery task cleans up failed caches (24h threshold), old commits (keep 5 most recent per repo), and orphaned MinIO objects for deleted repositories.

**Idempotency**: Upload operations check content_hash before uploading, PostgreSQL UNIQUE constraints prevent duplicate entries, optimistic locking via version column.


# 15-dec-2025 - Chat Branch Context Awareness

## Files Created
- `backend/alembic/versions/019_add_chat_message_context_ref.py` - Migration adding context_ref VARCHAR(255) column to chat_messages with index

## Files Modified
- `backend/app/models/chat.py` - Added `context_ref: Mapped[str | None]` field to ChatMessage model
- `backend/app/api/v1/chat.py` - Added `_detect_ref_change()` for ref comparison, `_build_context_switch_notification()` for system message injection, updated `_build_chat_messages()` and `_stream_response()` to inject notifications, save context_ref with user/assistant messages
- `frontend/lib/api.ts` - Added `context_ref?: string` to message interface
- `frontend/components/chat-panel.tsx` - Added branch indicator badge showing shortened ref when different from current context

## What Was Done
Implemented branch/commit context awareness for chat conversations. When users switch branches or commits mid-conversation, the system detects the change and injects a system notification to inform the LLM about the context switch.

**Context Detection**: Compares current `context.ref` with last message's stored `context_ref`. Handles null refs and empty message history gracefully.

**System Notification**: Injects clear message explaining the switch (previous ref → current ref) so LLM understands earlier messages were about different code version.

**Message Persistence**: Both user and assistant messages store their `context_ref` in PostgreSQL, enabling conversation history to show which branch/commit each message was about.

**Frontend Display**: Messages show branch indicator badge when their ref differs from current context. Shortened display (first 7 chars for commit SHAs).

**Cache Integration**: Works with existing repo content cache - cached commits get fast responses, uncached branches fall back to GitHub API.
