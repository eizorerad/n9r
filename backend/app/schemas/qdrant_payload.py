"""Pydantic schema for Qdrant point payloads.

Provides validation for vector payloads stored in Qdrant, ensuring
consistent schema across embeddings worker and semantic API endpoints.
"""

from pydantic import BaseModel, Field


class QdrantPointPayload(BaseModel):
    """Schema for Qdrant code embedding point payloads.
    
    All fields match the payload structure in embeddings.py.
    Use .model_dump() when creating PointStruct payloads.
    """
    
    # Schema versioning for future migrations
    schema_version: int = Field(default=1, description="Payload schema version")
    
    # Identity fields
    repository_id: str = Field(..., description="Repository UUID as string")
    commit_sha: str = Field(..., description="Git commit SHA")
    file_path: str = Field(..., description="Relative file path in repository")
    
    # Code metadata
    language: str | None = Field(default=None, description="Programming language")
    chunk_type: str | None = Field(default=None, description="Type: function, class, method, module, block")
    name: str | None = Field(default=None, description="Symbol name (function/class name)")
    line_start: int = Field(..., description="Starting line number")
    line_end: int = Field(..., description="Ending line number")
    parent_name: str | None = Field(default=None, description="Parent class/module name")
    docstring: str | None = Field(default=None, description="Extracted docstring")
    
    # Content (truncated to 2000 chars)
    content: str = Field(..., max_length=2000, description="Code content (max 2000 chars)")
    content_truncated: bool = Field(default=False, description="True if content was truncated")
    full_content_length: int | None = Field(default=None, description="Original content length")
    
    # Token and hierarchy
    token_estimate: int | None = Field(default=None, description="Estimated token count")
    level: int | None = Field(default=None, description="Nesting level in AST")
    qualified_name: str | None = Field(default=None, description="Fully qualified name")
    
    # Metrics
    cyclomatic_complexity: float | None = Field(default=None, description="Cyclomatic complexity score")
    line_count: int | None = Field(default=None, description="Number of lines")
    
    # Cluster assignment (set by cluster analysis)
    cluster_id: int | None = Field(default=None, description="Assigned cluster ID")

    model_config = {
        "extra": "forbid",  # Reject unknown fields
    }
