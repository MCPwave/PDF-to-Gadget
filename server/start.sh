#!/bin/bash
# Start PDF-to-Gadget web server
cd "$(dirname "$0")"
# Note: --reload disabled due to file watcher issues with multiple agent modules
# To enable reload during development: uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-dir agents
exec uvicorn main:app --host 0.0.0.0 --port 8000
