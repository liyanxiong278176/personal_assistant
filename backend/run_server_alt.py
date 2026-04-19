"""Backend server startup script with alternative port."""
import os
import sys
import uvicorn

# Set environment variables before importing the app
os.environ["AMAP_API_KEY"] = "9b42cd0a72b507c5a3e87f1e93babb03"

# Import and run
from app.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)  # Use port 8001 instead
