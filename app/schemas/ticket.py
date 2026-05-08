from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

# ============ PAINÉIS ============
class TicketPanelCreate(BaseModel):
    title: str = Field(..., max_length=100)
    description: Optional[str] = None
    button_label: str = Field(default="Abrir Ticket", max_length=80)
    button_color: str = Field(default="green")
    channel_id: int
    category_id: Optional[int] = None
    
class TicketPanelUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    button_label: Optional[str] = None
    button_color: Optional[str] = None
    channel_id: Optional[int] = None
    category_id: Optional[int] = None
    is_active: Optional[bool] = None

class TicketPanelResponse(BaseModel):   
    id: uuid.UUID
    guild_id: int
    channel_id: Optional[int] = None
    message_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    button_label: str
    button_color: str
    category_id: Optional[int] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    class Config: from_attributes = True

# ============ STAFF ROLES ============
class StaffRoleCreate(BaseModel):
    role_id: int
    role_name: str
    level: int = Field(..., ge=1, le=4)

class StaffRoleUpdate(BaseModel):
    role_name: Optional[str] = None
    level: Optional[int] = None
    can_claim: Optional[bool] = None
    can_transfer: Optional[bool] = None
    can_add_users: Optional[bool] = None
    can_remove_users: Optional[bool] = None
    can_ban_users: Optional[bool] = None
    can_view_all: Optional[bool] = None
    can_manage_panels: Optional[bool] = None
    can_manage_config: Optional[bool] = None

class StaffRoleResponse(BaseModel):
    id: uuid.UUID
    guild_id: int
    role_id: int
    role_name: str
    level: int
    can_claim: bool
    can_transfer: bool
    can_add_users: bool
    can_remove_users: bool
    can_ban_users: bool
    can_view_all: bool
    can_manage_panels: bool
    can_manage_config: bool
    is_trainee: bool
    created_at: datetime
    class Config: from_attributes = True

# ============ TICKETS ============
class TicketResponse(BaseModel):
    id: uuid.UUID
    guild_id: int
    panel_id: Optional[uuid.UUID] = None
    channel_id: int
    user_id: int
    claimed_by: Optional[int] = None
    status: str
    priority: str
    closed_by: Optional[int] = None
    close_reason: Optional[str] = None
    members: List[int] = []
    last_activity_at: datetime
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None
    class Config: from_attributes = True

class TicketPriorityUpdate(BaseModel):
    priority: str = Field(..., pattern="^(low|medium|high|urgent)$")

class TicketTransferRequest(BaseModel):
    to_staff_id: int
    reason: Optional[str] = None

class TicketMemberRequest(BaseModel):
    user_id: int

class TicketCloseRequest(BaseModel):
    reason: Optional[str] = None

# ============ BANS ============
class TicketBanCreate(BaseModel):
    user_id: int
    reason: Optional[str] = None
    expires_in_days: Optional[int] = None  # null = permanente

class TicketBanResponse(BaseModel):
    id: uuid.UUID
    guild_id: int
    user_id: int
    reason: Optional[str] = None
    banned_by: int
    expires_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    class Config: from_attributes = True

# ============ FEEDBACK ============
class TicketFeedbackCreate(BaseModel):
    staff_id: int
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None

class TicketFeedbackResponse(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    user_id: int
    staff_id: int
    rating: int
    comment: Optional[str] = None
    created_at: datetime
    class Config: from_attributes = True

class FeedbackStatsResponse(BaseModel):
    average_rating: float
    total_feedbacks: int
    by_staff: Dict[str, Dict[str, Any]]

# ============ CONFIG ============
class TicketConfigUpdate(BaseModel):
    max_open_tickets: Optional[int] = None
    auto_close_hours: Optional[int] = None
    allow_user_close: Optional[bool] = None
    allow_attachments: Optional[bool] = None
    transcript_channel: Optional[int] = None

class TicketConfigResponse(BaseModel):
    guild_id: int
    max_open_tickets: int
    auto_close_hours: int
    allow_user_close: bool
    allow_attachments: bool
    transcript_channel: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    class Config: from_attributes = True