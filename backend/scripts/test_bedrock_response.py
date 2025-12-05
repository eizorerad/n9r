#!/usr/bin/env python3
"""Test Bedrock Claude response format.

This script sends a small test prompt to Bedrock Claude and prints
the raw response to debug why 0 issues are being returned.

Usage:
    cd backend
    uv run python scripts/test_bedrock_response.py
"""

import asyncio
import json
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


# Simple test code with obvious issues
TEST_CODE = """
# File: app/utils.py

import os
import sys
import json  # unused import

API_KEY = "sk-1234567890abcdef"  # hardcoded secret!
PASSWORD = "admin123"  # another hardcoded secret

def process_data(data, temp, x, y, z):  # generic names
    result = []
    for i in range(100):  # magic number
        if data:
            result.append(data[i] * 42)  # magic number
    return result

def calculate(a, b, c, d, e, f, g, h):  # too many parameters
    # TODO: fix this later
    # FIXME: this is broken
    return a + b + c + d + e + f + g + h

def unused_function():
    pass

class GodClass:
    def __init__(self):
        self.db = None
        self.cache = None
        self.api = None
        self.logger = None
        self.config = None
        self.metrics = None
    
    def do_everything(self, input):
        # This class does too much
        data = self.db.query(input)
        cached = self.cache.get(input)
        response = self.api.call(input)
        self.logger.log(input)
        self.config.update(input)
        self.metrics.record(input)
        return data, cached, response

# SQL injection vulnerability
def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return execute_query(query)

# File: app/api.py

def handle_request(request):
    # No input validation
    user_input = request.get("data")
    eval(user_input)  # code injection!
    return {"status": "ok"}
"""

SYSTEM_PROMPT = """You are an expert code analyst. Analyze the code and return issues in JSON format.

You MUST respond with valid JSON in this structure:
{
  "repo_overview": {
    "guessed_project_type": "string",
    "main_languages": ["string"],
    "overall_assessment": "string"
  },
  "issues": [
    {
      "id_hint": "sec-001",
      "dimension": "security|db_consistency|api_correctness|code_health|other",
      "severity": "critical|high|medium|low",
      "files": [{"path": "string", "line_start": 1, "line_end": 10}],
      "summary": "Brief summary",
      "detailed_description": "Full description",
      "evidence_snippets": ["code snippet"],
      "potential_impact": "What could go wrong",
      "remediation_idea": "How to fix",
      "confidence": "high|medium|low"
    }
  ]
}

The code has OBVIOUS issues - hardcoded secrets, SQL injection, eval(), etc. You MUST find them."""


async def test_bedrock_raw():
    """Test Bedrock Claude and print raw response."""
    print("=" * 80)
    print("TESTING BEDROCK CLAUDE RAW RESPONSE")
    print("=" * 80)
    
    # Check credentials
    if not os.environ.get("AWS_ACCESS_KEY_ID"):
        print("ERROR: AWS_ACCESS_KEY_ID not set")
        return
    
    print("\n1. Initializing LiteLLM...")
    import litellm
    litellm.drop_params = True
    
    model = "bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    print(f"   Model: {model}")
    
    print("\n2. Sending request WITHOUT response_format (fix for tool_calls issue)...")
    print(f"   Prompt length: {len(TEST_CODE)} chars")
    
    # Add explicit JSON instruction to system prompt
    system_with_json = SYSTEM_PROMPT + "\n\nIMPORTANT: Return ONLY valid JSON, no markdown, no explanation."
    
    try:
        response = await litellm.acompletion(
            model=model,
            messages=[
                {"role": "system", "content": system_with_json},
                {"role": "user", "content": f"Analyze this code:\n\n{TEST_CODE}"}
            ],
            temperature=0.1,
            max_tokens=4096,
            # NO response_format for Bedrock - causes tool_calls issue!
            extra_headers={"anthropic-beta": "context-1m-2025-08-07"},
        )
        
        print("\n3. RAW RESPONSE OBJECT:")
        print("-" * 40)
        print(f"   Model used: {response.model}")
        print(f"   Finish reason: {response.choices[0].finish_reason}")
        print(f"   Usage: {response.usage}")
        
        content = response.choices[0].message.content
        print(f"\n4. RAW CONTENT (type={type(content).__name__}, len={len(content) if content else 0}):")
        print("-" * 40)
        print(content)
        print("-" * 40)
        
        # Try to parse
        print("\n5. PARSING ATTEMPT:")
        print("-" * 40)
        
        if not content:
            print("   ERROR: Content is empty!")
            return
        
        # Check for markdown wrapping
        cleaned = content.strip()
        if cleaned.startswith("```"):
            print("   Found markdown code block, extracting...")
            first_newline = cleaned.find("\n")
            if first_newline != -1:
                cleaned = cleaned[first_newline + 1:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
            print(f"   Cleaned content preview: {cleaned[:200]}...")
        
        try:
            data = json.loads(cleaned)
            print(f"   JSON parsed successfully!")
            print(f"   Keys: {list(data.keys())}")
            
            issues = data.get("issues", [])
            print(f"\n6. ISSUES FOUND: {len(issues)}")
            print("-" * 40)
            
            if isinstance(issues, list):
                for i, issue in enumerate(issues[:10]):  # First 10
                    print(f"\n   Issue {i+1}:")
                    print(f"     id_hint: {issue.get('id_hint')}")
                    print(f"     dimension: {issue.get('dimension')}")
                    print(f"     severity: {issue.get('severity')}")
                    print(f"     summary: {issue.get('summary', '')[:100]}")
            else:
                print(f"   ERROR: 'issues' is not a list: {type(issues)}")
                print(f"   Value: {issues}")
                
        except json.JSONDecodeError as e:
            print(f"   JSON PARSE ERROR: {e}")
            print(f"   Content that failed to parse:")
            print(f"   {cleaned[:500]}")
            
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


async def test_bedrock_with_large_context():
    """Test with larger context similar to real repo view."""
    print("\n" + "=" * 80)
    print("TESTING WITH LARGER CONTEXT (simulating repo view)")
    print("=" * 80)
    
    # Create a larger test payload
    large_code = TEST_CODE * 50  # ~50x larger
    print(f"\n1. Large prompt size: {len(large_code)} chars (~{len(large_code)//4} tokens)")
    
    import litellm
    model = "bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    
    # Add explicit JSON instruction
    system_with_json = SYSTEM_PROMPT + "\n\nIMPORTANT: Return ONLY valid JSON, no markdown, no explanation."
    
    print("\n2. Sending large request WITHOUT response_format...")
    
    try:
        response = await litellm.acompletion(
            model=model,
            messages=[
                {"role": "system", "content": system_with_json},
                {"role": "user", "content": f"Analyze this code:\n\n{large_code}"}
            ],
            temperature=0.1,
            max_tokens=16384,
            # NO response_format for Bedrock!
            extra_headers={"anthropic-beta": "context-1m-2025-08-07"},
        )
        
        content = response.choices[0].message.content
        print(f"\n3. Response received!")
        print(f"   Content length: {len(content) if content else 0}")
        print(f"   Finish reason: {response.choices[0].finish_reason}")
        
        # Parse and count issues
        if content:
            cleaned = content.strip()
            if cleaned.startswith("```"):
                first_newline = cleaned.find("\n")
                if first_newline != -1:
                    cleaned = cleaned[first_newline + 1:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3].strip()
            
            try:
                data = json.loads(cleaned)
                issues = data.get("issues", [])
                print(f"\n4. ISSUES FOUND: {len(issues)}")
                
                if len(issues) == 0:
                    print("\n   WARNING: 0 issues found!")
                    print("   Full response:")
                    print(content[:2000])
            except json.JSONDecodeError as e:
                print(f"\n   JSON PARSE ERROR: {e}")
                
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")


async def main():
    """Run all tests."""
    await test_bedrock_raw()
    await test_bedrock_with_large_context()
    
    print("\n" + "=" * 80)
    print("DONE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
