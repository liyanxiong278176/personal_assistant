@echo off
set QWEATHER_API_KEY=6e0919b8feba472a8487c4a4416de871
set AMAP_API_KEY=9b42cd0a72b507c5a3e87f1e93babb03
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
