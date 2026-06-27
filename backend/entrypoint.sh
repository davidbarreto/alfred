#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Loading embedding model..."
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL:-all-MiniLM-L6-v2}')"

echo "Seeding intent examples..."
python db/seeds/seed_intents.py

echo "Seeding language tracks..."
python db/seeds/seed_language_tracks.py

echo "Seeding grammar scopes..."
python db/seeds/seed_grammar_scopes.py

echo "Seeding language chunks..."
python db/seeds/seed_language_chunks.py

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
