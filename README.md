<h1 align="center">n9r</h1>

<p align="center">
  <strong>Semantic Code Analysis Platform Using Machine Learning and Static Analysis</strong>
</p>

<p align="center">
  <em>A research-oriented system that combines traditional software metrics with vector embeddings to detect code quality issues, architectural anomalies, and technical debt.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/ML-embeddings-blue?style=for-the-badge" alt="ML Embeddings" />
  <img src="https://img.shields.io/badge/analysis-multi--language-green?style=for-the-badge" alt="Multi-Language Analysis" />
</p>

<p align="center">
  <img src="frontend/public/Screenshot n9r.png" alt="n9r Dashboard" width="100%" />
</p>

---

## Abstract

Modern software development increasingly relies on AI-assisted code generation tools (GitHub Copilot, Cursor, ChatGPT), which introduce unique challenges for code quality management. While these tools accelerate development, they often produce code with subtle issues that traditional static analyzers miss:

- **Increased cyclomatic complexity** — AI-generated code tends toward verbose, nested structures
- **Semantic duplication** — Functionally identical code with syntactic variations
- **Architectural inconsistency** — Code that works but doesn't follow established patterns
- **Unreachable code accumulation** — Functions generated "just in case" that are never called
- **Implicit dependencies** — Hidden coupling between modules

**n9r** addresses these challenges by combining classical software engineering metrics with modern machine learning techniques, specifically vector embeddings and density-based clustering, to provide deeper insight into code quality.

---

## Research Contributions

This project demonstrates several key technical contributions:

1. **Hybrid Analysis Approach** — Integrates static analysis (cyclomatic complexity, Halstead metrics) with semantic analysis (code embeddings, clustering) to detect issues that neither approach finds alone

2. **Composite Quality Metric** — The Vibe-Code Index (VCI) provides a single, interpretable score derived from multiple weighted factors, enabling longitudinal tracking of code health

3. **Unsupervised Anomaly Detection** — Uses HDBSCAN clustering on code embeddings to identify outliers without requiring labeled training data

4. **Multi-Factor Confidence Scoring** — A novel approach to ranking detected issues by combining structural, semantic, and contextual signals

---

## Methodology

### Vibe-Code Index (VCI)

The VCI is a composite metric (0-100) that aggregates multiple quality dimensions:

| Component | Weight | Measurement Approach |
|-----------|--------|---------------------|
| Complexity | 25% | Cyclomatic complexity (McCabe), function length |
| Duplication | 20% | Token-based clone detection |
| Maintainability | 25% | Halstead metrics, file organization |
| Code Smells | 20% | AST-based heuristic detection |
| Architecture | 10% | Cluster cohesion, coupling analysis |

**Interpretation:**
```
80-100  High Quality      — Well-structured, maintainable code
60-79   Acceptable        — Minor issues, manageable technical debt
40-59   Concerning        — Significant refactoring recommended
0-39    Critical          — Major architectural problems detected
```

### Semantic Analysis Pipeline

The system uses vector embeddings to understand code at a semantic level:

1. **Code Chunking** — Source files are parsed into semantic units (functions, classes, modules) using language-specific AST parsers (Tree-sitter)

2. **Embedding Generation** — Each code chunk is converted to a high-dimensional vector (1536-3072 dimensions) using LLM embedding models

3. **Density-Based Clustering** — HDBSCAN identifies natural groupings in the embedding space, revealing the actual modular structure of the codebase

4. **Anomaly Detection** — Points that don't belong to any cluster (outliers) are flagged as potential dead code, misplaced functions, or architectural violations

### Outlier Confidence Scoring

Not all detected outliers are true positives. The system uses a multi-factor scoring approach:

```
Base Score: 0.5

Penalties (reduce confidence):
- Boilerplate patterns detected: -0.15
- Import relationships exist: -0.1
- Cross-layer utility code: -0.1

Boosts (increase confidence):
- High isolation (no references): +0.2
- Semantic duplicates found: +0.15
- Circular import involvement: +0.1

Final Score: clamped to [0.1, 0.9]
```

| Confidence | Classification | Recommended Action |
|------------|---------------|-------------------|
| ≥ 0.7 | High confidence | Immediate review |
| 0.5-0.7 | Medium confidence | Schedule review |
| < 0.4 | Low confidence | Likely false positive |

---

## Technical Implementation

### Static Analysis Methods

**Cyclomatic Complexity (CC)** — Measures the number of linearly independent paths through code using McCabe's formula: `CC = E - N + 2P`, where E = edges, N = nodes, P = connected components in the control flow graph.

**Halstead Metrics** — Computes software science metrics from operator/operand counts:
- Volume: `V = N × log₂(η)` where N = total operators + operands, η = unique operators + operands
- Difficulty: `D = (η₁/2) × (N₂/η₂)`
- Effort: `E = D × V`

**Maintainability Index** — Composite formula: `MI = 171 - 5.2×ln(V) - 0.23×CC - 16.2×ln(LOC)`, normalized to 0-100.

**AST-Based Detection** — Uses Tree-sitter for language-agnostic parsing to detect:
- Generic variable names (data, temp, result)
- Magic numbers (unexplained numeric literals)
- Single-letter variables outside loop contexts

### Semantic Analysis Methods

**Code Embeddings** — Leverages pre-trained language models (OpenAI, Azure, Gemini) to generate dense vector representations that capture semantic meaning, not just syntax.

**HDBSCAN Clustering** — Hierarchical Density-Based Spatial Clustering of Applications with Noise:
- Automatically determines cluster count
- Handles varying cluster densities
- Explicitly identifies noise points (outliers)
- Parameters: `min_cluster_size`, `min_samples`

**Cluster Cohesion** — Measures intra-cluster similarity: `Cohesion = 1 - mean(pairwise_cosine_distances)`. Values ≥0.7 indicate well-organized modules.

**Architecture Health Score** — Weighted aggregation:
```
Health = 0.35×Cohesion + 0.30×(1-OutlierRatio) + 0.25×Balance + 0.10×(1-Coupling)
```

---

## System Architecture

### Analysis Pipeline

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Clone     │────▶│   Analyze   │────▶│  Calculate  │────▶│    Store    │
│   Repo      │     │   Code      │     │   VCI Score │     │   Results   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         ┌────────┐   ┌────────┐   ┌────────┐
         │ radon  │   │ lizard │   │  AST   │
         │(Python)│   │(Other) │   │Analysis│
         └────────┘   └────────┘   └────────┘
```

### Semantic Analysis Pipeline

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│    Chunk    │────▶│   Generate  │────▶│   Cluster   │────▶│   Analyze   │
│   Code      │     │  Embeddings │     │   (HDBSCAN) │     │   Health    │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │                   │
       ▼                   ▼                   ▼                   ▼
  Functions,          LLM Vectors         Clusters,          Health Score,
  Classes,            (1536-3072d)        Outliers           Recommendations
  Modules
```

### Parallel Processing Architecture

The system employs a triple-track parallel analysis strategy:
- **Track 1**: Static analysis (complexity, metrics)
- **Track 2**: Embedding generation and clustering
- **Track 3**: LLM-powered code review

This reduces total analysis time by approximately 50% compared to sequential processing.

---

## Technology Stack

### Backend (Python 3.11+)
- **Framework**: FastAPI with async/await for high-concurrency API handling
- **ORM**: SQLAlchemy 2.0 with async support
- **Task Queue**: Celery with Redis for distributed processing
- **AI/LLM**: LiteLLM (multi-provider abstraction), LangChain
- **Analysis Tools**: radon (Python metrics), lizard (multi-language), tree-sitter (AST parsing)

### Frontend (TypeScript)
- **Framework**: Next.js 16 with App Router
- **Styling**: Tailwind CSS 4 + shadcn/ui component library
- **State Management**: Zustand + TanStack Query
- **Code Display**: Monaco Editor

### Infrastructure
- **Database**: PostgreSQL 16 (relational data, state management)
- **Vector Database**: Qdrant (embedding storage, similarity search)
- **Cache/Message Broker**: Redis 7
- **Object Storage**: MinIO (S3-compatible)

### Multi-Language Support

| Language | Analyzer | Available Metrics |
|----------|----------|-------------------|
| Python | radon | CC, Halstead, MI, Raw metrics |
| JavaScript/TypeScript | lizard | CC, NLOC, Parameters |
| Java, Go, C/C++ | lizard | CC, NLOC, Parameters |
| 20+ additional languages | lizard | Basic complexity metrics |

---

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Node.js 20+ and pnpm
- Python 3.11+ and uv
- GitHub OAuth App credentials

### Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/n9r.git
   cd n9r
   ```

2. **Set up environment**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Start infrastructure** (Postgres, Redis, Qdrant, MinIO)
   ```bash
   docker compose up -d
   ```

4. **Initialize backend**
   ```bash
   cd backend
   uv sync
   uv run python scripts/init_all.py
   uv run alembic upgrade head
   ```

5. **Start backend server**
   ```bash
   uv run uvicorn main:app --reload --port 8000
   ```

6. **Start Celery worker** (new terminal)
   ```bash
   cd backend
   uv run celery -A app.core.celery worker -Q default,analysis,embeddings,healing,notifications,ai_scan --loglevel=info
   ```

7. **Start frontend** (new terminal)
   ```bash
   cd frontend
   pnpm install
   pnpm dev
   ```

8. **Open the app** → [http://localhost:3000](http://localhost:3000)

### Production Deployment

For production, all services run in Docker containers:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

---

## Project Structure

```
n9r/
├── backend/                 # FastAPI Python backend
│   ├── app/
│   │   ├── api/v1/         # REST API endpoints
│   │   ├── services/       # Core analysis logic
│   │   │   ├── repo_analyzer.py    # VCI calculation
│   │   │   ├── cluster_analyzer.py # HDBSCAN clustering
│   │   │   ├── ast_analyzer.py     # Tree-sitter parsing
│   │   │   └── llm_gateway.py      # Multi-provider LLM
│   │   └── workers/        # Celery async tasks
│   └── tests/              # Unit and integration tests
├── frontend/               # Next.js 16 frontend
│   ├── app/                # App Router pages
│   ├── components/         # React components
│   └── lib/                # Utilities, API clients
└── docs/                   # Documentation
```

---

## Future Work

- [x] Composite VCI score calculation
- [x] Multi-language static analysis
- [x] Semantic clustering with HDBSCAN
- [x] Confidence-scored outlier detection
- [x] Commit-based historical analysis
- [ ] Automated pull request generation for fixes
- [ ] GitLab/Bitbucket integration
- [ ] VS Code extension for real-time analysis

---

## License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  <strong>n9r</strong> — Semantic Code Analysis Platform
</p>
