#!/bin/bash
# Pre-push CI check script
# Runs the same checks as .github/workflows/deploy.yml locally
# Usage: ./scripts/pre-push-check.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Track failures
BACKEND_LINT_FAILED=0
BACKEND_TESTS_FAILED=0
FRONTEND_LINT_FAILED=0
FRONTEND_TESTS_FAILED=0
FRONTEND_BUILD_FAILED=0

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  n9r Pre-Push CI Check${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Get the root directory
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# ============================================
# Backend Checks
# ============================================
echo -e "${YELLOW}🐍 BACKEND CHECKS${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

cd "$ROOT_DIR/backend"

# Lint
echo -e "${BLUE}Running ruff linter...${NC}"
if uv run ruff check .; then
    echo -e "${GREEN}✓ Ruff lint passed${NC}"
else
    echo -e "${RED}✗ Ruff lint failed${NC}"
    BACKEND_LINT_FAILED=1
fi
echo ""

# Type check (non-blocking, same as CI)
echo -e "${BLUE}Running mypy type checker (non-blocking)...${NC}"
if uv run mypy . --ignore-missing-imports; then
    echo -e "${GREEN}✓ Mypy passed${NC}"
else
    echo -e "${YELLOW}⚠ Mypy has errors (non-blocking)${NC}"
fi
echo ""

# Tests
echo -e "${BLUE}Running pytest...${NC}"
if uv run pytest -v --tb=short; then
    echo -e "${GREEN}✓ Backend tests passed${NC}"
else
    echo -e "${RED}✗ Backend tests failed${NC}"
    BACKEND_TESTS_FAILED=1
fi
echo ""

# ============================================
# Frontend Checks
# ============================================
echo -e "${YELLOW}⚛️  FRONTEND CHECKS${NC}"
echo -e "${YELLOW}----------------------------------------${NC}"

cd "$ROOT_DIR/frontend"

# Lint
echo -e "${BLUE}Running ESLint...${NC}"
if pnpm lint; then
    echo -e "${GREEN}✓ ESLint passed${NC}"
else
    echo -e "${RED}✗ ESLint failed${NC}"
    FRONTEND_LINT_FAILED=1
fi
echo ""

# Tests
echo -e "${BLUE}Running vitest...${NC}"
if pnpm test; then
    echo -e "${GREEN}✓ Frontend tests passed${NC}"
else
    echo -e "${RED}✗ Frontend tests failed${NC}"
    FRONTEND_TESTS_FAILED=1
fi
echo ""

# Build
echo -e "${BLUE}Running build check...${NC}"
if pnpm build; then
    echo -e "${GREEN}✓ Frontend build passed${NC}"
else
    echo -e "${RED}✗ Frontend build failed${NC}"
    FRONTEND_BUILD_FAILED=1
fi
echo ""

# ============================================
# Summary
# ============================================
cd "$ROOT_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  SUMMARY${NC}"
echo -e "${BLUE}========================================${NC}"

TOTAL_FAILURES=$((BACKEND_LINT_FAILED + BACKEND_TESTS_FAILED + FRONTEND_LINT_FAILED + FRONTEND_TESTS_FAILED + FRONTEND_BUILD_FAILED))

if [ $BACKEND_LINT_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ Backend lint${NC}"
else
    echo -e "${RED}✗ Backend lint${NC}"
fi

if [ $BACKEND_TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ Backend tests${NC}"
else
    echo -e "${RED}✗ Backend tests${NC}"
fi

if [ $FRONTEND_LINT_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ Frontend lint${NC}"
else
    echo -e "${RED}✗ Frontend lint${NC}"
fi

if [ $FRONTEND_TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ Frontend tests${NC}"
else
    echo -e "${RED}✗ Frontend tests${NC}"
fi

if [ $FRONTEND_BUILD_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ Frontend build${NC}"
else
    echo -e "${RED}✗ Frontend build${NC}"
fi

echo ""

if [ $TOTAL_FAILURES -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  ✅ All checks passed! Ready to push.${NC}"
    echo -e "${GREEN}========================================${NC}"
    exit 0
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  ❌ $TOTAL_FAILURES check(s) failed${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
fi
