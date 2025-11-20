import os
import sys
import logging
import re
import asyncio
import json
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dotenv import load_dotenv
from modules.scenarios import SCENARIOS
from modules.i18n import get_lang, set_lang

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
)

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    Text,
    text,
    inspect,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import requests
import qrcode
from io import BytesIO

# Initialize logging first (before config loading for error messages)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================================================
# Configuration Loading
# ============================================================================

def load_config():
    """
    Load configuration from environment variables.
    
    Loads .env file and validates required variables.
    Sets default values for optional variables.
    
    Returns:
        dict: Configuration dictionary with all settings
        
    Raises:
        SystemExit: If required variables are missing
    """
    # Load .env file
    env_loaded = load_dotenv()
    
    if not env_loaded:
        logger.warning("No .env file found. Using environment variables only.")
    
    # Required variables
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        print("=" * 60)
        print("ERROR: BOT_TOKEN is required but not set!")
        print("=" * 60)
        print("\nPlease create a .env file with the following content:")
        print("\n  BOT_TOKEN=your_bot_token_here")
        print("\nTo get a bot token:")
        print("  1. Open Telegram and search for @BotFather")
        print("  2. Send /newbot and follow instructions")
        print("  3. Copy the token and add it to .env file")
        print("\nExample .env file:")
        print("  BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz")
        print("  ADMIN_CHAT_ID=123456789")
        print("  QUIZ_PASS_THRESHOLD=3")
        print("=" * 60)
        sys.exit(1)
    
    # Optional variables with defaults
    database_url = os.getenv("DATABASE_URL", "sqlite:///fs_bot.db").strip()
    if not database_url:
        database_url = "sqlite:///fs_bot.db"
    
    quiz_pass_threshold = os.getenv("QUIZ_PASS_THRESHOLD", "3").strip()
    try:
        quiz_pass_threshold = int(quiz_pass_threshold)
        if quiz_pass_threshold < 1:
            logger.warning("QUIZ_PASS_THRESHOLD must be >= 1, using default: 3")
            quiz_pass_threshold = 3
    except ValueError:
        logger.warning(f"Invalid QUIZ_PASS_THRESHOLD value '{quiz_pass_threshold}', using default: 3")
        quiz_pass_threshold = 3
    
    # Admin IDs parsing
    admin_ids: List[int] = []
    admin_ids_env = os.getenv("ADMIN_IDS", "").strip()
    admin_chat_id = os.getenv("ADMIN_CHAT_ID", "").strip()
    
    if admin_ids_env:
        # Parse comma-separated list
        for raw_id in admin_ids_env.split(","):
            raw_id = raw_id.strip()
            if raw_id.isdigit():
                admin_ids.append(int(raw_id))
            else:
                logger.warning(f"Invalid admin ID in ADMIN_IDS: '{raw_id}', skipping")
    elif admin_chat_id:
        # Single admin ID
        if admin_chat_id.isdigit():
            admin_ids.append(int(admin_chat_id))
        else:
            logger.warning(f"Invalid ADMIN_CHAT_ID: '{admin_chat_id}', ignoring")
    
    config = {
        "BOT_TOKEN": bot_token,
        "DATABASE_URL": database_url,
        "QUIZ_PASS_THRESHOLD": quiz_pass_threshold,
        "ADMIN_IDS": admin_ids,
    }
    
    # Log configuration (without sensitive data)
    logger.info("Configuration loaded successfully")
    logger.info(f"Database URL: {database_url}")
    logger.info(f"Quiz pass threshold: {quiz_pass_threshold}")
    logger.info(f"Admin IDs configured: {len(admin_ids)} admin(s)")
    if admin_ids:
        logger.info(f"Admin IDs: {admin_ids}")
    
    return config

# Load configuration
config = load_config()

# Extract configuration values
BOT_TOKEN = config["BOT_TOKEN"]
DATABASE_URL = config["DATABASE_URL"]
QUIZ_PASS_THRESHOLD = config["QUIZ_PASS_THRESHOLD"]
ADMIN_IDS: List[int] = config["ADMIN_IDS"]

# All features are free - no subscriptions needed

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database
Base = declarative_base()
engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    subscribed = Column(Boolean, default=False)
    coins = Column(Integer, default=0)
    quizzes_passed = Column(Integer, default=0)
    max_unlocked_level = Column(Integer, default=1)
    scenario_score = Column(Integer, default=0)
    scenario_badges = Column(String, default="")
    # Связь с банком-партнером (если пользователь пришел через банк)
    bank_partner_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ScamReport(Base):
    __tablename__ = "scam_reports"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    telegram_id = Column(Integer, nullable=False)
    description = Column(Text, nullable=False)
    link = Column(String, nullable=True)
    contact = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="new")


class BroadcastLog(Base):
    __tablename__ = "broadcasts"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    admin_id = Column(Integer, nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# Startup Features: Premium Subscriptions
# Subscription model removed - all features are now free


# Startup Features: Analytics
class UserEvent(Base):
    __tablename__ = "user_events"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)  # quiz_start, quiz_complete, scenario_start, etc.
    event_data = Column(Text, nullable=True)  # JSON string
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class AnalyticsDaily(Base):
    __tablename__ = "analytics_daily"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    date = Column(DateTime, unique=True, nullable=False, index=True)
    dau = Column(Integer, default=0)  # Daily Active Users
    new_users = Column(Integer, default=0)
    premium_conversions = Column(Integer, default=0)
    quiz_completions = Column(Integer, default=0)
    scenario_completions = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


# Startup Features: Referrals
class Referral(Base):
    __tablename__ = "referrals"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    referrer_id = Column(Integer, nullable=False, index=True)
    referred_id = Column(Integer, nullable=True, index=True)
    referral_code = Column(String, unique=True, nullable=False, index=True)
    status = Column(String, default="pending")  # pending, completed, rewarded
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


# Startup Features: Leaderboards
class LeaderboardEntry(Base):
    __tablename__ = "leaderboard_entries"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    score = Column(Integer, default=0)
    rank = Column(Integer, nullable=True)
    period = Column(String, default="all_time")  # all_time, weekly, monthly
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Startup Features: Learning Paths
class UserLearningPath(Base):
    __tablename__ = "user_learning_paths"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    scenario_type = Column(String, nullable=False)  # phishing, social_engineering, etc.
    skill_level = Column(String, default="beginner")  # beginner, intermediate, advanced
    recommended_scenarios = Column(Text, nullable=True)  # JSON array of scenario IDs
    completed_scenarios = Column(Text, default="[]")  # JSON array
    weak_areas = Column(Text, default="[]")  # JSON array of identified weaknesses
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Startup Features: Bank Partners (для обратной совместимости, но теперь используем BankPartner)
class CorporateAccount(Base):
    __tablename__ = "corporate_accounts"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    company_name = Column(String, nullable=False)
    admin_user_id = Column(Integer, nullable=False, index=True)
    license_key = Column(String, unique=True, nullable=False, index=True)
    max_users = Column(Integer, default=100)
    current_users = Column(Integer, default=0)
    status = Column(String, default="active")  # active, suspended, expired
    subscription_tier = Column(String, default="enterprise")
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    # White-label customization
    brand_color = Column(String, default="#0066CC")
    brand_logo_url = Column(String, nullable=True)
    company_domain = Column(String, nullable=True)
    custom_welcome_message = Column(Text, nullable=True)


# Payment Transactions
class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    amount = Column(Integer, nullable=False)  # Amount in cents
    currency = Column(String, default="USD")
    payment_method = Column(String, nullable=False)  # stripe, payme, manual
    payment_intent_id = Column(String, nullable=True, index=True)
    status = Column(String, default="pending")  # pending, completed, failed, refunded
    subscription_id = Column(Integer, nullable=True, index=True)
    transaction_metadata = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


# Bank Partners - банки как партнеры/лицензиаты
class BankPartner(Base):
    __tablename__ = "bank_partners"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    bank_name = Column(String, nullable=False)  # Kaspi Bank, Halyk Bank, etc.
    admin_user_id = Column(Integer, nullable=False, index=True)  # Telegram ID администратора банка
    api_key = Column(String, unique=True, nullable=False, index=True)  # API ключ для интеграции
    license_key = Column(String, unique=True, nullable=False, index=True)  # Лицензионный ключ
    max_clients = Column(Integer, default=10000)  # Максимум клиентов банка
    current_clients = Column(Integer, default=0)  # Текущее количество клиентов
    status = Column(String, default="active")  # active, suspended, expired
    subscription_tier = Column(String, default="enterprise")  # basic, premium, enterprise
    # White-label customization для банков
    brand_color = Column(String, default="#0066CC")
    brand_logo_url = Column(String, nullable=True)
    bank_domain = Column(String, nullable=True)
    custom_welcome_message = Column(Text, nullable=True)
    # Интеграция с банковскими системами
    webhook_url = Column(String, nullable=True)  # URL для отправки событий в банк
    api_secret = Column(String, nullable=True)  # Секрет для верификации API запросов
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)


# Bank Clients - клиенты банка, использующие бота
class BankClient(Base):
    __tablename__ = "bank_clients"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    bank_partner_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)  # Telegram ID пользователя
    client_card_number = Column(String, nullable=True)  # Номер карты клиента (замаскированный)
    enrolled_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="active")  # active, suspended


# Bank Analytics - аналитика для банков о их клиентах
class BankAnalytics(Base):
    __tablename__ = "bank_analytics"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    bank_partner_id = Column(Integer, nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    total_clients = Column(Integer, default=0)  # Всего клиентов банка в боте
    active_users = Column(Integer, default=0)  # Активных пользователей за день
    quiz_completions = Column(Integer, default=0)  # Завершенных квизов
    scenario_completions = Column(Integer, default=0)  # Завершенных сценариев
    scam_reports = Column(Integer, default=0)  # Сообщений о скамах
    average_quiz_score = Column(Integer, default=0)  # Средний балл квизов
    protection_rate = Column(Integer, default=0)  # Процент успешных защит от скамов
    created_at = Column(DateTime, default=datetime.utcnow)


# Bank Custom Scenarios - кастомные сценарии, созданные банками
class BankCustomScenario(Base):
    __tablename__ = "bank_custom_scenarios"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    bank_partner_id = Column(Integer, nullable=False, index=True)
    scenario_id = Column(String, nullable=False, index=True)  # Уникальный ID сценария
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    scenario_data = Column(Text, nullable=False)  # JSON данные сценария
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Bank Custom Alerts - кастомные алерты от банков
class BankCustomAlert(Base):
    __tablename__ = "bank_custom_alerts"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    bank_partner_id = Column(Integer, nullable=False, index=True)
    alert_type = Column(String, nullable=False)  # phishing, sms, call, etc.
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String, default="high")  # low, medium, high, critical
    target_city = Column(String, nullable=True)  # Для конкретного города или null для всех
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)


# ============================================================================
# KAZAKHSTAN-SPECIFIC FEATURES
# ============================================================================

# Real-time Scam Alerts
class ScamAlert(Base):
    __tablename__ = "scam_alerts"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    alert_type = Column(String, nullable=False, index=True)  # kaspi, halyk, jusan, kazakhtelecom, general
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String, default="high")  # low, medium, high, critical
    city = Column(String, nullable=True, index=True)  # Almaty, Astana, Shymkent, etc.
    region = Column(String, nullable=True)
    source = Column(String, default="nbrk")  # nbrk, community, bank
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=True)


# Community Scam Reports (Anonymous)
class CommunityScamReport(Base):
    __tablename__ = "community_scam_reports"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    scam_type = Column(String, nullable=False)  # phishing, sms, call, investment, job, loan
    bank_name = Column(String, nullable=True)  # Kaspi, Halyk, Jusan, etc.
    description = Column(Text, nullable=False)
    city = Column(String, nullable=True, index=True)
    verified = Column(Boolean, default=False)
    verification_votes = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


# Scam Verification Votes
class ScamVerificationVote(Base):
    __tablename__ = "scam_verification_votes"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    report_id = Column(Integer, nullable=False, index=True)
    is_scam = Column(Boolean, nullable=False)  # True = scam, False = not scam
    created_at = Column(DateTime, default=datetime.utcnow)


# User Location/City
class UserLocation(Base):
    __tablename__ = "user_locations"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    city = Column(String, nullable=True, index=True)  # Almaty, Astana, etc.
    region = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# QR Code Safety Checks
class QRCodeCheck(Base):
    __tablename__ = "qr_code_checks"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    qr_data = Column(Text, nullable=False)
    is_safe = Column(Boolean, nullable=False)
    risk_level = Column(String, default="unknown")  # safe, low, medium, high, dangerous
    checked_at = Column(DateTime, default=datetime.utcnow, index=True)


# Emergency Fund Tracker
class EmergencyFund(Base):
    __tablename__ = "emergency_funds"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    target_amount = Column(Integer, default=0)
    current_amount = Column(Integer, default=0)
    monthly_expenses = Column(Integer, default=0)
    months_covered = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)
    upgrade_schema()


def upgrade_schema():
    try:
        with engine.begin() as conn:
            user_columns = []
            if engine.dialect.name == "sqlite":
                rows = conn.execute(text("PRAGMA table_info(users)")).fetchall()
                user_columns = [row[1] for row in rows]
            else:
                inspector = inspect(engine)
                user_columns = [col["name"] for col in inspector.get_columns("users")]

            if "max_unlocked_level" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN max_unlocked_level INTEGER DEFAULT 1"))
                logger.info("Added max_unlocked_level column to users table")
            if "scenario_score" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN scenario_score INTEGER DEFAULT 0"))
                logger.info("Added scenario_score column to users table")
            if "scenario_badges" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN scenario_badges VARCHAR DEFAULT ''"))
                logger.info("Added scenario_badges column to users table")
            if "bank_partner_id" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN bank_partner_id INTEGER"))
                logger.info("Added bank_partner_id column to users table")
    except Exception as e:
        logger.exception("Schema upgrade failed: %s", e)


def get_db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def ensure_user_record(user_id: int, username: str = None, first_name: str = None, last_name: str = None) -> Optional[User]:
    try:
        with SessionLocal() as db:
            u = db.query(User).filter_by(telegram_id=user_id).first()
            if not u:
                u = User(
                    telegram_id=user_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    subscribed=False,
                    coins=0,
                    quizzes_passed=0,
                    max_unlocked_level=1,
                    scenario_score=0,
                    scenario_badges="",
                )
                db.add(u)
                db.commit()
                db.refresh(u)
            return u
    except Exception as e:
        logger.exception("ensure_user_record error: %s", e)
        return None



def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


SUSPICIOUS_PATTERNS = [
    r"\.tk\b",
    r"free-.*-cash",
    r"claim-prize",
    r"verify-account",
    r"secure-login",
    r"signin\.",
    r"update-account",
    r"bit\.ly/",
    r"tinyurl\.com/",
]


def link_is_suspicious(url: str) -> bool:
    url = url.lower()
    for p in SUSPICIOUS_PATTERNS:
        if re.search(p, url):
            return True
    if re.match(r"https?://\d+\.\d+\.\d+\.\d+", url):
        return True
    if url.count(".") >= 4:
        return True
    return False


# ============================================================================
# STARTUP FEATURES: Analytics, Premium, Referrals, Leaderboards
# ============================================================================


def track_user_event(user_id: int, event_type: str, event_data: Optional[Dict] = None):
    """Track user events for analytics"""
    try:
        with SessionLocal() as db:
            event = UserEvent(
                user_id=user_id,
                event_type=event_type,
                event_data=json.dumps(event_data) if event_data else None,
            )
            db.add(event)
            db.commit()
    except Exception as e:
        logger.exception("Failed to track user event: %s", e)


# All subscription/premium code removed - all features are free


# ============================================================================
# B2B / BANK PARTNER FEATURES - Банки как партнеры для своих клиентов
# ============================================================================

def create_bank_partner(bank_name: str, admin_user_id: int, max_clients: int = 10000, webhook_url: str = None) -> Dict[str, any]:
    """Создать банк-партнер (лицензиат) для предоставления бота своим клиентам"""
    try:
        with SessionLocal() as db:
            # Generate API key and license key
            api_key = secrets.token_urlsafe(32)
            license_key = secrets.token_urlsafe(32)
            api_secret = secrets.token_urlsafe(32)
            
            bank = BankPartner(
                bank_name=bank_name,
                admin_user_id=admin_user_id,
                api_key=api_key,
                license_key=license_key,
                max_clients=max_clients,
                current_clients=0,
                status="active",
                subscription_tier="enterprise",
                webhook_url=webhook_url,
                api_secret=api_secret,
                expires_at=datetime.utcnow() + timedelta(days=365),
            )
            db.add(bank)
            db.commit()
            db.refresh(bank)
            
            return {
                "success": True,
                "bank_id": bank.id,
                "api_key": api_key,
                "license_key": license_key,
                "api_secret": api_secret,
            }
    except Exception as e:
        logger.exception("Failed to create bank partner: %s", e)
        return {"success": False, "error": str(e)}


def register_bank_client(bank_partner_id: int, user_id: int, card_number: str = None) -> bool:
    """Зарегистрировать клиента банка в боте (обычный гражданин)"""
    try:
        with SessionLocal() as db:
            bank = db.query(BankPartner).filter_by(id=bank_partner_id).first()
            if not bank or bank.status != "active":
                return False
            
            # Check client limit
            if bank.current_clients >= bank.max_clients:
                return False
            
            # Check if already registered
            existing = db.query(BankClient).filter_by(
                bank_partner_id=bank_partner_id,
                user_id=user_id
            ).first()
            
            if existing:
                return True  # Already registered
            
            # Register client
            client = BankClient(
                bank_partner_id=bank_partner_id,
                user_id=user_id,
                client_card_number=card_number,
                status="active",
            )
            db.add(client)
            
            # Update user's bank association
            user = db.query(User).filter_by(telegram_id=user_id).first()
            if user:
                user.bank_partner_id = bank_partner_id
            
            bank.current_clients += 1
            db.commit()
            
            track_user_event(user_id, "bank_client_registered", {
                "bank_id": bank_partner_id,
                "bank_name": bank.bank_name,
            })
            
            return True
    except Exception as e:
        logger.exception("Failed to register bank client: %s", e)
        return False


def get_bank_analytics(bank_partner_id: int, days: int = 30) -> Dict[str, any]:
    """Получить аналитику для банка о его клиентах"""
    try:
        with SessionLocal() as db:
            bank = db.query(BankPartner).filter_by(id=bank_partner_id).first()
            if not bank:
                return {"success": False, "error": "Bank partner not found"}
            
            # Get bank clients
            clients = db.query(BankClient).filter_by(
                bank_partner_id=bank_partner_id,
                status="active"
            ).all()
            client_user_ids = [c.user_id for c in clients]
            
            # Get analytics for bank's clients
            since_date = datetime.utcnow() - timedelta(days=days)
            
            # Quiz completions
            quiz_events = db.query(UserEvent).filter(
                UserEvent.user_id.in_(client_user_ids),
                UserEvent.event_type == "quiz_complete",
                UserEvent.timestamp >= since_date
            ).all()
            
            # Scenario completions
            scenario_events = db.query(UserEvent).filter(
                UserEvent.user_id.in_(client_user_ids),
                UserEvent.event_type == "scenario_complete",
                UserEvent.timestamp >= since_date
            ).all()
            
            # Scam reports
            scam_reports = db.query(ScamReport).filter(
                ScamReport.telegram_id.in_(client_user_ids),
                ScamReport.created_at >= since_date
            ).count()
            
            # Active users (users who used bot in last 7 days)
            week_ago = datetime.utcnow() - timedelta(days=7)
            active_user_ids = set()
            recent_events = db.query(UserEvent).filter(
                UserEvent.user_id.in_(client_user_ids),
                UserEvent.timestamp >= week_ago
            ).all()
            for event in recent_events:
                active_user_ids.add(event.user_id)
            
            # Calculate average quiz score
            quiz_scores = []
            for event in quiz_events:
                try:
                    event_data = json.loads(event.event_data) if event.event_data else {}
                    correct = event_data.get("correct", 0)
                    total = event_data.get("total", 1)
                    if total > 0:
                        quiz_scores.append(int((correct / total) * 100))
                except:
                    pass
            
            average_quiz_score = int(sum(quiz_scores) / len(quiz_scores)) if quiz_scores else 0
            
            # Protection rate (successful scenario completions)
            successful_scenarios = len([e for e in scenario_events if json.loads(e.event_data or "{}").get("outcome") == "success"])
            protection_rate = int((successful_scenarios / len(scenario_events) * 100)) if scenario_events else 0
            
            return {
                "success": True,
                "bank_id": bank_partner_id,
                "bank_name": bank.bank_name,
                "total_clients": len(clients),
                "active_users": len(active_user_ids),
                "quiz_completions": len(quiz_events),
                "scenario_completions": len(scenario_events),
                "scam_reports": scam_reports,
                "average_quiz_score": average_quiz_score,
                "protection_rate": protection_rate,
            }
    except Exception as e:
        logger.exception("Failed to get bank analytics: %s", e)
        return {"success": False, "error": str(e)}


def update_bank_analytics(bank_partner_id: int):
    """Обновить ежедневную аналитику для банка"""
    try:
        with SessionLocal() as db:
            today = datetime.utcnow().date()
            
            analytics = db.query(BankAnalytics).filter(
                BankAnalytics.bank_partner_id == bank_partner_id,
                BankAnalytics.date == today
            ).first()
            
            bank_data = get_bank_analytics(bank_partner_id, days=1)
            
            if analytics:
                analytics.total_clients = bank_data.get("total_clients", 0)
                analytics.active_users = bank_data.get("active_users", 0)
                analytics.quiz_completions = bank_data.get("quiz_completions", 0)
                analytics.scenario_completions = bank_data.get("scenario_completions", 0)
                analytics.scam_reports = bank_data.get("scam_reports", 0)
                analytics.average_quiz_score = bank_data.get("average_quiz_score", 0)
                analytics.protection_rate = bank_data.get("protection_rate", 0)
            else:
                analytics = BankAnalytics(
                    bank_partner_id=bank_partner_id,
                    date=datetime.utcnow(),
                    total_clients=bank_data.get("total_clients", 0),
                    active_users=bank_data.get("active_users", 0),
                    quiz_completions=bank_data.get("quiz_completions", 0),
                    scenario_completions=bank_data.get("scenario_completions", 0),
                    scam_reports=bank_data.get("scam_reports", 0),
                    average_quiz_score=bank_data.get("average_quiz_score", 0),
                    protection_rate=bank_data.get("protection_rate", 0),
                )
                db.add(analytics)
            
            db.commit()
    except Exception as e:
        logger.exception("Failed to update bank analytics: %s", e)


def get_white_label_config(bank_partner_id: int) -> Dict[str, any]:
    """Получить white-label конфигурацию для банка"""
    try:
        with SessionLocal() as db:
            bank = db.query(BankPartner).filter_by(id=bank_partner_id).first()
            if not bank:
                return {}
            
            return {
                "bank_name": bank.bank_name,
                "brand_color": bank.brand_color,
                "brand_logo_url": bank.brand_logo_url,
                "bank_domain": bank.bank_domain,
                "custom_welcome_message": bank.custom_welcome_message,
            }
    except Exception as e:
        logger.exception("Failed to get white-label config: %s", e)
        return {}


def create_bank_custom_scenario(bank_partner_id: int, scenario_id: str, title: str, scenario_data: str, description: str = None) -> Dict[str, any]:
    """Создать кастомный сценарий для банка"""
    try:
        with SessionLocal() as db:
            scenario = BankCustomScenario(
                bank_partner_id=bank_partner_id,
                scenario_id=scenario_id,
                title=title,
                description=description,
                scenario_data=scenario_data,
                active=True,
            )
            db.add(scenario)
            db.commit()
            
            return {"success": True, "scenario_id": scenario.id}
    except Exception as e:
        logger.exception("Failed to create bank scenario: %s", e)
        return {"success": False, "error": str(e)}


def create_bank_custom_alert(bank_partner_id: int, alert_type: str, title: str, description: str, severity: str = "high", target_city: str = None, expires_days: int = 7) -> Dict[str, any]:
    """Создать кастомный алерт от банка"""
    try:
        with SessionLocal() as db:
            alert = BankCustomAlert(
                bank_partner_id=bank_partner_id,
                alert_type=alert_type,
                title=title,
                description=description,
                severity=severity,
                target_city=target_city,
                active=True,
                expires_at=datetime.utcnow() + timedelta(days=expires_days),
            )
            db.add(alert)
            db.commit()
            
            return {"success": True, "alert_id": alert.id}
    except Exception as e:
        logger.exception("Failed to create bank alert: %s", e)
        return {"success": False, "error": str(e)}


def generate_referral_code(user_id: int) -> str:
    """Generate unique referral code for user"""
    base = f"{user_id}_{datetime.utcnow().timestamp()}"
    hash_obj = hashlib.md5(base.encode())
    return hash_obj.hexdigest()[:8].upper()


def get_or_create_referral_code(user_id: int) -> str:
    """Get existing referral code or create new one"""
    try:
        with SessionLocal() as db:
            referral = db.query(Referral).filter_by(referrer_id=user_id).first()
            if referral:
                return referral.referral_code
            
            code = generate_referral_code(user_id)
            referral = Referral(
                referrer_id=user_id,
                referral_code=code,
                status="pending",
            )
            db.add(referral)
            db.commit()
            return code
    except Exception as e:
        logger.exception("Failed to get/create referral code: %s", e)
        return generate_referral_code(user_id)


def process_referral(referral_code: str, new_user_id: int) -> Dict[str, any]:
    """Process a referral when new user signs up"""
    try:
        with SessionLocal() as db:
            referral = db.query(Referral).filter_by(referral_code=referral_code).first()
            if not referral or referral.referrer_id == new_user_id:
                return {"success": False, "message": "Invalid referral code"}
            
            if referral.status != "pending":
                return {"success": False, "message": "Referral already processed"}
            
            referral.referred_id = new_user_id
            referral.status = "completed"
            referral.completed_at = datetime.utcnow()
            db.commit()  # Commit to ensure count is accurate
            
            # Award referrer: count successful referrals (including this one)
            successful_refs = db.query(Referral).filter_by(
                referrer_id=referral.referrer_id,
                status="completed"
            ).count()
            
            # Award referrer with coins for referrals (no premium needed - all features free)
            if successful_refs > 0 and successful_refs % 3 == 0:
                # Give bonus coins for every 3 referrals
                referrer_user = db.query(User).filter_by(telegram_id=referral.referrer_id).first()
                if referrer_user:
                    referrer_user.coins = (referrer_user.coins or 0) + 50
                    db.commit()
            
            # Give new user welcome bonus coins
            new_user = db.query(User).filter_by(telegram_id=new_user_id).first()
            if new_user:
                new_user.coins = (new_user.coins or 0) + 20
            
            db.commit()
            return {"success": True, "referrer_id": referral.referrer_id}
    except Exception as e:
        logger.exception("Failed to process referral: %s", e)
        return {"success": False, "message": "Error processing referral"}


def update_leaderboard(user_id: int, score_delta: int = 0):
    """Update user's leaderboard score"""
    try:
        with SessionLocal() as db:
            # Get user's total score
            user = db.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                logger.warning(f"User {user_id} not found for leaderboard update")
                return
            
            # Calculate total score: coins + quiz completions * 10 + scenario score
            coins_score = (user.coins or 0) // 10  # 1 point per 10 coins
            quiz_score = (user.quizzes_passed or 0) * 10
            scenario_score = user.scenario_score or 0
            total_score = coins_score + quiz_score + scenario_score
            
            logger.info(f"Updating leaderboard for user {user_id}: coins={user.coins}, quizzes={user.quizzes_passed}, scenario={scenario_score}, total_score={total_score}")
            
            # Update or create leaderboard entry for all periods
            for period in ["all_time", "weekly", "monthly"]:
                entry = db.query(LeaderboardEntry).filter_by(
                    user_id=user_id,
                    period=period
                ).first()
                
                if entry:
                    entry.score = total_score
                    entry.updated_at = datetime.utcnow()
                else:
                    entry = LeaderboardEntry(
                        user_id=user_id,
                        score=total_score,
                        period=period,
                    )
                    db.add(entry)
            
            db.commit()
            
            # Recalculate ranks for all periods
            recalculate_leaderboard_ranks()
            
            logger.info(f"Leaderboard updated successfully for user {user_id}")
    except Exception as e:
        logger.exception("Failed to update leaderboard: %s", e)


def recalculate_leaderboard_ranks():
    """Recalculate ranks for all leaderboard periods"""
    try:
        with SessionLocal() as db:
            for period in ["all_time", "weekly", "monthly"]:
                entries = db.query(LeaderboardEntry).filter_by(
                    period=period
                ).order_by(LeaderboardEntry.score.desc()).all()
                
                for rank, entry in enumerate(entries, start=1):
                    entry.rank = rank
                
            db.commit()
    except Exception as e:
        logger.exception("Failed to recalculate leaderboard ranks: %s", e)


def get_leaderboard(period: str = "all_time", limit: int = 10, user_id: int = None) -> Dict:
    """Get leaderboard for a specific period with user position"""
    try:
        with SessionLocal() as db:
            # Get all entries for ranking
            all_entries = db.query(LeaderboardEntry).filter_by(
                period=period
            ).order_by(LeaderboardEntry.score.desc()).all()
            
            total_players = len(all_entries)
            
            # Get top entries
            top_entries = all_entries[:limit] if len(all_entries) > limit else all_entries
            
            result = []
            for entry in top_entries:
                user = db.query(User).filter_by(telegram_id=entry.user_id).first()
                if user:
                    # Get display name
                    display_name = user.username or user.first_name or f"User {entry.user_id}"
                    if user.username:
                        display_name = f"@{user.username}"
                    elif user.first_name:
                        display_name = user.first_name
                        if user.last_name:
                            display_name += f" {user.last_name}"
                    else:
                        display_name = f"User {entry.user_id}"
                    
                    result.append({
                        "rank": entry.rank or 0,
                        "user_id": entry.user_id,
                        "username": display_name,
                        "score": entry.score,
                    })
            
            # Get user's position if requested
            user_position = None
            user_percentage = None
            if user_id:
                user_entry = db.query(LeaderboardEntry).filter_by(
                    user_id=user_id,
                    period=period
                ).first()
                
                if user_entry:
                    # Find user's rank
                    user_rank = 1
                    for entry in all_entries:
                        if entry.user_id == user_id:
                            user_position = user_rank
                            user_percentage = ((total_players - user_rank + 1) / total_players * 100) if total_players > 0 else 0
                            break
                        user_rank += 1
            
            return {
                "entries": result,
                "total_players": total_players,
                "user_position": user_position,
                "user_percentage": user_percentage,
            }
    except Exception as e:
        logger.exception("Failed to get leaderboard: %s", e)
        return {"entries": [], "total_players": 0, "user_position": None, "user_percentage": None}


def aggregate_daily_analytics():
    """Aggregate daily analytics metrics"""
    try:
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        with SessionLocal() as db:
            # Check if already aggregated
            existing = db.query(AnalyticsDaily).filter_by(date=today).first()
            if existing:
                return
            
            yesterday = today - timedelta(days=1)
            
            # Calculate DAU (users active in last 24h)
            # Use subquery for distinct count
            from sqlalchemy import func
            dau_events = db.query(func.count(func.distinct(UserEvent.user_id))).filter(
                UserEvent.timestamp >= yesterday
            ).scalar() or 0
            
            # New users today
            new_users = db.query(User).filter(
                User.created_at >= today
            ).count()
            
            # Quiz completions
            quiz_completions = db.query(UserEvent).filter(
                UserEvent.event_type == "quiz_complete",
                UserEvent.timestamp >= yesterday
            ).count()
            
            # Scenario completions
            scenario_completions = db.query(UserEvent).filter(
                UserEvent.event_type == "scenario_complete",
                UserEvent.timestamp >= yesterday
            ).count()
            
            # Premium conversions
            premium_conversions = db.query(Subscription).filter(
                Subscription.created_at >= yesterday,
                Subscription.tier == "premium"
            ).count()
            
            daily = AnalyticsDaily(
                date=today,
                dau=dau_events,
                new_users=new_users,
                premium_conversions=premium_conversions,
                quiz_completions=quiz_completions,
                scenario_completions=scenario_completions,
            )
            db.add(daily)
            db.commit()
            
            logger.info(f"Daily analytics aggregated for {today.date()}: DAU={dau_events}, New={new_users}")
    except Exception as e:
        logger.exception("Failed to aggregate daily analytics: %s", e)


def get_analytics_summary(days: int = 30) -> Dict:
    """Get analytics summary for last N days"""
    try:
        with SessionLocal() as db:
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            # Total users
            total_users = db.query(User).count()
            
            # Active users (last 7 days)
            from sqlalchemy import func
            active_7d = db.query(func.count(func.distinct(UserEvent.user_id))).filter(
                UserEvent.timestamp >= datetime.utcnow() - timedelta(days=7)
            ).scalar() or 0
            
            # Premium users
            premium_users = db.query(Subscription).filter(
                Subscription.tier == "premium",
                Subscription.status == "active",
                (Subscription.end_date.is_(None)) | (Subscription.end_date > datetime.utcnow())
            ).distinct(Subscription.user_id).count()
            
            # Quiz completion rate
            quiz_starts = db.query(UserEvent).filter(
                UserEvent.event_type == "quiz_start",
                UserEvent.timestamp >= cutoff
            ).count()
            quiz_completes = db.query(UserEvent).filter(
                UserEvent.event_type == "quiz_complete",
                UserEvent.timestamp >= cutoff
            ).count()
            completion_rate = (quiz_completes / quiz_starts * 100) if quiz_starts > 0 else 0
            
            # Most popular scenarios
            scenario_events = db.query(UserEvent).filter(
                UserEvent.event_type == "scenario_start",
                UserEvent.timestamp >= cutoff
            ).all()
            scenario_counts = {}
            for event in scenario_events:
                if event.event_data:
                    data = json.loads(event.event_data)
                    scenario_id = data.get("scenario_id", "unknown")
                    scenario_counts[scenario_id] = scenario_counts.get(scenario_id, 0) + 1
            
            most_popular = sorted(scenario_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            
            return {
                "total_users": total_users,
                "active_users_7d": active_7d,
                "premium_users": premium_users,
                "premium_conversion_rate": (premium_users / total_users * 100) if total_users > 0 else 0,
                "quiz_completion_rate": completion_rate,
                "most_popular_scenarios": most_popular,
            }
    except Exception as e:
        logger.exception("Failed to get analytics summary: %s", e)
        return {}


# Quiz content (multilingual, level-based)
QuizQuestion = Dict[str, object]

QUIZ_LEVELS = [1, 2, 3]
LEVEL_REWARD_MULTIPLIER = {1: 10, 2: 20, 3: 30}

QUIZ: Dict[str, Dict[int, List[QuizQuestion]]] = {
    "ru": {
        1: [
            {
                "question": "Какой признак чаще всего указывает на фишинговое письмо?",
                "options": [
                    "A) Обращение по имени и фамилии",
                    "B) Требование срочно перейти по ссылке под угрозой блокировки",
                    "C) Корректный адрес отправителя",
                    "D) Приложенный официальный договор",
                ],
                "answer": 1,
            },
            {
                "question": "Безопасная практика при переводе денег знакомому?",
                "options": [
                    "A) Отправить деньги сразу, чтобы не задерживать человека",
                    "B) Перевести по номеру карты из сообщения",
                    "C) Уточнить запрос по независимому каналу связи",
                    "D) Сохранить реквизиты в заметках на будущее",
                ],
                "answer": 2,
            },
            {
                "question": "Как поступить с подозрительной ссылкой из SMS?",
                "options": [
                    "A) Перейти и ввести данные, если логотип банка верный",
                    "B) Отправить друзьям, чтобы они проверили",
                    "C) Проверить информацию через службу поддержки банка",
                    "D) Перейти со скрытого окна браузера",
                ],
                "answer": 2,
            },
        ],
        2: [
            {
                "question": "Как защитить интернет-банк на новом устройстве?",
                "options": [
                    "A) Сразу войти и сохранить пароль в браузере",
                    "B) Включить биометрию, 2FA и удалить ненужные приложения",
                    "C) Установить APK-файл из неизвестного источника",
                    "D) Отключить PIN-код для ускорения входа",
                ],
                "answer": 1,
            },
            {
                "question": "Что делать при подозрительном push-уведомлении о входе?",
                "options": [
                    "A) Игнорировать, если сумма небольшая",
                    "B) Нажать на уведомление и подтвердить вход",
                    "C) Срочно сменить пароль и связаться с банком",
                    "D) Опубликовать уведомление в соцсетях",
                ],
                "answer": 2,
            },
            {
                "question": "Какой способ хранения резервных кодов 2FA корректный?",
                "options": [
                    "A) Отправить себе по электронной почте",
                    "B) Сохранить в заметках телефона",
                    "C) Хранить в зашифрованном менеджере паролей",
                    "D) Записать на листке и вложить в кошелек",
                ],
                "answer": 2,
            },
        ],
        3: [
            {
                "question": "Как выявить подмену номера (spoofing) при звонке «от банка»?",
                "options": [
                    "A) Проверить последние цифры номера — они всегда совпадают",
                    "B) Отклонить звонок и перезвонить по официальному номеру банка",
                    "C) Попросить оператора назвать ваше отчество",
                    "D) Запросить копию паспорта сотрудника",
                ],
                "answer": 1,
            },
            {
                "question": "После заражения трояном-шифровальщиком на ПК первое действие?",
                "options": [
                    "A) Оплатить выкуп, чтобы восстановить файлы",
                    "B) Подключить внешний диск для копии данных",
                    "C) Немедленно отключить устройство от сети и уведомить IT/банк",
                    "D) Попробовать перезагрузить компьютер",
                ],
                "answer": 2,
            },
            {
                "question": "Как проверить достоверность инвестиционного предложения?",
                "options": [
                    "A) Довериться отзыву в чате инвесторов",
                    "B) Перевести минимальную сумму «для теста»",
                    "C) Проверить лицензию компании на сайте регулятора и консультацию у банка",
                    "D) Согласиться, если обещают доход выше депозита",
                ],
                "answer": 2,
            },
        ],
    },
    "kk": {
        1: [
            {
                "question": "Фишинг хатындағы ең жиі белгі қайсы?",
                "options": [
                    "A) Аты-жөнімен ресми үндеу",
                    "B) Блоктау қатерімен бірге шұғыл әрекет ету талабы",
                    "C) Банктің ресми логотипі",
                    "D) Хат соңында байланыс деректері",
                ],
                "answer": 1,
            },
            {
                "question": "Жеке тұлғаға ақша жіберерде не қауіпсіз?",
                "options": [
                    "A) Қаражатты сұралған картаға бірден аудару",
                    "B) Сөйлеушінің сенімділігіне қарап аудару",
                    "C) Ақпаратты тәуелсіз арна арқылы тексеру",
                    "D) Скриншотты әлеуметтік желіде сұрау",
                ],
                "answer": 2,
            },
            {
                "question": "SMS арқылы келген күмәнді сілтеме?",
                "options": [
                    "A) Логотип дұрыс болса, өту",
                    "B) Достарға жіберу",
                    "C) Банктің ресми қолдауымен тексеру",
                    "D) VPN арқылы өту",
                ],
                "answer": 2,
            },
        ],
        2: [
            {
                "question": "Жаңа телефонда интернет-банкті қалай қорғау керек?",
                "options": [
                    "A) Парольді браузерге сақтау",
                    "B) 2FA қосып, қажетсіз қосымшаларды жою",
                    "C) Қолданбаны үшінші тарап сайтынан орнату",
                    "D) Экран құлпын өшіру",
                ],
                "answer": 1,
            },
            {
                "question": "Күдікті push-хабарламаны алған кезде?",
                "options": [
                    "A) Егер сома аз болса, елемеу",
                    "B) Қабылдап, операцияны растау",
                    "C) Парольді ауыстырып, банкке хабарласу",
                    "D) Мессенджерге жариялау",
                ],
                "answer": 2,
            },
            {
                "question": "2FA резервтік кодтарын сақтау жолы?",
                "options": [
                    "A) Өзіңізге e-mail жіберу",
                    "B) Телефон жазбасында сақтау",
                    "C) Шифрланған пароль менеджерінде сақтау",
                    "D) Әмияндағы қағазға жазу",
                ],
                "answer": 2,
            },
        ],
        3: [
            {
                "question": "Спуфинг қоңырауын қалай тануға болады?",
                "options": [
                    "A) Нөмірдің соңғы цифрларын тексеру жеткілікті",
                    "B) Қоңырауды үзіп, банктің ресми нөміріне қайта қоңырау шалу",
                    "C) Оператордан толық атыңызды айтуын сұрау",
                    "D) Қызметкердің құжаттарын сұрау",
                ],
                "answer": 1,
            },
            {
                "question": "Шифрлайтын троян жұққанда бірінші әрекет?",
                "options": [
                    "A) Файлдарды қайтару үшін ақысын төлеу",
                    "B) Деректерді көшіріп алу үшін флешка қосу",
                    "C) Құрылғыны желіден ажыратып, банк/IT-ге хабарлау",
                    "D) Компьютерді қайта жүктеу",
                ],
                "answer": 2,
            },
            {
                "question": "Инвестициялық ұсыныстың заңдылығын қалай тексеру керек?",
                "options": [
                    "A) Чаттағы пікірге сену",
                    "B) Тест үшін аз сома жіберу",
                    "C) Компания лицензиясын регулятор сайтынан қарап, банкке кеңес алу",
                    "D) Депозиттен жоғары табыс уәде етсе келісу",
                ],
                "answer": 2,
            },
        ],
    },
    "en": {
        1: [
            {
                "question": "Which sign most clearly indicates a phishing email?",
                "options": [
                    "A) Personalized greeting with your full name",
                    "B) Urgent demand to click a link or your account will be blocked",
                    "C) A professional-looking signature",
                    "D) Attachment labeled as invoice",
                ],
                "answer": 1,
            },
            {
                "question": "Safe approach when a friend asks for money online?",
                "options": [
                    "A) Send funds immediately to maintain trust",
                    "B) Transfer to the card number sent in the chat",
                    "C) Verify via an independent channel before sending money",
                    "D) Save the card for future transfers",
                ],
                "answer": 2,
            },
            {
                "question": "Suspicious SMS link received—best action?",
                "options": [
                    "A) Open it if the branding looks genuine",
                    "B) Share with friends to double-check",
                    "C) Contact official bank support to verify",
                    "D) Visit it in incognito mode",
                ],
                "answer": 2,
            },
        ],
        2: [
            {
                "question": "How do you secure mobile banking on a new phone?",
                "options": [
                    "A) Enable auto-fill passwords in the browser",
                    "B) Activate biometrics, 2FA, and remove risky apps",
                    "C) Install the APK from a third-party website",
                    "D) Disable screen lock for quicker access",
                ],
                "answer": 1,
            },
            {
                "question": "Response to an unexpected login push notification?",
                "options": [
                    "A) Ignore if the transaction amount is small",
                    "B) Tap approve to prevent account freeze",
                    "C) Change password immediately and call the bank",
                    "D) Post it in a community forum",
                ],
                "answer": 2,
            },
            {
                "question": "Proper storage for emergency 2FA backup codes?",
                "options": [
                    "A) Email them to yourself",
                    "B) Keep them in phone notes",
                    "C) Store inside an encrypted password manager",
                    "D) Print and carry in your wallet",
                ],
                "answer": 2,
            },
        ],
        3: [
            {
                "question": "Detecting caller ID spoofing from a ‘bank’ caller?",
                "options": [
                    "A) Genuine calls always match the bank number exactly",
                    "B) Hang up and dial the number printed on your bank card",
                    "C) Ask the caller to tell your middle name",
                    "D) Request a badge photo",
                ],
                "answer": 1,
            },
            {
                "question": "First step after ransomware infects your PC?",
                "options": [
                    "A) Pay the ransom to get files back quickly",
                    "B) Connect a drive to back up remaining data",
                    "C) Disconnect from networks and alert IT/bank",
                    "D) Run a quick system restart",
                ],
                "answer": 2,
            },
            {
                "question": "Validating a high-return investment pitch?",
                "options": [
                    "A) Trust screenshots shared in a chat",
                    "B) Test by sending a small amount",
                    "C) Verify licenses with the regulator and consult your bank",
                    "D) Agree if returns beat fixed deposits",
                ],
                "answer": 2,
            },
        ],
    },
}

# Conversation states
(
    R_REPORT_DESC,
    R_REPORT_LINK,
    R_REPORT_CONTACT,
    QUIZ_Q,
    BROADCAST_MSG,
) = range(5)


# --- Navigation helpers (simple stack per user) ---
def push_nav(context: ContextTypes.DEFAULT_TYPE, view: dict):
    stk = context.user_data.get("nav_stack", [])
    if not stk:
        stk = [{"view": "main_menu"}]
    if stk and stk[-1] == view:
        context.user_data["nav_stack"] = stk
        return
    stk = stk + [view]
    context.user_data["nav_stack"] = stk


def pop_nav(context: ContextTypes.DEFAULT_TYPE) -> Optional[dict]:
    stk = context.user_data.get("nav_stack", [])
    if not stk:
        return None
    popped = stk.pop()
    context.user_data["nav_stack"] = stk
    return popped


def peek_nav(context: ContextTypes.DEFAULT_TYPE) -> Optional[dict]:
    stk = context.user_data.get("nav_stack", [])
    return stk[-1] if stk else None


# --- UI / Menu helpers ---
def build_main_inline(lang: str = "ru", user_id: int = None):
    # Read coins and premium status
    coins_text = ""
    premium_badge = ""
    if user_id:
        try:
            with SessionLocal() as db:
                u = db.query(User).filter_by(telegram_id=user_id).first()
                if u:
                    coins_text = f" (💰 {u.coins})"
            
            # All features are free - no premium badge needed
        except Exception:
            coins_text = ""

    titles = {
        "ru": {
            "tips": "Советы по безопасности",
            "quiz": "Пройти квиз",
            "report": "Сообщить о мошенничестве",
            "subscribe": "Подписаться на оповещения",
            "scenarios": "Практика сценариев",
            "balance": "💰 Мой баланс",
            "shop": "🛒 Магазин",
            "leaderboard": "🏆 Таблица лидеров",
            "referral": "🎁 Реферальная программа",
            "premium": "📚 Защита от подписок",
            "education": "📚 Защита от подписок",
            "alerts": "🚨 Предупреждения",
            "qr": "📱 Проверить QR",
            "report_scam": "📝 Сообщить о скаме",
            "fund": "💰 Резервный фонд",
        },
        "kk": {
            "tips": "Қауіпсіздік кеңестері",
            "quiz": "Квиз",
            "report": "Алаяқтықты хабарлау",
            "subscribe": "Хабарландыруларға жазылу",
            "scenarios": "Сценариймен тәжірибе",
            "balance": "💰 Балансым",
            "shop": "🛒 Дүкен",
            "leaderboard": "🏆 Кесте",
            "referral": "🎁 Рефералдық бағдарлама",
            "premium": "📚 Защита от подписок",
            "education": "📚 Защита от подписок",
            "alerts": "🚨 Ескертулер",
            "qr": "📱 QR тексеру",
            "report_scam": "📝 Алаяқтықты хабарлау",
            "fund": "💰 Резервтік қор",
        },
        "en": {
            "tips": "Security tips",
            "quiz": "Take quiz",
            "report": "Report fraud",
            "subscribe": "Subscribe alerts",
            "scenarios": "Practice scenarios",
            "balance": "💰 My balance",
            "shop": "🛒 Shop",
            "leaderboard": "🏆 Leaderboard",
            "referral": "🎁 Referral Program",
            "premium": "📚 Защита от подписок",
            "education": "📚 Защита от подписок",
            "alerts": "🚨 Alerts",
            "qr": "📱 Check QR",
            "report_scam": "📝 Report Scam",
            "fund": "💰 Emergency Fund",
        },
    }
    L = titles.get(lang, titles["ru"])
    kb = [
        [InlineKeyboardButton(L["tips"], callback_data="tips")],
        [
            InlineKeyboardButton(L["quiz"], callback_data="quiz_start"),
            InlineKeyboardButton(L["report"], callback_data="report_start"),
        ],
        [
            InlineKeyboardButton(L["alerts"], callback_data="alerts"),
            InlineKeyboardButton(L["qr"], callback_data="qr"),
        ],
        [InlineKeyboardButton(L["balance"] + coins_text, callback_data="balance")],
        [
            InlineKeyboardButton(L["shop"], callback_data="shop"),
            InlineKeyboardButton(L["leaderboard"], callback_data="leaderboard"),
        ],
        [
            InlineKeyboardButton(L["education"], callback_data="education"),
            InlineKeyboardButton(L["referral"], callback_data="referral"),
        ],
        [
            InlineKeyboardButton(L["report_scam"], callback_data="report_scam"),
            InlineKeyboardButton(L["fund"], callback_data="fund"),
        ],
        [InlineKeyboardButton(L["subscribe"], callback_data="subscribe")],
        [InlineKeyboardButton(L["scenarios"], callback_data="scenario_start")],
    ]
    return InlineKeyboardMarkup(kb)


async def safe_edit_message(query, text: str, reply_markup=None, max_retries=2):
    for attempt in range(max_retries):
        try:
            await query.edit_message_text(text, reply_markup=reply_markup)
            return
        except Exception as e:
            if "message is not modified" in str(e).lower():
                return
            logger.debug("Edit attempt %s failed: %s", attempt, e)
            await asyncio.sleep(0.1)
    # fallback
    try:
        await query.message.reply_text(text, reply_markup=reply_markup)
    except Exception as e:
        logger.error("Failed to send fallback message: %s", e)


# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    tg_id = user.id
    is_new_user = False
    
    # Check for referral code or bank license key in command args
    referral_code = None
    bank_license_key = None
    if update.message and update.message.text:
        args = update.message.text.split()
        if len(args) > 1:
            arg = args[1]
            if arg.startswith("bank_"):
                # Bank license key registration
                bank_license_key = arg.replace("bank_", "")
            else:
                referral_code = arg.upper()
    
    try:
        with SessionLocal() as db:
            db_user = db.query(User).filter_by(telegram_id=tg_id).first()
            if not db_user:
                is_new_user = True
                db_user = User(
                    telegram_id=tg_id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    subscribed=False,
                    coins=0,
                    quizzes_passed=0,
                    max_unlocked_level=1,
                    scenario_score=0,
                    scenario_badges="",
                )
                db.add(db_user)
                db.commit()
                
                # Process referral if new user
                if referral_code:
                    result = process_referral(referral_code, tg_id)
                    if result.get("success"):
                        track_user_event(tg_id, "referral_signup", {"referral_code": referral_code})
                
                # Process bank registration if license key provided
                if bank_license_key:
                    bank = db.query(BankPartner).filter_by(license_key=bank_license_key).first()
                    if bank and bank.status == "active":
                        register_bank_client(bank.id, tg_id)
                        track_user_event(tg_id, "bank_client_registered", {"bank_id": bank.id, "bank_name": bank.bank_name})
                
                # Track new user event
                track_user_event(tg_id, "user_signup", {"referral_code": referral_code, "bank_license": bank_license_key})
            else:
                # Track returning user
                track_user_event(tg_id, "user_return")
    except Exception as e:
        logger.exception("DB error on start: %s", e)

    lang_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Русский", callback_data="set_lang_ru")],
        [InlineKeyboardButton("Қазақша", callback_data="set_lang_kk")],
        [InlineKeyboardButton("English", callback_data="set_lang_en")],
    ])
    
    # Get white-label config if user is bank client
    bank_config = {}
    try:
        with SessionLocal() as db:
            user = db.query(User).filter_by(telegram_id=tg_id).first()
            if user and user.bank_partner_id:
                bank_config = get_white_label_config(user.bank_partner_id)
    except Exception as e:
        logger.exception("Failed to get bank config: %s", e)
    
    # Customize welcome message if bank config exists
    if bank_config.get("custom_welcome_message"):
        welcome_msg = bank_config["custom_welcome_message"]
    else:
        welcome_msg = "Выберите язык / Тілді таңдаңыз / Choose language:"
    
    if is_new_user and referral_code:
        welcome_msg += "\n\n🎁 Referral code applied! You'll get 7 days premium trial after your first quiz!"
    elif is_new_user and bank_license_key:
        welcome_msg += "\n\n🏦 Вы зарегистрированы через банк-партнер!"
    
    await safe_reply(update.message, welcome_msg, lang_kb)


async def set_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id

    if q.data == "set_lang_ru":
        set_lang(user_id, "ru")
    elif q.data == "set_lang_kk":
        set_lang(user_id, "kk")
    elif q.data == "set_lang_en":
        set_lang(user_id, "en")

    lang = get_lang(user_id)
    markup = build_main_inline(lang, user_id)
    # reset navigation stack and push main menu
    context.user_data["nav_stack"] = [{"view": "main_menu"}]
    await q.message.edit_text({"ru": "Главное меню", "kk": "Басты мәзір", "en": "Main menu"}[lang], reply_markup=markup)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "/start — запуск и регистрация\n"
        "/tips — советы по безопасности\n"
        "/quiz — пройти короткий тест по безопасности\n"
        "/report — сообщить о мошенничестве\n"
        "/subscribe — подписаться на оповещения\n"
        "/unsubscribe — отписаться\n"
        "/myinfo — информация о вас в системе\n"
    )
    await safe_reply(update.message, text)


# Root callback router
async def callback_root(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    # Push current view to stack so back returns here
    push_nav(context, {"view": data})

    if data == "tips":
        await send_tips(query, context)
    elif data == "quiz_start":
        await start_quiz(query, context)
    elif data == "report_start":
        await report_start_via_callback(query, context)
    elif data == "subscribe":
        await subscribe_user(query, context)
    elif data == "unsubscribe":
        await unsubscribe_user(query, context)
    elif data == "scenario_start":
        await start_scenario_from_callback(query, context)
    elif data == "balance":
        await show_balance(query, context)
    elif data == "shop":
        await show_shop(query, context)
    elif data == "leaderboard":
        await leaderboard_callback(query, context)
    elif data == "referral":
        await referral_callback(query, context)
    elif data == "premium" or data == "education":
        await education_callback(query, context)
    elif data == "alerts":
        # Use query.message directly and create a simple handler
        await query.answer()
        user_id = query.from_user.id
        lang = get_lang(user_id)
        city = get_user_city(user_id)
        
        alerts = get_active_scam_alerts(city=city, limit=5)
        
        if not alerts:
            text = {
                "ru": "✅ Нет активных предупреждений о мошенничестве в вашем городе.",
                "kk": "✅ Қалаңызда алаяқтық туралы белсенді ескертулер жоқ.",
                "en": "✅ No active scam alerts in your city.",
            }[lang]
        else:
            lines = [{
                "ru": f"🚨 Активные предупреждения ({len(alerts)}):",
                "kk": f"🚨 Белсенді ескертулер ({len(alerts)}):",
                "en": f"🚨 Active Alerts ({len(alerts)}):",
            }[lang]]
            
            for alert in alerts:
                severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(alert["severity"], "⚪")
                lines.append(f"\n{severity_emoji} {alert['title']}")
                lines.append(f"   {alert['description'][:100]}...")
                if alert["city"]:
                    lines.append(f"   📍 {alert['city']}")
            
            text = "\n".join(lines)
        
        await safe_edit_message_or_send(query, text)
    elif data == "qr":
        await query.answer()
        user_id = query.from_user.id
        lang = get_lang(user_id)
        
        text = {
            "ru": "📱 Отправьте QR код для проверки безопасности.\n\nПросто отправьте текст или ссылку из QR кода.",
            "kk": "📱 Қауіпсіздігін тексеру үшін QR код жіберіңіз.\n\nQR кодтың мәтінін немесе сілтемесін жіберіңіз.",
            "en": "📱 Send QR code to check safety.\n\nJust send the text or link from the QR code.",
        }[lang]
        
        await safe_edit_message_or_send(query, text)
        context.user_data["waiting_qr"] = True
    elif data == "report_scam":
        await query.answer()
        user_id = query.from_user.id
        lang = get_lang(user_id)
        
        text = {
            "ru": "📝 Сообщить о мошенничестве (анонимно)\n\nВыберите тип:",
            "kk": "📝 Алаяқтық туралы хабарлау (анонимдік)\n\nТүрін таңдаңыз:",
            "en": "📝 Report a scam (anonymous)\n\nChoose type:",
        }[lang]
        
        buttons = [
            [InlineKeyboardButton("📱 SMS/Фишинг", callback_data="report_type_phishing")],
            [InlineKeyboardButton("☎️ Звонок", callback_data="report_type_call")],
            [InlineKeyboardButton("💰 Инвестиции", callback_data="report_type_investment")],
            [InlineKeyboardButton("💼 Работа", callback_data="report_type_job")],
            [InlineKeyboardButton("💳 Займ", callback_data="report_type_loan")],
            [InlineKeyboardButton({"ru": "Назад", "kk": "Артқа", "en": "Back"}[lang], callback_data="back")],
        ]
        markup = InlineKeyboardMarkup(buttons)
        await safe_edit_message_or_send(query, text, markup)
        context.user_data["report_flow"] = "type_selected"
    elif data == "fund":
        await query.answer()
        user_id = query.from_user.id
        lang = get_lang(user_id)
        
        fund = get_or_create_emergency_fund(user_id)
        
        target = fund["target_amount"]
        current = fund["current_amount"]
        expenses = fund["monthly_expenses"]
        months = fund["months_covered"]
        
        progress = (current / target * 100) if target > 0 else 0
        progress_bar = "█" * int(progress / 10) + "░" * (10 - int(progress / 10))
        
        text = {
            "ru": (
                f"💰 Резервный фонд\n\n"
                f"Цель: {target:,}₸\n"
                f"Текущий: {current:,}₸\n"
                f"Месячные расходы: {expenses:,}₸\n"
                f"Покрытие: {months} месяцев\n\n"
                f"Прогресс: {progress:.0f}%\n{progress_bar}\n\n"
                f"💡 Рекомендуется иметь резерв на 3-6 месяцев расходов."
            ),
            "kk": (
                f"💰 Резервтік қор\n\n"
                f"Мақсат: {target:,}₸\n"
                f"Қазіргі: {current:,}₸\n"
                f"Айлық шығыстар: {expenses:,}₸\n"
                f"Қамту: {months} ай\n\n"
                f"Прогресс: {progress:.0f}%\n{progress_bar}\n\n"
                f"💡 3-6 айлық шығыстарға резерв қалдыру ұсынылады."
            ),
            "en": (
                f"💰 Emergency Fund\n\n"
                f"Target: {target:,}₸\n"
                f"Current: {current:,}₸\n"
                f"Monthly expenses: {expenses:,}₸\n"
                f"Coverage: {months} months\n\n"
                f"Progress: {progress:.0f}%\n{progress_bar}\n\n"
                f"💡 Recommended: 3-6 months of expenses."
            ),
        }[lang]
        
        buttons = [
            [InlineKeyboardButton({"ru": "✏️ Редактировать", "kk": "✏️ Өңдеу", "en": "✏️ Edit"}[lang], callback_data="fund_edit")],
            [InlineKeyboardButton({"ru": "Назад", "kk": "Артқа", "en": "Back"}[lang], callback_data="back")],
        ]
        markup = InlineKeyboardMarkup(buttons)
        await safe_edit_message_or_send(query, text, markup)
    else:
        await safe_reply(query.message, "Неопознанная команда.")


# Tips
async def send_tips(source, context: ContextTypes.DEFAULT_TYPE):
    user_id = source.from_user.id
    lang = get_lang(user_id)

    tips_content = {
        "ru": [
            "Не переходите по ссылкам из сомнительных SMS/письмах. Проверяйте URL у официального сайта банка.",
            "Никому не сообщайте код из SMS и одноразовые пароли.",
            "Используйте менеджер паролей и включите 2FA там, где возможно.",
            "Проверяйте реквизиты получателя перед переводом, перепроверяйте по независимым каналам.",
            "При сомнении — связывайтесь с официальной поддержкой банка через сайт/приложение.",
            "Создавайте уникальные пароли для каждого аккаунта длиной не менее 12 символов.",
            "Используйте комбинацию букв, цифр и специальных символов в паролях.",
            "Никогда не используйте личную информацию (дата рождения, имя) в паролях.",
            "Включайте двухфакторную аутентификацию (2FA) на всех важных аккаунтах.",
            "Регулярно обновляйте пароли для критичных сервисов (банк, почта) каждые 3-6 месяцев.",
            "Не публикуйте в соцсетях информацию о поездках, покупках и финансовых операциях.",
            "Ограничьте видимость профиля в социальных сетях — используйте приватные настройки.",
            "Не принимайте запросы на дружбу от незнакомых людей в финансовых приложениях.",
            "Избегайте публичного WiFi для банковских операций — используйте мобильный интернет или VPN.",
            "Отключайте автоматическое подключение к открытым WiFi сетям на смартфоне.",
            "Проверяйте сертификат безопасности сайта (HTTPS) перед вводом данных.",
            "Используйте официальные приложения банка из App Store или Google Play.",
            "Не храните пароли и PIN-коды в заметках на телефоне или в облаке без шифрования.",
            "Регулярно проверяйте активные устройства и сессии в банковских приложениях.",
            "Удаляйте неиспользуемые приложения с доступом к финансовым данным.",
            "Не переводите деньги незнакомым людям по просьбе в мессенджерах — всегда проверяйте личность.",
            "Будьте осторожны с криптовалютными инвестициями — проверяйте легитимность платформ.",
            "Используйте аппаратные кошельки для хранения больших сумм криптовалюты.",
            "Никогда не делитесь seed-фразой криптокошелька ни с кем и нигде.",
            "Регулярно проверяйте кредитную историю на предмет несанкционированных операций.",
            "Замораживайте кредитные отчеты при подозрении на утечку данных.",
            "Уничтожайте документы с персональными данными перед выбрасыванием (шредер).",
            "Не отвечайте на звонки с незнакомых номеров, требующих личные данные.",
        ],
        "kk": [
            "Күдікті SMS/хаттардағы сілтемелерді ашпаңыз. Банктің ресми сайтын тексеріңіз.",
            "SMS кодын және бір реттік парольді ешкімге айтпаңыз.",
            "Пароль менеджерін қолданыңыз және 2FA іске қосыңыз.",
            "Аударымдан бұрын алушыны тәуелсіз арналар арқылы тексеріңіз.",
            "Күмәнданған жағдайда — банктің ресми қолдауымен байланысыңыз.",
            "Әр аккаунт үшін кемінде 12 таңбадан тұратын бірегей парольдер құрыңыз.",
            "Парольдерде әріптер, сандар және арнайы таңбалардың комбинациясын пайдаланыңыз.",
            "Парольдерде жеке ақпаратты (туған күні, аты) ешқашан пайдаланбаңыз.",
            "Барлық маңызды аккаунттарда екі факторлы аутентификацияны (2FA) қосыңыз.",
            "Маңызды сервистер үшін парольдерді 3-6 айда бір рет жаңартыңыз.",
            "Әлеуметтік желілерде саяхат, сатып алу және қаржылық операциялар туралы ақпарат жарияламаңыз.",
            "Әлеуметтік желілердегі профильдің көрінуін шектеңіз — жеке параметрлерді пайдаланыңыз.",
            "Қаржылық қосымшаларда таныс емес адамдардан достау сұрауларын қабылдамаңыз.",
            "Банк операциялары үшін қоғамдық WiFi пайдаланбаңыз — мобильді интернет немесе VPN қолданыңыз.",
            "Смартфонда ашық WiFi желілеріне автоматты қосылуды өшіріңіз.",
            "Деректерді енгізгенге дейін сайттың қауіпсіздік сертификатын (HTTPS) тексеріңіз.",
            "App Store немесе Google Play-ден банктің ресми қосымшаларын пайдаланыңыз.",
            "Телефонда немесе шифрлаусыз бұлтта парольдер мен PIN-кодтарды сақтамаңыз.",
            "Банк қосымшаларында белсенді құрылғылар мен сессияларды үнемі тексеріңіз.",
            "Қаржылық деректерге қол жеткізуі бар пайдаланылмаған қосымшаларды жойыңыз.",
            "Мессенджерлерде таныс емес адамдарға ақша аударумаңыз — әрқашан тұлғаны тексеріңіз.",
            "Криптовалюта инвестицияларымен сақ болыңыз — платформалардың заңдылығын тексеріңіз.",
            "Үлкен сомаларды сақтау үшін криптовалюта аппараттық әмияндарын пайдаланыңыз.",
            "Криптоәмиянның seed-фразасын ешкімге және ешқайда бөліспеңіз.",
            "Рұқсатсыз операцияларды тексеру үшін несие тарихын үнемі тексеріңіз.",
            "Деректердің ағуынан күдіктенген кезде несие есептерін тоқтатыңыз.",
            "Тастамас бұрын жеке деректері бар құжаттарды жойыңыз (шредер).",
            "Жеке деректерді талап ететін таныс емес нөмірлерден қоңырауларға жауап бермеңіз.",
        ],
        "en": [
            "Don't click links from suspicious SMS/emails. Check URL at official bank website.",
            "Never share SMS codes and one-time passwords.",
            "Use password manager and enable 2FA where possible.",
            "Verify recipient details before transfer via independent channels.",
            "When in doubt — contact official bank support via website/app.",
            "Create unique passwords for each account, at least 12 characters long.",
            "Use combination of letters, numbers, and special characters in passwords.",
            "Never use personal information (birthdate, name) in passwords.",
            "Enable two-factor authentication (2FA) on all important accounts.",
            "Regularly update passwords for critical services (bank, email) every 3-6 months.",
            "Don't post information about trips, purchases, and financial transactions on social media.",
            "Limit profile visibility on social networks — use private settings.",
            "Don't accept friend requests from strangers in financial apps.",
            "Avoid public WiFi for banking operations — use mobile internet or VPN.",
            "Disable automatic connection to open WiFi networks on smartphone.",
            "Check website security certificate (HTTPS) before entering data.",
            "Use official bank apps from App Store or Google Play.",
            "Don't store passwords and PIN codes in phone notes or cloud without encryption.",
            "Regularly check active devices and sessions in banking apps.",
            "Delete unused apps with access to financial data.",
            "Don't transfer money to strangers upon request in messengers — always verify identity.",
            "Be cautious with cryptocurrency investments — verify platform legitimacy.",
            "Use hardware wallets for storing large amounts of cryptocurrency.",
            "Never share crypto wallet seed phrase with anyone or anywhere.",
            "Regularly check credit history for unauthorized transactions.",
            "Freeze credit reports when suspecting data breach.",
            "Destroy documents with personal data before disposal (shredder).",
            "Don't answer calls from unknown numbers requesting personal data.",
        ],
    }

    tips = tips_content.get(lang, tips_content["ru"])
    title = {"ru": "Советы по финансовой безопасности:", "kk": "Қаржылық қауіпсіздік кеңестері:", "en": "Financial security tips:"}[lang]
    text = title + "\n\n" + "\n\n".join(f"- {t}" for t in tips)

    back_button = InlineKeyboardMarkup([[InlineKeyboardButton({"ru": "Назад", "kk": "Артқа", "en": "Back"}[lang], callback_data="back")]])
    await safe_edit_message_or_send(source, text, back_button)


async def safe_edit_message_or_send(source, text, markup=None):
    # Helper to either edit (for callback_query) or send (for commands)
    if hasattr(source, "edit_message_text"):
        current_message = getattr(source, "message", None)
        if current_message is not None:
            current_text = getattr(current_message, "text", None)
            current_markup = getattr(current_message, "reply_markup", None)
            markup_same = False
            if markup is None and current_markup is None:
                markup_same = True
            elif markup is not None and current_markup is not None:
                try:
                    markup_same = markup.to_dict() == current_markup.to_dict()
                except Exception:
                    markup_same = False
            if current_text == text and markup_same:
                return
        try:
            await source.edit_message_text(text, reply_markup=markup)
            return
        except Exception as e:
            logger.warning("Edit via callback failed: %s", e)
            try:
                await source.message.reply_text(text, reply_markup=markup)
                return
            except Exception as e:
                logger.exception("Fallback reply failed: %s", e)
    else:
        try:
            await source.reply_text(text, reply_markup=markup)
        except Exception as e:
            logger.exception("Failed to send message: %s", e)


async def safe_reply(message, text, markup=None):
    try:
        await message.reply_text(text, reply_markup=markup)
    except Exception as e:
        logger.exception("Failed to reply to user: %s", e)


async def send_typing_action(context: ContextTypes.DEFAULT_TYPE, chat_id: int, duration: float = 1.2):
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except Exception as e:
        logger.debug("Failed to send typing action: %s", e)
    await asyncio.sleep(duration)


def render_progress_bar(progress: float) -> str:
    pct = max(0.0, min(progress, 1.0))
    total_blocks = 10
    filled = int(round(pct * total_blocks))
    empty = max(0, total_blocks - filled)
    return f"{int(pct * 100)}% [{'=' * filled}{'.' * empty}]"


def parse_badges(badge_str: str) -> List[str]:
    if not badge_str:
        return []
    return [badge.strip() for badge in badge_str.split(",") if badge.strip()]


def add_badge(badge_str: str, badge: str) -> str:
    badges = set(parse_badges(badge_str))
    if badge:
        badges.add(badge)
    return ",".join(sorted(badges))


async def grant_scenario_rewards(user_id: int, reward: int, badge: Optional[str]) -> Dict[str, Optional[object]]:
    ensure_user_record(user_id)
    try:
        with SessionLocal() as db:
            db_user = db.query(User).filter_by(telegram_id=user_id).first()
            if not db_user:
                return {"coins": 0, "badge": None, "score": 0, "badges": []}
            original_badges = db_user.scenario_badges or ""
            updated_badges = add_badge(original_badges, badge) if badge else original_badges
            badge_unlocked = updated_badges != original_badges
            if reward > 0:
                db_user.coins = (db_user.coins or 0) + reward
                db_user.scenario_score = (db_user.scenario_score or 0) + reward
            if badge_unlocked:
                db_user.scenario_badges = updated_badges
            db.commit()
            
            # Update leaderboard after scenario completion
            update_leaderboard(user_id)
            
            # Track scenario completion
            track_user_event(user_id, "scenario_complete", {
                "scenario_score": db_user.scenario_score or 0,
                "reward": reward,
                "badge": badge if badge_unlocked else None,
            })
            
            return {
                "coins": reward,
                "badge": badge if badge_unlocked else None,
                "score": db_user.scenario_score or 0,
                "badges": parse_badges(db_user.scenario_badges or ""),
            }
    except Exception as e:
        logger.exception("Failed to grant scenario rewards: %s", e)
    return {"coins": 0, "badge": None, "score": 0, "badges": []}


# SUBSCRIBE/UNSUBSCRIBE
async def subscribe_user(source, context: ContextTypes.DEFAULT_TYPE):
    user = source.from_user
    lang = get_lang(user.id)

    try:
        with SessionLocal() as db:
            db_user = db.query(User).filter_by(telegram_id=user.id).first()
            if not db_user:
                db_user = User(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    subscribed=True,
                    coins=0,
                    quizzes_passed=0,
                    max_unlocked_level=1,
                    scenario_score=0,
                    scenario_badges="",
                )
                db.add(db_user)
            else:
                db_user.subscribed = True
            db.commit()
    except Exception as e:
        logger.exception("DB subscribe error: %s", e)

    text = {"ru": "Подписка оформлена. Вы будете получать оповещения.", "kk": "Жазылым рәсімделді. Хабарландырулар аласыз.", "en": "Subscription confirmed. You will receive alerts."}[lang]
    back_button = InlineKeyboardMarkup([[InlineKeyboardButton({"ru": "Назад", "kk": "Артқа", "en": "Back"}[lang], callback_data="back")]])
    await safe_edit_message_or_send(source, text, back_button)


async def unsubscribe_user(source, context: ContextTypes.DEFAULT_TYPE):
    user = source.from_user
    lang = get_lang(user.id)
    try:
        with SessionLocal() as db:
            db_user = db.query(User).filter_by(telegram_id=user.id).first()
            if db_user:
                db_user.subscribed = False
                db.commit()
    except Exception as e:
        logger.exception("DB unsubscribe error: %s", e)

    text = {"ru": "Вы отписаны от оповещений.", "kk": "Хабарландырулардан шықтыңыз.", "en": "You unsubscribed from alerts."}[lang]
    back_button = InlineKeyboardMarkup([[InlineKeyboardButton({"ru": "Назад", "kk": "Артқа", "en": "Back"}[lang], callback_data="back")]])
    await safe_edit_message_or_send(source, text, back_button)


# REPORT flow (message-based) - unchanged but with better transitions
async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["report_stage"] = 1
    await safe_reply(update.message, "Опишите проблему кратко (что произошло, сумма, канал связи):")
    return R_REPORT_DESC


async def report_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["report_desc"] = update.message.text.strip()
    context.user_data["report_stage"] = 2
    await safe_reply(update.message, "Если есть ссылка — пришлите её, иначе отправьте 'нет'.")
    return R_REPORT_LINK


async def report_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    link = None if text.lower() in ("нет", "no", "n") else text
    context.user_data["report_link"] = link
    context.user_data["report_stage"] = 3
    await safe_reply(update.message, "Контакт для связи (телефон или email) или 'нет'.")
    return R_REPORT_CONTACT


async def report_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.text.strip()
    link = context.user_data.get("report_link")
    desc = context.user_data.get("report_desc")
    try:
        with SessionLocal() as db:
            rpt = ScamReport(
                telegram_id=update.effective_user.id,
                description=desc,
                link=link,
                contact=None if contact.lower() in ("нет", "no", "n") else contact,
            )
            db.add(rpt)
            db.commit()
    except Exception as e:
        logger.exception("DB report save error: %s", e)
    suspicious = False
    if link:
        suspicious = link_is_suspicious(link)
    reply = "Сообщение принято. Спасибо."
    if suspicious:
        reply += " Присланная ссылка выглядит подозрительно — избегайте перехода по ней."
    await safe_reply(update.message, reply)

    # notify admins
    admin_msg = (
        f"Новый отчёт о мошенничестве от @{update.effective_user.username or update.effective_user.id}:\n\n"
        f"{desc}\n\nLink: {link or 'нет'}\nContact: {contact or 'нет'}"
    )
    for aid in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=aid, text=admin_msg)
        except Exception as e:
            logger.warning("Не удалось отправить админу %s: %s", aid, e)
    # cleanup
    context.user_data.pop("report_stage", None)
    context.user_data.pop("report_desc", None)
    context.user_data.pop("report_link", None)
    return ConversationHandler.END


async def cancel_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(update.message, "Отмена.")
    return ConversationHandler.END


# QUIZ flow - improved and bugfixed
async def start_quiz(source, context):
    user = source.from_user if hasattr(source, "from_user") else (source.effective_user if hasattr(source, "effective_user") else None)
    if user:
        track_user_event(user.id, "quiz_start")
    await present_quiz_levels(source, context)
    return QUIZ_Q


async def quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await present_quiz_levels(update, context)
    return QUIZ_Q


async def present_quiz_levels(source, context: ContextTypes.DEFAULT_TYPE, push: bool = True):
    user = None
    if hasattr(source, "from_user"):
        user = source.from_user
    elif isinstance(source, Update):
        user = source.effective_user
    elif hasattr(source, "effective_user"):
        user = source.effective_user
    if not user:
        logger.error("present_quiz_levels: unable to determine user")
        return

    user_id = user.id
    lang = get_lang(user_id)
    ensure_user_record(user_id, getattr(user, "username", None), getattr(user, "first_name", None), getattr(user, "last_name", None))

    try:
        with SessionLocal() as db:
            db_user = db.query(User).filter_by(telegram_id=user_id).first()
            max_unlocked = db_user.max_unlocked_level if db_user and db_user.max_unlocked_level else 1
    except Exception as e:
        logger.exception("Failed to load quiz levels: %s", e)
        max_unlocked = 1

    lang_quiz = QUIZ.get(lang) or QUIZ["ru"]
    headers = {
        "ru": "Выберите уровень сложности:",
        "kk": "Қиындық деңгейін таңдаңыз:",
        "en": "Choose difficulty level:",
    }
    reward_hint = {
        "ru": "Награда за правильный ответ",
        "kk": "Дұрыс жауап үшін сыйақы",
        "en": "Reward per correct answer",
    }
    level_titles = {
        "ru": "Уровень",
        "kk": "Деңгей",
        "en": "Level",
    }
    locked_hint = {
        "ru": "🔒 — откройте в магазине",
        "kk": "🔒 — дүкеннен ашыңыз",
        "en": "🔒 — unlock in the shop",
    }

    lines = [headers.get(lang, headers["ru"])]
    for level in QUIZ_LEVELS:
        status = "✅" if level <= max_unlocked else "🔒"
        question_count = len(lang_quiz.get(level, []))
        # Base reward: 10 coins per quiz + 5 bonus for perfect score
        reward_text = {
            "ru": f"+10 (+5 за идеальный результат)",
            "kk": f"+10 (+5 тамаша нәтиже үшін)",
            "en": f"+10 (+5 bonus for perfect score)",
        }[lang]
        lines.append(f"{status} {level_titles.get(lang, 'Level')} {level}: {question_count} • {reward_hint.get(lang, 'Reward')}: {reward_text}")

    lines.append(locked_hint.get(lang, locked_hint["ru"]))
    text = "\n".join(lines)

    buttons = []
    for level in QUIZ_LEVELS:
        status = "✅" if level <= max_unlocked else "🔒"
        label = {
            "ru": f"{status} Уровень {level}",
            "kk": f"{status} {level}-деңгей",
            "en": f"{status} Level {level}",
        }[lang]
        if level <= max_unlocked:
            buttons.append([InlineKeyboardButton(label, callback_data=f"quiz_level|{level}")])
        else:
            buttons.append([InlineKeyboardButton(label, callback_data=f"quiz_locked|{level}")])

    buttons.append([InlineKeyboardButton({"ru": "Назад", "kk": "Артқа", "en": "Back"}[lang], callback_data="back")])
    markup = InlineKeyboardMarkup(buttons)

    if push:
        push_nav(context, {"view": "quiz_levels"})
    await safe_edit_message_or_send(source, text, markup)


async def send_quiz_question(user_or_query, context: ContextTypes.DEFAULT_TYPE):
    qi = context.user_data.get("quiz_qi", 0)
    user_id = None
    if hasattr(user_or_query, "from_user"):
        user_id = user_or_query.from_user.id
    elif hasattr(user_or_query, "id"):
        user_id = user_or_query.id
    elif isinstance(user_or_query, Update):
        user_id = user_or_query.effective_user.id
    if user_id is None:
        logger.error("send_quiz_question: unknown user")
        return ConversationHandler.END

    lang = get_lang(user_id)
    level = context.user_data.get("quiz_level", 1)
    lang_quiz = QUIZ.get(lang) or QUIZ["ru"]
    quiz_questions = lang_quiz.get(level, [])

    if not quiz_questions:
        await safe_edit_message_or_send(
            user_or_query,
            {
                "ru": "Для выбранного уровня пока нет вопросов.",
                "kk": "Таңдалған деңгейге әзірге сұрақтар жоқ.",
                "en": "No questions available for this level yet.",
            }[lang],
        )
        return ConversationHandler.END

    if qi >= len(quiz_questions):
        await finish_quiz(user_or_query, context)
        return ConversationHandler.END

    question = quiz_questions[qi]
    total = len(quiz_questions)

    headers = {
        "ru": f"Уровень {level} · Вопрос {qi + 1}/{total}",
        "kk": f"{level}-деңгей · Сұрақ {qi + 1}/{total}",
        "en": f"Level {level} · Question {qi + 1}/{total}",
    }
    text = (
        headers.get(lang, headers["ru"])
        + "\n\n"
        + question.get("question", "")
        + "\n\n"
        + "\n".join(question["options"])
    )

    buttons = [
        [InlineKeyboardButton(chr(ord("A") + i), callback_data=f"quiz_ans:{i}")]
        for i in range(len(question["options"]))
    ]
    buttons.append([InlineKeyboardButton({"ru": "Назад к уровням", "kk": "Деңгейлерге оралу", "en": "Back to levels"}[lang], callback_data="quiz_back_levels")])
    kb = InlineKeyboardMarkup(buttons)

    push_nav(context, {"view": f"quiz_level_{level}"})
    await safe_edit_message_or_send(user_or_query, text, kb)


async def quiz_answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    m = re.match(r"quiz_ans:(\d+)", data)
    if not m:
        await safe_reply(query.message, "Неверный ответ.")
        return QUIZ_Q

    ans = int(m.group(1))
    qi = context.user_data.get("quiz_qi", 0)
    user_id = query.from_user.id
    lang = get_lang(user_id)
    level = context.user_data.get("quiz_level", 1)
    lang_quiz = QUIZ.get(lang) or QUIZ["ru"]
    quiz_questions = lang_quiz.get(level, [])

    if not quiz_questions:
        await safe_edit_message_or_send(
            query,
            {
                "ru": "Вопросы не найдены. Попробуйте выбрать уровень ещё раз.",
                "kk": "Сұрақтар табылмады. Деңгейді қайта таңдаңыз.",
                "en": "Questions not found. Please reselect the level.",
            }[lang],
        )
        return ConversationHandler.END

    if qi >= len(quiz_questions):
        return ConversationHandler.END

    correct = quiz_questions[qi]["answer"]

    if ans == correct:
        context.user_data["quiz_correct"] = context.user_data.get("quiz_correct", 0) + 1
        feedback = {
            "ru": "✅ Правильно!",
            "kk": "✅ Дұрыс!",
            "en": "✅ Correct!",
        }[lang]
        await safe_edit_message_or_send(query, feedback)
    else:
        feedback = {"ru": "❌ Неправильно", "kk": "❌ Дұрыс емес", "en": "❌ Incorrect"}[lang]
        await safe_edit_message_or_send(query, feedback)

    context.user_data["quiz_qi"] = qi + 1
    await asyncio.sleep(0.5)

    if context.user_data["quiz_qi"] < len(quiz_questions):
        await send_quiz_question(query, context)
        return QUIZ_Q
    else:
        await finish_quiz(query, context, callback_query=query)
        return ConversationHandler.END


async def quiz_level_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    level_raw = query.data.split("|")[1]
    try:
        level = int(level_raw)
    except ValueError:
        await query.answer()
        await safe_edit_message_or_send(query, "Ошибка выбора уровня.")
        return

    user_id = query.from_user.id
    lang = get_lang(user_id)

    if level not in QUIZ_LEVELS:
        await query.answer()
        await safe_edit_message_or_send(
            query,
            {"ru": "Такого уровня нет.", "kk": "Мұндай деңгей жоқ.", "en": "Level not available."}[lang],
        )
        return

    try:
        with SessionLocal() as db:
            db_user = db.query(User).filter_by(telegram_id=user_id).first()
            max_unlocked = db_user.max_unlocked_level if db_user and db_user.max_unlocked_level else 1
    except Exception as e:
        logger.exception("Failed to verify level access: %s", e)
        max_unlocked = 1

    # All quiz levels are free - no premium check needed
    
    if level > max_unlocked:
        await query.answer(
            {
                "ru": f"Уровень {level} откроется после 100% прохождения текущего уровня.",
                "kk": f"{level}-деңгей ағымдағы деңгейді 100% өткен соң ашылады.",
                "en": f"Level {level} unlocks after a 100% score on your current level.",
            }[lang],
            show_alert=True,
        )
        return

    context.user_data["quiz_level"] = level
    context.user_data["quiz_qi"] = 0
    context.user_data["quiz_correct"] = 0
    
    # Track quiz level start
    track_user_event(user_id, "quiz_level_start", {"level": level})

    await send_quiz_question(query, context)


async def quiz_locked_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    level_raw = query.data.split("|")[1]
    try:
        level = int(level_raw)
    except ValueError:
        await query.answer("Неверный уровень.", show_alert=True)
        return
    lang = get_lang(query.from_user.id)
    msg = {
        "ru": f"Уровень {level} откроется после идеального прохождения предыдущего уровня.",
        "kk": f"{level}-деңгей алдыңғы деңгейді мінсіз өткен соң ашылады.",
        "en": f"Level {level} unlocks after a perfect score on the previous level.",
    }[lang]
    await query.answer(msg, show_alert=True)


async def quiz_back_levels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("quiz_level", None)
    context.user_data.pop("quiz_qi", None)
    context.user_data.pop("quiz_correct", None)

    user_id = query.from_user.id
    lang = get_lang(user_id)
    markup = build_main_inline(lang, user_id)
    context.user_data["nav_stack"] = [{"view": "main_menu"}]
    
    # Send NEW message instead of editing to avoid "message not modified" error
    main_menu_text = {"ru": "🏠 Главное меню", "kk": "🏠 Басты мәзір", "en": "🏠 Main menu"}[lang]
    try:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=main_menu_text,
            reply_markup=markup
        )
        # Optionally delete the level selection message
        try:
            await query.message.delete()
        except Exception:
            pass
    except Exception as e:
        logger.exception("Failed to send main menu message: %s", e)


async def quiz_home_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = get_lang(user_id)
    markup = build_main_inline(lang, user_id)
    context.user_data["nav_stack"] = [{"view": "main_menu"}]
    
    # Send NEW message instead of editing to avoid "message not modified" error
    main_menu_text = {"ru": "🏠 Главное меню", "kk": "🏠 Басты мәзір", "en": "🏠 Main menu"}[lang]
    try:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=main_menu_text,
            reply_markup=markup
        )
        # Optionally delete the quiz completion message
        try:
            await query.message.delete()
        except Exception:
            pass
    except Exception as e:
        logger.exception("Failed to send main menu message: %s", e)


async def finish_quiz(source, context: ContextTypes.DEFAULT_TYPE, callback_query=None):
    correct = context.user_data.get("quiz_correct", 0)
    user_id = source.from_user.id if hasattr(source, "from_user") else source.id
    lang = get_lang(user_id)
    level = context.user_data.get("quiz_level", 1)
    lang_quiz = QUIZ.get(lang) or QUIZ["ru"]
    quiz_questions = lang_quiz.get(level, [])
    total = len(quiz_questions)
    passed = correct >= QUIZ_PASS_THRESHOLD
    
    # Base reward: 10 coins per quiz + bonus for perfect scores
    base_reward = 10
    perfect_score_bonus = 5 if total > 0 and correct == total else 0
    earned = base_reward + perfect_score_bonus
    
    telegram_user = None
    if hasattr(source, "from_user"):
        telegram_user = source.from_user
    elif hasattr(source, "effective_user") and source.effective_user:
        telegram_user = source.effective_user
    new_level_unlocked = None
    try:
        with SessionLocal() as db:
            db_user = db.query(User).filter_by(telegram_id=user_id).first()
            if not db_user:
                db_user = User(
                    telegram_id=user_id,
                    username=getattr(telegram_user, "username", None) if telegram_user else None,
                    first_name=getattr(telegram_user, "first_name", None) if telegram_user else None,
                    last_name=getattr(telegram_user, "last_name", None) if telegram_user else None,
                    subscribed=False,
                    coins=0,
                    quizzes_passed=0,
                    max_unlocked_level=1,
                    scenario_score=0,
                    scenario_badges="",
                )
                db.add(db_user)
                db.commit()
                db.refresh(db_user)
            
            # Update coins and quizzes_passed for ALL users (not just new ones)
            current_coins = db_user.coins or 0
            new_coins = current_coins + earned
            db_user.coins = new_coins
            
            if passed:
                current_quizzes = db_user.quizzes_passed or 0
                db_user.quizzes_passed = current_quizzes + 1
            
            # Unlock next level if perfect score
            if total > 0 and correct == total and level < max(QUIZ_LEVELS):
                next_level = level + 1
                current_max = db_user.max_unlocked_level or 1
                if current_max < next_level:
                    db_user.max_unlocked_level = next_level
                    new_level_unlocked = next_level
            
            # Commit all changes to database
                db.commit()
            db.refresh(db_user)  # Refresh to ensure we have latest data
            
            # Log the update for debugging
            logger.info(f"Quiz completed - User {user_id}: coins {current_coins} -> {new_coins}, quizzes_passed: {db_user.quizzes_passed}")
            
            # Update leaderboard
            update_leaderboard(user_id)
            
            # Track quiz completion event
            track_user_event(user_id, "quiz_complete", {
                "level": level,
                "correct": correct,
                "total": total,
                "passed": passed,
                "earned": earned,
                "new_level_unlocked": new_level_unlocked,
            })
            
            # Update bank analytics if user is bank client
            user = db.query(User).filter_by(telegram_id=user_id).first()
            if user and user.bank_partner_id:
                update_bank_analytics(user.bank_partner_id)
    except Exception as e:
        logger.exception("DB update on finish_quiz failed: %s", e)

    reward_message = ""
    if perfect_score_bonus > 0:
        reward_message = {
            "ru": f"💰 Награда: {earned} монет (10 базовых + {perfect_score_bonus} за идеальный результат!)",
            "kk": f"💰 Сыйақы: {earned} тиын (10 базалық + {perfect_score_bonus} тамаша нәтиже үшін!)",
            "en": f"💰 Reward: {earned} coins (10 base + {perfect_score_bonus} bonus for perfect score!)",
        }[lang]
    else:
        reward_message = {
            "ru": f"💰 Награда: {earned} монет",
            "kk": f"💰 Сыйақы: {earned} тиын",
            "en": f"💰 Reward: {earned} coins",
        }[lang]

    text = {
        "ru": (
            f"Уровень {level} завершён.\n"
            f"Правильных ответов: {correct}/{total}.\n"
            f"{'🎉 Квиз пройден!' if passed else '😔 Недостаточно правильных ответов.'}\n\n"
            f"{reward_message}"
        ),
        "kk": (
            f"{level}-деңгей аяқталды.\n"
            f"Дұрыс жауаптар: {correct}/{total}.\n"
            f"{'🎉 Квиз сәтті өтті!' if passed else '😔 Дұрыс жауаптар жеткіліксіз.'}\n\n"
            f"{reward_message}"
        ),
        "en": (
            f"Level {level} completed.\n"
            f"Correct answers: {correct}/{total}.\n"
            f"{'🎉 You passed the quiz!' if passed else '😔 Not enough correct answers.'}\n\n"
            f"{reward_message}"
        ),
    }[lang]

    if new_level_unlocked:
        unlock_note = {
            "ru": f"🔓 Уровень {new_level_unlocked} открыт! Попробуйте новые вопросы.",
            "kk": f"🔓 {new_level_unlocked}-деңгей ашылды! Жаңа сұрақтарды байқап көріңіз.",
            "en": f"🔓 Level {new_level_unlocked} unlocked! Try the new questions.",
        }[lang]
        text += "\n\n" + unlock_note

    home_button = InlineKeyboardMarkup([
        [InlineKeyboardButton({"ru": "🏠 Домой", "kk": "🏠 Бас мәзір", "en": "🏠 Home"}[lang], callback_data="quiz_home")]
    ])

    target = callback_query or source
    if hasattr(target, "edit_message_text") or hasattr(target, "message") or hasattr(target, "reply_text"):
        await safe_edit_message_or_send(target, text, home_button)
    else:
        try:
            await context.bot.send_message(chat_id=user_id, text=text, reply_markup=home_button)
        except Exception as e:
            logger.exception("Failed to send quiz completion message: %s", e)

    context.user_data.pop("quiz_qi", None)
    context.user_data.pop("quiz_correct", None)
    context.user_data.pop("quiz_level", None)



def resolve_scenario_language(lang: str) -> str:
    candidate = "kz" if lang == "kk" else lang
    return candidate if candidate in SCENARIOS else "ru"


def get_scenario_catalog(lang: str) -> Tuple[Dict[str, dict], str]:
    scenario_lang = resolve_scenario_language(lang)
    return SCENARIOS.get(scenario_lang, {}), scenario_lang


async def start_scenario_from_callback(query_or_update, context: ContextTypes.DEFAULT_TYPE, push_to_nav: bool = True):
    query = query_or_update if hasattr(query_or_update, "answer") else None
    if query:
        await query.answer()
        chat_id = query.message.chat_id
        user_id = query.from_user.id
        is_callback = True
    else:
        chat_id = query_or_update.effective_chat.id
        user_id = query_or_update.effective_user.id
        is_callback = False

    lang = get_lang(user_id)
    catalog, scenario_lang = get_scenario_catalog(lang)

    ensure_user_record(user_id)
    badges: List[str] = []
    score = 0
    try:
        with SessionLocal() as db:
            db_user = db.query(User).filter_by(telegram_id=user_id).first()
            if db_user:
                badges = parse_badges(db_user.scenario_badges or "")
                score = db_user.scenario_score or 0
    except Exception as e:
        logger.exception("Failed to get scenario stats: %s", e)

    if not catalog:
        text = {"ru": "Сценарии недоступны.", "kk": "Сценарий жоқ.", "en": "Scenarios unavailable."}[lang]
        if is_callback:
            await safe_edit_message_or_send(query, text)
        else:
            try:
                await context.bot.send_message(chat_id=chat_id, text=text)
            except Exception as e:
                logger.exception("Failed to send scenario unavailable message: %s", e)
        return

    status_lines = {
        "ru": f"🎮 Общий счёт: {score}",
        "kk": f"🎮 Жалпы ұпай: {score}",
        "en": f"🎮 Total score: {score}",
    }

    header = {
        "ru": "Выберите сценарий тренировки:",
        "kk": "Тәжірибелік сценарийді таңдаңыз:",
        "en": "Choose a practice scenario:",
    }[lang]

    lines = [header]
    buttons: List[List[InlineKeyboardButton]] = []
    for idx, (scenario_id, meta) in enumerate(catalog.items(), start=1):
        completed = meta.get("badge") in badges
        icon = "✅" if completed else "🆕"
        reward = meta.get("reward", 0)
        lines.append(f"{icon} {idx}. {meta.get('title', 'Scenario')} — +{reward} 💰")
        buttons.append([InlineKeyboardButton(f"{idx}. {meta.get('title', 'Scenario')}", callback_data=f"scenario_topic|{scenario_id}")])

    lines.append(status_lines[lang])
    buttons.append([InlineKeyboardButton({"ru": "Назад", "kk": "Артқа", "en": "Back"}[lang], callback_data="back")])
    markup = InlineKeyboardMarkup(buttons)

    if is_callback:
        await safe_edit_message_or_send(query, "\n\n".join(lines), markup)
    else:
        try:
            await context.bot.send_message(chat_id=chat_id, text="\n\n".join(lines), reply_markup=markup)
        except Exception as e:
            logger.exception("Failed to send scenario menu: %s", e)

    context.user_data["scenario_state"] = None
    context.user_data["scenario_lang"] = scenario_lang
    if push_to_nav:
        current_stack = context.user_data.get("nav_stack", [])
        if not current_stack or current_stack[-1].get("view") != "scenario_menu":
            push_nav(context, {"view": "scenario_menu"})


async def scenario_choice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, scenario_id = query.data.split("|", 1)
    user_id = query.from_user.id
    lang = get_lang(user_id)
    scenario_lang = context.user_data.get("scenario_lang", resolve_scenario_language(lang))
    catalog, scenario_lang = get_scenario_catalog(scenario_lang)
    scenario_meta = catalog.get(scenario_id)
    if not scenario_meta:
        await safe_edit_message_or_send(query, {"ru": "Сценарий не найден.", "kk": "Сценарий табылмады.", "en": "Scenario not found."}[lang])
        return

    chat_id = query.message.chat_id
    context.user_data["scenario_lang"] = scenario_lang
    context.user_data["scenario_state"] = {
        "id": scenario_id,
        "lang": scenario_lang,
        "node": scenario_meta.get("start"),
        "history": [],
    }
    push_nav(context, {"view": f"scenario_play_{scenario_id}"})
    
    # Track scenario start
    track_user_event(user_id, "scenario_start", {"scenario_id": scenario_id})

    intro_text = scenario_meta.get("intro", scenario_meta.get("title", ""))
    await send_typing_action(context, chat_id, 1.0)
    await safe_edit_message_or_send(query, intro_text)

    next_node = scenario_meta.get("start")
    if next_node:
        await send_scenario_node(context, chat_id, user_id, scenario_meta, scenario_id, next_node, lang)


async def send_scenario_node(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, scenario_meta: dict, scenario_id: str, node_id: str, lang: str, edit_source=None):
    nodes = scenario_meta.get("nodes", {})
    node = nodes.get(node_id)
    if not node:
        await context.bot.send_message(chat_id=chat_id, text={"ru": "Сценарий прерван из-за ошибки данных.", "kk": "Мәлімет қатесіне байланысты сценарий тоқтады.", "en": "Scenario interrupted due to data error."}[lang])
        context.user_data.pop("scenario_state", None)
        return

    state = context.user_data.get("scenario_state", {})
    state["node"] = node_id
    context.user_data["scenario_state"] = state

    if node.get("type") == "ending":
        await conclude_scenario(context, chat_id, user_id, scenario_meta, scenario_id, node, lang)
        return

    progress_text = render_progress_bar(node.get("progress", 0.0))
    header = f"{scenario_meta.get('title', '')} · {progress_text}"
    body = f"{header}\n\n{node.get('text', '')}"
    buttons = []
    for idx, option in enumerate(node.get("options", [])):
        buttons.append([InlineKeyboardButton(option.get("label", f"Option {idx+1}"), callback_data=f"scenario_choose|{scenario_id}|{node_id}|{idx}")])

    buttons.append([InlineKeyboardButton({"ru": "🏠 Домой", "kk": "🏠 Бас мәзір", "en": "🏠 Home"}[lang], callback_data="scenario_home")])
    markup = InlineKeyboardMarkup(buttons)

    await send_typing_action(context, chat_id)
    if edit_source is not None:
        await safe_edit_message_or_send(edit_source, body, markup)
    else:
        await context.bot.send_message(chat_id=chat_id, text=body, reply_markup=markup)


async def scenario_option_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("|")
    if len(parts) != 4:
        await safe_edit_message_or_send(query, {"ru": "Некорректный выбор.", "kk": "Қате таңдау.", "en": "Invalid choice."}[get_lang(query.from_user.id)])
        return
    _, scenario_id_from_cb, node_id, idx_str = parts
    try:
        choice_index = int(idx_str)
    except ValueError:
        await safe_edit_message_or_send(query, {"ru": "Некорректный ответ.", "kk": "Қате жауап.", "en": "Invalid response."}[get_lang(query.from_user.id)])
        return
    user_id = query.from_user.id
    lang = get_lang(user_id)

    state = context.user_data.get("scenario_state")
    if not state:
        await query.answer({"ru": "Сценарий завершён. Начните заново.", "kk": "Сценарий аяқталды. Қайта бастаңыз.", "en": "Scenario finished. Start again."}[lang], show_alert=True)
        return

    scenario_id = state.get("id")
    if scenario_id != scenario_id_from_cb:
        scenario_id = scenario_id_from_cb
        state["id"] = scenario_id
    scenario_lang = state.get("lang", resolve_scenario_language(lang))
    catalog, _ = get_scenario_catalog(scenario_lang)
    scenario_meta = catalog.get(scenario_id)
    if not scenario_meta:
        await safe_edit_message_or_send(query, {"ru": "Сценарий не найден.", "kk": "Сценарий табылмады.", "en": "Scenario not found."}[lang])
        return

    nodes = scenario_meta.get("nodes", {})
    node = nodes.get(node_id)
    if not node:
        await safe_edit_message_or_send(query, {"ru": "Шаг сценария не найден.", "kk": "Сценарий қадамы табылмады.", "en": "Scenario step missing."}[lang])
        return

    options = node.get("options", [])
    if choice_index >= len(options):
        await safe_edit_message_or_send(query, {"ru": "Вариант недоступен.", "kk": "Таңдау қолжетімсіз.", "en": "Option unavailable."}[lang])
        return

    option = options[choice_index]
    impact_icon = {
        "safe": "🟢",
        "warning": "🟠",
        "danger": "🔴",
        "report": "🟡",
    }.get(option.get("impact"), "ℹ️")

    original_text = query.message.text or ""
    feedback_text = option.get("feedback", "")
    choice_label = option.get("label", "Выбор")
    updated_text = f"{original_text}\n\n➡️ {choice_label}\n{impact_icon} {feedback_text}"
    await safe_edit_message_or_send(query, updated_text)

    state.setdefault("history", []).append(
        {"node": node_id, "choice": choice_label, "impact": option.get("impact")}
    )
    context.user_data["scenario_state"] = state

    next_node_id = option.get("next")
    chat_id = query.message.chat_id

    if not next_node_id:
        await conclude_scenario(context, chat_id, user_id, scenario_meta, scenario_id, {"type": "ending", "outcome": "fail", "progress": 1.0, "text": feedback_text}, lang)
        return

    next_node = nodes.get(next_node_id)
    if not next_node:
        await conclude_scenario(context, chat_id, user_id, scenario_meta, scenario_id, {"type": "ending", "outcome": "fail", "progress": 1.0, "text": feedback_text}, lang)
        return

    state["node"] = next_node_id
    context.user_data["scenario_state"] = state

    if next_node.get("type") == "ending":
        await conclude_scenario(context, chat_id, user_id, scenario_meta, scenario_id, next_node, lang)
    else:
        await send_scenario_node(context, chat_id, user_id, scenario_meta, scenario_id, next_node_id, lang)


async def conclude_scenario(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, scenario_meta: dict, scenario_id: str, ending_node: dict, lang: str):
    outcome = ending_node.get("outcome", "fail")
    progress_text = render_progress_bar(ending_node.get("progress", 1.0))
    base_text = f"{scenario_meta.get('title', '')} · {progress_text}\n\n{ending_node.get('text', '')}"

    badge_awarded = None
    total_score = None
    reward_coins = scenario_meta.get("reward", 0) if outcome == "success" else 0
    if reward_coins > 0 and outcome == "success":
        ensure_user_record(user_id)
        result = await grant_scenario_rewards(user_id, reward_coins, scenario_meta.get("badge"))
        badge_awarded = result.get("badge")
        total_score = result.get("score")
        reward_line = {
            "ru": f"💰 Награда: +{reward_coins} монет",
            "kk": f"💰 Сыйақы: +{reward_coins} тиын",
            "en": f"💰 Reward: +{reward_coins} coins",
        }[lang]
        base_text += f"\n\n{reward_line}"
        if badge_awarded:
            badge_line = {
                "ru": f"🏅 Новый значок: {badge_awarded}",
                "kk": f"🏅 Жаңа бейдж: {badge_awarded}",
                "en": f"🏅 New badge unlocked: {badge_awarded}",
            }[lang]
            base_text += f"\n{badge_line}"
        if total_score is not None:
            score_line = {
                "ru": f"🎮 Общий счёт сценариев: {total_score}",
                "kk": f"🎮 Сценарий ұпайы: {total_score}",
                "en": f"🎮 Scenario score: {total_score}",
            }[lang]
            base_text += f"\n{score_line}"

    endings = {
        "success": {"ru": "🛡️ Итог: Вы избежали мошенничества!", "kk": "🛡️ Қорытынды: Алаяқтықтан сақтандыңыз!", "en": "🛡️ Outcome: Scam avoided!"},
        "fail": {"ru": "⚠️ Итог: Вы попались на удочку мошенников.", "kk": "⚠️ Қорытынды: Алаяққа алдандыңыз.", "en": "⚠️ Outcome: You were scammed."},
        "report": {"ru": "📢 Итог: Вы отправили отчёт и помогли другим.", "kk": "📢 Қорытынды: Сіз хабар беріп, басқаларды құтқардыңыз.", "en": "📢 Outcome: You reported the scam and helped others."},
    }
    base_text += f"\n\n{endings.get(outcome, endings['fail'])[lang]}"

    buttons = [
        [InlineKeyboardButton({"ru": "🔁 Снова", "kk": "🔁 Қайтадан", "en": "🔁 Retry"}[lang], callback_data=f"scenario_topic|{scenario_id}")],
        [InlineKeyboardButton({"ru": "📚 Все сценарии", "kk": "📚 Барлық сценарий", "en": "📚 Scenarios"}[lang], callback_data="scenario_start")],
        [InlineKeyboardButton({"ru": "🏠 Домой", "kk": "🏠 Бас мәзір", "en": "🏠 Home"}[lang], callback_data="to_main")],
    ]
    markup = InlineKeyboardMarkup(buttons)

    await send_typing_action(context, chat_id, 1.0)
    await context.bot.send_message(chat_id=chat_id, text=base_text, reply_markup=markup)

    context.user_data.pop("scenario_state", None)
    stack = context.user_data.get("nav_stack", [])
    if stack:
        stack[-1] = {"view": "scenario_menu"}
        context.user_data["nav_stack"] = stack


async def scenario_home_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    stack = context.user_data.get("nav_stack", [])
    if stack and stack[-1].get("view", "").startswith("scenario_play"):
        stack = stack[:-1]
        context.user_data["nav_stack"] = stack
    await start_scenario_from_callback(query, context)


async def report_start_via_callback(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    # Handle both Update and CallbackQuery
    if hasattr(update_or_query, 'callback_query'):
        query = update_or_query.callback_query
    else:
        query = update_or_query
    await query.answer()
    user_id = query.from_user.id
    lang = get_lang(user_id)
    context.user_data["report_stage"] = 1
    push_nav(context, {"view": "report_start"})
    await safe_reply(
        query.message,
        {
            "ru": "Опишите проблему кратко (что произошло, сумма, канал связи):",
            "kk": "Қысқаша сипаттаңыз (немесе сума, байланыс каналы):",
            "en": "Describe the issue briefly (amount, channel):",
        }[lang],
    )


async def report_message_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if this is a community report description
    if context.user_data.get("community_report_flow") == "waiting_description":
        await community_report_description_handler(update, context)
        return
    
    stage = context.user_data.get("report_stage")
    if not stage:
        return  

    message = update.message
    text = (message.text or "").strip()
    user = update.effective_user
    user_id = user.id
    lang = get_lang(user_id)

    if stage == 1:
        context.user_data["report_desc"] = text
        context.user_data["report_stage"] = 2
        await safe_reply(
            message,
            {
                "ru": "Если есть ссылка — пришлите её, иначе отправьте 'нет'.",
                "kk": "Сілтеме болса жіберіңіз, болмаса 'жоқ' деп жазыңыз.",
                "en": "If there is a link — send it, otherwise reply 'no'.",
            }[lang]
        )
        return

    if stage == 2:
        link_value = None if text.lower() in ("нет", "no", "n", "жоқ") else text
        context.user_data["report_link"] = link_value
        context.user_data["report_stage"] = 3
        await safe_reply(
            message,
            {
                "ru": "Контакт для связи (телефон или email) или 'нет'.",
                "kk": "Байланыс үшін телефон немесе email немесе 'жоқ'.",
                "en": "Contact (phone/email) or 'no'.",
            }[lang]
        )
        return

    # Stage 3: contact
    desc = context.user_data.get("report_desc", "")
    link = context.user_data.get("report_link")
    contact = None if text.lower() in ("нет", "no", "n", "жоқ") else text

    try:
        with SessionLocal() as db:
            report = ScamReport(
                telegram_id=user_id,
                description=desc,
                link=link,
                contact=contact,
            )
            db.add(report)
            db.commit()
    except Exception as e:
        logger.exception("DB report save error: %s", e)
        await safe_reply(
            message,
            {
                "ru": "Не удалось сохранить отчёт. Попробуйте позже.",
                "kk": "Есепті сақтау мүмкін болмады. Кейінірек қайталап көріңіз.",
                "en": "Failed to save the report. Please try again later.",
            }[lang]
        )
        return

    suspicious = link_is_suspicious(link) if link else False
    reply = {
        "ru": "Сообщение принято. Спасибо.",
        "kk": "Хабарлама қабылданды. Рақмет.",
        "en": "Report received. Thank you.",
    }[lang]
    if suspicious:
        reply += {
            "ru": " Присланная ссылка выглядит подозрительно — избегайте перехода по ней.",
            "kk": " Қосылған сілтеме күдікті көрінеді — оған өтпеңіз.",
            "en": " The provided link looks suspicious — avoid visiting it.",
        }[lang]

    await safe_reply(message, reply)

    admin_msg = (
        f"Новый отчёт о мошенничестве от @{user.username or user_id}:\n\n"
        f"{desc or '-'}\n\nLink: {link or 'нет'}\nContact: {contact or 'нет'}"
    )
    for aid in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=aid, text=admin_msg)
        except Exception as e:
            logger.warning("Не удалось отправить админу %s: %s", aid, e)

    context.user_data.pop("report_stage", None)
    context.user_data.pop("report_desc", None)
    context.user_data.pop("report_link", None)


# ADMIN broadcast
async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await safe_reply(update.message, "Доступ запрещён.")
        return
    await safe_reply(update.message, "Пришлите текст для рассылки всем подписчикам:")
    return BROADCAST_MSG


async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await safe_reply(update.message, "Доступ запрещён.")
        return ConversationHandler.END
    msg = update.message.text
    sent = 0
    try:
        with SessionLocal() as db:
            subs = db.query(User).filter_by(subscribed=True).all()
            for u in subs:
                try:
                    await context.bot.send_message(chat_id=u.telegram_id, text=msg)
                    sent += 1
                except Exception as e:
                    logger.warning("Ошибка при отправке %s: %s", u.telegram_id, e)
            bl = BroadcastLog(admin_id=user.id, message=msg)
            db.add(bl)
            db.commit()
    except Exception as e:
        logger.exception("Broadcast error: %s", e)
    await safe_reply(update.message, f"Рассылка выполнена. Отправлено: {sent}")
    return ConversationHandler.END


# /myinfo
async def myinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        with SessionLocal() as db:
            db_user = db.query(User).filter_by(telegram_id=user.id).first()
    except Exception as e:
        logger.exception("Failed to load user info: %s", e)
        await safe_reply(update.message, "Не удалось получить данные. Попробуйте позже.")
        return
    if not db_user:
        await safe_reply(update.message, "Вас нет в базе.")
        return
    lines = [
        f"ID: {db_user.telegram_id}",
        f"Username: @{db_user.username}" if db_user.username else "Username: -",
        f"Имя: {db_user.first_name or '-'} {db_user.last_name or ''}",
        f"Подписан: {'Да' if db_user.subscribed else 'Нет'}",
        f"Баланс: {db_user.coins} монет",
        f"Пройдено квизов: {db_user.quizzes_passed}",
        f"Зарегистрирован: {db_user.created_at.isoformat()}",
    ]
    await safe_reply(update.message, "\n".join(lines))


async def analyze_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    urls = re.findall(r"https?://[^\s]+", text)
    if not urls:
        await safe_reply(update.message, "Ссылок не найдено.")
        return
    for url in urls:
        suspicious = link_is_suspicious(url)
        accessible = False
        try:
            r = requests.head(url, allow_redirects=True, timeout=5)
            accessible = r.status_code < 400
        except Exception:
            accessible = False
        reply = f"URL: {url}\nДоступен: {'да' if accessible else 'нет'}\nПодозрительный: {'да' if suspicious else 'нет'}"
        await safe_reply(update.message, reply)


async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text or ""
    if re.search(r"https?://", txt):
        return await analyze_link_handler(update, context)
    await safe_reply(update.message, "Команда не распознана. /help")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Exception while handling an update: %s", context.error)


async def back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = get_lang(user_id)
    
    # Pop the current view from navigation stack
    stack = context.user_data.get("nav_stack", [])
    if len(stack) > 1:
        stack = stack[:-1]  # Remove current view
        context.user_data["nav_stack"] = stack
        view = stack[-1].get("view", "main_menu")
    else:
        # If stack is empty or only has one item, go to main menu
        view = "main_menu"
    context.user_data["nav_stack"] = [{"view": "main_menu"}]

    # Handle different views
    if view == "tips":
        await send_tips(query, context)
        return
    if view == "quiz_start":
        await start_quiz(query, context)
        return
    if view == "quiz_levels":
        await present_quiz_levels(query, context, push=False)
        return
    if view.startswith("quiz_level"):
        await present_quiz_levels(query, context, push=False)
        return
    if view == "scenario_menu":
        await start_scenario_from_callback(query, context, push_to_nav=False)
        return
    if view.startswith("scenario_play"):
        await start_scenario_from_callback(query, context, push_to_nav=False)
        return
    if view == "report_start":
        await report_start_via_callback(query, context)
        return
    if view == "shop":
        await show_shop(query, context, skip_answer=True)
        return
    if view == "balance":
        await show_balance(query, context, skip_answer=True)
        return
    if view == "leaderboard":
        await leaderboard_callback(query, context)
        return
    if view == "referral":
        await referral_callback(query, context)
        return
    if view == "education" or view == "premium":
        await education_callback(query, context)
        return
    if view == "report_scam" or view == "report_scam_description":
        # Return to main menu from report flow
        markup = build_main_inline(lang, user_id)
        main_menu_text = {"ru": "🏠 Главное меню", "kk": "🏠 Басты мәзір", "en": "🏠 Main menu"}[lang]
        context.user_data.pop("community_report_flow", None)
        context.user_data.pop("community_report_type", None)
        context.user_data.pop("community_report_description", None)
        context.user_data.pop("community_report_bank", None)
        try:
            await safe_edit_message_or_send(query, main_menu_text, markup)
        except Exception as e:
            logger.exception("Failed to send main menu message: %s", e)
        return

    # Default: return to main menu
    markup = build_main_inline(lang, user_id)
    main_menu_text = {"ru": "🏠 Главное меню", "kk": "🏠 Басты мәзір", "en": "🏠 Main menu"}[lang]
    try:
        await safe_edit_message_or_send(query, main_menu_text, markup)
    except Exception as e:
        logger.exception("Failed to send main menu message: %s", e)


#balance and shop
async def show_balance(query, context: ContextTypes.DEFAULT_TYPE, skip_answer: bool = False):
    if not skip_answer:
        await query.answer()
    user_id = query.from_user.id
    lang = get_lang(user_id)
    ensure_user_record(user_id, query.from_user.username, query.from_user.first_name, query.from_user.last_name)

    try:
        with SessionLocal() as db:
            u = db.query(User).filter_by(telegram_id=user_id).first()
            coins = u.coins if u else 0
            quizzes = u.quizzes_passed if u else 0
            scenario_score = u.scenario_score if u else 0
    except Exception as e:
        logger.exception("Error fetching balance: %s", e)
        coins = 0
        quizzes = 0
        scenario_score = 0

    text = {
        "ru": f"💰 Ваш баланс: {coins} монет\n🏆 Пройдено квизов: {quizzes}\n🎮 Очки сценариев: {scenario_score}",
        "kk": f"💰 Сіздің балансыңыз: {coins} тиын\n🏆 Өткен квиздер: {quizzes}\n🎮 Сценарий ұпайы: {scenario_score}",
        "en": f"💰 Your balance: {coins} coins\n🏆 Quizzes passed: {quizzes}\n🎮 Scenario score: {scenario_score}",
    }[lang]

    back_button = InlineKeyboardMarkup([[InlineKeyboardButton({"ru": "Назад", "kk": "Артқа", "en": "Back"}[lang], callback_data="back")]])
    push_nav(context, {"view": "balance"})
    await safe_edit_message_or_send(query, text, back_button)


async def show_shop(query, context: ContextTypes.DEFAULT_TYPE, skip_answer: bool = False, status_message: Optional[str] = None):
    if not skip_answer:
        await query.answer()  #лобавить ответ
    user_id = query.from_user.id
    lang = get_lang(user_id)
    ensure_user_record(user_id, query.from_user.username, query.from_user.first_name, query.from_user.last_name)

    try:
        with SessionLocal() as db:
            user_row = db.query(User).filter_by(telegram_id=user_id).first()
            coins = user_row.coins if user_row else 0
            max_level = user_row.max_unlocked_level if user_row and user_row.max_unlocked_level else 1
    except Exception as e:
        logger.exception("Error fetching shop data: %s", e)
        coins = 0
        max_level = 1

    lines = ["🛒 " + {"ru": "Магазин", "kk": "Дүкен", "en": "Shop"}[lang]]
    lines.append({
        "ru": f"Ваш баланс: {coins} монет",
        "kk": f"Балансыңыз: {coins} тиын",
        "en": f"Your balance: {coins} coins",
    }[lang])
    if status_message:
        lines.append(status_message)

    hint_cost = 20
    lines.append({
        "ru": f"• Подсказка (раздел практики) — {hint_cost} монет",
        "kk": f"• Кеңес (жаттығу бөлімі) — {hint_cost} тиын",
        "en": f"• Practice hint — {hint_cost} coins",
    }[lang])

    for level in QUIZ_LEVELS[1:]:
        status = "✅" if max_level >= level else "🔒"
        lines.append({
            "ru": f"{status} Уровень {level} квиза — награда +10 монет (+5 за идеальный результат)",
            "kk": f"{status} {level}-деңгей квиз — сыйақы +10 тиын (+5 тамаша нәтиже үшін)",
            "en": f"{status} Quiz Level {level} — reward +10 coins (+5 bonus for perfect score)",
        }[lang])

    buttons = [
        [InlineKeyboardButton(
            {"ru": f"Купить подсказку ({hint_cost})", "kk": f"Кеңес сатып алу ({hint_cost})", "en": f"Buy hint ({hint_cost})"}[lang],
            callback_data="buy_hint",
        )]
    ]

    for level in QUIZ_LEVELS[1:]:
        buttons.append([InlineKeyboardButton(
            {"ru": f"{'✅' if max_level >= level else '🔒'} Уровень {level}", "kk": f"{'✅' if max_level >= level else '🔒'} {level}-деңгей", "en": f"{'✅' if max_level >= level else '🔒'} Level {level}"}[lang],
            callback_data="shop_level_info",
        )])

    buttons.append([InlineKeyboardButton({"ru": "Назад", "kk": "Артқа", "en": "Back"}[lang], callback_data="back")])
    kb = InlineKeyboardMarkup(buttons)
    push_nav(context, {"view": "shop"})
    await safe_edit_message_or_send(query, "\n".join(lines), kb)  


async def shop_buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    lang = get_lang(user_id)
    action = query.data
    try:
        with SessionLocal() as db:
            user_row = db.query(User).filter_by(telegram_id=user_id).first()
            if not user_row:
                user_row = User(
                    telegram_id=user_id,
                    username=query.from_user.username,
                    first_name=query.from_user.first_name,
                    last_name=query.from_user.last_name,
                    subscribed=False,
                    coins=0,
                    quizzes_passed=0,
                    max_unlocked_level=1,
                    scenario_score=0,
                    scenario_badges="",
                )
                db.add(user_row)
                db.commit()
                db.refresh(user_row)

            current_coins = user_row.coins or 0

            if action == "buy_hint":
                cost = 20
                if current_coins < cost:
                    await query.answer(
                        {"ru": "Недостаточно монет для подсказки.", "kk": "Кеңес үшін тиын жеткіліксіз.", "en": "Not enough coins for the hint."}[lang],
                        show_alert=True,
                    )
                    await show_shop(query, context, skip_answer=True)
                    return
                user_row.coins = current_coins - cost
                db.commit()
                logger.info(f"User {user_id}: purchased hint, coins: {current_coins} -> {user_row.coins}")
                message = {
                    "ru": "Подсказка скоро появится в сценариях. Монеты списаны.",
                    "kk": "Кеңес жақын арада сценарийлерде қолжетімді болады. Тиын шегерілді.",
                    "en": "Hint feature coming soon. Coins deducted.",
                }[lang]
                await show_shop(query, context, skip_answer=True, status_message=message)
                return

            await query.answer({"ru": "Товар недоступен.", "kk": "Бұл өнім қолжетімсіз.", "en": "Item not available."}[lang], show_alert=True)
            await show_shop(query, context, skip_answer=True)
    except Exception as e:
        logger.exception("Shop purchase failed: %s", e)
        await safe_edit_message_or_send(query, {"ru": "Ошибка покупки.", "kk": "Сатып алу қатесі.", "en": "Purchase error."}[lang])
        return


async def shop_level_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    lang = get_lang(user_id)
    try:
        with SessionLocal() as db:
            user_row = db.query(User).filter_by(telegram_id=user_id).first()
            max_level = user_row.max_unlocked_level if user_row and user_row.max_unlocked_level else 1
    except Exception as e:
        logger.exception("Failed to fetch level info: %s", e)
        max_level = 1

    next_level = max_level + 1 if max_level < max(QUIZ_LEVELS) else None
    if next_level:
        message = {
            "ru": f"Следующий уровень {next_level} откроется после идеального прохождения текущего уровня.",
            "kk": f"Келесі {next_level}-деңгей ағымдағы деңгейді мінсіз өткен соң ашылады.",
            "en": f"Level {next_level} unlocks after a perfect score on the current level.",
        }[lang]
    else:
        message = {
            "ru": "Вы уже открыли максимальный уровень. Отличная работа!",
            "kk": "Сіз максималды деңгейді аштыңыз. Жарайсыз!",
            "en": "You’ve already unlocked the highest level. Great job!",
        }[lang]
    await query.answer(
        message,
        show_alert=True,
    )


# ============================================================================
# STARTUP FEATURES: New Commands
# ============================================================================

async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show leaderboard"""
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    
    # All features are free - no premium check needed
    has_premium = True  # All features free
    period = "all_time"  # Default to all-time
    
    if context.args and context.args[0] in ["weekly", "monthly"]:
        period = context.args[0]
    
    leaderboard_data = get_leaderboard(period=period, limit=10, user_id=user_id)
    entries = leaderboard_data.get("entries", [])
    total_players = leaderboard_data.get("total_players", 0)
    user_position = leaderboard_data.get("user_position")
    user_percentage = leaderboard_data.get("user_percentage")
    
    if not entries:
        await safe_reply(update.message, {
            "ru": "Таблица лидеров пуста. Пройдите квизы, чтобы попасть в рейтинг!",
            "kk": "Кесте бос. Квиздерді өтіп, рейтингке кіріңіз!",
            "en": "Leaderboard is empty. Complete quizzes to get ranked!",
        }[lang])
        return

    period_names = {
        "ru": {"all_time": "За всё время", "weekly": "За неделю", "monthly": "За месяц"},
        "kk": {"all_time": "Барлық уақыт", "weekly": "Апта", "monthly": "Ай"},
        "en": {"all_time": "All Time", "weekly": "Weekly", "monthly": "Monthly"},
    }
    
    lines = [{
        "ru": f"🏆 Таблица лидеров ({period_names[lang].get(period, period)}):",
        "kk": f"🏆 Кесте ({period_names[lang].get(period, period)}):",
        "en": f"🏆 Leaderboard ({period_names[lang].get(period, period)}):",
    }[lang]]
    
    lines.append(f"Всего игроков: {total_players}\n")
    
    for entry in entries:
        medal = "🥇" if entry["rank"] == 1 else "🥈" if entry["rank"] == 2 else "🥉" if entry["rank"] == 3 else f"{entry['rank']}."
        lines.append(f"{medal} {entry['username']}: {entry['score']} pts")
    
    if user_position:
        if user_position <= 10:
            lines.append(f"\n✅ Вы в топ-10!")
        else:
            lines.append(f"\n📍 Ваша позиция: #{user_position} из {total_players}")
            if user_percentage:
                lines.append(f"📊 Вы в топ {user_percentage:.1f}% игроков!")
    
    if not has_premium:
        lines.append("\n💎 Premium: Полный доступ к таблице лидеров и фильтрам!")
    
    text = "\n".join(lines)
    await safe_reply(update.message, text)


async def leaderboard_callback(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    """Show leaderboard via callback"""
    # Handle both Update and CallbackQuery
    if hasattr(update_or_query, 'callback_query'):
        query = update_or_query.callback_query
    else:
        query = update_or_query
    await query.answer()
    user_id = query.from_user.id
    lang = get_lang(user_id)
    
    # Ensure user has a leaderboard entry
    update_leaderboard(user_id)
    
    # All features are free - no premium check needed
    has_premium = True  # All features free
    period = "all_time"
    
    # Get leaderboard with user position
    leaderboard_data = get_leaderboard(period=period, limit=10, user_id=user_id)
    entries = leaderboard_data.get("entries", [])
    total_players = leaderboard_data.get("total_players", 0)
    user_position = leaderboard_data.get("user_position")
    user_percentage = leaderboard_data.get("user_percentage")
    
    if not entries:
        # Try to initialize leaderboard for all users if empty
        try:
            with SessionLocal() as db:
                users = db.query(User).all()
                for user in users:
                    update_leaderboard(user.telegram_id)
            # Retry getting leaderboard
            leaderboard_data = get_leaderboard(period=period, limit=10, user_id=user_id)
            entries = leaderboard_data.get("entries", [])
            total_players = leaderboard_data.get("total_players", 0)
            user_position = leaderboard_data.get("user_position")
            user_percentage = leaderboard_data.get("user_percentage")
        except Exception as e:
            logger.exception("Failed to initialize leaderboard: %s", e)
    
    if not entries:
        text = {
            "ru": "Таблица лидеров пуста. Пройдите квизы, чтобы попасть в рейтинг!",
            "kk": "Кесте бос. Квиздерді өтіп, рейтингке кіріңіз!",
            "en": "Leaderboard is empty. Complete quizzes to get ranked!",
        }[lang]
        back_btn = InlineKeyboardMarkup([[InlineKeyboardButton({"ru": "Назад", "kk": "Артқа", "en": "Back"}[lang], callback_data="back")]])
        await safe_edit_message_or_send(query, text, back_btn)
        return

    period_names = {
        "ru": {"all_time": "За всё время", "weekly": "За неделю", "monthly": "За месяц"},
        "kk": {"all_time": "Барлық уақыт", "weekly": "Апта", "monthly": "Ай"},
        "en": {"all_time": "All Time", "weekly": "Weekly", "monthly": "Monthly"},
    }
    
    lines = [{
        "ru": f"🏆 Таблица лидеров ({period_names[lang].get(period, period)}):",
        "kk": f"🏆 Кесте ({period_names[lang].get(period, period)}):",
        "en": f"🏆 Leaderboard ({period_names[lang].get(period, period)}):",
    }[lang]]
    
    lines.append({
        "ru": f"Всего игроков: {total_players}\n",
        "kk": f"Барлық ойыншылар: {total_players}\n",
        "en": f"Total players: {total_players}\n",
    }[lang])
    
    if entries:
        for entry in entries:
            medal = "🥇" if entry["rank"] == 1 else "🥈" if entry["rank"] == 2 else "🥉" if entry["rank"] == 3 else f"{entry['rank']}."
            lines.append(f"{medal} {entry['username']}: {entry['score']} pts")
    else:
        lines.append({
            "ru": "Пока нет записей в таблице лидеров.",
            "kk": "Әлі кестеде жазбалар жоқ.",
            "en": "No leaderboard entries yet.",
        }[lang])
    
    # Show user's position
    if user_position:
        if user_position <= 10:
            lines.append({
                "ru": f"\n✅ Вы в топ-10!",
                "kk": f"\n✅ Сіз топ-10-да!",
                "en": f"\n✅ You're in top 10!",
            }[lang])
        else:
            lines.append({
                "ru": f"\n📍 Ваша позиция: #{user_position} из {total_players}",
                "kk": f"\n📍 Сіздің орныңыз: #{user_position} / {total_players}",
                "en": f"\n📍 Your position: #{user_position} of {total_players}",
            }[lang])
            if user_percentage:
                lines.append({
                    "ru": f"📊 Вы в топ {user_percentage:.1f}% игроков!",
                    "kk": f"📊 Сіз топ {user_percentage:.1f}% ойыншыларда!",
                    "en": f"📊 You're in top {user_percentage:.1f}% of players!",
                }[lang])
    
    # All features are free - no premium message needed
    
    text = "\n".join(lines)
    
    # Add period selection buttons
    buttons = []
    if has_premium:
        buttons.append([
            InlineKeyboardButton({"ru": "📅 За неделю", "kk": "📅 Апта", "en": "📅 Weekly"}[lang], callback_data="leaderboard_weekly"),
            InlineKeyboardButton({"ru": "📅 За месяц", "kk": "📅 Ай", "en": "📅 Monthly"}[lang], callback_data="leaderboard_monthly"),
        ])
    buttons.append([InlineKeyboardButton({"ru": "Назад", "kk": "Артқа", "en": "Back"}[lang], callback_data="back")])
    
    back_btn = InlineKeyboardMarkup(buttons)
    await safe_edit_message_or_send(query, text, back_btn)


async def referral_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's referral code and stats"""
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    
    code = get_or_create_referral_code(user_id)
    
    # Get referral stats
    try:
        with SessionLocal() as db:
            total_refs = db.query(Referral).filter_by(referrer_id=user_id).count()
            completed_refs = db.query(Referral).filter_by(
                referrer_id=user_id,
                status="completed"
            ).count()
    except Exception as e:
        logger.exception("Failed to get referral stats: %s", e)
        total_refs = 0
        completed_refs = 0
    
    text = {
        "ru": (
            f"🎁 Реферальная программа\n\n"
            f"Ваш код: `{code}`\n\n"
            f"Приглашено: {completed_refs} из {total_refs}\n\n"
            f"Пригласите друзей по ссылке:\n"
            f"https://t.me/your_bot?start={code}\n\n"
            f"🎯 За каждые 3 успешных приглашения — 1 месяц Premium бесплатно!"
        ),
        "kk": (
            f"🎁 Рефералдық бағдарлама\n\n"
            f"Сіздің кодыңыз: `{code}`\n\n"
            f"Шақырылған: {completed_refs} / {total_refs}\n\n"
            f"Достарды сілтеме арқылы шақырыңыз:\n"
            f"https://t.me/your_bot?start={code}\n\n"
            f"🎯 Әр 3 сәтті шақыруға — 1 ай Premium тегін!"
        ),
        "en": (
            f"🎁 Referral Program\n\n"
            f"Your code: `{code}`\n\n"
            f"Invited: {completed_refs} of {total_refs}\n\n"
            f"Invite friends with this link:\n"
            f"https://t.me/your_bot?start={code}\n\n"
            f"🎯 Get 1 month Premium free for every 3 successful referrals!"
        ),
    }[lang]
    
    await safe_reply(update.message, text)


async def referral_callback(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    """Show referral info via callback"""
    # Handle both Update and CallbackQuery
    if hasattr(update_or_query, 'callback_query'):
        query = update_or_query.callback_query
    else:
        query = update_or_query
    await query.answer()
    user_id = query.from_user.id
    lang = get_lang(user_id)
    
    code = get_or_create_referral_code(user_id)
    
    try:
        with SessionLocal() as db:
            # Get referral stats
            total_refs = db.query(Referral).filter_by(referrer_id=user_id).count()
            completed_refs = db.query(Referral).filter_by(
                referrer_id=user_id,
                status="completed"
            ).count()
            
            # Get bot username for proper link
            bot_info = await context.bot.get_me()
            bot_username = bot_info.username if bot_info else "your_bot"
            
            # Calculate progress to next reward (every 3 referrals)
            next_reward_progress = completed_refs % 3
            referrals_needed = 3 - next_reward_progress if next_reward_progress > 0 else 0
            
    except Exception as e:
        logger.exception("Failed to get referral stats: %s", e)
        total_refs = 0
        completed_refs = 0
        referrals_needed = 3
        bot_username = "your_bot"
    
    referral_link = f"https://t.me/{bot_username}?start={code}"
    
    text = {
        "ru": (
            f"🎁 Реферальная программа\n\n"
            f"Ваш код: `{code}`\n\n"
            f"📊 Статистика:\n"
            f"• Приглашено друзей: {completed_refs}\n"
            f"• Всего попыток: {total_refs}\n\n"
            f"🎯 До следующей награды: {referrals_needed} приглашений\n"
            f"(За каждые 3 приглашения — 1 месяц Premium)\n\n"
            f"🔗 Ваша реферальная ссылка:\n"
            f"`{referral_link}`\n\n"
            f"💡 Поделитесь ссылкой с друзьями!"
        ),
        "kk": (
            f"🎁 Рефералдық бағдарлама\n\n"
            f"Сіздің кодыңыз: `{code}`\n\n"
            f"📊 Статистика:\n"
            f"• Шақырылған достар: {completed_refs}\n"
            f"• Барлық әрекеттер: {total_refs}\n\n"
            f"🎯 Келесі сыйақыға: {referrals_needed} шақыру\n"
            f"(Әр 3 шақыруға — 1 ай Premium)\n\n"
            f"🔗 Сіздің рефералдық сілтемеңіз:\n"
            f"`{referral_link}`\n\n"
            f"💡 Достармен бөлісіңіз!"
        ),
        "en": (
            f"🎁 Referral Program\n\n"
            f"Your code: `{code}`\n\n"
            f"📊 Statistics:\n"
            f"• Friends invited: {completed_refs}\n"
            f"• Total attempts: {total_refs}\n\n"
            f"🎯 Until next reward: {referrals_needed} referrals\n"
            f"(Every 3 referrals = 1 month Premium)\n\n"
            f"🔗 Your referral link:\n"
            f"`{referral_link}`\n\n"
            f"💡 Share with friends!"
        ),
    }[lang]
    
    back_btn = InlineKeyboardMarkup([[InlineKeyboardButton({"ru": "Назад", "kk": "Артқа", "en": "Back"}[lang], callback_data="back")]])
    await safe_edit_message_or_send(query, text, back_btn)


# Premium commands removed - replaced with educational module

async def education_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler for /education and /premium commands"""
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    
    text = {
        "ru": (
            "📚 Образовательный модуль\n\n"
            "Изучите основы финансовой безопасности:\n\n"
            "• Как распознать мошенничество\n"
            "• Защита банковских карт\n"
            "• Безопасные платежи\n"
            "• Что делать при подозрении\n\n"
            "Используйте кнопки ниже для навигации:"
        ),
        "kk": (
            "📚 Білім беру модулі\n\n"
            "Қаржылық қауіпсіздіктің негіздерін үйреніңіз:\n\n"
            "• Алаяқтықты қалай тануға болады\n"
            "• Банк карталарын қорғау\n"
            "• Қауіпсіз төлемдер\n"
            "• Күдік тұрғанда не істеу керек\n\n"
            "Навигация үшін төмендегі батырмаларды пайдаланыңыз:"
        ),
        "en": (
            "📚 Educational Module\n\n"
            "Learn the basics of financial security:\n\n"
            "• How to recognize fraud\n"
            "• Protecting bank cards\n"
            "• Safe payments\n"
            "• What to do if suspicious\n\n"
            "Use the buttons below to navigate:"
        ),
    }[lang]
    
    # Create buttons for educational steps
    buttons = []
    for i in range(1, 6):  # 5 educational steps
        step_text = {
            "ru": f"Урок {i}",
            "kk": f"Сабақ {i}",
            "en": f"Lesson {i}",
        }[lang]
        buttons.append([InlineKeyboardButton(step_text, callback_data=f"education_step_{i}")])
    
    markup = InlineKeyboardMarkup(buttons)
    push_nav(context, {"view": "education"})
    await safe_reply(update.message, text, markup)


async def education_callback(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    """Show educational module menu"""
    # Handle both Update and CallbackQuery
    if hasattr(update_or_query, 'callback_query'):
        query = update_or_query.callback_query
    else:
        query = update_or_query
    
    if hasattr(query, 'answer'):
        await query.answer()
    
    user_id = query.from_user.id
    lang = get_lang(user_id)
    
    text = {
        "ru": (
            "📚 Образовательный модуль\n\n"
            "Изучите основы финансовой безопасности:\n\n"
            "• Как распознать мошенничество\n"
            "• Защита банковских карт\n"
            "• Безопасные платежи\n"
            "• Что делать при подозрении\n\n"
            "Выберите урок для начала:"
        ),
        "kk": (
            "📚 Білім беру модулі\n\n"
            "Қаржылық қауіпсіздіктің негіздерін үйреніңіз:\n\n"
            "• Алаяқтықты қалай тануға болады\n"
            "• Банк карталарын қорғау\n"
            "• Қауіпсіз төлемдер\n"
            "• Күдік тұрғанда не істеу керек\n\n"
            "Бастау үшін сабақты таңдаңыз:"
        ),
        "en": (
            "📚 Educational Module\n\n"
            "Learn the basics of financial security:\n\n"
            "• How to recognize fraud\n"
            "• Protecting bank cards\n"
            "• Safe payments\n"
            "• What to do if suspicious\n\n"
            "Select a lesson to begin:"
        ),
    }[lang]
    
    # Create buttons for educational steps
    buttons = []
    for i in range(1, 6):  # 5 educational steps
        step_text = {
            "ru": f"Урок {i}",
            "kk": f"Сабақ {i}",
            "en": f"Lesson {i}",
        }[lang]
        buttons.append([InlineKeyboardButton(step_text, callback_data=f"education_step_{i}")])
    
    buttons.append([InlineKeyboardButton(
        {"ru": "Назад", "kk": "Артқа", "en": "Back"}[lang],
        callback_data="back"
    )])
    
    markup = InlineKeyboardMarkup(buttons)
    push_nav(context, {"view": "education"})
    await safe_edit_message_or_send(query, text, markup)


async def education_module_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle education step callbacks"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = get_lang(user_id)
    
    data = query.data
    
    if data == "education_complete":
        text = {
            "ru": "✅ Поздравляем! Вы завершили образовательный модуль.",
            "kk": "✅ Құттықтаймыз! Сіз білім беру модулін аяқтадыңыз.",
            "en": "✅ Congratulations! You've completed the educational module.",
        }[lang]
        buttons = [[InlineKeyboardButton(
            {"ru": "Назад", "kk": "Артқа", "en": "Back"}[lang],
            callback_data="back"
        )]]
        markup = InlineKeyboardMarkup(buttons)
        await safe_edit_message_or_send(query, text, markup)
        return

    # Extract step number from callback data
    if data.startswith("education_step_"):
        step_num = int(data.split("_")[-1])
        
        lessons = {
            1: {
                "ru": (
                    "📖 Урок 1: Распознавание мошенничества\n\n"
                    "Мошенники часто используют:\n"
                    "• Срочные просьбы о деньгах\n"
                    "• Поддельные сайты банков\n"
                    "• Фишинговые письма\n"
                    "• Подозрительные ссылки\n\n"
                    "Всегда проверяйте отправителя!"
                ),
                "kk": (
                    "📖 Сабақ 1: Алаяқтықты тану\n\n"
                    "Алаяқтар жиі пайдаланады:\n"
                    "• Ақшаға шұғыл сұраулар\n"
                    "• Банктердің жалған сайттары\n"
                    "• Фишинг хаттары\n"
                    "• Күдікті сілтемелер\n\n"
                    "Жіберушіні әрдайым тексеріңіз!"
                ),
                "en": (
                    "📖 Lesson 1: Recognizing Fraud\n\n"
                    "Scammers often use:\n"
                    "• Urgent requests for money\n"
                    "• Fake bank websites\n"
                    "• Phishing emails\n"
                    "• Suspicious links\n\n"
                    "Always verify the sender!"
                ),
            },
            2: {
                "ru": (
                    "📖 Урок 2: Защита банковских карт\n\n"
                    "Правила безопасности:\n"
                    "• Никогда не сообщайте CVV код\n"
                    "• Не пересылайте фото карты\n"
                    "• Используйте двухфакторную аутентификацию\n"
                    "• Регулярно проверяйте выписки\n\n"
                    "Берегите свои данные!"
                ),
                "kk": (
                    "📖 Сабақ 2: Банк карталарын қорғау\n\n"
                    "Қауіпсіздік ережелері:\n"
                    "• CVV кодын ешқашан айтпаңыз\n"
                    "• Картаның фотосын жібермеңіз\n"
                    "• Екі факторлы аутентификацияны пайдаланыңыз\n"
                    "• Ай сайын шотыңызды тексеріңіз\n\n"
                    "Деректеріңізді қорғаңыз!"
                ),
                "en": (
                    "📖 Lesson 2: Protecting Bank Cards\n\n"
                    "Safety rules:\n"
                    "• Never share your CVV code\n"
                    "• Don't send card photos\n"
                    "• Use two-factor authentication\n"
                    "• Regularly check statements\n\n"
                    "Protect your data!"
                ),
            },
            3: {
                "ru": (
                    "📖 Урок 3: Безопасные платежи\n\n"
                    "При совершении платежей:\n"
                    "• Проверяйте адрес сайта (HTTPS)\n"
                    "• Используйте официальные приложения\n"
                    "• Не вводите данные на подозрительных сайтах\n"
                    "• Проверяйте получателя платежа\n\n"
                    "Будьте внимательны!"
                ),
                "kk": (
                    "📖 Сабақ 3: Қауіпсіз төлемдер\n\n"
                    "Төлем жасағанда:\n"
                    "• Сайт мекенжайын тексеріңіз (HTTPS)\n"
                    "• Ресми қосымшаларды пайдаланыңыз\n"
                    "• Күдікті сайттарда деректерді енгізбеңіз\n"
                    "• Төлем алушыны тексеріңіз\n\n"
                    "Абай болыңыз!"
                ),
                "en": (
                    "📖 Lesson 3: Safe Payments\n\n"
                    "When making payments:\n"
                    "• Check the website address (HTTPS)\n"
                    "• Use official applications\n"
                    "• Don't enter data on suspicious sites\n"
                    "• Verify the payment recipient\n\n"
                    "Be careful!"
                ),
            },
            4: {
                "ru": (
                    "📖 Урок 4: Что делать при подозрении\n\n"
                    "Если вы подозреваете мошенничество:\n"
                    "• Немедленно заблокируйте карту\n"
                    "• Свяжитесь с банком\n"
                    "• Сообщите о мошенничестве через бота\n"
                    "• Сохраните все доказательства\n\n"
                    "Действуйте быстро!"
                ),
                "kk": (
                    "📖 Сабақ 4: Күдік тұрғанда не істеу керек\n\n"
                    "Алаяқтықтан күдіктансаңыз:\n"
                    "• Картаны бірден бұғаттаңыз\n"
                    "• Банкпен байланысыңыз\n"
                    "• Бот арқылы алаяқтық туралы хабарлаңыз\n"
                    "• Барлық дәлелдерді сақтаңыз\n\n"
                    "Жылдам әрекет етіңіз!"
                ),
                "en": (
                    "📖 Lesson 4: What to Do If Suspicious\n\n"
                    "If you suspect fraud:\n"
                    "• Immediately block the card\n"
                    "• Contact the bank\n"
                    "• Report fraud through the bot\n"
                    "• Save all evidence\n\n"
                    "Act quickly!"
                ),
            },
            5: {
                "ru": (
                    "📖 Урок 5: Итоговый тест\n\n"
                    "Проверьте свои знания:\n"
                    "• Пройдите квизы в боте\n"
                    "• Используйте сценарии для практики\n"
                    "• Следите за обновлениями\n"
                    "• Делитесь знаниями с друзьями\n\n"
                    "Продолжайте учиться!"
                ),
                "kk": (
                    "📖 Сабақ 5: Қорытынды тест\n\n"
                    "Біліміңізді тексеріңіз:\n"
                    "• Боттағы квиздерді өтіңіз\n"
                    "• Тәжірибе үшін сценарийлерді пайдаланыңыз\n"
                    "• Жаңартуларды бақылаңыз\n"
                    "• Достармен білім бөлісіңіз\n\n"
                    "Оқуды жалғастырыңыз!"
                ),
                "en": (
                    "📖 Lesson 5: Final Test\n\n"
                    "Test your knowledge:\n"
                    "• Complete quizzes in the bot\n"
                    "• Use scenarios for practice\n"
                    "• Follow updates\n"
                    "• Share knowledge with friends\n\n"
                    "Keep learning!"
                ),
            },
        }
        
        lesson_content = lessons.get(step_num, lessons[1])
        text = lesson_content.get(lang, lesson_content["en"])
        
        buttons = []
        if step_num < 5:
            buttons.append([InlineKeyboardButton(
                {"ru": "Следующий урок", "kk": "Келесі сабақ", "en": "Next lesson"}[lang],
                callback_data=f"education_step_{step_num + 1}"
            )])
        else:
            buttons.append([InlineKeyboardButton(
                {"ru": "Завершить", "kk": "Аяқтау", "en": "Complete"}[lang],
                callback_data="education_complete"
            )])
        
        buttons.append([InlineKeyboardButton(
            {"ru": "Назад", "kk": "Артқа", "en": "Back"}[lang],
            callback_data="back"
        )])
        
        markup = InlineKeyboardMarkup(buttons)
        await safe_edit_message_or_send(query, text, markup)


async def leaderboard_period_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle weekly/monthly leaderboard selection"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = get_lang(user_id)
    
    period = "all_time"
    if query.data == "leaderboard_weekly":
        period = "weekly"
    elif query.data == "leaderboard_monthly":
        period = "monthly"
    elif query.data == "leaderboard_all":
        period = "all_time"
    
    # All leaderboard features are free
    if False and period != "all_time":  # All periods available for free
        await query.answer({
            "ru": "Доступ к фильтрам лидеров доступен только для Premium!",
            "kk": "Кесте фильтрлері тек Premium үшін!",
            "en": "Leaderboard filters are Premium only!",
        }[lang], show_alert=True)
        return

    # Get leaderboard with user position
    leaderboard_data = get_leaderboard(period=period, limit=10, user_id=user_id)
    entries = leaderboard_data.get("entries", [])
    total_players = leaderboard_data.get("total_players", 0)
    user_position = leaderboard_data.get("user_position")
    user_percentage = leaderboard_data.get("user_percentage")
    
    period_names = {
        "ru": {"all_time": "За всё время", "weekly": "За неделю", "monthly": "За месяц"},
        "kk": {"all_time": "Барлық уақыт", "weekly": "Апта", "monthly": "Ай"},
        "en": {"all_time": "All Time", "weekly": "Weekly", "monthly": "Monthly"},
    }
    
    lines = [{
        "ru": f"🏆 Таблица лидеров ({period_names[lang].get(period, period)}):",
        "kk": f"🏆 Кесте ({period_names[lang].get(period, period)}):",
        "en": f"🏆 Leaderboard ({period_names[lang].get(period, period)}):",
    }[lang]]
    
    lines.append(f"Всего игроков: {total_players}\n")
    
    for entry in entries:
        medal = "🥇" if entry["rank"] == 1 else "🥈" if entry["rank"] == 2 else "🥉" if entry["rank"] == 3 else f"{entry['rank']}."
        lines.append(f"{medal} {entry['username']}: {entry['score']} pts")
    
    if user_position:
        if user_position <= 10:
            lines.append(f"\n✅ Вы в топ-10!")
        else:
            lines.append(f"\n📍 Ваша позиция: #{user_position} из {total_players}")
            if user_percentage:
                lines.append(f"📊 Вы в топ {user_percentage:.1f}% игроков!")
    
    text = "\n".join(lines)
    
    buttons = [
        [
            InlineKeyboardButton({"ru": "📅 За всё время", "kk": "📅 Барлық", "en": "📅 All Time"}[lang], callback_data="leaderboard_all"),
            InlineKeyboardButton({"ru": "📅 За неделю", "kk": "📅 Апта", "en": "📅 Weekly"}[lang], callback_data="leaderboard_weekly"),
            InlineKeyboardButton({"ru": "📅 За месяц", "kk": "📅 Ай", "en": "📅 Monthly"}[lang], callback_data="leaderboard_monthly"),
        ],
        [InlineKeyboardButton({"ru": "Назад", "kk": "Артқа", "en": "Back"}[lang], callback_data="back")],
    ]
    markup = InlineKeyboardMarkup(buttons)
    await safe_edit_message_or_send(query, text, markup)


def reset_weekly_leaderboard():
    """Reset weekly leaderboard scores (call this weekly via scheduler)"""
    try:
        with SessionLocal() as db:
            # Reset weekly scores
            db.query(LeaderboardEntry).filter_by(period="weekly").update({"score": 0})
            db.commit()
            
            # Recalculate ranks
            recalculate_leaderboard_ranks()
            logger.info("Weekly leaderboard reset completed")
    except Exception as e:
        logger.exception("Failed to reset weekly leaderboard: %s", e)


async def analytics_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: Show analytics"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await safe_reply(update.message, "Access denied. Admin only.")
        return
    
    days = 30
    if context.args and context.args[0].isdigit():
        days = int(context.args[0])
    
    summary = get_analytics_summary(days=days)
    
    text = f"📊 Analytics Summary (Last {days} days)\n\n"
    text += f"Total Users: {summary.get('total_users', 0)}\n"
    text += f"Active Users (7d): {summary.get('active_users_7d', 0)}\n"
    text += f"Premium Users: {summary.get('premium_users', 0)}\n"
    text += f"Premium Conversion: {summary.get('premium_conversion_rate', 0):.2f}%\n"
    text += f"Quiz Completion Rate: {summary.get('quiz_completion_rate', 0):.2f}%\n\n"
    
    popular = summary.get('most_popular_scenarios', [])
    if popular:
        text += "Most Popular Scenarios:\n"
        for scenario_id, count in popular:
            text += f"  • {scenario_id}: {count} starts\n"
    
    # Aggregate daily analytics
    aggregate_daily_analytics()
    
    await safe_reply(update.message, text)


async def scheduled_tip_job(application: Application):
    tips = [
        "Еженедельный совет: проверьте активные устройства в ваших банковских приложениях.",
        "Еженедельный совет: обновите пароли для критичных сервисов каждые 3 месяца.",
    ]
    tip = tips[datetime.utcnow().second % len(tips)]
    with SessionLocal() as db:
        subs = db.query(User).filter_by(subscribed=True).all()
        for u in subs:
            try:
                await application.bot.send_message(chat_id=u.telegram_id, text=f"Оповещение: {tip}")
            except Exception as e:
                logger.warning("Scheduled send failed to %s: %s", u.telegram_id, e)


# ============================================================================
# KAZAKHSTAN-SPECIFIC FEATURES
# ============================================================================

def get_user_city(user_id: int) -> Optional[str]:
    """Get user's city from UserLocation table"""
    try:
        with SessionLocal() as db:
            location = db.query(UserLocation).filter_by(user_id=user_id).first()
            return location.city if location else None
    except Exception as e:
        logger.exception("Error getting user city: %s", e)
        return None


def set_user_city(user_id: int, city: str, region: Optional[str] = None):
    """Set user's city"""
    try:
        with SessionLocal() as db:
            location = db.query(UserLocation).filter_by(user_id=user_id).first()
            if location:
                location.city = city
                location.region = region
                location.updated_at = datetime.utcnow()
            else:
                location = UserLocation(user_id=user_id, city=city, region=region)
                db.add(location)
            db.commit()
    except Exception as e:
        logger.exception("Error setting user city: %s", e)


def get_active_scam_alerts(city: Optional[str] = None, alert_type: Optional[str] = None, limit: int = 10) -> List[Dict]:
    """Get active scam alerts, optionally filtered by city and type"""
    try:
        with SessionLocal() as db:
            query = db.query(ScamAlert).filter_by(active=True)
            if city:
                query = query.filter_by(city=city)
            if alert_type:
                query = query.filter_by(alert_type=alert_type)
            alerts = query.order_by(ScamAlert.created_at.desc()).limit(limit).all()
            return [
                {
                    "id": a.id,
                    "type": a.alert_type,
                    "title": a.title,
                    "description": a.description,
                    "severity": a.severity,
                    "city": a.city,
                    "created_at": a.created_at,
                }
                for a in alerts
            ]
    except Exception as e:
        logger.exception("Error getting scam alerts: %s", e)
        return []


def create_scam_alert(alert_type: str, title: str, description: str, severity: str = "high", 
                      city: Optional[str] = None, source: str = "nbrk") -> bool:
    """Create a new scam alert (admin function)"""
    try:
        with SessionLocal() as db:
            alert = ScamAlert(
                alert_type=alert_type,
                title=title,
                description=description,
                severity=severity,
                city=city,
                source=source,
                active=True,
            )
            db.add(alert)
            db.commit()
            
            # Notify all users in the city (or all users if city is None)
            # This would be done via a background job in production
            return True
    except Exception as e:
        logger.exception("Error creating scam alert: %s", e)
        return False


def check_qr_code_safety(qr_data: str) -> Dict[str, Any]:
    """Check if QR code is safe (basic validation)"""
    risk_level = "unknown"
    is_safe = False
    
    # Check for suspicious patterns
    suspicious_patterns = [
        "bit.ly", "tinyurl", "short.link",
        "kaspi-bank.kz", "halyk-bank.com",  # Common phishing domains
        "http://",  # Non-HTTPS
    ]
    
    qr_lower = qr_data.lower()
    
    # Check for suspicious patterns
    for pattern in suspicious_patterns:
        if pattern in qr_lower:
            risk_level = "high"
            is_safe = False
            break
    
    # Check if it's a payment QR (Kaspi QR format)
    if "kaspi.kz" in qr_lower or "kaspi.kz/pay" in qr_lower:
        risk_level = "safe"
        is_safe = True
    elif "halykbank.kz" in qr_lower:
        risk_level = "safe"
        is_safe = True
    elif qr_data.startswith("https://") and not any(p in qr_lower for p in suspicious_patterns):
        risk_level = "low"
        is_safe = True
    
    return {
        "is_safe": is_safe,
        "risk_level": risk_level,
        "reason": {
            "safe": "QR код выглядит безопасным",
            "low": "Низкий риск, но будьте осторожны",
            "high": "⚠️ Высокий риск! Не сканируйте этот QR код",
            "unknown": "Не удалось определить безопасность",
        }.get(risk_level, "unknown")
    }


def save_qr_check(user_id: int, qr_data: str, is_safe: bool, risk_level: str):
    """Save QR code check to database"""
    try:
        with SessionLocal() as db:
            check = QRCodeCheck(
                user_id=user_id,
                qr_data=qr_data[:500],  # Limit length
                is_safe=is_safe,
                risk_level=risk_level,
            )
            db.add(check)
            db.commit()
    except Exception as e:
        logger.exception("Error saving QR check: %s", e)


def create_community_scam_report(user_id: int, scam_type: str, description: str, 
                                 bank_name: Optional[str] = None, city: Optional[str] = None) -> int:
    """Create a community scam report (anonymous)"""
    try:
        with SessionLocal() as db:
            report = CommunityScamReport(
                user_id=user_id,
                scam_type=scam_type,
                bank_name=bank_name,
                description=description,
                city=city or get_user_city(user_id),
                verified=False,
                verification_votes=0,
            )
            db.add(report)
            db.commit()
            db.refresh(report)
            return report.id
    except Exception as e:
        logger.exception("Error creating scam report: %s", e)
        return 0


def vote_on_scam_report(user_id: int, report_id: int, is_scam: bool) -> bool:
    """Vote on whether a report is a scam"""
    try:
        with SessionLocal() as db:
            # Check if user already voted
            existing = db.query(ScamVerificationVote).filter_by(
                user_id=user_id, report_id=report_id
            ).first()
            if existing:
                return False  # Already voted
            
            # Create vote
            vote = ScamVerificationVote(
                user_id=user_id,
                report_id=report_id,
                is_scam=is_scam,
            )
            db.add(vote)
            
            # Update report verification votes
            report = db.query(CommunityScamReport).filter_by(id=report_id).first()
            if report:
                scam_votes = db.query(ScamVerificationVote).filter_by(
                    report_id=report_id, is_scam=True
                ).count()
                total_votes = db.query(ScamVerificationVote).filter_by(
                    report_id=report_id
                ).count()
                
                report.verification_votes = scam_votes
                if total_votes >= 5 and scam_votes >= total_votes * 0.7:
                    report.verified = True
            
            db.commit()
            return True
    except Exception as e:
        logger.exception("Error voting on scam report: %s", e)
        return False


def get_recent_scam_reports(city: Optional[str] = None, limit: int = 10) -> List[Dict]:
    """Get recent community scam reports"""
    try:
        with SessionLocal() as db:
            query = db.query(CommunityScamReport)
            if city:
                query = query.filter_by(city=city)
            reports = query.order_by(CommunityScamReport.created_at.desc()).limit(limit).all()
            return [
                {
                    "id": r.id,
                    "scam_type": r.scam_type,
                    "bank_name": r.bank_name,
                    "description": r.description[:200],  # Truncate
                    "city": r.city,
                    "verified": r.verified,
                    "votes": r.verification_votes,
                    "created_at": r.created_at,
                }
                for r in reports
            ]
    except Exception as e:
        logger.exception("Error getting scam reports: %s", e)
        return []


def get_regional_leaderboard(city: str, limit: int = 10) -> List[Dict]:
    """Get leaderboard for a specific city"""
    try:
        with SessionLocal() as db:
            # Get users from this city
            city_users = db.query(UserLocation.user_id).filter_by(city=city).subquery()
            
            # Get leaderboard entries for these users
            entries = db.query(LeaderboardEntry, User).join(
                User, LeaderboardEntry.user_id == User.telegram_id
            ).filter(
                LeaderboardEntry.user_id.in_(db.query(city_users.c.user_id))
            ).order_by(
                LeaderboardEntry.score.desc()
            ).limit(limit).all()
            
            result = []
            for rank, (entry, user) in enumerate(entries, 1):
                result.append({
                    "rank": rank,
                    "user_id": user.telegram_id,
                    "username": user.username or user.first_name or f"User {user.telegram_id}",
                    "score": entry.score,
                })
            return result
    except Exception as e:
        logger.exception("Error getting regional leaderboard: %s", e)
        return []


def get_or_create_emergency_fund(user_id: int) -> Dict[str, Any]:
    """Get or create emergency fund tracker for user"""
    try:
        with SessionLocal() as db:
            fund = db.query(EmergencyFund).filter_by(user_id=user_id).first()
            if not fund:
                fund = EmergencyFund(user_id=user_id)
                db.add(fund)
                db.commit()
                db.refresh(fund)
            
            # Calculate months covered
            if fund.monthly_expenses > 0:
                months_covered = fund.current_amount / fund.monthly_expenses
            else:
                months_covered = 0
            
            fund.months_covered = int(months_covered)
            db.commit()
            
            return {
                "target_amount": fund.target_amount,
                "current_amount": fund.current_amount,
                "monthly_expenses": fund.monthly_expenses,
                "months_covered": fund.months_covered,
            }
    except Exception as e:
        logger.exception("Error getting emergency fund: %s", e)
        return {"target_amount": 0, "current_amount": 0, "monthly_expenses": 0, "months_covered": 0}


def update_emergency_fund(user_id: int, target_amount: Optional[int] = None,
                          current_amount: Optional[int] = None,
                          monthly_expenses: Optional[int] = None):
    """Update emergency fund values"""
    try:
        with SessionLocal() as db:
            fund = db.query(EmergencyFund).filter_by(user_id=user_id).first()
            if not fund:
                fund = EmergencyFund(user_id=user_id)
                db.add(fund)
            
            if target_amount is not None:
                fund.target_amount = target_amount
            if current_amount is not None:
                fund.current_amount = current_amount
            if monthly_expenses is not None:
                fund.monthly_expenses = monthly_expenses
            
            # Recalculate months covered
            if fund.monthly_expenses > 0:
                fund.months_covered = int(fund.current_amount / fund.monthly_expenses)
            
            fund.updated_at = datetime.utcnow()
            db.commit()
    except Exception as e:
        logger.exception("Error updating emergency fund: %s", e)


# ============================================================================
# HANDLERS FOR KAZAKHSTAN FEATURES
# ============================================================================

async def scam_alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show active scam alerts for user's city"""
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    city = get_user_city(user_id)
    
    alerts = get_active_scam_alerts(city=city, limit=5)
    
    if not alerts:
        text = {
            "ru": "✅ Нет активных предупреждений о мошенничестве в вашем городе.",
            "kk": "✅ Қалаңызда алаяқтық туралы белсенді ескертулер жоқ.",
            "en": "✅ No active scam alerts in your city.",
        }[lang]
    else:
        lines = [{
            "ru": f"🚨 Активные предупреждения ({len(alerts)}):",
            "kk": f"🚨 Белсенді ескертулер ({len(alerts)}):",
            "en": f"🚨 Active Alerts ({len(alerts)}):",
        }[lang]]
        
        for alert in alerts:
            severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(alert["severity"], "⚪")
            lines.append(f"\n{severity_emoji} {alert['title']}")
            lines.append(f"   {alert['description'][:100]}...")
            if alert["city"]:
                lines.append(f"   📍 {alert['city']}")
        
        text = "\n".join(lines)
    
    await safe_reply(update.message, text)


async def qr_scanner_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """QR code scanner command - user sends QR code data"""
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    
    text = {
        "ru": "📱 Отправьте QR код для проверки безопасности.\n\nПросто отправьте текст или ссылку из QR кода.",
        "kk": "📱 Қауіпсіздігін тексеру үшін QR код жіберіңіз.\n\nQR кодтың мәтінін немесе сілтемесін жіберіңіз.",
        "en": "📱 Send QR code to check safety.\n\nJust send the text or link from the QR code.",
    }[lang]
    
    await safe_reply(update.message, text)
    context.user_data["waiting_qr"] = True


async def qr_check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle QR code text input"""
    if not context.user_data.get("waiting_qr"):
        return
    
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    qr_data = update.message.text
    
    result = check_qr_code_safety(qr_data)
    save_qr_check(user_id, qr_data, result["is_safe"], result["risk_level"])
    
    emoji = "✅" if result["is_safe"] else "⚠️" if result["risk_level"] == "low" else "❌"
    text = f"{emoji} {result['reason']}\n\nQR: {qr_data[:100]}"
    
    await safe_reply(update.message, text)
    context.user_data.pop("waiting_qr", None)


async def community_report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start community scam report flow"""
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    
    text = {
        "ru": "📝 Сообщить о мошенничестве (анонимно)\n\nВыберите тип:",
        "kk": "📝 Алаяқтық туралы хабарлау (анонимдік)\n\nТүрін таңдаңыз:",
        "en": "📝 Report a scam (anonymous)\n\nChoose type:",
    }[lang]
    
    buttons = [
        [InlineKeyboardButton("📱 SMS/Фишинг", callback_data="report_type_phishing")],
        [InlineKeyboardButton("☎️ Звонок", callback_data="report_type_call")],
        [InlineKeyboardButton("💰 Инвестиции", callback_data="report_type_investment")],
        [InlineKeyboardButton("💼 Работа", callback_data="report_type_job")],
        [InlineKeyboardButton("💳 Займ", callback_data="report_type_loan")],
        [InlineKeyboardButton({"ru": "Назад", "kk": "Артқа", "en": "Back"}[lang], callback_data="back")],
    ]
    markup = InlineKeyboardMarkup(buttons)
    await safe_reply(update.message, text, markup)
    push_nav(context, {"view": "report_scam"})


async def report_type_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle report type selection"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = get_lang(user_id)
    
    # Extract report type from callback data
    data = query.data
    if not data.startswith("report_type_"):
        return
    
    report_type = data.replace("report_type_", "")
    
    # Map callback types to database types
    type_mapping = {
        "phishing": "phishing",
        "call": "call",
        "investment": "investment",
        "job": "job",
        "loan": "loan",
    }
    
    scam_type = type_mapping.get(report_type, "other")
    context.user_data["community_report_type"] = scam_type
    
    # Ask for description
    text = {
        "ru": (
            f"📝 Вы выбрали тип: {report_type}\n\n"
            "Опишите ситуацию подробно:\n"
            "• Что произошло?\n"
            "• Какие данные запрашивали?\n"
            "• Откуда пришло сообщение/звонок?\n\n"
            "Отправьте описание текстом."
        ),
        "kk": (
            f"📝 Сіз таңдаған түр: {report_type}\n\n"
            "Жағдайды егжей-тегжейлі сипаттаңыз:\n"
            "• Не болды?\n"
            "• Қандай деректер сұралды?\n"
            "• Хабарлама/қоңырау қайдан келді?\n\n"
            "Сипаттаманы мәтін ретінде жіберіңіз."
        ),
        "en": (
            f"📝 You selected type: {report_type}\n\n"
            "Describe the situation in detail:\n"
            "• What happened?\n"
            "• What data was requested?\n"
            "• Where did the message/call come from?\n\n"
            "Send the description as text."
        ),
    }[lang]
    
    await safe_edit_message_or_send(query, text)
    context.user_data["community_report_flow"] = "waiting_description"
    push_nav(context, {"view": "report_scam_description"})


async def community_report_description_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle community report description input"""
    if not context.user_data.get("community_report_flow") == "waiting_description":
        return
    
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    description = update.message.text.strip()
    
    if len(description) < 10:
        await safe_reply(update.message, {
            "ru": "Описание слишком короткое. Пожалуйста, опишите ситуацию подробнее (минимум 10 символов).",
            "kk": "Сипаттама тым қысқа. Жағдайды толығырақ сипаттаңыз (кемінде 10 таңба).",
            "en": "Description is too short. Please describe the situation in more detail (minimum 10 characters).",
        }[lang])
        return
    
    context.user_data["community_report_description"] = description
    
    # Ask for bank (optional)
    text = {
        "ru": (
            "💳 Укажите банк (если применимо):\n\n"
            "Выберите банк или отправьте 'нет' / 'пропустить'"
        ),
        "kk": (
            "💳 Банкті көрсетіңіз (егер қолданылатын болса):\n\n"
            "Банкті таңдаңыз немесе 'жоқ' / 'өткізу' деп жіберіңіз"
        ),
        "en": (
            "💳 Specify the bank (if applicable):\n\n"
            "Select a bank or send 'no' / 'skip'"
        ),
    }[lang]
    
    buttons = [
        [InlineKeyboardButton("Kaspi Bank", callback_data="report_bank_kaspi")],
        [InlineKeyboardButton("Halyk Bank", callback_data="report_bank_halyk")],
        [InlineKeyboardButton("Jusan Bank", callback_data="report_bank_jusan")],
        [InlineKeyboardButton({"ru": "Другой", "kk": "Басқа", "en": "Other"}[lang], callback_data="report_bank_other")],
        [InlineKeyboardButton({"ru": "Пропустить", "kk": "Өткізу", "en": "Skip"}[lang], callback_data="report_bank_skip")],
    ]
    markup = InlineKeyboardMarkup(buttons)
    await safe_reply(update.message, text, markup)
    context.user_data["community_report_flow"] = "waiting_bank"


async def report_bank_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bank selection for community report"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = get_lang(user_id)
    
    data = query.data
    if data == "report_bank_skip":
        bank_name = None
    elif data.startswith("report_bank_"):
        bank = data.replace("report_bank_", "")
        bank_mapping = {
            "kaspi": "Kaspi Bank",
            "halyk": "Halyk Bank",
            "jusan": "Jusan Bank",
            "other": None,
        }
        bank_name = bank_mapping.get(bank)
    else:
        return
    
    context.user_data["community_report_bank"] = bank_name
    
    # Save the report
    scam_type = context.user_data.get("community_report_type", "other")
    description = context.user_data.get("community_report_description", "")
    
    try:
        report_id = create_community_scam_report(
            user_id=user_id,
            scam_type=scam_type,
            description=description,
            bank_name=bank_name,
            city=None  # Can be added later if needed
        )
        
        text = {
            "ru": (
                "✅ Отчет успешно отправлен!\n\n"
                "Спасибо за помощь в защите других пользователей. "
                "Ваш отчет будет проверен сообществом."
            ),
            "kk": (
                "✅ Есеп сәтті жіберілді!\n\n"
                "Басқа пайдаланушыларды қорғауға көмектескеніңізге рақмет. "
                "Сіздің есебіңіз қауымдастық тарапынан тексеріледі."
            ),
            "en": (
                "✅ Report successfully submitted!\n\n"
                "Thank you for helping protect other users. "
                "Your report will be verified by the community."
            ),
        }[lang]
        
        await safe_edit_message_or_send(query, text)
        
        # Cleanup
        context.user_data.pop("community_report_type", None)
        context.user_data.pop("community_report_description", None)
        context.user_data.pop("community_report_bank", None)
        context.user_data.pop("community_report_flow", None)
        
    except Exception as e:
        logger.exception("Failed to save community report: %s", e)
        await safe_edit_message_or_send(query, {
            "ru": "❌ Не удалось сохранить отчет. Попробуйте позже.",
            "kk": "❌ Есепті сақтау мүмкін болмады. Кейінірек қайталап көріңіз.",
            "en": "❌ Failed to save the report. Please try again later.",
        }[lang])


async def emergency_fund_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show emergency fund tracker"""
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    
    fund = get_or_create_emergency_fund(user_id)
    
    target = fund["target_amount"]
    current = fund["current_amount"]
    expenses = fund["monthly_expenses"]
    months = fund["months_covered"]
    
    progress = (current / target * 100) if target > 0 else 0
    progress_bar = "█" * int(progress / 10) + "░" * (10 - int(progress / 10))
    
    text = {
        "ru": (
            f"💰 Резервный фонд\n\n"
            f"Цель: {target:,}₸\n"
            f"Текущий: {current:,}₸\n"
            f"Месячные расходы: {expenses:,}₸\n"
            f"Покрытие: {months} месяцев\n\n"
            f"Прогресс: {progress:.0f}%\n{progress_bar}\n\n"
            f"💡 Рекомендуется иметь резерв на 3-6 месяцев расходов."
        ),
        "kk": (
            f"💰 Резервтік қор\n\n"
            f"Мақсат: {target:,}₸\n"
            f"Қазіргі: {current:,}₸\n"
            f"Айлық шығыстар: {expenses:,}₸\n"
            f"Қамту: {months} ай\n\n"
            f"Прогресс: {progress:.0f}%\n{progress_bar}\n\n"
            f"💡 3-6 айлық шығыстарға резерв қалдыру ұсынылады."
        ),
        "en": (
            f"💰 Emergency Fund\n\n"
            f"Target: {target:,}₸\n"
            f"Current: {current:,}₸\n"
            f"Monthly expenses: {expenses:,}₸\n"
            f"Coverage: {months} months\n\n"
            f"Progress: {progress:.0f}%\n{progress_bar}\n\n"
            f"💡 Recommended: 3-6 months of expenses."
        ),
    }[lang]
    
    buttons = [
        [InlineKeyboardButton({"ru": "✏️ Редактировать", "kk": "✏️ Өңдеу", "en": "✏️ Edit"}[lang], callback_data="fund_edit")],
        [InlineKeyboardButton({"ru": "Назад", "kk": "Артқа", "en": "Back"}[lang], callback_data="back")],
    ]
    markup = InlineKeyboardMarkup(buttons)
    await safe_reply(update.message, text, markup)


# ============================================================================
# B2B / CORPORATE COMMANDS FOR BANKS
# ============================================================================

async def bank_create_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать банк-партнер (admin only) - для лицензирования бота банкам"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await safe_reply(update.message, "❌ Доступ запрещён. Только для администраторов.")
        return
    
    args = context.args
    if not args or len(args) < 2:
        await safe_reply(update.message, "Использование: /bank_create <bank_name> <max_clients> [webhook_url]")
        return
    
    bank_name = " ".join(args[:-2]) if len(args) > 2 else args[0]
    try:
        max_clients = int(args[-2] if len(args) > 2 else args[-1])
        webhook_url = args[-1] if len(args) > 2 else None
    except ValueError:
        await safe_reply(update.message, "Ошибка: max_clients должно быть числом")
        return
    
    result = create_bank_partner(bank_name, user_id, max_clients, webhook_url)
    if result.get("success"):
        await safe_reply(update.message, (
            f"✅ Банк-партнер создан!\n\n"
            f"Банк: {bank_name}\n"
            f"ID: {result['bank_id']}\n"
            f"API ключ: `{result['api_key']}`\n"
            f"Лицензионный ключ: `{result['license_key']}`\n"
            f"API секрет: `{result['api_secret']}`\n\n"
            f"Максимум клиентов: {max_clients}\n"
            f"Webhook URL: {webhook_url or 'не настроен'}\n\n"
            f"💡 Банк может использовать API ключ для интеграции и регистрации своих клиентов."
        ))
    else:
        await safe_reply(update.message, f"❌ Ошибка: {result.get('error', 'Unknown error')}")


async def bank_register_client_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Зарегистрировать клиента банка (обычный гражданин)"""
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    
    args = context.args
    if not args or len(args) < 1:
        await safe_reply(update.message, {
            "ru": "Использование: /bank_register <license_key> [card_number]\n\nИли банк может зарегистрировать вас через API.",
            "kk": "Пайдалану: /bank_register <license_key> [card_number]\n\nНемесе банк сізді API арқылы тіркей алады.",
            "en": "Usage: /bank_register <license_key> [card_number]\n\nOr bank can register you via API.",
        }[lang])
        return
    
    license_key = args[0]
    card_number = args[1] if len(args) > 1 else None
    
    try:
        with SessionLocal() as db:
            bank = db.query(BankPartner).filter_by(license_key=license_key).first()
            if not bank or bank.status != "active":
                await safe_reply(update.message, {
                    "ru": "❌ Неверный или неактивный лицензионный ключ",
                    "kk": "❌ Дұрыс емес немесе белсенді емес лицензия кілті",
                    "en": "❌ Invalid or inactive license key",
                }[lang])
                return
            
            if register_bank_client(bank.id, user_id, card_number):
                await safe_reply(update.message, {
                    "ru": f"✅ Вы зарегистрированы как клиент {bank.bank_name}!\n\nТеперь вы можете использовать бота для защиты от финансовых мошенников.",
                    "kk": f"✅ Сіз {bank.bank_name} клиенті ретінде тіркелдіңіз!\n\nЕнді сіз қаржылық алаяқтықтан қорғау үшін ботты пайдалана аласыз.",
                    "en": f"✅ You are registered as {bank.bank_name} client!\n\nNow you can use the bot to protect against financial scams.",
                }[lang])
            else:
                await safe_reply(update.message, {
                    "ru": "❌ Не удалось зарегистрироваться. Возможно, достигнут лимит клиентов.",
                    "kk": "❌ Тіркеу мүмкін болмады. Клиенттер лимитіне жетуі мүмкін.",
                    "en": "❌ Failed to register. Client limit may have been reached.",
                }[lang])
    except Exception as e:
        logger.exception("Bank client registration error: %s", e)
        await safe_reply(update.message, {
            "ru": "❌ Произошла ошибка при регистрации",
            "kk": "❌ Тіркеу кезінде қате пайда болды",
            "en": "❌ An error occurred during registration",
        }[lang])


async def bank_dashboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать аналитику для банка о его клиентах"""
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    
    try:
        with SessionLocal() as db:
            # Find bank partner where user is admin
            bank = db.query(BankPartner).filter_by(admin_user_id=user_id).first()
            
            if not bank:
                await safe_reply(update.message, {
                    "ru": "❌ Вы не являетесь администратором банка-партнера",
                    "kk": "❌ Сіз банк-серіктес әкімшісі емессіз",
                    "en": "❌ You are not a bank partner administrator",
                }[lang])
                return
            
            analytics = get_bank_analytics(bank.id, days=30)
            if analytics.get("success"):
                text = {
                    "ru": (
                        f"📊 Аналитика банка: {bank.bank_name}\n\n"
                        f"👥 Всего клиентов: {analytics['total_clients']}\n"
                        f"📱 Активных пользователей: {analytics['active_users']}\n"
                        f"✅ Завершено квизов: {analytics['quiz_completions']}\n"
                        f"🎮 Завершено сценариев: {analytics['scenario_completions']}\n"
                        f"📝 Сообщений о скамах: {analytics['scam_reports']}\n"
                        f"📈 Средний балл квизов: {analytics['average_quiz_score']}%\n"
                        f"🛡️ Процент успешной защиты: {analytics['protection_rate']}%\n\n"
                        f"📅 Период: последние 30 дней\n\n"
                        f"💡 Эта аналитика показывает, как ваши клиенты используют бота для защиты от мошенников."
                    ),
                    "kk": (
                        f"📊 Банк аналитикасы: {bank.bank_name}\n\n"
                        f"👥 Барлық клиенттер: {analytics['total_clients']}\n"
                        f"📱 Белсенді пайдаланушылар: {analytics['active_users']}\n"
                        f"✅ Аяқталған квиздер: {analytics['quiz_completions']}\n"
                        f"🎮 Аяқталған сценарийлер: {analytics['scenario_completions']}\n"
                        f"📝 Алаяқтық туралы хабарламалар: {analytics['scam_reports']}\n"
                        f"📈 Орташа квиз баллы: {analytics['average_quiz_score']}%\n"
                        f"🛡️ Сәтті қорғау пайызы: {analytics['protection_rate']}%\n\n"
                        f"📅 Кезең: соңғы 30 күн\n\n"
                        f"💡 Бұл аналитика клиенттеріңіздің алаяқтықтан қорғау үшін ботты қалай пайдаланатынын көрсетеді."
                    ),
                    "en": (
                        f"📊 Bank Analytics: {bank.bank_name}\n\n"
                        f"👥 Total Clients: {analytics['total_clients']}\n"
                        f"📱 Active Users: {analytics['active_users']}\n"
                        f"✅ Quiz Completions: {analytics['quiz_completions']}\n"
                        f"🎮 Scenario Completions: {analytics['scenario_completions']}\n"
                        f"📝 Scam Reports: {analytics['scam_reports']}\n"
                        f"📈 Average Quiz Score: {analytics['average_quiz_score']}%\n"
                        f"🛡️ Protection Rate: {analytics['protection_rate']}%\n\n"
                        f"📅 Period: Last 30 days\n\n"
                        f"💡 This analytics shows how your clients use the bot to protect against scams."
                    ),
                }[lang]
                await safe_reply(update.message, text)
            else:
                await safe_reply(update.message, {
                    "ru": f"❌ Ошибка получения аналитики: {analytics.get('error', 'Unknown')}",
                    "kk": f"❌ Аналитиканы алу қатесі: {analytics.get('error', 'Unknown')}",
                    "en": f"❌ Analytics error: {analytics.get('error', 'Unknown')}",
                }[lang])
    except Exception as e:
        logger.exception("Bank dashboard error: %s", e)
        await safe_reply(update.message, {
            "ru": "❌ Произошла ошибка при получении аналитики",
            "kk": "❌ Аналитиканы алу кезінде қате пайда болды",
            "en": "❌ An error occurred while fetching analytics",
        }[lang])


# ============================================================================
# STRIPE WEBHOOK HANDLER (Flask server)
# ============================================================================

# Webhook server removed - no payment processing needed for demo


def main():
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()
    
    # No webhook server needed - demo system only
    application.add_handler(CallbackQueryHandler(back_handler, pattern="^to_main$"))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("tips", lambda u, c: send_tips(u, c)))
    application.add_handler(CommandHandler("quiz", quiz_cmd))
    application.add_handler(CommandHandler("report", report_cmd))
    application.add_handler(CommandHandler("subscribe", lambda u, c: subscribe_user(u, c)))
    application.add_handler(CommandHandler("unsubscribe", lambda u, c: unsubscribe_user(u, c)))
    application.add_handler(CommandHandler("myinfo", myinfo))
    application.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    application.add_handler(CommandHandler("referral", referral_cmd))
    application.add_handler(CommandHandler("premium", education_cmd))
    application.add_handler(CommandHandler("education", education_cmd))
    application.add_handler(CommandHandler("analytics", analytics_cmd))
    # B2B / Bank Partner features - банки как партнеры для своих клиентов
    application.add_handler(CommandHandler("bank_create", bank_create_cmd))
    application.add_handler(CommandHandler("bank_register", bank_register_client_cmd))
    application.add_handler(CommandHandler("bank_dashboard", bank_dashboard_cmd))
    # Kazakhstan-specific features
    application.add_handler(CommandHandler("alerts", scam_alerts_cmd))
    application.add_handler(CommandHandler("qr", qr_scanner_cmd))
    application.add_handler(CommandHandler("report_scam", community_report_cmd))
    application.add_handler(CommandHandler("fund", emergency_fund_cmd))

    bc_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", admin_broadcast_start)],
        states={BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_send)]},
        fallbacks=[CommandHandler("cancel", lambda u, c: None)],
    )
    application.add_handler(bc_conv)

    report_conv = ConversationHandler(
        entry_points=[CommandHandler("report", report_cmd)],
        states={
            R_REPORT_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_desc)],
            R_REPORT_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_link)],
            R_REPORT_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_contact)],
        },
        fallbacks=[CommandHandler("cancel", cancel_report)],
    )
    application.add_handler(report_conv)
    
    # QR code check handler (when user sends text after /qr)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, qr_check_handler))

    application.add_handler(CallbackQueryHandler(set_language_callback, pattern="^set_lang_"))
    application.add_handler(CallbackQueryHandler(quiz_level_selected, pattern=r"^quiz_level\|"))
    application.add_handler(CallbackQueryHandler(quiz_locked_callback, pattern=r"^quiz_locked\|"))
    application.add_handler(CallbackQueryHandler(quiz_back_levels, pattern=r"^quiz_back_levels$"))
    application.add_handler(CallbackQueryHandler(quiz_home_callback, pattern=r"^quiz_home$"))
    application.add_handler(CallbackQueryHandler(quiz_answer_callback, pattern=r"^quiz_ans:\d+$"))
    application.add_handler(CallbackQueryHandler(scenario_choice_handler, pattern=r"^scenario_topic\|"))
    application.add_handler(CallbackQueryHandler(scenario_option_handler, pattern=r"^scenario_choose\|"))
    application.add_handler(CallbackQueryHandler(scenario_home_handler, pattern=r"^scenario_home$"))
    application.add_handler(CallbackQueryHandler(back_handler, pattern="^back$"))
    application.add_handler(CallbackQueryHandler(back_handler, pattern="^back_to_menu$"))
    application.add_handler(CallbackQueryHandler(callback_root, pattern="^(tips|quiz_start|report_start|subscribe|unsubscribe|scenario_start|balance|shop|leaderboard|referral|premium|education|alerts|qr|report_scam|fund)$"))
    # Payment handlers
    # Educational module handlers
    application.add_handler(CallbackQueryHandler(education_module_handler, pattern=r"^education_step_\d+$"))
    application.add_handler(CallbackQueryHandler(education_module_handler, pattern=r"^education_complete$"))
    # Leaderboard period handlers
    application.add_handler(CallbackQueryHandler(leaderboard_period_handler, pattern=r"^leaderboard_(weekly|monthly|all)$"))
    application.add_handler(CallbackQueryHandler(shop_buy_callback, pattern=r"^buy_hint$"))
    application.add_handler(CallbackQueryHandler(shop_level_info_callback, pattern="^shop_level_info$"))
    # Community report handlers
    application.add_handler(CallbackQueryHandler(report_type_handler, pattern=r"^report_type_"))
    application.add_handler(CallbackQueryHandler(report_bank_handler, pattern=r"^report_bank_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, report_message_flow))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))
    application.add_error_handler(error_handler)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(lambda: asyncio.create_task(scheduled_tip_job(application)), "interval", hours=24)
    # Aggregate daily analytics at midnight UTC
    scheduler.add_job(aggregate_daily_analytics, "cron", hour=0, minute=0)
    # Reset weekly leaderboard every Monday at midnight
    scheduler.add_job(reset_weekly_leaderboard, "cron", day_of_week="mon", hour=0, minute=0)
    scheduler.start()
    application.run_polling()


if __name__ == "__main__":
    main()
