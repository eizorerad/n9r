"""Common schemas and utilities."""

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class BaseSchema(BaseModel):
    """Base schema with common configuration."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class TimestampMixin(BaseModel):
    """Mixin for timestamp fields."""

    created_at: datetime
    updated_at: datetime


class PaginationParams(BaseModel):
    """Pagination parameters."""

    page: int = 1
    per_page: int = 20


class PaginationMeta(BaseModel):
    """Pagination metadata in response."""

    page: int
    per_page: int
    total: int
    total_pages: int


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper."""

    data: list[T]
    pagination: PaginationMeta


class ErrorDetail(BaseModel):
    """Error detail for validation errors."""

    field: str
    message: str


class ErrorResponse(BaseModel):
    """Standard error response."""

    code: str
    message: str
    details: list[ErrorDetail] | None = None


class SuccessResponse(BaseModel):
    """Simple success response."""

    success: bool = True
    message: str | None = None
