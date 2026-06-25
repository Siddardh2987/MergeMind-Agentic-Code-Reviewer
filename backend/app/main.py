"""
MergeMind — FastAPI Application Entry Point

This is the main application file that:
  • Creates the FastAPI app instance
  • Configures CORS middleware (required for Chrome extension)
  • Includes all API routers
  • Initializes the database on startup
  • Provides a health check endpoint
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.routers import webhook, reviews
from app.routers import settings as settings_router
from app.schemas import HealthResponse

# ── Logging Configuration ─────────────────────────────────────────────
# Configure logging format for the entire application
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── App Configuration ─────────────────────────────────────────────────
settings = get_settings()

app = FastAPI(
    title="MergeMind",
    description=(
        "🧠 Agentic AI Code Reviewer — "
        "Analyzes GitHub commits using multiple specialized AI agents"
    ),
    version="1.0.0",
    docs_url="/docs",      # Swagger UI at /docs
    redoc_url="/redoc",    # ReDoc at /redoc
)

# ── CORS Middleware ───────────────────────────────────────────────────
# The Chrome extension needs to make cross-origin requests to this API.
# We also allow GitHub and localhost origins for development.
cors_origins = [
    origin.strip()
    for origin in settings.CORS_ORIGINS.split(",")
    if origin.strip()
]

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=cors_origins + [
#         "https://github.com",
#         "http://localhost:*",
#     ],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"chrome-extension://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Include Routers ──────────────────────────────────────────────────
# Mount the webhook and reviews routers
app.include_router(webhook.router)
app.include_router(reviews.router)
app.include_router(settings_router.router)


# ── Startup Event ────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    """
    Initialize the database tables when the application starts.
    This creates tables if they don't exist (safe to run multiple times).
    """
    logger.info("🧠 MergeMind is starting up...")
    init_db()
    logger.info("✅ Database initialized")
    logger.info(f"📡 Backend URL: {settings.BACKEND_URL}")
    logger.info("📖 API docs available at /docs")


# ── Health Check ─────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """
    Simple health check endpoint.
    
    Returns 200 OK if the server is running.
    Useful for monitoring, load balancers, and the Chrome extension
    to verify backend connectivity.
    """
    return HealthResponse(status="ok", version="1.0.0")


# ── Root Endpoint ────────────────────────────────────────────────────
@app.get("/", tags=["health"])
async def root():
    """Root endpoint with a friendly welcome message."""
    return {
        "app": "MergeMind",
        "tagline": "🧠 Agentic AI Code Reviewer",
        "docs": "/docs",
        "health": "/health",
    }
