#!/bin/bash

# Start the LangGraph AI worker in the background
python secondfile.py &

# Start the MongoDB watcher worker in the background
python thirdfile.py &

# Start the FastAPI web server
uvicorn app:app --host 0.0.0.0 --port $PORT