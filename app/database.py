# app/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Tabelas criadas/verificadas com sucesso")
    
# Adicionar função para criar roles padrão
async def create_default_roles():
    """Cria roles padrão do sistema"""
    from app.models.role import Role
    from app.database import async_session
    
    default_roles = [
        {
            "name": "Owner",
            "description": "Dono do sistema - acesso total",
            "permissions": "[]",
            "color": "#FF0000",
            "position": 100,
            "is_default": False,
            "is_system": True,
        },
        {
            "name": "Admin",
            "description": "Administrador do sistema",
            "permissions": "[]",
            "color": "#FF6B6B",
            "position": 80,
            "is_default": False,
            "is_system": False,
        },
        {
            "name": "Mod",
            "description": "Moderador do sistema",
            "permissions": "[]",
            "color": "#4ECDC4",
            "position": 50,
            "is_default": False,
            "is_system": False,
        },
        {
            "name": "Player",
            "description": "Usuário padrão",
            "permissions": "[]",
            "color": "#99AAB5",
            "position": 10,
            "is_default": True,
            "is_system": True,
        },
    ]
    
    async with async_session() as session:
        from sqlalchemy import select
        
        for role_data in default_roles:
            # Verificar se já existe
            result = await session.execute(
                select(Role).where(Role.name == role_data["name"])
            )
            existing = result.scalar_one_or_none()
            
            if not existing:
                role = Role(**role_data)
                session.add(role)
                print(f"✅ Role criada: {role_data['name']}")
            else:
                print(f"⏭️ Role já existe: {role_data['name']}")
        
        await session.commit()
    print("✅ Roles padrão verificadas/criadas")

async def drop_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    print("🗑️ Tabelas removidas")