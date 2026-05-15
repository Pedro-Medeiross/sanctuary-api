from fastapi import WebSocket
from typing import Dict, Set
import json


class WebSocketManager:
    """Gerencia conexões WebSocket por guild"""

    def __init__(self):
        self.active_connections: Dict[int, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, guild_id: int):
        """Aceita conexão WebSocket e registra"""
        await websocket.accept()
        if guild_id not in self.active_connections:
            self.active_connections[guild_id] = set()
        self.active_connections[guild_id].add(websocket)
        print(f"🔌 WS conectado: guild {guild_id} (total: {len(self.active_connections[guild_id])})")

    def disconnect(self, websocket: WebSocket, guild_id: int):
        """Remove conexão WebSocket"""
        if guild_id in self.active_connections:
            self.active_connections[guild_id].discard(websocket)
            if not self.active_connections[guild_id]:
                del self.active_connections[guild_id]
            print(f"🔌 WS desconectado: guild {guild_id}")

    async def broadcast_to_guild(self, guild_id: int, data: dict):
        """Envia mensagem para todos conectados na guild"""
        if guild_id not in self.active_connections:
            return

        message = json.dumps(data, default=str)
        disconnected = set()

        for ws in self.active_connections[guild_id]:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.add(ws)

        for ws in disconnected:
            self.disconnect(ws, guild_id)

    def get_connections_count(self) -> Dict[int, int]:
        """Retorna número de conexões por guild"""
        return {gid: len(conns) for gid, conns in self.active_connections.items()}


ws_manager = WebSocketManager()