# app/models/__init__.py

# Core
from app.models.core.user import User
from app.models.core.role import Role, user_roles
from app.models.core.user_connection import UserConnection
from app.models.core.session import Session

# Discord/Guild
from app.models.discord.guild import Guild
from app.models.discord.guild_stats import GuildStats
from app.models.discord.log_channel import LogChannel

# Tickets - Config
from app.models.tickets.ticket_config import TicketConfig
from app.models.tickets.ticket_staff_role import TicketStaffRole
from app.models.tickets.ticket_panel import TicketPanel
from app.models.tickets.ticket_category import TicketCategory

# Tickets - Core
from app.models.tickets.ticket import Ticket
from app.models.tickets.ticket_member import TicketMember
from app.models.tickets.ticket_transfer import TicketTransfer

# Tickets - Extras
from app.models.tickets.ticket_ban import TicketBan
from app.models.tickets.ticket_feedback import TicketFeedback

# MongoDB (não-SQLAlchemy)
from app.models.mongo.action_log import ActionLog