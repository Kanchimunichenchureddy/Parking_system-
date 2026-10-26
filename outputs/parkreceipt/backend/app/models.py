from .config import database_url
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

def now(): return datetime.now(timezone.utc).replace(tzinfo=None)
_url = database_url()
engine = create_engine(_url, pool_pre_ping=True, **({"connect_args":{"connect_timeout":5}} if _url.drivername=="mysql+pymysql" else {}))
Session = sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
class Location(Base):
    __tablename__="locations"
    id: Mapped[int]=mapped_column(primary_key=True)
    slug: Mapped[str]=mapped_column(String(60),unique=True)
    name: Mapped[str]=mapped_column(String(100))
    rate: Mapped[int]=mapped_column(Integer,default=3000)
class User(Base):
    __tablename__="users"
    id: Mapped[int]=mapped_column(primary_key=True)
    username: Mapped[str]=mapped_column(String(80),unique=True)
    password_hash: Mapped[str]=mapped_column(String(255))
    role: Mapped[str]=mapped_column(String(10))
    location_id: Mapped[int|None]=mapped_column(ForeignKey("locations.id"),nullable=True)
class PaymentRequest(Base):
    __tablename__="payment_requests"
    id: Mapped[int]=mapped_column(primary_key=True)
    token: Mapped[str]=mapped_column(String(64),unique=True)
    idempotency_key: Mapped[str]=mapped_column(String(100),unique=True)
    reference: Mapped[str]=mapped_column(String(16),unique=True)
    location_id: Mapped[int]=mapped_column(ForeignKey("locations.id"))
    vehicle: Mapped[str]=mapped_column(String(32))
    phone: Mapped[str|None]=mapped_column(String(20),nullable=True)
    amount: Mapped[int]=mapped_column(Integer)
    method: Mapped[str]=mapped_column(String(10))
    state: Mapped[str]=mapped_column(String(12),default="pending")
    created_at: Mapped[datetime]=mapped_column(DateTime,default=now)
    confirmed_at: Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    confirmed_by: Mapped[int|None]=mapped_column(ForeignKey("users.id"),nullable=True)
class PaymentAttempt(Base):
    __tablename__="payment_attempts"
    id: Mapped[int]=mapped_column(primary_key=True)
    request_id: Mapped[int]=mapped_column(ForeignKey("payment_requests.id"))
    outcome: Mapped[str]=mapped_column(String(12))
    created_at: Mapped[datetime]=mapped_column(DateTime,default=now)
class Receipt(Base):
    __tablename__="receipts"
    id: Mapped[int]=mapped_column(primary_key=True)
    request_id: Mapped[int]=mapped_column(ForeignKey("payment_requests.id"),unique=True)
    number: Mapped[str]=mapped_column(String(40),unique=True)
class AuditEvent(Base):
    __tablename__="audit_events"
    id: Mapped[int]=mapped_column(primary_key=True)
    actor_id: Mapped[int|None]=mapped_column(ForeignKey("users.id"),nullable=True)
    request_id: Mapped[int|None]=mapped_column(ForeignKey("payment_requests.id"),nullable=True)
    action: Mapped[str]=mapped_column(String(60))
    detail: Mapped[str]=mapped_column(Text,default="")
    created_at: Mapped[datetime]=mapped_column(DateTime,default=now)
class LoginSession(Base):
    __tablename__="login_sessions"
    digest: Mapped[str]=mapped_column(String(64),primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime]=mapped_column(DateTime)
