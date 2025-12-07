#!/usr/bin/env python3
"""Manual test script to verify AI API keys are working for AI Scan.

This script tests each LLM provider configured in your .env file to ensure
the API keys are valid and the models respond correctly.

Usage:
    cd backend
    uv run python scripts/test_ai_apis.py

The script will test:
1. Gemini API (gemini/gemini-3-pro-preview) - for AI Scan broad scan
2. AWS Bedrock Claude (bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0) - for AI Scan broad scan
3. OpenAI API (gpt-4o) - fallback and embeddings
4. Anthropic API (claude-3-5-sonnet) - fallback
5. Embedding generation - required for semantic analysis
"""

import asyncio
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set up environment before importing app modules
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    print(f"⚠️  No .env file found at {env_path}")
    print("   Looking for environment variables...")


def print_header(title: str):
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(success: bool, message: str):
    """Print a test result."""
    icon = "✅" if success else "❌"
    print(f"{icon} {message}")


def check_env_vars():
    """Check which API keys are configured."""
    print_header("Environment Variables Check")

    keys = {
        "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", ""),
        "AWS_ACCESS_KEY_ID": os.environ.get("AWS_ACCESS_KEY_ID", ""),
        "AWS_SECRET_ACCESS_KEY": os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
        "AWS_REGION_NAME": os.environ.get("AWS_REGION_NAME", "us-east-1"),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
        "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", ""),
        "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", ""),
        "AZURE_API_KEY": os.environ.get("AZURE_API_KEY", ""),
    }

    configured = []
    missing = []

    for key, value in keys.items():
        if value and not value.startswith("sk-xxx") and not value.startswith("your-"):
            # Mask the key for display
            masked = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
            print_result(True, f"{key}: {masked}")
            configured.append(key)
        else:
            print_result(False, f"{key}: Not configured")
            missing.append(key)

    print(f"\n📊 Summary: {len(configured)} configured, {len(missing)} missing")

    # Check AI Scan specific requirements
    print("\n🔍 AI Scan Requirements:")

    has_gemini = "GEMINI_API_KEY" in configured
    has_bedrock = "AWS_ACCESS_KEY_ID" in configured and "AWS_SECRET_ACCESS_KEY" in configured
    has_openai = "OPENAI_API_KEY" in configured
    has_anthropic = "ANTHROPIC_API_KEY" in configured

    if has_gemini:
        print_result(True, "Gemini API configured (primary AI Scan model)")
    else:
        print_result(False, "Gemini API NOT configured (primary AI Scan model)")

    if has_bedrock:
        print_result(True, "AWS Bedrock configured (secondary AI Scan model)")
    else:
        print_result(False, "AWS Bedrock NOT configured (secondary AI Scan model)")

    if has_openai or has_gemini:
        print_result(True, "Embedding provider available")
    else:
        print_result(False, "No embedding provider (need OpenAI or Gemini)")

    return {
        "gemini": has_gemini,
        "bedrock": has_bedrock,
        "openai": has_openai,
        "anthropic": has_anthropic,
    }


async def test_gemini():
    """Test Gemini 3 Pro API (1M context)."""
    print_header("Testing Gemini 3 Pro (gemini/gemini-3-pro-preview)")

    if not os.environ.get("GEMINI_API_KEY"):
        print_result(False, "GEMINI_API_KEY not set, skipping")
        return False

    try:
        from app.services.llm_gateway import get_llm_gateway

        llm = get_llm_gateway()

        # Test only Gemini 3 Pro (1M context model)
        model = "gemini/gemini-3-pro-preview"
        print(f"   Testing {model}...")

        response = await llm.complete(
            prompt="Say 'Hello from Gemini 3 Pro!' in exactly those words.",
            model=model,
            max_tokens=50,
            temperature=0,
            fallback=False,
        )

        content = response.get("content", "") or ""
        usage = response.get("usage") or {}
        tokens = usage.get("total_tokens", 0)
        cost = response.get("cost", 0) or 0

        print_result(True, f"Model {model} works!")
        print(f"   Response: {content[:100]}...")
        print(f"   Tokens: {tokens}, Cost: ${cost:.6f}")
        return True

    except Exception as e:
        print_result(False, f"Error: {e}")
        return False


async def test_bedrock_claude():
    """Test AWS Bedrock Claude Sonnet 4.5 (1M context)."""
    print_header("Testing AWS Bedrock Claude Sonnet 4.5 (1M context)")

    if not os.environ.get("AWS_ACCESS_KEY_ID") or not os.environ.get("AWS_SECRET_ACCESS_KEY"):
        print_result(False, "AWS credentials not set, skipping")
        return False

    try:
        from app.services.llm_gateway import get_llm_gateway

        llm = get_llm_gateway()

        # Test Claude Sonnet 4.5 with cross-region inference profile
        model = "bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0"
        print(f"   Testing {model}...")

        response = await llm.complete(
            prompt="Say 'Hello from Claude Sonnet 4.5!' in exactly those words.",
            model=model,
            max_tokens=50,
            temperature=0,
            fallback=False,
            extra_headers={"anthropic-beta": "context-1m-2025-08-07"},
        )

        content = response.get("content", "") or ""
        usage = response.get("usage") or {}
        tokens = usage.get("total_tokens", 0)
        cost = response.get("cost", 0) or 0

        print_result(True, f"Model {model} works!")
        print(f"   Response: {content[:100]}...")
        print(f"   Tokens: {tokens}, Cost: ${cost:.6f}")
        return True

    except Exception as e:
        error_msg = str(e)
        print_result(False, f"Error: {error_msg[:100]}...")

        if "inference profile" in error_msg.lower() or "on-demand" in error_msg.lower():
            print("\n   💡 To fix Bedrock Sonnet 4.5 access:")
            print("   1. Go to AWS Console → Amazon Bedrock → Cross-region inference")
            print("   2. Create an inference profile for Claude Sonnet 4.5")
            print("   3. Or enable the model in Model access settings")

        return False


async def test_openai():
    """Test OpenAI API."""
    print_header("Testing OpenAI API (gpt-4o)")

    if not os.environ.get("OPENAI_API_KEY"):
        print_result(False, "OPENAI_API_KEY not set, skipping")
        return False

    try:
        from app.services.llm_gateway import get_llm_gateway

        llm = get_llm_gateway()

        # Test with a simple prompt
        response = await llm.complete(
            prompt="Say 'Hello from OpenAI!' in exactly those words.",
            model="openai/gpt-4o",
            max_tokens=50,
            temperature=0,
            fallback=False,
        )

        content = response.get("content", "")
        tokens = response.get("usage", {}).get("total_tokens", 0)
        cost = response.get("cost", 0)

        print_result(True, f"Response: {content[:100]}...")
        print(f"   Tokens: {tokens}, Cost: ${cost:.6f}")
        return True

    except Exception as e:
        print_result(False, f"Error: {e}")
        return False


async def test_anthropic():
    """Test Anthropic API (direct, not Bedrock)."""
    print_header("Testing Anthropic API (claude-3-5-sonnet)")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print_result(False, "ANTHROPIC_API_KEY not set, skipping")
        return False

    try:
        from app.services.llm_gateway import get_llm_gateway

        llm = get_llm_gateway()

        # Test with a simple prompt
        response = await llm.complete(
            prompt="Say 'Hello from Anthropic!' in exactly those words.",
            model="anthropic/claude-3-5-sonnet-20241022",
            max_tokens=50,
            temperature=0,
            fallback=False,
        )

        content = response.get("content", "")
        tokens = response.get("usage", {}).get("total_tokens", 0)
        cost = response.get("cost", 0)

        print_result(True, f"Response: {content[:100]}...")
        print(f"   Tokens: {tokens}, Cost: ${cost:.6f}")
        return True

    except Exception as e:
        print_result(False, f"Error: {e}")
        return False


async def test_embeddings():
    """Test embedding generation."""
    print_header("Testing Embedding Generation")

    try:
        from app.services.llm_gateway import get_llm_gateway

        llm = get_llm_gateway()

        # Get the auto-detected embedding model
        model = llm._get_embedding_model()
        print(f"   Auto-detected embedding model: {model}")

        # Test embedding generation
        embeddings = await llm.embed(
            texts=["This is a test sentence for embedding generation."],
            model=model,
        )

        if embeddings and len(embeddings) > 0:
            dim = len(embeddings[0])
            print_result(True, f"Generated embedding with {dim} dimensions")
            return True
        else:
            print_result(False, "No embeddings returned")
            return False

    except Exception as e:
        print_result(False, f"Error: {e}")
        return False


async def test_broad_scan_agent():
    """Test the BroadScanAgent with a minimal repo view."""
    print_header("Testing BroadScanAgent (AI Scan Core)")

    # Check if at least one AI Scan model is available
    has_gemini = bool(os.environ.get("GEMINI_API_KEY"))
    has_bedrock = bool(os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"))

    if not has_gemini and not has_bedrock:
        print_result(False, "Neither Gemini nor Bedrock configured, skipping")
        return False

    try:
        from app.services.broad_scan_agent import get_broad_scan_agent

        # Use only 1M context models: Gemini 3 Pro and Claude Sonnet 4.5
        models = []
        if has_gemini:
            models.append("gemini/gemini-3-pro-preview")
        if has_bedrock:
            models.append("bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0")

        print(f"   Testing with models: {models}")

        agent = get_broad_scan_agent(models=models, max_cost_usd=1.0)

        # Minimal test repo view
        test_repo_view = """# Test Repository

## File Tree
```
test-repo/
├── main.py
└── config.py
```

## Files

### main.py
```python
import os

# TODO: Fix this hardcoded secret
API_KEY = "sk-1234567890abcdef"

def main():
    print(f"Using API key: {API_KEY}")

if __name__ == "__main__":
    main()
```

### config.py
```python
DEBUG = True
DATABASE_URL = "postgresql://user:password@localhost/db"
```
"""

        print("   Running broad scan on test repo...")
        result = await agent.scan(test_repo_view)

        print_result(True, "Scan completed!")
        print(f"   Models used: {result.models_used}")
        print(f"   Models succeeded: {result.models_succeeded}")
        print(f"   Issues found: {len(result.candidates)}")
        print(f"   Total tokens: {result.total_tokens}")
        print(f"   Total cost: ${result.total_cost:.4f}")

        if result.repo_overview:
            print(f"   Project type: {result.repo_overview.get('guessed_project_type', 'Unknown')}")

        if result.candidates:
            print("\n   Sample issues found:")
            for issue in result.candidates[:3]:
                print(f"   - [{issue.severity}] {issue.summary[:60]}...")

        return len(result.models_succeeded) > 0

    except Exception as e:
        print_result(False, f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n" + "🔬 " * 20)
    print("  AI API Manual Test Suite for n9r AI Scan")
    print("🔬 " * 20)

    # Check environment variables first
    env_status = check_env_vars()

    # Run individual API tests
    results = {}

    if env_status["gemini"]:
        results["Gemini"] = await test_gemini()

    if env_status["bedrock"]:
        results["Bedrock Claude"] = await test_bedrock_claude()

    if env_status["openai"]:
        results["OpenAI"] = await test_openai()

    if env_status["anthropic"]:
        results["Anthropic"] = await test_anthropic()

    # Test embeddings
    results["Embeddings"] = await test_embeddings()

    # Test the full BroadScanAgent
    results["BroadScanAgent"] = await test_broad_scan_agent()

    # Print summary
    print_header("Test Summary")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, success in results.items():
        print_result(success, test_name)

    print(f"\n📊 Results: {passed}/{total} tests passed")

    # AI Scan readiness check
    print_header("AI Scan Readiness")

    gemini_ok = results.get("Gemini", False)
    bedrock_ok = results.get("Bedrock Claude", False)
    embeddings_ok = results.get("Embeddings", False)
    broad_scan_ok = results.get("BroadScanAgent", False)

    if broad_scan_ok and embeddings_ok:
        print_result(True, "AI Scan is READY to use! 🚀")
        print("\n   You can now run AI Scan from the dashboard.")
    elif (gemini_ok or bedrock_ok) and embeddings_ok:
        print_result(True, "AI Scan should work with available models")
        print(f"   Available: {'Gemini' if gemini_ok else ''} {'Bedrock' if bedrock_ok else ''}")
    else:
        print_result(False, "AI Scan is NOT ready")
        print("\n   Required:")
        if not gemini_ok and not bedrock_ok:
            print("   - At least one of: GEMINI_API_KEY or AWS Bedrock credentials")
        if not embeddings_ok:
            print("   - Embedding provider (OPENAI_API_KEY or GEMINI_API_KEY)")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
