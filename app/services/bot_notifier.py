# app/services/bot_notifier.py
import aiohttp
from app.config import settings

async def notify_bot(guild_id: int, event_type: str, data: dict):
    """Envia notificação para o bot"""
    bot_url = settings.BOT_URL or "http://localhost:8001"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{bot_url}/events/{event_type}",
                json={
                    "guild_id": guild_id,
                    **data
                },
                headers={"Authorization": f"Bearer {settings.API_USER}:{settings.API_PASS}"}
            ) as resp:
                if resp.status == 200:
                    print(f"✅ Bot notificado: {event_type} guild={guild_id}")
                else:
                    print(f"⚠️ Bot respondeu {resp.status}: {event_type}")
        except Exception as e:
            print(f"❌ Erro ao notificar bot: {e}")

async def notify_panel_created(guild_id: int, panel: dict):
    """Notifica bot que um painel foi criado"""
    await notify_bot(guild_id, "panel/created", {
        "panel_id": str(panel["id"]),
        "title": panel["title"],
        "description": panel.get("description", ""),
        "button_label": panel["button_label"],
        "button_color": panel["button_color"],
        "category_id": str(panel["category_id"]) if panel.get("category_id") else None,
        "support_roles": panel.get("support_roles", []),
    })

async def notify_panel_updated(guild_id: int, panel: dict):
    """Notifica bot que um painel foi atualizado"""
    await notify_bot(guild_id, "panel/updated", {
        "panel_id": str(panel["id"]),
        "title": panel["title"],
        "description": panel.get("description", ""),
        "button_label": panel["button_label"],
        "button_color": panel["button_color"],
        "category_id": str(panel["category_id"]) if panel.get("category_id") else None,
        "support_roles": panel.get("support_roles", []),
        "is_active": panel.get("is_active", True),
    })

async def notify_panel_deleted(guild_id: int, panel_id: str):
    """Notifica bot que um painel foi deletado"""
    await notify_bot(guild_id, "panel/deleted", {
        "panel_id": panel_id,
    })

async def notify_ticket_created(guild_id: int, ticket: dict):
    """Notifica bot que um ticket foi criado"""
    await notify_bot(guild_id, "ticket/created", {
        "ticket_id": str(ticket["id"]),
        "channel_id": str(ticket["channel_id"]),
        "user_id": str(ticket["user_id"]),
    })

async def notify_ticket_closed(guild_id: int, ticket_id: str, closed_by: str, reason: str = None):
    """Notifica bot que um ticket foi fechado"""
    await notify_bot(guild_id, "ticket/closed", {
        "ticket_id": ticket_id,
        "closed_by": closed_by,
        "reason": reason,
    })

async def notify_ticket_claimed(guild_id: int, ticket_id: str, staff_id: str):
    """Notifica bot que um ticket foi reinvindicado"""
    await notify_bot(guild_id, "ticket/claimed", {
        "ticket_id": ticket_id,
        "staff_id": staff_id,
    })