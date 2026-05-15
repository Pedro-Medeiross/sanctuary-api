from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config import settings

mongo_client: AsyncIOMotorClient = None
mongo_db: AsyncIOMotorDatabase = None


async def init_mongo():
    """Inicializa conexão com MongoDB e cria índices"""
    global mongo_client, mongo_db

    try:
        mongo_client = AsyncIOMotorClient(
            settings.MONGODB_URL,
            serverSelectionTimeoutMS=5000,
            maxPoolSize=50,
            minPoolSize=5
        )
        await mongo_client.admin.command('ping')
        mongo_db = mongo_client[settings.MONGODB_DB]
        await create_indexes()
        print("✅ MongoDB conectado")
    except Exception as e:
        print(f"⚠️ MongoDB não disponível: {e}")
        mongo_client = None
        mongo_db = None


async def create_indexes():
    """Cria índices para performance"""
    if mongo_db is None:
        return

    await mongo_db.action_logs.create_index(
        [("guild_id", 1), ("log_type", 1), ("created_at", -1)],
        name="idx_guild_type_date"
    )
    await mongo_db.action_logs.create_index(
        [("guild_id", 1), ("user_id", 1), ("created_at", -1)],
        name="idx_guild_user_date"
    )
    await mongo_db.action_logs.create_index(
        [("data.content", "text"), ("data.member_name", "text")],
        name="idx_text_search"
    )
    await mongo_db.ticket_transcripts.create_index(
        "ticket_id", unique=True, name="idx_transcript_ticket"
    )
    await mongo_db.ticket_transcripts.create_index(
        "guild_id", name="idx_transcript_guild"
    )

    print("✅ Índices MongoDB criados")


async def close_mongo():
    """Fecha conexão com MongoDB"""
    global mongo_client
    if mongo_client:
        mongo_client.close()
        print("🛑 MongoDB desconectado")


def get_mongo() -> AsyncIOMotorDatabase:
    return mongo_db


def is_mongo_available() -> bool:
    return mongo_db is not None