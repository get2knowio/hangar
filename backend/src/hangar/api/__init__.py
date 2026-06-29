"""FastAPI routers — the OpenAPI surface (one module per screen domain)."""

from fastapi import APIRouter

from hangar.api import catalog, fleet, providers, repos, system
from hangar.providers.github.app_flow import router as github_app_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(fleet.router)
api_router.include_router(catalog.router)
api_router.include_router(providers.router)
api_router.include_router(repos.router)
# One-click "Connect with GitHub" manifest+install flow (#25). Under /api/v1 → behind the
# access-control middleware; the operator is already logged in when they start it.
api_router.include_router(github_app_router)

__all__ = ["api_router"]
