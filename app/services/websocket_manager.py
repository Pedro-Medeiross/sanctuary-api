# app/services/websocket_manager.py
from fastapi import WebSocket
from typing import Dict, List, Set
import json

class WebSocketManager:
    """Gerencia conexões WebSocket por guild"""
    
    def __init__(self):
        # guild_id -> set de WebSockets
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
        
        for websocket in self.active_connections[guild_id]:
            try:
                await websocket.send_text(message)
            except Exception:
                disconnected.add(websocket)
        
        # Limpar conexões mortas
        for ws in disconnected:
            self.disconnect(ws, guild_id)
    
    def get_connections_count(self) -> Dict[int, int]:
        """Retorna número de conexões por guild"""
        return {guild_id: len(connections) for guild_id, connections in self.active_connections.items()}

# Instância global
ws_manager = WebSocketManager()