"""
Money Clarity FastAPI backend.

Run locally:
  uvicorn backend.main:app --reload --port 8000

Production:
  gunicorn backend.main:app -k uvicorn.workers.UvicornWorker -w 4 --bind 0.0.0.0:8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.routes import gmail, parse, summary, upload


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate required config on startup
    get_settings()
    yield


app = FastAPI(
    title="Money Clarity API",
    version="1.0.0",
    description="Secure personal finance backend with Supabase Auth, Gmail OAuth, and encrypted storage",
    lifespan=lifespan,
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(upload.router)
app.include_router(parse.router)
app.include_router(gmail.router)
app.include_router(summary.router)


@app.get("/health")
async def health():
    return {"status": "ok", "environment": settings.environment}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    # Never leak internal errors to client in production
    if settings.is_production:
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
    raise exc
