from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.asyncio import AsyncSession
from .database import Base
import secrets
import string
import enum

class FileStatus(enum.Enum):
    INIT = "init"
    PROCESSING = "processing"
    FAILED = "failed"
    COMPLETED = "completed"

def generate_random_password(length=12):
    alphabet = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(alphabet) for _ in range(length))

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String, nullable=True)
    first_name = Column(String)
    last_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    bot_user = relationship("BotUser", back_populates="user", uselist=False)
    file_translations = relationship("FileTranslation", back_populates="user")

    @staticmethod
    async def create_from_telegram(db: AsyncSession, telegram_user, password_hash_func=None):
        """Create a new User from Telegram user data"""
        # Generate a temporary email if not available
        email = f"{telegram_user.username}@telegram.user" if telegram_user.username else f"user_{telegram_user.id}@telegram.user"
        
        user = User(
            email=email,
            username=telegram_user.username or f"user_{telegram_user.id}",
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            is_active=True
        )
        db.add(user)
        await db.flush()  # Get the user ID without committing
        return user

class BotUser(Base):
    __tablename__ = "bot_users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)
    username = Column(String, unique=True, index=True)
    first_name = Column(String)
    last_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Foreign key to User
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    user = relationship("User", back_populates="bot_user")

    @staticmethod
    async def create_from_telegram(db: AsyncSession, telegram_user, password_hash_func=None, create_user=True):
        """Create a new BotUser from Telegram user data, optionally creating a linked User"""
        bot_user = BotUser(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            is_active=True
        )
        
        user = None
        password = None
        
        if create_user:
            user = await User.create_from_telegram(db, telegram_user, password_hash_func)
            bot_user.user = user
            
            if password_hash_func:
                password = generate_random_password()
                user.hashed_password = password_hash_func(password)
        
        db.add(bot_user)
        await db.flush()
        
        return bot_user, user, password

class FileTranslation(Base):
    __tablename__ = "file_translations"

    id = Column(Integer, primary_key=True, index=True)
    input_file_id = Column(String)
    output_file_id = Column(String, nullable=True)
    status = Column(Enum(FileStatus), default=FileStatus.INIT)
    total_lines = Column(Integer)
    price_unit = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    file_name = Column(String, nullable=True)
    total_token_used = Column(Integer, nullable=True)
    total_cost = Column(Integer, nullable=True)  # Store cost in Dollar
    
    # Foreign key to User
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="file_translations")

    @staticmethod
    async def create_from_telegram(
            db: AsyncSession,
            user_id: int,
            input_file_id: str,
            total_lines: int,
            price_unit: int = 200,
            file_name: str = None
        ):
        """Create a new file translation record"""
        file_translation = FileTranslation(
            user_id=user_id,
            input_file_id=input_file_id,
            total_lines=total_lines,
            price_unit=price_unit,
            status=FileStatus.INIT,
            file_name=file_name
        )
        
        db.add(file_translation)
        await db.flush()
        
        return file_translation
