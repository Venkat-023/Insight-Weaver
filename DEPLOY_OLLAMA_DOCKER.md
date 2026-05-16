# Docker + Ollama Deployment

This deployment keeps the application code path intact and runs three services:

- `ollama`: local model server with a persistent model volume
- `backend`: FastAPI API, configured to call Ollama at `http://ollama:11434`
- `frontend`: Vite build served by Nginx, proxying `/api` to the backend

## Quick Start

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open:

- Frontend: `http://localhost:8080`
- Backend health: `http://localhost:8000/health`
- Ollama: `http://localhost:11434`

## Model

The default model is the same one already configured in the backend:

```env
OLLAMA_MODEL=gemma4:e4b
```

To use a different Ollama tag, edit `.env` before running Compose:

```env
OLLAMA_MODEL=gemma4:e2b
```

The `ollama-pull` service pulls the configured model into the persistent `ollama-models` volume. If you already have a custom Gemma model in Ollama, set `OLLAMA_MODEL` to that exact tag.

## Useful Commands

```powershell
docker compose up --build
docker compose logs -f backend
docker compose logs -f ollama
docker compose down
```

To reset downloaded models and app data:

```powershell
docker compose down -v
```

## Persistent Data

Compose stores runtime data in Docker volumes:

- `ollama-models`: Ollama model files
- `backend-data`: SQLite database and Chroma vector store
- `backend-uploads`: uploaded papers

Local project folders such as `uploads`, `data`, `dist`, `node_modules`, and `__pycache__` are excluded from Docker build contexts so existing local data is not baked into images.
