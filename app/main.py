import os

# from app.api.tasks.scheduler import start_scheduler, stop_scheduler
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

load_dotenv()

from app.api.router import api_router
from app.core.rate_limiter import limiter
from app.core.database import init_db
from app.services.image_asset_service import mount_rag_image_storage
from app.services.image_search_source_service import mount_image_search_source_storage

# Determine whether to expose the interactive documentation.
env = os.getenv("ENVIRONMENT", "development").lower()
docs_url = "/docs"
redoc_url = "/redoc"
openapi_url = "/openapi.json"
if env == "production":
    docs_url = None
    redoc_url = None
    openapi_url = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan hook."""
    # Initialize Beanie ODM
    await init_db()
    
    yield


app = FastAPI(
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
mount_rag_image_storage(app)
mount_image_search_source_storage(app)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

if env != "production":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix="/api")

# app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return {"message": "Xoai API ready!"}


# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     print("[App] Starting up...")
#     start_scheduler()

#     yield

#     print("[App] Shutting down...")
#     stop_scheduler()
