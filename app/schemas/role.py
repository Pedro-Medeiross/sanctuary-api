from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid

class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    permissions: Optional[List[str]] = []
    color: Optional[str] = "#99AAB5"
    position: Optional[int] = 0

class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[List[str]] = None
    color: Optional[str] = None
    position: Optional[int] = None
    is_active: Optional[bool] = None

class RoleResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    permissions: str
    color: str
    position: int
    is_default: bool
    is_system: bool
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class UserRoleAssign(BaseModel):
    user_id: uuid.UUID
    role_id: uuid.UUID

class UserRoleRemove(BaseModel):
    user_id: uuid.UUID
    role_id: uuid.UUID