#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Seeding intent examples..."
python db/seeds/seed_intents.py

echo "Loading embedding model..."
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL:-all-MiniLM-L6-v2}')"

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
