# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time

from app.config import settings
from app.database import create_tables, create_default_roles, engine
from app.database_mongo import init_mongo, close_mongo
from app.routes import guilds, auth, dashboard, profile, uploads, roles
from app.routes.logs import router as logs_router, ws_router as logs_ws_router
from app.routes.tickets import router as tickets_router, ws_router as tickets_ws_router
from app.utils.security import verify_app_auth

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Iniciando API...")
    await create_tables()
    await create_default_roles()
    await init_mongo()
    print("✅ Banco de dados inicializado")
    yield
    print("🛑 Finalizando API...")
    await engine.dispose()
    await close_mongo()

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
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

# Health check
@app.get("/health")
async def health_check(
    app_user: str = Depends(verify_app_auth)
):
    return {
        "status": "ok",
        "timestamp": time.time(),
        "version": "1.0.0"
    }

# Routers REST
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(guilds.router)
app.include_router(dashboard.router)
app.include_router(uploads.router)
app.include_router(logs_router)
app.include_router(tickets_router)
app.include_router(roles.router)

# Routers WebSocket
app.include_router(logs_ws_router)
app.include_router(tickets_ws_router)

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