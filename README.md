#  Financial Security Telegram Bot for Kazakhstan

A comprehensive Telegram bot that protects and educates users about financial scams, with special focus on Kazakhstan's banking ecosystem (Kaspi, Halyk, Jusan). Built with Python 3.9+ and python-telegram-bot.

## Table of Contents

1. [Project Description](#project-description)
2. [Installation & Setup](#installation--setup)
3. [Dependencies](#dependencies)
4. [Configuration](#configuration)
5. [Testing Instructions](#testing-instructions)
6. [API Access](#api-access)
7. [Deployment](#deployment)
8. [Video Tutorials](#video-tutorials)
9. [Features Overview](#features-overview)
10. [Commands Reference](#commands-reference)
11. [Architecture & Technical Implementation](#architecture--technical-implementation)
12. [Database Structure](#database-structure)
13. [Startup Implementation Plan](#startup-implementation-plan)
14. [Troubleshooting](#troubleshooting)

---

## Project Description

The Financial Security Bot is an educational Telegram bot designed specifically for Kazakhstan users to learn about and protect themselves from financial scams. The bot provides:

- **Interactive Learning**: Multi-level quizzes and branching scenario conversations
- **Real-time Protection**: City-based scam alerts, QR code scanner, emergency fund tracker
- **Gamification**: Coins, badges, leaderboards, and achievements
- **Community Features**: Anonymous scam reporting, crowd verification, referral program
- **Kazakhstan-Specific Content**: Scenarios based on Kaspi, Halyk, Jusan, and local scam patterns

### Key Features

- 🎓 **Educational Quizzes**: Progressive difficulty levels with coin rewards
- 🎭 **Interactive Scenarios**: Branching conversations simulating real scam attempts
- 🚨 **Scam Alerts**: Real-time warnings based on user's city (Almaty, Astana, Shymkent, etc.)
- 📱 **QR Code Scanner**: Safety verification for QR codes and links
- 💰 **Emergency Fund Tracker**: Monitor and manage your financial safety net
- 📝 **Community Reports**: Anonymous scam reporting with crowd verification
- 🏆 **Leaderboards**: Global and regional rankings with weekly resets
- 🎁 **Referral Program**: Invite friends and earn rewards
- 📚 **Educational Modules**: Interactive lessons on subscription scams and fraud prevention

---

## Installation & Setup

### Prerequisites

- Python 3.9 or higher
- pip (Python package manager)
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)

### Step-by-Step Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/mara-werils/financial-security-bot-kazakhstan.git
   cd Finance_security_bot
   ```

2. **Create a virtual environment (recommended)**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Create `.env` file**
   ```bash
   # Option 1: Copy from example (if .env.example exists)
   cp .env.example .env
   
   # Option 2: Create manually
   touch .env
   ```

5. **Configure environment variables**
   Edit `.env` file and add your configuration (see [Configuration](#configuration) section)
   
   **⚠️ IMPORTANT**: The bot will not start without `BOT_TOKEN` configured!

6. **Get Bot Token**
   - Open Telegram and search for [@BotFather](https://t.me/BotFather)
   - Send `/newbot` and follow instructions
   - Copy the bot token

7. **Run the bot**
   ```bash
   python bot.py
   ```

The bot will start and connect to Telegram. You should see log messages indicating successful initialization.

---

## Dependencies

The project requires the following Python packages (see `requirements.txt`):

```
python-telegram-bot==20.7
sqlalchemy==2.0.23
apscheduler==3.10.4
requests==2.31.0
python-dotenv==1.0.0
qrcode==7.4.2
Pillow==10.2.0
```

### Dependency Descriptions

- **python-telegram-bot**: Telegram Bot API wrapper for Python
- **sqlalchemy**: ORM for database operations
- **apscheduler**: Background task scheduling (daily analytics, weekly leaderboard resets)
- **requests**: HTTP library for API calls
- **python-dotenv**: Environment variable management
- **qrcode**: QR code generation and processing
- **Pillow**: Image processing for QR codes

---

## Configuration

### Environment Variables Setup

The bot uses environment variables for configuration. All settings are loaded from a `.env` file in the project root.

#### Step 1: Create `.env` File

Create a `.env` file in the project root directory:

```bash
# In the project root directory
touch .env
```

Or copy from example (if available):
```bash
cp .env.example .env
```

#### Step 2: Get Bot Token

1. Open Telegram and search for [@BotFather](https://t.me/BotFather)
2. Send `/newbot` command
3. Follow the instructions to create your bot
4. Copy the bot token (format: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

#### Step 3: Get Your Telegram ID (for Admin)

1. Open Telegram and search for [@userinfobot](https://t.me/userinfobot)
2. Send `/start` command
3. Copy your Telegram ID (numeric value)

#### Step 4: Configure `.env` File

Edit the `.env` file and add the following variables:

```env
# ============================================================================
# REQUIRED: Bot Token from @BotFather
# ============================================================================
BOT_TOKEN=your_bot_token_here

# ============================================================================
# OPTIONAL: Database Configuration
# ============================================================================
# Default: sqlite:///fs_bot.db
# For PostgreSQL: postgresql://user:password@localhost/dbname
DATABASE_URL=sqlite:///fs_bot.db

# ============================================================================
# OPTIONAL: Admin Configuration
# ============================================================================
# Option 1: Multiple admins (comma-separated)
ADMIN_IDS=123456789,987654321

# Option 2: Single admin (alternative to ADMIN_IDS)
# ADMIN_CHAT_ID=123456789

# ============================================================================
# OPTIONAL: Quiz Configuration
# ============================================================================
# Minimum correct answers to pass a quiz level (default: 3)
QUIZ_PASS_THRESHOLD=3
```

### Configuration Details

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BOT_TOKEN` | ✅ **Yes** | - | Telegram bot token from @BotFather. **Bot will not start without this!** |
| `DATABASE_URL` | ❌ No | `sqlite:///fs_bot.db` | SQLAlchemy database URL. Use SQLite for development, PostgreSQL for production. |
| `ADMIN_IDS` | ❌ No | `[]` | Comma-separated list of admin Telegram IDs (e.g., `123456789,987654321`) |
| `ADMIN_CHAT_ID` | ❌ No | - | Single admin Telegram ID (alternative to ADMIN_IDS). Only used if ADMIN_IDS is not set. |
| `QUIZ_PASS_THRESHOLD` | ❌ No | `3` | Minimum correct answers required to pass a quiz level. Must be >= 1. |

### Example `.env` File

```env
# Required: Bot Token
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# Optional: Database (defaults to SQLite)
DATABASE_URL=sqlite:///finance_bot.db

# Optional: Admin (get your ID from @userinfobot)
ADMIN_CHAT_ID=123456789

# Optional: Quiz threshold (defaults to 3)
QUIZ_PASS_THRESHOLD=3
```

### Configuration Validation

The bot automatically validates configuration on startup:

- ✅ **Checks for BOT_TOKEN**: If missing, shows helpful error message and exits
- ✅ **Validates QUIZ_PASS_THRESHOLD**: Ensures it's a valid integer >= 1
- ✅ **Parses ADMIN_IDS**: Handles comma-separated values and validates numeric IDs
- ✅ **Sets defaults**: Uses sensible defaults for optional variables

### Error Messages

If configuration is invalid, the bot will display helpful error messages:

**Missing BOT_TOKEN:**
```
ERROR: BOT_TOKEN is required but not set!

Please create a .env file with the following content:
  BOT_TOKEN=your_bot_token_here
```

**Invalid QUIZ_PASS_THRESHOLD:**
```
WARNING: Invalid QUIZ_PASS_THRESHOLD value 'abc', using default: 3
```

### Security Notes

- ⚠️ **Never commit `.env` file to git** - it contains sensitive information
- ✅ `.env` is automatically ignored by `.gitignore`
- ✅ Use `.env.example` as a template (without real values)
- ✅ Keep your bot token secret and never share it publicly

---

## Testing Instructions

### Basic Functionality Tests

1. **Start the Bot**
   - Run `python bot.py`
   - Verify bot starts without errors
   - Check logs for successful database initialization

2. **Test `/start` Command**
   - Send `/start` to the bot
   - Verify main menu appears with all buttons
   - Check language selection works

3. **Test Quizzes**
   - Click "Пройти квиз" (Take Quiz)
   - Complete Level 1 quiz
   - Verify coins are awarded (should see coin balance increase)
   - Check that `completed_quizzes` counter increments
   - Try unlocking Level 2 with a perfect score

4. **Test Scenarios**
   - Click "Практика сценариев" (Practice Scenarios)
   - Select a scenario (e.g., "Kaspi Bank Phishing")
   - Complete the interactive conversation
   - Verify coins are awarded upon completion

5. **Test Navigation**
   - Click "Back" buttons in various menus
   - Verify all back buttons return to previous screen
   - Test quiz level selection back button
   - Check main menu navigation

6. **Test Leaderboard**
   - Click "🏆 Таблица лидеров" (Leaderboard)
   - Verify real user rankings are displayed
   - Test period filters (Weekly, Monthly, All Time)
   - Check that your score appears correctly

7. **Test Referral Program**
   - Click "🎁 Реферальная программа" (Referral Program)
   - Verify unique referral code is generated
   - Check referral statistics display
   - Test referral tracking

8. **Test Educational Module**
   - Click "📚 Защита от подписок" (Subscription Scams)
   - Complete all 5 steps of the lesson
   - Verify +20 coins are awarded
   - Check navigation between steps

9. **Test Scam Alerts**
   - Click "🚨 Предупреждения" (Alerts)
   - Verify alerts display (or "No active alerts" message)
   - Check city-based filtering

10. **Test QR Scanner**
    - Click "📱 Проверить QR" (Check QR)
    - Send a test link or QR code text
    - Verify safety check results

11. **Test Scam Reporting**
    - Click "📝 Сообщить о скаме" (Report Scam)
    - Complete the reporting flow
    - Verify report is saved to database
    - Check admin notification (if configured)

12. **Test Emergency Fund**
    - Click "💰 Резервный фонд" (Emergency Fund)
    - Verify fund tracker displays
    - Test editing fund details

### Advanced Tests

- **Database Integrity**: Verify all user actions are saved correctly
- **Coin System**: Complete multiple activities and verify coin accumulation
- **Badge System**: Unlock badges and verify they're saved
- **Scheduled Tasks**: Wait for daily analytics aggregation and weekly leaderboard reset
- **Error Handling**: Test with invalid inputs, missing data, etc.

---

## API Access

### Bot Username

The bot can be accessed via Telegram:
- **Bot Username**: `@FinanceSecurityKZBot` (or your configured username)
- **Direct Link**: `https://t.me/FinanceSecurityKZBot`

### Demo Credentials

For testing purposes, you can use:
- Test with your own Telegram account
- Admin features require configuration in `.env` file

### API Endpoints

The bot uses Telegram Bot API via `python-telegram-bot` library. All interactions happen through:
- **Webhook** (production) or **Polling** (development)
- Configured via `Application.builder().token(BOT_TOKEN).build()`

### Webhook Setup (Production)

For production deployment, configure webhooks:

```python
# In bot.py, replace run_polling() with:
application.run_webhook(
    listen="0.0.0.0",
    port=8443,
    url_path=BOT_TOKEN,
    webhook_url="https://yourdomain.com/" + BOT_TOKEN
)
```

---

## Deployment

### Server Setup

1. **Choose a Server**
   - VPS (DigitalOcean, AWS, Hetzner, etc.)
   - Minimum: 1GB RAM, 1 CPU core
   - Ubuntu 20.04+ or similar Linux distribution

2. **Install Dependencies**
   ```bash
   sudo apt update
   sudo apt install python3 python3-pip python3-venv git
   ```

3. **Clone and Setup**
   ```bash
   git clone <repository-url>
   cd Finance_security_bot
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Configure Environment**
   ```bash
   cp .env.example .env
   nano .env  # Edit with your configuration
   ```

5. **Database Initialization**
   The database is automatically created on first run. To manually initialize:
   ```bash
   python3 -c "from bot import init_db; init_db()"
   ```

### Process Management

Use `systemd` or `supervisord` to keep the bot running:

**systemd Service** (`/etc/systemd/system/finance-bot.service`):
```ini
[Unit]
Description=Financial Security Telegram Bot
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/Finance_security_bot
Environment="PATH=/path/to/Finance_security_bot/venv/bin"
ExecStart=/path/to/Finance_security_bot/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable finance-bot
sudo systemctl start finance-bot
sudo systemctl status finance-bot
```

### Monitoring

1. **Logs**
   - Check logs: `journalctl -u finance-bot -f`
   - Log files: Configure in `logging.basicConfig()`

2. **Health Checks**
   - Monitor bot response time
   - Check database size and performance
   - Monitor memory usage

3. **Backup**
   - Database: `sqlite3 fs_bot.db ".backup backup.db"`
   - Schedule daily backups
   - Store backups securely

### Maintenance

- **Database Cleanup**: Periodically clean old records
- **Update Dependencies**: `pip install -r requirements.txt --upgrade`
- **Restart Bot**: `sudo systemctl restart finance-bot`
- **Check Logs**: Monitor for errors and warnings

---

## Video Tutorials

### Setup and Installation Guide

**Video 1: Initial Setup (5 minutes)**
- Installing Python and dependencies
- Creating `.env` file
- Getting bot token from @BotFather
- Running the bot for the first time

**Video 2: Configuration (3 minutes)**
- Setting up admin IDs
- Database configuration
- Environment variables explained

### Feature Demonstration

**Video 3: User Features (10 minutes)**
- Taking quizzes and earning coins
- Completing interactive scenarios
- Using scam alerts and QR scanner
- Emergency fund tracker
- Leaderboard and referrals

**Video 4: Advanced Features (8 minutes)**
- Educational modules
- Community scam reporting
- Badge system
- Navigation and menus

### Testing Procedures

**Video 5: Testing Guide (7 minutes)**
- Complete testing workflow
- Verifying coin rewards
- Checking database updates
- Testing all navigation paths
- Troubleshooting common issues

---

## Features Overview

### 🎓 Learning Features

- **Multi-Level Quizzes**: Progressive difficulty with unlock system
- **Interactive Scenarios**: Branching conversations with real scam simulations
- **Kazakhstan-Specific Content**: Kaspi, Halyk, Jusan, loan, and job scams
- **Educational Modules**: Step-by-step lessons on subscription scams

### 🚨 Protection Features

- **Real-time Scam Alerts**: City-based warnings (Almaty, Astana, Shymkent, etc.)
- **QR Code Scanner**: Safety verification for QR codes and suspicious links
- **Emergency Fund Tracker**: Monitor and manage financial safety net
- **Community Reports**: Anonymous scam reporting with crowd verification

### 🏆 Gamification

- **Coin System**: Earn coins through quizzes, scenarios, and lessons
- **Badge System**: Unlock achievements and track progress
- **Leaderboards**: Global and regional rankings (Weekly, Monthly, All Time)
- **Progress Tracking**: Monitor quiz completion and scenario scores

### 🎁 Community Features

- **Referral Program**: Generate unique codes, track referrals, earn rewards
- **Anonymous Reporting**: Report scams without revealing identity
- **Crowd Verification**: Community votes on scam reports
- **Regional Leaderboards**: Compete with users in your city

---

## Commands Reference

### User Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Start bot, show main menu | `/start` |
| `/quiz` | Take security quiz | `/quiz` |
| `/tips` | View security tips | `/tips` |
| `/alerts` | View active scam alerts | `/alerts` |
| `/qr` | Check QR code safety | `/qr` |
| `/fund` | Emergency fund tracker | `/fund` |
| `/report_scam` | Report scam anonymously | `/report_scam` |
| `/leaderboard` | View rankings | `/leaderboard` |
| `/referral` | Referral program | `/referral` |
| `/education` | Educational module | `/education` |
| `/myinfo` | View your profile | `/myinfo` |
| `/help` | Show help message | `/help` |

### Admin Commands

| Command | Description | Access |
|---------|-------------|--------|
| `/broadcast` | Send message to all users | Admin only |
| `/analytics` | View bot analytics | Admin only |
| `/bank_create` | Create bank partner account | Admin only |
| `/bank_register` | Register bank client | Admin only |
| `/bank_dashboard` | Bank partner dashboard | Admin only |

---

## Architecture & Technical Implementation

### System Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Telegram Bot API                           │
│              (Telegram Servers - External)                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ HTTP/WebSocket (Long Polling)
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              Financial Security Bot                          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Application Layer (python-telegram-bot)            │  │
│  │  - Command Handlers                                   │  │
│  │  - Callback Handlers                                  │  │
│  │  - Message Handlers                                   │  │
│  │  - Conversation Handlers                             │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Business Logic Layer                                 │  │
│  │  - Quiz System                                        │  │
│  │  - Scenario Engine                                    │  │
│  │  - Gamification (Coins, Badges, Leaderboards)        │  │
│  │  - Alert System                                       │  │
│  │  - Community Features                                 │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Data Access Layer (SQLAlchemy ORM)                  │  │
│  │  - Session Management                                 │  │
│  │  - Model Definitions                                  │  │
│  │  - Query Abstraction                                  │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Background Jobs (APScheduler)                       │  │
│  │  - Daily Analytics Aggregation                        │  │
│  │  - Weekly Leaderboard Reset                           │  │
│  │  - Alert Notifications                                │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ SQL Queries
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              SQLite Database                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  User Data (15+ Tables)                               │  │
│  │  - Users, Referrals                                   │  │
│  │  - Scam Alerts, Community Reports                    │  │
│  │  - Leaderboards, Analytics, Events                    │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Architecture Pattern

**Layered Architecture (3-Tier)**
- **Presentation Layer**: Telegram Bot API handlers
- **Business Logic Layer**: Core functionality modules
- **Data Access Layer**: SQLAlchemy ORM with SQLite

**Design Patterns Used:**
- **Repository Pattern**: Database access through ORM models
- **Handler Pattern**: Command/Callback/Message handlers
- **State Machine Pattern**: Conversation flows (quiz, scenarios, reports)
- **Singleton Pattern**: Database session management
- **Factory Pattern**: Dynamic scenario loading

### Technical Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Language** | Python | 3.9+ | Core development language |
| **Bot Framework** | python-telegram-bot | 20.7 | Telegram Bot API wrapper |
| **ORM** | SQLAlchemy | 2.0.23 | Database abstraction layer |
| **Database** | SQLite | 3.x | Embedded relational database |
| **Scheduler** | APScheduler | 3.10.4 | Background job scheduling |
| **HTTP Client** | requests | 2.31.0 | External API calls |
| **Environment** | python-dotenv | 1.0.0 | Configuration management |

### Code Structure

```
Finance_security_bot/
├── bot.py                    # Main application (4500+ lines)
│   ├── Imports & Config      # Lines 1-70
│   ├── Database Models        # Lines 77-276
│   ├── Database Functions     # Lines 278-400
│   ├── Helper Functions       # Lines 400-1100
│   ├── Command Handlers       # Lines 1100-2500
│   ├── Callback Handlers      # Lines 2500-3500
│   ├── Kazakhstan Features    # Lines 3530-4000
│   └── Main & Scheduler       # Lines 4000-4524
│
├── modules/
│   ├── scenarios.py          # Scenario definitions (1200+ lines)
│   │   └── SCENARIOS dict    # Nested structure by language
│   │
│   └── i18n.py               # Internationalization
│       ├── get_lang()        # Get user language
│       └── set_lang()        # Set user language
│
├── requirements.txt          # Dependencies
├── .env.example             # Configuration template
└── fs_bot.db                # SQLite database (auto-created)
```

### Request Flow Architecture

**Command Flow:**
```
User sends /command
    │
    ▼
Telegram API receives message
    │
    ▼
Application.route_command()
    │
    ▼
CommandHandler matches pattern
    │
    ▼
Handler function executes
    │
    ├──► Database query (if needed)
    │    │
    │    └──► SQLAlchemy ORM
    │         │
    │         └──► SQLite database
    │
    ├──► Business logic processing
    │
    └──► Response sent via Bot API
         │
         └──► User receives message
```

**Callback Query Flow:**
```
User clicks inline button
    │
    ▼
CallbackQueryHandler matches pattern
    │
    ▼
callback_root() routes to specific handler
    │
    ├──► Simple callback (direct response)
    │    └──► Edit message or send new
    │
    └──► Complex callback (state change)
         ├──► Update user_data
         ├──► Database update
         └──► Send response
```

### Security Implementation

**User Identification:**
- Telegram User ID (unique, immutable)
- No password required (Telegram handles auth)
- Admin check via `ADMIN_IDS` list

**Data Protection:**
- All user input sanitized
- SQL injection prevention (SQLAlchemy parameterized queries)
- XSS prevention (Telegram auto-escapes HTML)
- No payment card data stored
- No passwords stored
- User reports are anonymous (user_id only, no personal info)

**Database Security:**
- SQLite file permissions (read/write for bot only)
- No external database connections
- Transaction isolation (ACID compliance)

### Performance & Scalability

**Current Limitations:**
- **SQLite Constraints**: Limited concurrent writes (1 write at a time)
- **Max Users**: ~10,000 active users comfortably
- **Database Size**: Up to 140TB (practical limit: ~100GB)

**Optimization Strategies:**
- Indexes on frequently queried columns
- Connection pooling (SessionLocal)
- Batch operations where possible
- Lazy loading for relationships
- User language cached in memory
- Scenario data loaded once at startup
- Heavy operations moved to scheduler

**Scalability Path:**
- For 10,000+ Users: Migrate to PostgreSQL, add Redis cache
- For 100,000+ Users: Microservices architecture, message queue, CDN

---

## Database Structure

### Core Tables

#### `users`
- `telegram_id` (unique, primary key)
- `username`, `first_name`, `last_name`
- `coins` (default: 0)
- `quizzes_passed` (default: 0)
- `max_unlocked_level` (default: 1)
- `scenario_score` (default: 0)
- `scenario_badges` (comma-separated)
- `created_at`

#### `scam_alerts`
- `alert_type` (kaspi, halyk, jusan, etc.)
- `title`, `description`
- `severity` (critical, high, medium, low)
- `city`, `region`
- `source` (nbrk, community, bank)
- `active` (boolean)
- `created_at`, `expires_at`

#### `community_scam_reports`
- `user_id`
- `scam_type` (phishing, sms, call, investment, job, loan)
- `bank_name` (optional)
- `description`
- `city`
- `verified` (boolean)
- `verification_votes` (integer)
- `created_at`

#### `scam_verification_votes`
- `user_id`
- `report_id`
- `is_scam` (boolean)
- `created_at`

#### `user_locations`
- `user_id` (unique)
- `city` (Almaty, Astana, etc.)
- `region`
- `updated_at`

#### `qr_code_checks`
- `user_id`
- `qr_data`
- `is_safe` (boolean)
- `risk_level` (safe, low, medium, high, dangerous)
- `checked_at`

#### `emergency_funds`
- `user_id` (unique)
- `target_amount`
- `current_amount`
- `monthly_expenses`
- `months_covered`
- `updated_at`

#### `referrals`
- `referrer_id`
- `referred_id`
- `referral_code` (unique)
- `status` (pending, completed)
- `created_at`

#### `leaderboard_entries`
- `user_id`
- `score`
- `rank`
- `period` (all_time, weekly, monthly)
- `updated_at`

#### `user_events`
- `user_id`
- `event_type` (quiz_start, quiz_complete, scenario_start, etc.)
- `event_data` (JSON)
- `timestamp`

#### `analytics_daily`
- `date` (unique)
- `dau` (Daily Active Users)
- `new_users`
- `quiz_completions`
- `scenario_completions`
- `created_at`

### Database Migration Strategy

**Automatic Schema Upgrades:**
- `upgrade_schema()` function runs on startup
- Checks for missing columns using `PRAGMA table_info()` (SQLite)
- Adds columns dynamically without data loss
- Backward compatible with existing data

### Indexing Strategy

**Performance Optimizations:**
- Primary Keys: All tables have auto-incrementing IDs
- Foreign Key Indexes: `user_id`, `referrer_id`, `report_id`
- Query Indexes: `city`, `alert_type`, `event_type`, `timestamp`
- Composite Indexes: `(user_id, period)` for leaderboards
- Unique Constraints: `telegram_id`, `referral_code`

---

## Startup Implementation Plan

### Phase 1: Foundation & Analytics ✅ COMPLETED

**Implemented Features:**
- ✅ Enhanced database schema (15+ tables)
- ✅ User event tracking system
- ✅ Daily analytics aggregation
- ✅ Admin analytics dashboard (`/analytics`)
- ✅ Premium subscription framework
- ✅ Referral program
- ✅ Leaderboard system
- ✅ Content gating for premium features

**Metrics Tracked:**
- Daily Active Users (DAU)
- Weekly/Monthly Active Users (WAU/MAU)
- Total users
- Quiz completion rates
- Scenario completion rates
- Most popular scenarios
- User retention (via event tracking)

### Phase 2: Premium Subscription Model ⏳ READY

**Features:**
- Free Tier: Level 1 quiz, basic scenarios, tips
- Premium Tier: All quiz levels, all scenarios, full leaderboard access
- Content Gating: Quiz levels > 1 require premium
- Subscription Status Tracking: Expiration dates, tier management

**Payment Integration:**
- Structure ready for Stripe/Payme integration
- Purchase handlers implemented
- Database fields ready
- Webhook handlers ready

### Phase 3: Growth Features ✅ COMPLETED

**Referral Program:**
- ✅ Unique referral codes per user
- ✅ Automatic referral processing on signup
- ✅ Referrer rewards: 1 month premium per 3 referrals
- ✅ Referee rewards: 7 days premium trial
- ✅ Real-time statistics and progress tracking

**Leaderboards:**
- ✅ Global leaderboard (all-time)
- ✅ Weekly leaderboard (resets every Monday)
- ✅ Monthly leaderboard
- ✅ User position display with percentage
- ✅ Automatic score updates

### Phase 4: AI & Personalization ⏳ PLANNED

**Planned Features:**
- Personalized learning paths based on weaknesses
- Adaptive difficulty adjustment
- Real-time threat intelligence integration
- Weekly threat reports for premium users

### Phase 5: B2B Features ⏳ PLANNED

**Planned Features:**
- Corporate accounts with multi-user management
- Team leaderboards
- Compliance tracking
- Custom scenarios for organizations
- White-label solution
- API access

### Phase 6: Community Features ✅ PARTIALLY COMPLETED

**Implemented:**
- ✅ Anonymous scam reporting
- ✅ Crowd verification system
- ✅ Community reports database

**Planned:**
- User-generated scenario marketplace
- Forum/discussion features
- Enhanced gamification

### Phase 7: Multi-platform ⏳ PLANNED

**Planned:**
- Mobile app (iOS/Android)
- Browser extension
- Email plugin

### Revenue Streams

1. **B2C Premium Subscriptions**: $9.99/month, $99/year
2. **B2B Enterprise Licenses**: $500-5000/month per organization
3. **B2G Government Contracts**: Custom pricing for financial literacy programs
4. **Scenario Marketplace**: 30% commission on paid user-generated scenarios
5. **API Access**: Pay-per-use for developers
6. **White-label Licensing**: One-time + monthly fees

### Success Metrics

**User Growth:**
- Target: 10,000 users in 3 months
- Target: 1,000 premium subscribers in 6 months
- Target: 10 enterprise clients in 12 months

**Engagement:**
- DAU/MAU ratio > 30%
- Day 7 retention > 40%
- Day 30 retention > 20%
- Average sessions per user > 5/week

**Revenue:**
- $10K MRR in 6 months
- $100K ARR in 12 months
- Premium conversion rate > 5%

---

## Troubleshooting

### Common Issues

1. **Bot doesn't start**
   - Check `BOT_TOKEN` in `.env` file
   - Verify Python version: `python3 --version` (should be 3.9+)
   - Check dependencies: `pip install -r requirements.txt`

2. **Database errors**
   - Ensure write permissions in project directory
   - Check `DATABASE_URL` in `.env`
   - Try deleting `fs_bot.db` and restarting (will recreate)

3. **Commands not working**
   - Verify bot is running: check logs
   - Restart bot: `sudo systemctl restart finance-bot`
   - Check Telegram for bot status

4. **Coins not updating**
   - Verify database commits are happening
   - Check logs for errors
   - Ensure user record exists in database

5. **Navigation issues**
   - Check callback handlers are registered
   - Verify button callback_data matches handler patterns
   - Check for "message not modified" errors in logs

### Error Messages

**"BOT_TOKEN required in environment"**
- Solution: Add `BOT_TOKEN` to `.env` file

**"Message is not modified"**
- Solution: This is normal when trying to edit a message with identical content. The bot handles this gracefully.

**"Database locked"**
- Solution: Ensure only one instance of the bot is running. SQLite doesn't support concurrent writes well.

**"Module not found"**
- Solution: Install dependencies: `pip install -r requirements.txt`

---

## Languages

The bot supports three languages:

- 🇷🇺 **Russian** (default): `ru`
- 🇰🇿 **Kazakh**: `kk`
- 🇬🇧 **English**: `en`

Users can change language via the main menu or `/start` command.

---

## Security & Privacy

- ✅ **Anonymous Reporting**: Scam reports don't reveal user identity
- ✅ **No Payment Info**: Bot doesn't collect or store payment information
- ✅ **Secure Database**: All data stored securely in SQLite database
- ✅ **Community Verification**: Scam reports verified by community votes
- ✅ **Free Access**: All features are free, no subscriptions required

---

## Background Jobs (APScheduler)

### Scheduled Tasks

**Daily Analytics Aggregation**
- Runs at midnight UTC
- Aggregates daily metrics (DAU, new users, completions)
- Stores in `analytics_daily` table

**Weekly Leaderboard Reset**
- Runs every Monday at midnight
- Resets weekly leaderboard scores
- Maintains all-time and monthly leaderboards

**Scheduled Tips** (Future)
- Daily security tips sent to subscribed users
- Configurable timing

---

## Project Structure

```
Finance_security_bot/
├── bot.py                 # Main bot logic and handlers
├── requirements.txt       # Python dependencies
├── .env                  # Environment variables (create from .env.example)
├── .env.example         # Environment template
├── README.md            # This file
├── modules/
│   ├── scenarios.py     # Interactive scenario definitions
│   └── i18n.py          # Internationalization (language settings)
└── fs_bot.db            # SQLite database (created automatically)
```

---

## Contributing

This is an educational project. Contributions welcome for:
- New scenarios and quiz questions
- Language translations
- Bug fixes and improvements
- Documentation updates

---

## License

Educational and security awareness purposes.

---

## Support

- **In-Bot Help**: Use `/help` command
- **Report Issues**: Use `/report_scam` or contact admin
- **Check Alerts**: Use `/alerts` for latest scam warnings

---

**Made for Kazakhstan** 🇰🇿 | **Protecting Users from Financial Scams** 🛡️

---

## Quick Reference

### First-Time Setup Checklist

- [ ] Install Python 3.9+
- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Create `.env` file with `BOT_TOKEN`
- [ ] Get bot token from @BotFather
- [ ] Run bot: `python bot.py`
- [ ] Test with `/start` command

### Production Deployment Checklist

- [ ] Set up VPS/server
- [ ] Install system dependencies
- [ ] Clone repository
- [ ] Create virtual environment
- [ ] Configure `.env` file
- [ ] Set up systemd service
- [ ] Configure webhook (optional)
- [ ] Set up monitoring
- [ ] Schedule backups
- [ ] Test all features

---

*Last Updated: 2025*
*Version: 2.0*
*Status: Production Ready *
