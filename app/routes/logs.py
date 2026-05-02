# app/routes/logs.py
from fastapi import APIRouter, Depends, HTTPException, Request, Query, WebSocket, WebSocketDisconnect
from typing import Optional, List
from datetime import datetime, timedelta

from app.database import get_db
from app.database_mongo import get_mongo, is_mongo_available
from app.models.user import User
from app.models.action_log import ActionLog
from app.utils.security import verify_bot_auth, get_current_user
from app.services.websocket_manager import ws_manager

# Router REST (prefixo /guilds)
router = APIRouter(prefix="/guilds", tags=["Logs"])

# Router WebSocket (SEM prefixo)
ws_router = APIRouter(tags=["WebSocket"])

# ============ BOT: ENVIAR LOG ============

@router.post("/{guild_id}/logs")
async def create_log(
    guild_id: int,
    log_data: dict,
    bot_user: str = Depends(verify_bot_auth)
):
    """[Bot] Registra um novo log de ação"""
    if not is_mongo_available():
        raise HTTPException(503, "Serviço de logs indisponível")
    
    mongo_db = get_mongo()
    
    log = ActionLog(
        guild_id=guild_id,
        log_type=log_data.get("log_type"),
        user_id=log_data.get("user_id"),
        target_id=log_data.get("target_id"),
        channel_id=log_data.get("channel_id"),
        data=log_data.get("data", {})
    )
    
    result = await mongo_db.action_logs.insert_one(log.to_dict())
    
    log_response = log.to_response()
    log_response["id"] = str(result.inserted_id)
    
    await ws_manager.broadcast_to_guild(guild_id, {
        "type": "new_log",
        "log": log_response
    })
    
    return {"id": str(result.inserted_id), "created_at": log.created_at.isoformat()}

# ============ DASHBOARD: CONSULTAR LOGS ============

@router.get("/{guild_id}/logs")
async def get_logs(
    guild_id: int,
    request: Request,
    log_type: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    before: Optional[str] = Query(None),
    after: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user)
):
    """[Dashboard] Consulta logs com filtros"""
    if not is_mongo_available():
        raise HTTPException(503, "Serviço de logs indisponível")
    
    mongo_db = get_mongo()
    query = {"guild_id": guild_id}
    
    if log_type:
        query["log_type"] = log_type
    if user_id:
        query["user_id"] = user_id
    if before:
        query["created_at"] = {"$lt": datetime.fromisoformat(before)}
    if after:
        if "created_at" in query:
            query["created_at"]["$gt"] = datetime.fromisoformat(after)
        else:
            query["created_at"] = {"$gt": datetime.fromisoformat(after)}
    
    cursor = mongo_db.action_logs.find(query).sort("created_at", -1).limit(limit)
    
    logs = []
    async for doc in cursor:
        log = ActionLog.from_dict(doc)
        log.id = doc["_id"]
        logs.append(log.to_response())
    
    total = await mongo_db.action_logs.count_documents({"guild_id": guild_id})
    
    return {
        "logs": logs,
        "total": total,
        "limit": limit,
        "has_more": len(logs) == limit
    }

# ============ DASHBOARD: ESTATÍSTICAS ============

@router.get("/{guild_id}/logs/stats")
async def get_log_stats(
    guild_id: int,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """[Dashboard] Estatísticas de logs"""
    if not is_mongo_available():
        raise HTTPException(503, "Serviço de logs indisponível")
    
    mongo_db = get_mongo()
    
    pipeline = [
        {"$match": {"guild_id": guild_id}},
        {"$group": {
            "_id": "$log_type",
            "count": {"$sum": 1},
            "last_event": {"$max": "$created_at"}
        }},
        {"$sort": {"count": -1}}
    ]
    
    stats_by_type = {}
    total = 0
    
    async for doc in mongo_db.action_logs.aggregate(pipeline):
        stats_by_type[doc["_id"]] = {
            "count": doc["count"],
            "last_event": doc["last_event"].isoformat() if doc.get("last_event") else None
        }
        total += doc["count"]
    
    return {
        "guild_id": guild_id,
        "total_logs": total,
        "by_type": stats_by_type
    }

# ============ WEBSOCKET (router separado, sem prefixo) ============

@ws_router.websocket("/ws/guilds/{guild_id}/logs")
async def websocket_logs(
    websocket: WebSocket,
    guild_id: int,
    token: str = Query(None)
):
    """WebSocket para receber logs em tempo real"""
    if not token:
        await websocket.close(code=4001, reason="Token não fornecido")
        return
    
    from app.utils.security import verify_token
    try:
        payload = verify_token(token, "access")
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=4001, reason="Token inválido")
            return
    except Exception:
        await websocket.close(code=4001, reason="Token inválido")
        return
    
    await ws_manager.connect(websocket, guild_id)
    
    try:
        if is_mongo_available():
            mongo_db = get_mongo()
            cursor = mongo_db.action_logs.find(
                {"guild_id": guild_id}
            ).sort("created_at", -1).limit(50)
            
            recent_logs = []
            async for doc in cursor:
                log = ActionLog.from_dict(doc)
                log.id = doc["_id"]
                recent_logs.append(log.to_response())
            
            await websocket.send_json({
                "type": "initial_logs",
                "logs": recent_logs
            })
        
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:
                break
    except Exception:
        pass
    finally:
        ws_manager.disconnect(websocket, guild_id)