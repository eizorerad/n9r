<h1 align="center">🎃 Necromancer (n9r)</h1>

<p align="center">
  <strong>AI-Powered Code Detox & Auto-Healing Platform</strong>
</p>

<p align="center">
  <em>Resurrect your dead code. Exorcise the demons. Bring your codebase back from the grave.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/spooky-certified-purple?style=for-the-badge" alt="Spooky Certified" />
  <img src="https://img.shields.io/badge/dead_code-resurrected-green?style=for-the-badge" alt="Dead Code Resurrected" />
</p>

<p align="center">
  <img src="frontend/public/Screenshot n9r.png" alt="Necromancer Dashboard" width="100%" />
</p>

---

## 👻 The Haunting Problem

Teams using AI coding assistants (Copilot, Cursor, ChatGPT) have unleashed a new horror upon their codebases:

- 🍝 **AI-generated spaghetti** — tangled code that would make Frankenstein's monster weep
- 📋 **Copy-paste zombies** — duplicated logic shambling across files
- 🏚️ **Architectural decay** — structures crumbling like haunted mansions
- 💀 **Dead code graveyards** — functions that nobody calls, yet nobody dares delete
- 📝 **Prompt-driven curses** — code that works but nobody understands why

**Classic tools like linters are mere mortals.** They catch syntax issues, not the supernatural rot lurking in your architecture.

## 🧙‍♂️ The Necromancer's Solution

**Necromancer (n9r)** is an AI-powered platform that practices the dark arts of code resurrection:

1. 🔮 **Divines** your codebase semantically using vector embeddings
2. 👁️ **Detects** vibe-code, dead code, and architectural hauntings
3. 📊 **Calculates** a VCI (Vibe-Code Index) — your code's life force
4. ⚗️ **Heals** your project through small, safe auto-PRs with tests

*"We don't just find dead code — we decide if it should stay buried."*

---

## 🦇 Features

### 📊 Vibe-Code Index (VCI) — The Life Force Meter

A composite score (0-100) measuring your code's vital signs:

| Component | Weight | What It Measures |
|-----------|--------|------------------|
| 💀 Complexity | 25% | Cyclomatic complexity, function length |
| 👯 Duplication | 20% | Repeated code patterns (clones!) |
| 🏚️ Maintainability | 25% | File sizes, code organization |
| 🎭 Heuristics | 20% | Generic names, magic numbers, TODOs |
| 🏗️ Architecture | 10% | Structural consistency |

```
🟢 80-100  Alive & Thriving   — Your code has a strong pulse!
🟡 60-79   Needs Healing      — Some dark spots detected
🟠 40-59   Critical Condition — The curse is spreading
🔴 0-39    Undead Territory   — Call the Necromancer immediately!
```

### 🧠 Semantic Analysis — The Third Eye

Vector-based architecture understanding that sees beyond the veil:

- **🕸️ Cluster Detection** — Find natural module boundaries using HDBSCAN
- **💀 Outlier Detection** — Identify dead, orphaned, or possessed code
- **🕷️ Coupling Hotspots** — Find "god files" that have grown too powerful
- **⚰️ Architecture Health Score** — Quantify how haunted your structure is

### 🌍 Multi-Language Séance

| Language | Analyzer | Metrics |
|----------|----------|---------|
| 🐍 Python | radon | CC, Halstead, MI, Raw |
| 👻 JavaScript/TypeScript | lizard | CC, NLOC, Parameters |
| ☕ Java, 🐹 Go, 💀 C/C++ | lizard | CC, NLOC, Parameters |
| 20+ languages | lizard | Basic complexity |

---

## 🕸️ How It Works

### The Resurrection Pipeline

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  🪦 Clone   │────▶│  🔍 Analyze │────▶│  📊 Calculate│────▶│  💾 Store   │
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

### The Séance Pipeline (Semantic Analysis)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  🔪 Chunk   │────▶│  🔮 Generate│────▶│  🕸️ Cluster │────▶│  👁️ Analyze │
│   Code      │     │  Embeddings │     │   (HDBSCAN) │     │   Health    │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │                   │
       ▼                   ▼                   ▼                   ▼
  Functions,          LLM Vectors         Clusters,          Health Score,
  Classes,            (1536-3072d)        Outliers           Suggestions
  Modules
```

---

## 🔬 Technical Methods & Algorithms

### 1. Static Code Analysis

**Cyclomatic Complexity (CC)** — Measures independent code paths using McCabe's formula: `CC = E - N + 2P`. We use **radon** for Python and **lizard** for 20+ other languages.

**Halstead Metrics** — Computes program Volume, Difficulty, Effort, and Bug estimates from operators and operands.

**Maintainability Index** — Formula: `MI = 171 - 5.2×ln(V) - 0.23×CC - 16.2×ln(LOC)`, normalized to 0-100.

**AST-Based Detection** — Uses **Tree-sitter** to parse Python/JS/TS and detect generic variable names, magic numbers, and single-letter variables with full context awareness (ignores loop variables and function parameters).

### 2. Semantic Analysis (Vector-Based)

**Code Embeddings** — Code is chunked into semantic units (functions, classes) and converted to high-dimensional vectors (1536-3072 dimensions) using LLM embedding models (OpenAI, Azure, Gemini).

**HDBSCAN Clustering** — Hierarchical Density-Based Spatial Clustering discovers natural code groupings without specifying cluster count. Automatically identifies outliers (label = -1).

**Cluster Cohesion** — Measures how related code within a cluster is: `Cohesion = 1 - mean(pairwise_cosine_distances)`. Values ≥0.7 indicate healthy, well-organized modules.

**Outlier Confidence Scoring** — Multi-factor system starting at 0.5, with penalties (boilerplate detection, import relationships, cross-layer) and boosts (isolation, duplicates, circular imports). Final score clamped to 0.1-0.9.

| Confidence | Tier | Action |
|------------|------|--------|
| ≥ 0.7 | Critical | Immediate review needed |
| 0.5-0.7 | Recommended | Should address soon |
| < 0.4 | Filtered | Not shown (likely false positive) |

**Architecture Health Score** — Weighted formula:
```
Health = Cohesion(35%) + Outliers(30%) + Balance(25%) + Coupling(10%)
```

### 3. VCI Score Calculation

The Vibe-Code Index combines all metrics:
```
VCI = Complexity(25%) + Duplication(20%) + Maintainability(25%) + Heuristics(20%) + Architecture(10%)
```

Complexity score scales inversely with average CC. Heuristics score penalizes generic names, magic numbers, missing documentation, and TODO comments.

### 4. Supporting Technologies

**Import Analysis** — Regex-based extraction of Python and JS/TS imports to detect circular dependencies, shared modules, and intentional relationships.

**Qdrant Vector DB** — Stores code embeddings for semantic search with cosine similarity and metadata filtering by repository, file path, and language.

---

## ⚰️ Tech Stack

### Backend (Python 3.11+)
- **Framework**: FastAPI with async/await
- **ORM**: SQLAlchemy 2.0 (async)
- **Task Queue**: Celery with Redis
- **AI/LLM**: LiteLLM (multi-provider), LangChain
- **Analysis**: radon, lizard, tree-sitter

### Frontend (TypeScript)
- **Framework**: Next.js 16 (App Router)
- **Styling**: Tailwind CSS 4 + shadcn/ui
- **State**: Zustand + TanStack Query
- **Editor**: Monaco Editor

### Infrastructure
- **Database**: PostgreSQL 16
- **Vector DB**: Qdrant
- **Cache/Broker**: Redis 7
- **Storage**: MinIO (S3-compatible)

---

## 🧟 Getting Started

### Prerequisites

- 🐳 Docker & Docker Compose
- 📦 Node.js 20+ and pnpm
- 🐍 Python 3.11+ and uv
- 🔑 GitHub OAuth App credentials

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

8. **Open the app** → [http://localhost:3000](http://localhost:3000) 🌙

### Production Deployment

For production, all services run in Docker containers:

1. **Build and start all services**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```

2. **Check status**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
   ```

3. **View logs**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f backend celery-worker
   ```

This starts: Postgres, Redis, Qdrant, MinIO, Backend API, Celery Worker, and Celery Beat.

---

## 🏚️ Project Structure

```
n9r/
├── backend/                 # FastAPI Python backend
│   ├── app/
│   │   ├── api/v1/         # REST API endpoints
│   │   ├── services/       # Business logic
│   │   │   ├── repo_analyzer.py    # VCI calculation
│   │   │   ├── cluster_analyzer.py # Semantic analysis
│   │   │   └── llm_gateway.py      # Multi-provider LLM
│   │   └── workers/        # Celery tasks
│   └── tests/
├── frontend/               # Next.js 16 frontend
│   ├── app/                # App Router pages
│   ├── components/         # React components
│   └── lib/                # Utilities, API clients
└── docs/                   # Documentation
```

---

## 🗺️ Roadmap

- [x] 📊 VCI Score calculation
- [x] 🌍 Multi-language complexity analysis
- [x] 🕸️ Semantic clustering with HDBSCAN
- [x] 💀 Outlier detection with confidence scoring
- [x] 📅 Commit-centric dashboard
- [ ] 🔧 Auto-PR generation (auto-healing)
- [ ] 🦊 GitLab/Bitbucket support
- [ ] 🧩 VS Code extension

---

## 📋 Release Notes

### v0.2.0-alpha — The AI & Semantic Update

> We've successfully merged traditional static analysis with LLM-powered insights.

#### ✨ Added
- **AI Insights Panel** — Drill down into issues with "Expand for Evidence" and severity grouping
- **Commit Timeline** — Time-travel through your repo's history to see how code health has evolved
- **Transparent Scoring** — New "Dead Code Impact" and "Hotspot Risk" formulas so you know exactly why a file is flagged
- **Multi-Language Support** — Added JS/TS, Go, and Java support via Lizard (alongside Radon for Python)

#### ⚡ Improved
- **Triple-Track Parallel Analysis** — Static, Embeddings, and AI Scans now run simultaneously, cutting analysis time by ~50%
- **AST-enabled Call Graphs** — 99% accuracy in dead code detection

#### 🔧 Changed
- Refactored state management to PostgreSQL (goodbye Redis dependency for critical state)
- Refactored UI in VSC style

---

## 📜 License

This project is licensed under the Apache 2 License - see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  <strong>🎃 Necromancer (n9r)</strong>
</p>

<p align="center">
  <em>Because AI-generated code deserves AI-powered resurrection.</em>
</p>

<p align="center">
  🦇 Happy Haunting! 🦇
</p>
