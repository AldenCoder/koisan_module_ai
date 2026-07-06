import os

from fastapi import APIRouter

from app.api.router_v0 import api_router as api_router_v0
from app.api.router_v1 import api_router as api_router_v1

api_router = APIRouter()

ENABLE_API_V0 = os.getenv("ENABLE_API_V0", "true").lower() == "true"
ENABLE_API_V1 = os.getenv("ENABLE_API_V1", "true").lower() == "true"

if ENABLE_API_V0:
    api_router.include_router(api_router_v0, prefix="/v0")

if ENABLE_API_V1:
    api_router.include_router(api_router_v1, prefix="/v1")
