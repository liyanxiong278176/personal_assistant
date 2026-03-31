"""FastAPI application entry point.

References:
- D-06: Use FastAPI as independent Python backend
- D-08: Use Uvicorn as ASGI server
- D-09: API routes: /ws/chat, /api/conversations, /api/messages
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.db.postgres import Database
from app.api.chat import websocket_chat_endpoint, router

load_dotenv()

# Lifespan context manager for database connections
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    # Startup
    await Database.connect()
    yield
    # Shutdown
    await Database.disconnect()

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
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "travel-assistant-backend"}

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
            "messages": "/api/messages/{conversation_id}"
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
