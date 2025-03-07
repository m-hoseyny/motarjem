import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database configuration from environment
LOCAL_DB = os.getenv("LOCAL_DB", "false").lower() == "true"
# Use sqlite+aiosqlite:// instead of sqlite:// for async support
DATABASE_URL = os.getenv("SQLITE_URL", "sqlite+aiosqlite:///./sql_app.db") if LOCAL_DB else os.getenv("DATABASE_URL")

if LOCAL_DB and not DATABASE_URL.startswith("sqlite+aiosqlite://"):
    DATABASE_URL = DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://")
print('Database URL: ', DATABASE_URL)
print('LOCAL_DB: ', os.getenv("LOCAL_DB", "false"))
# Create async SQLAlchemy engine
engine = create_async_engine(
    str(DATABASE_URL),
    echo=False,
    connect_args={"check_same_thread": False} if LOCAL_DB else {}
)

# Create async session factory
async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Create Base class
Base = declarative_base()

# Dependency
async def get_db():
    db = async_session()
    try:
        yield db
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()
