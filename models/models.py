from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, Session
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
    def create_from_telegram(db: Session, telegram_user, password_hash_func=None):
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
        db.flush()  # Get the user ID without committing
        return user, None


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
    # Relationship with User
    user = relationship("User", back_populates="bot_user")

    @staticmethod
    def create_from_telegram(db: Session, telegram_user, password_hash_func=None, create_user=True):
        """Create a new BotUser from Telegram user data, optionally creating a linked User"""
        bot_user = None
        user = None
        password = None

        if create_user:
            # Create the User first
            user, password = User.create_from_telegram(db, telegram_user, password_hash_func)

        # Create the BotUser
        bot_user = BotUser(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            is_active=True,
            user_id=user.id if user else None
        )
        db.add(bot_user)
        db.flush()  # Get the bot_user ID without committing

        return bot_user, user, password


class FileTranslation(Base):
    __tablename__ = "file_translations"

    id = Column(Integer, primary_key=True, index=True)
    input_file_id = Column(String)
    output_file_id = Column(String, nullable=True)
    status = Column(Enum(FileStatus), default=FileStatus.INIT)
    total_lines = Column(Integer)
    price_unit = Column(Integer)  # Price per line in Toman
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Foreign key to User
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="file_translations")

    @staticmethod
    def create_from_telegram(
        db: Session,
        user_id: int,
        input_file_id: str,
        total_lines: int,
        price_unit: int = 200
    ):
        """Create a new file translation record"""
        file_translation = FileTranslation(
            input_file_id=input_file_id,
            user_id=user_id,
            total_lines=total_lines,
            price_unit=price_unit,
            status=FileStatus.INIT
        )
        db.add(file_translation)
        db.flush()
        return file_translation
