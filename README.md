# 🎁 Ultra Giveaway Bot

Production-grade Telegram giveaway and raffle bot with server-side validation, atomic number claiming, DB-backed FSM, and zero in-memory state loss.

Built with **Python 3.12**, **aiogram 3.x** (webhook mode only), **FastAPI**, **SQLAlchemy 2.0 async**, and **PostgreSQL** (Neon / Render).

---

## 🚀 Key Features & Architecture

- **Webhook-Only Execution:** High-performance FastAPI server running on Uvicorn. The webhook endpoint returns `200 OK` in `< 100ms` by offloading update processing to asynchronous tasks.
- **Atomic 10x10 Number Grid:** Participants select numbers 1–100 via an interactive 10x10 inline button grid. Number claims use atomic database updates with race-condition prevention (`UPDATE ... WHERE number IS NULL AND NOT EXISTS (...)`).
- **Resilient DB-Backed FSM:** Multi-step actions (drafting giveaways, submitting names, payment proofs, reviews) are persisted in `pending_actions`, ensuring zero state is lost across cold starts or restarts.
- **Idempotency & Duplicate Protection:** All Telegram `update_id`s are logged to `processed_updates` (with 24h automatic cleanup) to skip duplicate deliveries.
- **Strict Role-Based Security:** Server-side DB permission checks for Hosts and Admins. Callback payloads are never blindly trusted.
- **Clean Ops:** `/healthz` endpoint with active database ping, structured JSON logging to stdout without PII leakage, and graceful SIGTERM lifecycle handling.

---

## 📁 Repository Structure

```
ultra-giveaway-bot/
├── app/
│   ├── bot/
│   │   ├── handlers/         # Aiogram handlers (host, participant, actions, common)
│   │   ├── keyboards/        # Inline keyboards (10x10 grid, draft menu, approvals)
│   │   ├── middlewares/      # User sync, sliding-window rate limit, error handler
│   │   ├── instance.py       # Bot and Dispatcher initialization
│   │   └── utils.py          # Message chunking & caption truncating
│   ├── models/               # SQLAlchemy 2.0 ORM models
│   ├── services/             # Business logic (atomic claims, FSM, draw, audit)
│   ├── web/                  # FastAPI app, lifespan, /healthz, webhook route
│   ├── config.py             # Pydantic Settings (.env configuration)
│   ├── database.py           # Async SQLAlchemy engine with serverless pool
│   └── logging_config.py     # Production JSON structured logging
├── alembic/                  # Database migration scripts
│   ├── versions/             # Migration revisions
│   └── env.py
├── tests/                    # Pytest test suite (races, restarts, permissions, etc.)
├── Dockerfile                # Multi-stage container definition
├── render.yaml               # Render Infrastructure-as-Code blueprint
├── requirements.txt          # Python dependencies
├── .env.example              # Template environment variables
└── README.md
```

---

## 🛠️ Local Development (with ngrok)

### 1. Prerequisites
- Python 3.12+
- PostgreSQL database (or Neon serverless Postgres)
- [ngrok](https://ngrok.com/) for exposing your local webhook port to Telegram

### 2. Setup Virtual Environment & Install Dependencies
```bash
python -m venv venv
# Linux / macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Fill in your credentials:
```env
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/giveaway_db?ssl=require
WEBHOOK_SECRET=your_high_entropy_secret_token_123
WEBHOOK_BASE_URL=https://your-subdomain.ngrok-free.app
ADMIN_CHAT_ID=123456789
LOG_LEVEL=INFO
PORT=8000
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=0
```

### 4. Run Database Migrations
```bash
alembic upgrade head
```

### 5. Launch ngrok
In a separate terminal:
```bash
ngrok http 8000
```
Copy the generated HTTPS URL (e.g. `https://abc123.ngrok-free.app`) and set it as `WEBHOOK_BASE_URL` in your `.env`.

### 6. Start the Webhook Server
```bash
uvicorn app.web.app:app --host 0.0.0.0 --port 8000 --reload
```
On startup, the bot automatically registers its webhook with Telegram using your `WEBHOOK_SECRET`.

---

## 🗄️ Database Migrations

Generate a new migration:
```bash
alembic revision --autogenerate -m "describe_changes"
```

Apply migrations:
```bash
alembic upgrade head
```

Rollback one migration:
```bash
alembic downgrade -1
```

---

## 📡 Webhook Management via cURL

### Check Webhook Status
```bash
curl -s "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo" | jq .
```

### Manually Set Webhook
```bash
curl -F "url=<WEBHOOK_BASE_URL>/webhook" \
     -F "secret_token=<WEBHOOK_SECRET>" \
     -F "allowed_updates=[\"message\",\"callback_query\",\"chat_member\"]" \
     -F "drop_pending_updates=false" \
     "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook"
```

### Delete Webhook (Switch back to polling if needed)
```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/deleteWebhook?drop_pending_updates=false"
```

---

## ☁️ Deploying to Render

### Option A: Deploy via `render.yaml` Blueprint (Recommended)
1. Push your repository to GitHub or GitLab.
2. In the Render Dashboard, navigate to **Blueprints** -> **New Blueprint Instance**.
3. Select your repository. Render reads `render.yaml` automatically.
4. Fill in the required environment variables:
   - `BOT_TOKEN`: From Telegram @BotFather.
   - `DATABASE_URL`: Your Neon Postgres connection string.
   - `WEBHOOK_BASE_URL`: Will be `https://<your-service-name>.onrender.com`.
   - `ADMIN_CHAT_ID`: Your Telegram numeric User ID.
5. Click **Apply**.

### Option B: Manual Web Service Deployment
1. Go to **Render Dashboard** -> **New** -> **Web Service**.
2. Select your repository.
3. Configure the settings:
   - **Environment:** Docker
   - **Branch:** main
   - **Plan:** Free
   - **Health Check Path:** `/healthz`
4. Under **Environment Variables**, add:
   - `BOT_TOKEN`
   - `DATABASE_URL` (format: `postgresql+asyncpg://user:pass@host/db?ssl=require`)
   - `WEBHOOK_SECRET` (generate a random 32+ char alphanumeric token)
   - `WEBHOOK_BASE_URL` (e.g. `https://ultra-giveaway-bot.onrender.com`)
   - `ADMIN_CHAT_ID`
   - `DATABASE_POOL_SIZE` = `5`
   - `DATABASE_MAX_OVERFLOW` = `0`
5. Click **Create Web Service**.

Render runs `alembic upgrade head` followed by `uvicorn` on container boot.

---

## 🔒 Rotating Bot Tokens & Webhook Secrets

To rotate your `BOT_TOKEN` or `WEBHOOK_SECRET` without downtime:
1. Generate a new secret token or request a new Bot Token from `@BotFather`.
2. Update the environment variables in your Render Dashboard.
3. Trigger a **Manual Deploy** with **Clear Build Cache**.
4. The application lifespan hook will automatically call `set_webhook` with the updated credentials during startup.

---

## 🧪 Running Automated Tests

Run the complete test suite:
```bash
pytest -v
```

The test suite covers:
- **Concurrent Number Claims:** Two participants race for the same number simultaneously; exactly one wins and the loser gets an updated grid.
- **FSM Restart Persistence:** Process restart mid-number pick resumes flawlessly from `pending_actions`.
- **Update Idempotency:** Duplicate update delivery by Telegram is safely skipped.
- **RBAC Checks:** Non-admins cannot approve entries; non-hosts cannot draw winners.
- **Proof Resubmission Limits:** Rejected participant can resubmit proof once, blocked on second attempt.
- **Participant Cap:** Blocks the 101st participant when all 100 numbers are filled.
