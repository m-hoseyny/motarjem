from sqlalchemy import BigInteger, Column, Integer, String, DateTime, ForeignKey, Boolean, Enum, Double
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.sql import func, select
from sqlalchemy.orm import relationship
from sqlalchemy.ext.asyncio import AsyncSession
from .database import Base
import secrets
import string
import enum
from sqlalchemy.types import TypeDecorator, String
import json
import uuid

class FileStatus(enum.Enum):
    INIT = "init"
    PROCESSING = "processing"
    FAILED = "failed"
    COMPLETED = "completed"

class PaymentMethod(enum.Enum):
    ONLINE = "online"
    CART2CART = "cart2cart"

class PaymentStatus(enum.Enum):
    INIT = "init"
    PENDING = "pending"
    FAILED = "failed"
    SUCCESS = "success"

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

    async def get_balance(self, db: AsyncSession) -> float:
        """Calculate user's balance based on incoming and outgoing transactions"""
        # Get incoming transactions
        incoming_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .filter(Transaction.to_user_id == self.id)
        )
        incoming_sum = incoming_result.scalar_one()

        # Get outgoing transactions
        outgoing_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .filter(Transaction.from_user_id == self.id)
        )
        outgoing_sum = outgoing_result.scalar_one()

        return incoming_sum - outgoing_sum

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
    price_unit = Column(Double)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    file_name = Column(String, nullable=True)
    total_token_used = Column(Integer, nullable=True)
    total_cost = Column(Double, nullable=True)  # Store cost in Dollar
    message_id = Column(BigInteger, nullable=True)
    
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
            file_name: str = None,
            message_id: int = None
        ):
        """Create a new file translation record"""
        file_translation = FileTranslation(
            user_id=user_id,
            input_file_id=input_file_id,
            total_lines=total_lines,
            price_unit=price_unit,
            status=FileStatus.INIT,
            file_name=file_name,
            message_id=message_id
        )
        
        db.add(file_translation)
        await db.flush()
        
        return file_translation

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    amount = Column(Double, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])
    invoice = relationship("Invoice", back_populates="transactions", secondary="invoice_transactions")
    receipt = relationship("Receipt", back_populates="transactions", secondary="receipt_transactions")

class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String, unique=True, index=True)
    description = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="invoices")
    transactions = relationship("Transaction", back_populates="invoice", secondary="invoice_transactions")

class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Double, nullable=False)
    description = Column(String, nullable=True)
    tracker_id = Column(String, nullable=True)
    bank = Column(String, nullable=True)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.INIT)
    method = Column(Enum(PaymentMethod), default=PaymentMethod.ONLINE)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    extra_data = Column(JSON, nullable=True)  # Using our custom JSONString type

    def update_extra_data(self, new_data: dict):
        """Update extra_data by merging with existing data"""
        current_data = self.extra_data or {}
        current_data.update(new_data)
        self.extra_data = current_data

    # Relationships
    user = relationship("User", backref="receipts")
    transactions = relationship("Transaction", back_populates="receipt", secondary="receipt_transactions")
    
    def __repr__(self):
        return f"Receipt(id={self.id}, number={self.number}, amount={self.amount}, status={self.status}, method={self.method})"

class JSONString(TypeDecorator):
    """Represents a JSON object as a string."""

    impl = String

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
        return None

    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)
        return None

# Association tables for many-to-many relationships
class InvoiceTransaction(Base):
    __tablename__ = "invoice_transactions"
    
    invoice_id = Column(Integer, ForeignKey("invoices.id"), primary_key=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), primary_key=True)

class ReceiptTransaction(Base):
    __tablename__ = "receipt_transactions"
    
    receipt_id = Column(Integer, ForeignKey("receipts.id"), primary_key=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), primary_key=True)



from models.database import async_session

async def get_user_balance(user_id: int) -> float:
    async with async_session() as db:
        incoming_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .filter(Transaction.to_user_id == user_id)
        )
        incoming_sum = incoming_result.scalar()

        # Get outgoing transactions sum
        outgoing_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .filter(Transaction.from_user_id == user_id)
        )
        outgoing_sum = outgoing_result.scalar()
        balance = incoming_sum - outgoing_sum
        return balance / 10

async def init_user_charge(user_id: int, amount_toman: int, db) -> None:
    """Initialize user's account with given amount in Tomans"""
    # Convert Tomans to Rials
    amount_rial = amount_toman * 10
    
    # Create initial charge transaction
    initial_charge = Transaction(
        to_user_id=user_id,
        amount=amount_rial,
        description=f"Initial welcome bonus: {amount_toman:,} Tomans"
    )
    db.add(initial_charge)
    await db.flush()
    
    # Create welcome invoice
    welcome_invoice = Invoice(
        user_id=user_id,
        number=str(uuid.uuid4()),
        description="Welcome bonus credit"
    )
    db.add(welcome_invoice)
    await db.flush()
    
    # Link transaction to invoice
    invoice_transaction = InvoiceTransaction(
        invoice_id=welcome_invoice.id,
        transaction_id=initial_charge.id
    )
    db.add(invoice_transaction)