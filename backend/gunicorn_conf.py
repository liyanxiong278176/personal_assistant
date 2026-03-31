"""Gunicorn configuration for FastAPI production deployment.

Per CONTEXT.md decision (INFRA-05):
- Gunicorn with Uvicorn workers
- 2-4 workers depending on server RAM
- Connection pooling, graceful shutdown, health check
"""

import os
import multiprocessing

# Worker configuration
# Use CPU count for workers, but cap at 4 for student servers
# Override with WORKERS env var
workers = int(os.getenv("WORKERS", multiprocessing.cpu_count()))
workers = min(workers, 4)  # Cap at 4 for memory constraints

# Uvicorn worker class for async support
worker_class = "uvicorn.workers.UvicornWorker"

# Socket binding
bind = "0.0.0.0:8000"

# Process naming
proc_name = "travel-assistant"

# Timeout settings
timeout = 120  # Long requests (LLM calls can be slow)
keepalive = 5

# Graceful shutdown (give workers time to finish)
graceful_timeout = 30

# Worker recycling (prevent memory leaks)
max_requests = 1000  # Restart worker after 1000 requests
max_requests_jitter = 100  # Add randomness to prevent thundering herd

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = os.getenv("LOG_LEVEL", "info")

# Process management
daemon = False  # Run in foreground (Docker best practice)
pidfile = None
umask = 0o007

# Server hooks
def on_starting(server):
    """Called when Gunicorn starts."""
    server.log.info("Starting Travel Assistant API with %d workers", server.NUM_WORKERS)

def on_exit(server):
    """Called when Gunicorn shuts down."""
    server.log.info("Shutting down Travel Assistant API")

def worker_int(worker):
    """Called when worker receives SIGINT."""
    worker.log.info("Worker received interrupt signal")

def pre_fork(server, worker):
    """Called before worker is forked."""
    server.log.info("Spawning worker %s", worker.pid)

def post_fork(server, worker):
    """Called after worker is forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def pre_exec(server):
    """Called just before new master is forked."""
    server.log.info("Forked child, re-executing.")

def pre_request(worker, req):
    """Called before processing request."""
    worker.log.debug("Request: %s", req)

def post_request(worker, req, environ, resp):
    """Called after processing request."""
    # Log slow requests
    if resp.status >= 400:
        worker.log.warning("Request failed: %s %s -> %s",
                         req.method, req.path, resp.status)
