"""FastAPI routers — the OpenAPI surface (one module per screen domain)."""

from fastapi import APIRouter

from hangar.api import catalog, fleet, providers, repos, system

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(fleet.router)
api_router.include_router(catalog.router)
api_router.include_router(providers.router)
api_router.include_router(repos.router)

__all__ = ["api_router"]
