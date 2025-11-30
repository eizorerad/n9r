# Requirements Document

## Introduction

This document specifies the requirements for implementing multi-language code complexity analysis in the n9r platform. Currently, the system only analyzes Python code using `radon`, leaving JavaScript, TypeScript, and other languages without complexity metrics (Cyclomatic Complexity, Halstead Metrics, Maintainability Index). This feature will add support for analyzing JS/TS and other common languages, with intelligent merging of results for monorepos containing multiple languages.

## Glossary

- **VCI (Vibe-Code Index)**: Composite code health score (0-100) based on complexity, duplication, maintainability, and architecture metrics
- **Cyclomatic Complexity (CC)**: Measure of code complexity based on the number of linearly independent paths through a program
- **Halstead Metrics**: Software metrics based on operators and operands (Volume, Difficulty, Effort, Bugs estimate)
- **Maintainability Index (MI)**: Composite metric indicating how maintainable code is (0-100 scale)
- **radon**: Python-only static analysis tool currently used for complexity metrics
- **lizard**: Polyglot code complexity analyzer supporting 20+ languages including Python, JS, TS, Java, Go, C/C++
- **RepoAnalyzer**: Backend service class responsible for analyzing repositories
- **Monorepo**: Repository containing multiple projects/languages (e.g., backend + frontend)

## Requirements

### Requirement 1: Multi-Language Complexity Detection

**User Story:** As a developer scanning a JavaScript/TypeScript project, I want to see cyclomatic complexity metrics, so that I can identify complex functions that need refactoring.

#### Acceptance Criteria

1. WHEN the RepoAnalyzer scans a repository containing JavaScript files THEN the system SHALL calculate cyclomatic complexity for all JS functions
2. WHEN the RepoAnalyzer scans a repository containing TypeScript files THEN the system SHALL calculate cyclomatic complexity for all TS functions
3. WHEN a repository contains only JS/TS files (no Python) THEN the system SHALL return non-zero complexity_distribution metrics
4. WHEN analyzing JS/TS files THEN the system SHALL populate the top_complex_functions list with JS/TS functions sorted by complexity
5. WHEN the complexity analyzer encounters a syntax error in a JS/TS file THEN the system SHALL log the error and continue analyzing other files

### Requirement 2: Halstead Metrics for JavaScript/TypeScript

**User Story:** As a tech lead reviewing code quality, I want to see Halstead metrics for our Next.js frontend, so that I can estimate maintenance effort and potential bugs.

#### Acceptance Criteria

1. WHEN analyzing JS/TS files THEN the system SHALL calculate Halstead Volume metric
2. WHEN analyzing JS/TS files THEN the system SHALL calculate Halstead Difficulty metric
3. WHEN analyzing JS/TS files THEN the system SHALL calculate Halstead Effort metric
4. WHEN analyzing JS/TS files THEN the system SHALL calculate estimated bugs based on Halstead metrics
5. IF the analysis tool does not support Halstead metrics for JS/TS THEN the system SHALL use alternative estimation formulas based on available metrics

### Requirement 3: Maintainability Index for JavaScript/TypeScript

**User Story:** As a CTO, I want to see maintainability scores for our entire codebase including the frontend, so that I can prioritize refactoring efforts.

#### Acceptance Criteria

1. WHEN analyzing JS/TS files THEN the system SHALL calculate a Maintainability Index score (0-100)
2. WHEN displaying MI results THEN the system SHALL categorize files by grade (A: MI≥20, B: 10-20, C: <10)
3. WHEN a file has MI below 65 THEN the system SHALL flag it as hard to maintain
4. IF the analysis tool provides different MI scale THEN the system SHALL normalize to 0-100 scale

### Requirement 4: Monorepo Support with Merged Metrics

**User Story:** As a developer with a monorepo containing Python backend and TypeScript frontend, I want unified metrics across all languages, so that I can see the overall health of my project.

#### Acceptance Criteria

1. WHEN a repository contains both Python and JS/TS files THEN the system SHALL run appropriate analyzers for each language
2. WHEN merging complexity distributions THEN the system SHALL sum the counts for each grade (A, B, C, D, E, F)
3. WHEN calculating average complexity for mixed repos THEN the system SHALL use weighted average based on function count
4. WHEN generating top_complex_functions THEN the system SHALL combine functions from all languages and sort by complexity
5. WHEN merging Halstead metrics THEN the system SHALL sum volumes and calculate weighted averages for difficulty/effort
6. WHEN merging MI scores THEN the system SHALL calculate weighted average based on file count per language

### Requirement 5: Per-Language Breakdown

**User Story:** As a developer, I want to see metrics broken down by language, so that I can identify which part of my codebase needs the most attention.

#### Acceptance Criteria

1. WHEN analyzing a multi-language repository THEN the system SHALL include a by_language breakdown in the metrics
2. WHEN providing per-language breakdown THEN the system SHALL include file count, line count, and average complexity for each language
3. WHEN displaying results THEN the frontend SHALL render a "By Language" card showing per-language metrics
4. IF a language has zero files THEN the system SHALL omit that language from the breakdown
5. WHEN the by_language data is available THEN the frontend SHALL display language name, file count, line count, and average complexity for each language

### Requirement 6: Graceful Degradation

**User Story:** As a system administrator, I want the analysis to continue even if one language analyzer fails, so that users still get partial results.

#### Acceptance Criteria

1. IF the Python analyzer (radon) fails THEN the system SHALL continue with JS/TS analysis and return partial results
2. IF the JS/TS analyzer fails THEN the system SHALL continue with Python analysis and return partial results
3. WHEN an analyzer fails THEN the system SHALL log the error with sufficient detail for debugging
4. WHEN returning partial results THEN the system SHALL indicate which languages were successfully analyzed
5. IF all analyzers fail THEN the system SHALL return basic file/line counts with zero complexity metrics

### Requirement 7: Performance Requirements

**User Story:** As a user scanning a large repository, I want the analysis to complete in reasonable time, so that I don't have to wait too long for results.

#### Acceptance Criteria

1. WHEN analyzing a repository with up to 10,000 lines of code THEN the system SHALL complete complexity analysis within 60 seconds
2. WHEN analyzing a repository with up to 50,000 lines of code THEN the system SHALL complete complexity analysis within 180 seconds
3. WHEN running multiple analyzers THEN the system SHALL execute them sequentially to avoid resource contention
4. IF analysis exceeds timeout THEN the system SHALL return partial results with a timeout warning

### Requirement 8: Tool Selection and Installation

**User Story:** As a DevOps engineer, I want the complexity analyzer to be easy to install and maintain, so that deployment is straightforward.

#### Acceptance Criteria

1. THE system SHALL use lizard as the primary polyglot complexity analyzer
2. THE system SHALL keep radon for Python-specific metrics (Halstead, MI) as lizard provides better Python-specific analysis
3. WHEN the lizard tool is not installed THEN the system SHALL fall back to radon-only analysis with a warning
4. THE system SHALL add lizard to pyproject.toml dependencies
5. THE system SHALL document the tool selection rationale in architecture docs

