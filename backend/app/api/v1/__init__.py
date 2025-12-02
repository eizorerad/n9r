"""API v1 module."""

from fastapi import APIRouter

from app.api.v1 import (
    analyses,
    auth,
    auto_prs,
    chat,
    health,
    issues,
    playground,
    repositories,
    semantic,
    users,
    webhooks,
)

router = APIRouter()

router.include_router(health.router, prefix="/health", tags=["health"])
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(repositories.router, prefix="/repositories", tags=["repositories"])
router.include_router(analyses.router, tags=["analyses"])
router.include_router(issues.router, tags=["issues"])
router.include_router(auto_prs.router, tags=["auto-prs"])
router.include_router(chat.router, tags=["chat"])
router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
router.include_router(playground.router, tags=["playground"])
router.include_router(semantic.router, tags=["semantic"])
