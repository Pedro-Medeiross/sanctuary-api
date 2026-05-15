from pydantic import BaseModel, Field


class PrefixUpdate(BaseModel):
    prefix: str = Field(..., min_length=1, max_length=10)


class PrefixResponse(BaseModel):
    prefix: str
    guild_id: int