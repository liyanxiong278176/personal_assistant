"""FastAPI application entry point.

References:
- D-06: Use FastAPI as independent Python backend
- D-08: Use Uvicorn as ASGI server
- D-09: API routes: /ws/chat, /api/conversations, /api/messages
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pathlib import Path

from app.db.postgres import Database
from app.api.chat import websocket_chat_endpoint, router
from app.api.itinerary import router as itinerary_router
from app.api.routes import router as routes_router
from app.api.memory import memory_router
from app.api.users import users_router
from app.api.agent_core import router as agent_core_router
from app.auth import auth_router
from app.eval.dashboard.api import router as eval_router
from app.conversations.router import router as conversations_router
from app.memory.router import router as memory_router_v2

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Explicitly load .env from backend directory
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Lifespan context manager for database connections
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    # Startup
    logger.info("=" * 50)
    logger.info("AI Travel Assistant Backend Starting")
    logger.info("=" * 50)
    await Database.connect()
    logger.info("[Startup] ✓ Database connected")
    yield
    # Shutdown
    await Database.disconnect()
    logger.info("[Shutdown] Database disconnected")

# Create FastAPI app
app = FastAPI(
    title="AI Travel Assistant API",
    description="Backend for AI Travel Assistant with WebSocket streaming",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware (allow frontend access)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(router)
app.include_router(itinerary_router)
app.include_router(routes_router)
app.include_router(memory_router)
app.include_router(users_router)
app.include_router(conversations_router)
app.include_router(memory_router_v2)
app.include_router(agent_core_router)
app.include_router(eval_router)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for Docker and load balancers.

    Returns service status and basic metadata.
    """
    return {
        "status": "ok",
        "service": "travel-assistant-api",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

# Test endpoint to trigger API calls with logging
@app.get("/test-apis")
async def test_apis():
    """Test endpoint to verify third-party API calls with logging."""
    from app.services.weather_service import weather_service
    from app.services.map_service import map_service

    logger.info("[Test] ===== Testing Third-Party APIs =====")

    # Test weather API
    logger.info("[Test] Testing QWeather API...")
    weather = await weather_service.get_weather_forecast("北京", days=3)
    logger.info(f"[Test] Weather API result: {weather.get('city', 'N/A')} - {len(weather.get('forecasts', []))} days")

    # Test map API
    logger.info("[Test] Testing Amap POI search...")
    poi = await map_service.search_poi("故宫", "北京", limit=5)
    logger.info(f"[Test] POI search result: {poi.get('count', 0)} results")

    return {
        "weather": f"{weather.get('city', 'N/A')} - {len(weather.get('forecasts', []))} days",
        "poi": f"{poi.get('count', 0)} results"
    }

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "AI Travel Assistant API",
        "version": "0.1.0",
        "endpoints": {
            "websocket": "/ws/chat",
            "conversations": "/api/conversations",
            "messages": "/api/messages/{conversation_id}",
            "itineraries": "/api/itineraries"
        }
    }

# WebSocket endpoint (per D-09: /ws/chat)
@app.websocket("/ws/chat")
async def websocket_route(websocket: WebSocket):
    """WebSocket route for chat."""
    await websocket_chat_endpoint(websocket)

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
