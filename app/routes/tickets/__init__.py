# app/routes/tickets/__init__.py
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.services.websocket_manager import ws_manager

# Router WebSocket (sem prefixo, registrado direto no main)
ws_router = APIRouter(tags=["WebSocket Tickets"])


@ws_router.websocket("/ws/guilds/{guild_id}/tickets")
async def websocket_tickets(
    websocket: WebSocket,
    guild_id: int,
    token: str = Query(None)
):
    """WebSocket para receber atualizações de tickets em tempo real"""
    if not token:
        await websocket.close(code=4001, reason="Token não fornecido")
        return

    from app.utils.security import verify_token
    try:
        payload = verify_token(token, "access")
        if not payload.get("sub"):
            await websocket.close(code=4001, reason="Token inválido")
            return
    except Exception:
        await websocket.close(code=4001, reason="Token inválido")
        return

    await ws_manager.connect(websocket, guild_id)

    try:
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        ws_manager.disconnect(websocket, guild_id)