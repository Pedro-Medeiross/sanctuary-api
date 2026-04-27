# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time

from app.config import settings
from app.database import create_tables, engine
from app.routes import guilds, auth, dashboard

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan para criar tabelas automaticamente"""
    print("🚀 Iniciando API...")
    await create_tables()
    print("✅ Banco de dados inicializado")
    yield
    print("🛑 Finalizando API...")
    await engine.dispose()

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, especificar origens
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware de log
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    print(f"📝 {request.method} {request.url.path} - {response.status_code} - {duration:.2f}s")
    
    return response

# Rotas
@app.get("/health")
async def health_check():
    """Health check"""
    return {
        "status": "ok",
        "timestamp": time.time(),
        "version": "1.0.0"
    }

app.include_router(auth.router)
app.include_router(guilds.router)
app.include_router(dashboard.router)

# Tratamento global de exceções
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"❌ Erro: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": str(exc) if settings.DEBUG else "Ocorreu um erro interno"
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True
    )