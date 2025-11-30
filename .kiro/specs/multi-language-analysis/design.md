# Design Document: Multi-Language Code Complexity Analysis

## Overview

This feature extends n9r's code analysis capabilities to support JavaScript, TypeScript, and other languages beyond Python. Currently, the `RepoAnalyzer` uses `radon` (Python-only) for complexity metrics, leaving JS/TS projects with zero values for Cyclomatic Complexity Distribution, Halstead Metrics, and Maintainability Index.

The solution adds `lizard` as a polyglot complexity analyzer while keeping `radon` for Python-specific metrics (Halstead, MI). For monorepos with multiple languages, results are intelligently merged.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      RepoAnalyzer.analyze()                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Clone Repository                                             │
│  2. Detect Languages (by file extensions)                        │
│                                                                  │
│  ┌─────────────────────┐    ┌─────────────────────┐             │
│  │  Python Files?      │    │  JS/TS/Other Files? │             │
│  │  ↓                  │    │  ↓                  │             │
│  │  radon cc/hal/mi    │    │  lizard             │             │
│  │  (full metrics)     │    │  (CC, LOC, params)  │             │
│  └─────────┬───────────┘    └─────────┬───────────┘             │
│            │                          │                          │
│            └──────────┬───────────────┘                          │
│                       ↓                                          │
│            ┌─────────────────────┐                               │
│            │  Merge Results      │                               │
│            │  - Sum CC dist      │                               │
│            │  - Weighted avg CC  │                               │
│            │  - Combined top 10  │                               │
│            │  - by_language      │                               │
│            └─────────────────────┘                               │
│                       ↓                                          │
│            ┌─────────────────────┐                               │
│            │  AnalysisResult     │                               │
│            └─────────────────────┘                               │
└─────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. LizardAnalyzer (New Class)

```python
@dataclass
class LizardFunctionMetrics:
    name: str
    file: str
    line: int
    complexity: int
    nloc: int  # Lines of code
    parameters: int
    rank: str  # A-F grade

@dataclass
class LizardAnalysisResult:
    functions_analyzed: int
    avg_complexity: float
    max_complexity: int
    high_complexity_count: int
    complexity_distribution: dict[str, int]  # {A: 10, B: 5, ...}
    top_complex_functions: list[LizardFunctionMetrics]
    total_nloc: int
    languages_analyzed: list[str]

class LizardAnalyzer:
    """Polyglot complexity analyzer using lizard."""
    
    SUPPORTED_EXTENSIONS = {
        '.js': 'javascript',
        '.jsx': 'javascript', 
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.java': 'java',
        '.go': 'go',
        '.c': 'c',
        '.cpp': 'cpp',
        '.rb': 'ruby',
        '.php': 'php',
    }
    
    def analyze(self, repo_path: Path, exclude_python: bool = True) -> LizardAnalysisResult:
        """Run lizard analysis on repository."""
        pass
    
    def _run_lizard(self, path: Path, languages: list[str]) -> dict:
        """Execute lizard CLI and parse JSON output."""
        pass
    
    def _calculate_rank(self, complexity: int) -> str:
        """Convert complexity to A-F grade."""
        pass
```

### 2. Updated RepoAnalyzer

```python
class RepoAnalyzer:
    def analyze(self) -> AnalysisResult:
        # ... existing clone, count_lines ...
        
        # NEW: Detect languages present
        languages = self._detect_languages()
        
        # Run Python analysis (radon) if Python files exist
        python_metrics = {}
        if 'python' in languages:
            python_metrics = self.analyze_python_complexity()
        
        # NEW: Run lizard for non-Python languages
        lizard_metrics = {}
        if languages - {'python'}:
            lizard_metrics = self.analyze_with_lizard()
        
        # NEW: Merge results
        complexity_data = self._merge_complexity_results(
            python_metrics, lizard_metrics
        )
        
        # ... rest of analysis ...
    
    def analyze_with_lizard(self) -> dict:
        """Analyze non-Python files using lizard."""
        pass
    
    def _detect_languages(self) -> set[str]:
        """Detect which languages are present in the repo."""
        pass
    
    def _merge_complexity_results(
        self, 
        python_data: dict, 
        lizard_data: dict
    ) -> dict:
        """Merge results from radon and lizard."""
        pass
```

### 3. Updated Metrics Schema

```python
# Extended metrics dict structure
{
    # Existing fields (unchanged)
    "complexity_score": float,
    "maintainability_score": float,
    "duplication_score": float,
    "architecture_score": float,
    "heuristics_score": float,
    "total_files": int,
    "total_lines": int,
    # ...
    
    # Complexity (now merged from radon + lizard)
    "avg_complexity": float,
    "max_complexity": int,
    "high_complexity_functions": int,
    "complexity_distribution": {"A": int, "B": int, ...},
    "top_complex_functions": [...],
    
    # Halstead (Python only, 0 for JS-only repos)
    "halstead": {...},
    
    # MI (Python only, 0 for JS-only repos)  
    "maintainability_index": {...},
    
    # NEW: Per-language breakdown
    "by_language": {
        "python": {
            "files": int,
            "lines": int,
            "avg_complexity": float,
            "functions": int,
        },
        "javascript": {...},
        "typescript": {...},
    }
}
```

## Data Models

### Complexity Grade Mapping

| Grade | Cyclomatic Complexity | Description |
|-------|----------------------|-------------|
| A | 1-5 | Simple, low risk |
| B | 6-10 | Low complexity |
| C | 11-20 | Moderate complexity |
| D | 21-30 | High complexity |
| E | 31-40 | Very high complexity |
| F | 41+ | Untestable |

### Lizard CLI Output Format

```json
{
  "filename": "src/utils.ts",
  "function_list": [
    {
      "name": "processData",
      "long_name": "processData at 10-45@src/utils.ts",
      "nloc": 35,
      "cyclomatic_complexity": 12,
      "token_count": 150,
      "parameter_count": 3,
      "start_line": 10,
      "end_line": 45
    }
  ]
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: JS/TS files produce non-zero complexity metrics
*For any* repository containing at least one JavaScript or TypeScript file with at least one function, the complexity_distribution SHALL have at least one non-zero grade count.
**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2: Top complex functions are sorted by complexity descending
*For any* analysis result with top_complex_functions containing more than one entry, each function's complexity SHALL be greater than or equal to the next function's complexity.
**Validates: Requirements 1.4, 4.4**

### Property 3: Merged complexity distribution equals sum of parts
*For any* monorepo with both Python and JS/TS files, the merged complexity_distribution[grade] SHALL equal python_distribution[grade] + lizard_distribution[grade] for all grades A-F.
**Validates: Requirements 4.2**

### Property 4: Weighted average complexity is correctly calculated
*For any* monorepo analysis, the merged avg_complexity SHALL equal (python_avg * python_func_count + lizard_avg * lizard_func_count) / total_func_count.
**Validates: Requirements 4.3**

### Property 5: by_language contains only languages with files
*For any* analysis result, every language in by_language SHALL have files > 0, and no language with 0 files SHALL appear in by_language.
**Validates: Requirements 5.1, 5.2, 5.4**

### Property 6: Partial results on analyzer failure
*For any* analysis where one analyzer fails, the result SHALL still contain metrics from the successful analyzer with non-zero values for that language's files.
**Validates: Requirements 6.1, 6.2, 6.4**

## Error Handling

| Scenario | Behavior |
|----------|----------|
| lizard not installed | Log warning, fall back to radon-only |
| radon not installed | Log warning, use lizard-only |
| Both tools fail | Return basic file/line counts, zero complexity |
| Syntax error in file | Skip file, log warning, continue |
| Timeout | Return partial results with warning |

## Testing Strategy

### Dual Testing Approach

**Unit Tests:**
- Test `LizardAnalyzer` with mock subprocess output
- Test `_merge_complexity_results` with various input combinations
- Test `_detect_languages` with different file structures
- Test grade calculation boundaries

**Property-Based Tests (using Hypothesis):**
- Generate random repository structures with mixed languages
- Verify merge properties hold across all inputs
- Test sorting invariants for top_complex_functions
- Verify by_language filtering properties

### Test Framework
- **Library**: `pytest` with `hypothesis` for property-based testing
- **Minimum iterations**: 100 per property test
- **Tag format**: `**Feature: multi-language-analysis, Property {N}: {description}**`

## Frontend Changes

### New "By Language" Card Component

Add a new card to `analysis-metrics.tsx` that displays per-language breakdown:

```tsx
{/* By Language Breakdown */}
{metrics.by_language && Object.keys(metrics.by_language).length > 0 && (
  <Card className="bg-gray-900/50 border-gray-800">
    <CardHeader>
      <CardTitle className="text-base flex items-center gap-2">
        <Code2 className="h-4 w-4" />
        By Language
      </CardTitle>
    </CardHeader>
    <CardContent>
      <div className="space-y-3">
        {Object.entries(metrics.by_language).map(([lang, data]) => (
          <div key={lang} className="flex items-center justify-between p-3 bg-gray-800/50 rounded-lg">
            <div className="flex items-center gap-3">
              <span className="text-lg">{getLanguageIcon(lang)}</span>
              <span className="font-medium capitalize">{lang}</span>
            </div>
            <div className="flex gap-6 text-sm">
              <div className="text-center">
                <p className="text-gray-400">Files</p>
                <p className="font-bold">{data.files}</p>
              </div>
              <div className="text-center">
                <p className="text-gray-400">Lines</p>
                <p className="font-bold">{data.lines.toLocaleString()}</p>
              </div>
              <div className="text-center">
                <p className="text-gray-400">Avg CC</p>
                <p className="font-bold">{data.avg_complexity.toFixed(1)}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </CardContent>
  </Card>
)}
```

### Language Icon Helper

```tsx
function getLanguageIcon(lang: string): string {
  const icons: Record<string, string> = {
    python: '🐍',
    javascript: '📜',
    typescript: '💠',
    java: '☕',
    go: '🐹',
    ruby: '💎',
    php: '🐘',
    c: '⚙️',
    cpp: '⚙️',
  }
  return icons[lang.toLowerCase()] || '📄'
}
```

### Updated TypeScript Interface

```tsx
interface AnalysisMetricsProps {
  metrics: {
    // ... existing fields ...
    
    // NEW: Per-language breakdown
    by_language?: Record<string, {
      files: number
      lines: number
      avg_complexity: number
      functions: number
    }>
  } | null
}
```

## Implementation Notes

### lizard Installation
```bash
pip install lizard
```

Add to `backend/pyproject.toml`:
```toml
[project.dependencies]
lizard = "^1.17.10"
```

### lizard CLI Usage
```bash
# JSON output for all supported languages
lizard --json /path/to/repo

# Exclude specific directories
lizard --json --exclude "node_modules/*,dist/*,build/*" /path/to/repo

# Specific languages only
lizard --json -l javascript -l typescript /path/to/repo
```

### Performance Considerations
- Run radon and lizard sequentially (not parallel) to avoid resource contention
- Use `--exclude` to skip node_modules, dist, build directories
- Set timeout of 120 seconds per analyzer
