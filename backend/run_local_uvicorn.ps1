$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptRoot

$env:POSTGRES_DSN                  = "sqlite+aiosqlite:///./scidb.db"
$env:REDIS_URL                     = "redis://localhost:6379/0"
$env:CELERY_BROKER_URL             = "redis://localhost:6379/1"
$env:CELERY_RESULT_BACKEND         = "redis://localhost:6379/2"
$env:PAPER_PROCESSING_MODE         = "local"
$env:INDEX_VECTORS_DURING_PROCESSING = "false"
$env:NEO4J_URI                     = "bolt://localhost:7687"
$env:OLLAMA_HOST                   = "http://localhost:11435"

# Model preference: e4b (preferred) → warmup auto-falls-back to e2b if e4b not found
$env:GEMMA_REASONING_MODEL         = "gemma4:e4b"
$env:GEMMA_LIGHT_MODEL             = "gemma4:e4b"
$env:GEMMA_TIMEOUT_SECONDS         = "60"
$env:GEMMA_KEEP_ALIVE              = "30m"
$env:GEMMA_NUM_THREAD              = "10"

$env:CHROMA_PATH                   = "./data/chroma_db"
$env:UPLOADS_DIR                   = "./uploads"
$env:HF_HOME                       = "./.hf-cache"
$env:TRANSFORMERS_CACHE            = "./.hf-cache/transformers"
$env:HTTP_PROXY                    = ""
$env:HTTPS_PROXY                   = ""
$env:ALL_PROXY                     = ""
$env:GIT_HTTP_PROXY                = ""
$env:GIT_HTTPS_PROXY               = ""
$env:NO_PROXY                      = "localhost,127.0.0.1,::1"

$pidFile = Join-Path $scriptRoot "local-uvicorn.pid"
$PID | Set-Content -Path $pidFile
.\\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
