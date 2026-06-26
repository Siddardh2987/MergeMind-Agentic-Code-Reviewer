# 🧠 MergeMind — Setup Guide

Complete setup guide for MergeMind, the Agentic AI GitHub Code Reviewer.

---

## 📖 Project Overview

MergeMind is an AI-powered code review system that automatically analyzes GitHub commits using multiple specialized AI agents. It consists of:

1. **FastAPI Backend** — Receives GitHub webhooks, orchestrates AI reviews, stores results
2. **Multi-Agent Pipeline** — Four specialist agents (Code Quality, Bug Detection, Security, Performance) + an Aggregator
3. **SQLite Database** — Stores review results for retrieval
4. **Chrome Extension** — Displays review results directly on GitHub pages

### Architecture Flow

```
GitHub Push Event
    → GitHub Webhook (POST /webhook)
    → FastAPI Backend receives payload
    → Creates pending review in DB & broadcasts it via WebSockets
    → Fetches commit diff + full file context from GitHub API
    → Runs 4 AI agents in parallel:
        ├── 🐞 Bug Detection Agent
        ├── 🔒 Security Agent
        ├── ⚡ Performance Agent
        └── ✨ Code Quality Agent
    → Aggregator combines & deduplicates results
    → Stores final review in SQLite
    → Broadcasts completed review details via WebSocket to connected subscribers
    → Chrome Extension receives real-time payload via /ws/review/{commit_sha}
    → Injected floating widget updates on GitHub page instantly
```

---

## 🛠️ Installation

### Prerequisites

- **Python 3.11+** — [Download](https://www.python.org/downloads/)
- **Google Chrome** — For the extension
- **Git** — For cloning the repo
- **Gemini API Key** — [Get one](https://aistudio.google.com/apikey)
- **GitHub Account** — For webhook configuration
- **ngrok** (for local development) — [Download](https://ngrok.com/download)

### Step 1: Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/MergeMind.git
cd MergeMind
```

### Step 2: Set Up the Backend

```bash
# Navigate to backend directory
cd backend

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables

```bash
# Copy the example env file
cp .env.example .env

# Edit .env with your actual values
# (See the Environment Variables section below for details)
```

### Step 4: Load the Chrome Extension

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable **Developer mode** (toggle in top-right corner)
3. Click **Load unpacked**
4. Select the `extension/` directory from the MergeMind project
5. The MergeMind icon (🧠) should appear in your Chrome toolbar

---

## 🔐 Environment Variables

All environment variables are configured in `backend/.env`. Here's every variable explained:

### Required Variables

| Variable | Description | Example Value |
|----------|-------------|---------------|
| `GEMINI_API_KEY` | Your Gemini API key. Required for AI agents. | `AIza...` |
| `GITHUB_WEBHOOK_SECRET` | Secret for validating webhook payloads. Must match the secret you set in GitHub's webhook configuration. | `mysecretkey123` |
| `GITHUB_TOKEN` | GitHub Personal Access Token with `repo` scope. Used to fetch diffs and file contents via GitHub API. | `ghp_abc123...` |

### Optional Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `GEMINI_MODEL` | Gemini model for reviews. `gemini-2.0-flash` is recommended for cost/speed balance. | `gemini-2.0-flash` | `gemini-2.5-pro` |
| `DATABASE_URL` | SQLite database file path. | `sqlite:///./mergemind.db` | `sqlite:///./data/reviews.db` |
| `BACKEND_URL` | Public URL of the backend. Update after deployment. | `http://localhost:8000` | `https://mergemind-api.onrender.com` |
| `CORS_ORIGINS` | Comma-separated list of allowed CORS origins. | `chrome-extension://*,http://localhost:3000` | `chrome-extension://abcdef123,https://github.com` |

### Generating a Webhook Secret

```bash
# Python one-liner to generate a secure random secret
python -c "import secrets; print(secrets.token_hex(32))"
```

### Creating a GitHub Personal Access Token

1. Go to [GitHub Settings → Tokens](https://github.com/settings/tokens)
2. Click **Generate new token (classic)**
3. Give it a descriptive name (e.g., "MergeMind Bot")
4. Select the `repo` scope (full control of private repositories)
5. Click **Generate token**
6. Copy the token and paste it as `GITHUB_TOKEN` in your `.env` file

> ⚠️ **Important**: The token is only shown once! Save it immediately.

---

## 🔗 GitHub Webhook Setup

### Step 1: Configure the Webhook

1. Go to your GitHub repository → **Settings** → **Webhooks**
2. Click **Add webhook**
3. Configure:
   - **Payload URL**: `https://YOUR_BACKEND_URL/webhook`
     - For local dev: Use your ngrok URL (e.g., `https://abc123.ngrok.io/webhook`)
     - For production: Use your deployed URL
   - **Content type**: `application/json`
   - **Secret**: The same value as `GITHUB_WEBHOOK_SECRET` in your `.env`
   - **Which events?**: Select **Just the push event**
   - **Active**: ✅ Check this box

4. Click **Add webhook**

### Step 2: Verify the Webhook

After adding the webhook, GitHub sends a ping event. Check:
- The webhook shows a ✅ green checkmark in GitHub's webhook settings
- Your backend logs show: `ℹ️ Ignoring non-push event: ping`

---

## 💻 Local Development

### Running the Backend

```bash
cd backend

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Start the FastAPI server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The server will be available at:
- **API**: http://localhost:8000
- **Swagger Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

### Running the Extension

1. Make sure the backend is running
2. Load the extension in Chrome (see Installation Step 4)
3. Navigate to any GitHub repository page
4. The extension will automatically detect the repo context

### Testing the Webhook Locally

You can simulate a GitHub webhook push event:

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: push" \
  -d '{
    "head_commit": {
      "id": "abc123def456789..."
    },
    "repository": {
      "full_name": "your-username/your-repo"
    },
    "pusher": {
      "name": "your-username"
    },
    "sender": {
      "id": 12345
    }
  }'
```

> Note: Without a valid `X-Hub-Signature-256` header, this will only work if `GITHUB_WEBHOOK_SECRET` is empty (development mode).

---

## 🌐 ngrok Setup

ngrok creates a public URL that tunnels to your local server, allowing GitHub to send webhooks to your machine.

### Step 1: Install ngrok

```bash
# Windows (with Chocolatey)
choco install ngrok

# macOS (with Homebrew)
brew install ngrok

# Or download from: https://ngrok.com/download
```

### Step 2: Authenticate ngrok

```bash
# Sign up at ngrok.com and get your auth token
ngrok config add-authtoken YOUR_AUTH_TOKEN
```

### Step 3: Start ngrok

```bash
# Tunnel to your local backend
ngrok http 8000
```

ngrok will display a URL like:
```
Forwarding  https://abc123.ngrok-free.app -> http://localhost:8000
```

### Step 4: Update GitHub Webhook

Use the ngrok URL as your webhook Payload URL:
```
https://abc123.ngrok-free.app/webhook
```

> ⚠️ **Note**: Free ngrok URLs change every time you restart ngrok. You'll need to update the GitHub webhook URL each time.

---

## 🚀 Deployment

### Deploying to Render

[Render](https://render.com) is recommended for easy Python deployment.

#### Step 1: Create a Render Account

Sign up at [render.com](https://render.com) and connect your GitHub account.

#### Step 2: Create a New Web Service

1. Click **New** → **Web Service**
2. Connect your MergeMind repository
3. Configure:
   - **Name**: `mergemind-api`
   - **Region**: Choose closest to you
   - **Branch**: `main`
   - **Root Directory**: `backend`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

#### Step 3: Set Environment Variables

In the Render dashboard, go to **Environment** and add:

| Key | Value |
|-----|-------|
| `GEMINI_API_KEY` | `AIza...` |
| `GITHUB_WEBHOOK_SECRET` | Your webhook secret |
| `GITHUB_TOKEN` | `ghp_...` |
| `BACKEND_URL` | `https://mergemind-api.onrender.com` |
| `DATABASE_URL` | `sqlite:///./mergemind.db` |
| `CORS_ORIGINS` | `chrome-extension://*` |

#### Step 4: Deploy

Click **Create Web Service**. Render will build and deploy automatically.

Your API will be available at: `https://mergemind-api.onrender.com`

### Deploying to Railway

[Railway](https://railway.app) is another great option.

1. Sign up at [railway.app](https://railway.app)
2. Click **New Project** → **Deploy from GitHub Repo**
3. Select your MergeMind repository
4. Set the **Root Directory** to `backend`
5. Add environment variables (same as Render above)
6. Railway auto-detects Python and deploys

Your API will be available at the Railway-provided URL.

### Database Considerations

- **SQLite** works great for low-to-medium traffic. The database file is stored on the server's filesystem.
- **Render/Railway**: On free tiers, the filesystem is ephemeral — the database resets on each deploy. For persistence, consider upgrading to a paid tier or switching to PostgreSQL.
- **To switch to PostgreSQL**: Update `DATABASE_URL` to a PostgreSQL connection string (e.g., from Render's managed PostgreSQL or Supabase).

---

## 🔄 Post-Deployment Changes

After deploying the backend, you **must** update these values:

### 1. Chrome Extension — Backend URL

Update the backend URL in the extension:

**Option A: Via Extension Popup**
1. Click the MergeMind icon in Chrome toolbar
2. Update the **Backend URL** field to your deployed URL
3. Click the save button (✓)

**Option B: Edit config.js**
1. Open `extension/config.js`
2. Change `BACKEND_URL` to your deployed URL:
   ```javascript
   BACKEND_URL: "https://mergemind-api.onrender.com",
   ```
3. Reload the extension in `chrome://extensions/`

### 2. GitHub Webhook URL

1. Go to your GitHub repo → **Settings** → **Webhooks**
2. Edit the webhook
3. Update **Payload URL** to: `https://YOUR_DEPLOYED_URL/webhook`

### 3. CORS Origins (if needed)

If you get CORS errors, update the `CORS_ORIGINS` environment variable to include your Chrome extension's ID:

```
CORS_ORIGINS=chrome-extension://YOUR_EXTENSION_ID
```

You can find your extension ID in `chrome://extensions/`.

---

## 🔧 Troubleshooting

### Common Issues

| Problem | Solution |
|---------|----------|
| **Webhook returns 401** | Check that `GITHUB_WEBHOOK_SECRET` matches between `.env` and GitHub webhook settings |
| **"Backend unreachable" in extension** | Verify the backend URL is correct and the server is running. Check CORS settings. |
| **Review stuck on "pending"** | Check backend logs for errors. Ensure `GEMINI_API_KEY` is valid. |
| **No diff fetched from GitHub** | Verify `GITHUB_TOKEN` has `repo` scope and is not expired. |
| **CORS errors in console** | Add your Chrome extension origin to `CORS_ORIGINS` |
| **Extension not detecting GitHub page** | Refresh the page. Check that the content script is loaded in `chrome://extensions/` → Details |
| **Rate limit errors from GitHub** | GitHub API has rate limits (5000 req/hr with token). Wait or use a different token. |
| **Rate limit errors from Gemini** | Check your Gemini API usage limits. Consider using `gemini-2.0-flash` for lower costs. |
| **Database locked error** | SQLite doesn't support concurrent writes well. This usually resolves itself. For high traffic, switch to PostgreSQL. |

### Checking Backend Logs

```bash
# If running locally
uvicorn app.main:app --reload --log-level debug

# On Render
# Check the "Logs" tab in your Render dashboard

# On Railway
# Check the "Deployments" → "Logs" section
```

### Testing API Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Get review for a commit
curl http://localhost:8000/review/COMMIT_SHA

# Get reviews for a user
curl http://localhost:8000/reviews/USERNAME
```

---

## 💡 Extra Tips & Useful Notes

### Scaling Ideas

1. **Queue System**: For high traffic, replace `asyncio.create_task` with a proper task queue (Celery, Redis Queue, or Bull). This prevents overwhelming the server with concurrent reviews.

2. **Caching**: Cache file contents from GitHub to avoid re-fetching the same files across multiple reviews. Redis works great for this.

3. **PostgreSQL**: For production, switch from SQLite to PostgreSQL. Just change the `DATABASE_URL`:
   ```
   DATABASE_URL=postgresql://user:pass@host:5432/mergemind
   ```

4. **Multiple Repos**: The current setup works with any number of repos — just add the webhook to each repo.

### Cost Optimization

- **gemini-2.0-flash** has a generous free tier and low cost on paid plans. A typical review uses ~2000-5000 tokens across 4 agents.
- For higher quality reviews, use `gemini-2.5-pro`.
- To reduce costs further, you could skip agents for trivial commits (e.g., only documentation changes).

### Security Best Practices

1. **Always set GITHUB_WEBHOOK_SECRET** in production. Without it, anyone can trigger reviews.
2. **Rotate your tokens** periodically (GitHub PAT, Gemini API key).
3. **Don't commit `.env`** — it's gitignored by default, but double-check.
4. **HTTPS only** in production — never expose the webhook over HTTP.

### Debugging Tips

1. **Check Swagger docs** at `/docs` — you can test all endpoints interactively.
2. **Enable SQL logging** by setting `echo=True` in `database.py` to see all SQL queries.
3. **Use Chrome DevTools** → Console to see extension logs (filter by "MergeMind").
4. **Webhook delivery log** — GitHub shows the full payload and response for each webhook delivery in the webhook settings page.

### Future Improvements

1. **PR Review Support** — Extend to review pull requests, not just individual commits.
2. **GitHub Comments** — Post review results as GitHub commit comments automatically.
5. **Custom Rules** — Let users configure which checks to enable/disable per repo.
6. **Team Dashboard** — Web dashboard showing review trends across a team.
7. **Multi-LLM Support** — Add support for Claude, OpenAI, or local models (Ollama).

---

## 📁 Project Structure

```
MergeMind/
├── backend/                        # FastAPI Application
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI entry point
│   │   ├── config.py               # Environment variables
│   │   ├── database.py             # SQLite/SQLAlchemy setup
│   │   ├── models.py               # ORM models
│   │   ├── schemas.py              # Pydantic schemas
│   │   ├── routers/
│   │   │   ├── webhook.py          # POST /webhook
│   │   │   ├── reviews.py          # HTTP endpoints for reviews
│   │   │   ├── settings.py         # HTTP endpoints for developer strictness settings
│   │   │   └── ws.py               # WebSocket endpoints for real-time updates
│   │   ├── services/
│   │   │   ├── github_service.py   # GitHub API interactions
│   │   │   ├── review_service.py   # Review orchestration pipeline
│   │   │   └── ws_manager.py       # WebSocket client connection manager
│   │   ├── agents/
│   │   │   ├── base_agent.py       # Base agent class
│   │   │   ├── code_quality.py     # Code Quality Agent
│   │   │   ├── bug_detection.py    # Bug Detection Agent
│   │   │   ├── security.py         # Security Agent
│   │   │   ├── performance.py      # Performance Agent
│   │   │   └── aggregator.py       # Aggregator Agent
│   │   └── utils/
│   │       ├── context_builder.py  # Enriched context builder
│   │       └── diff_parser.py      # Unified diff parser
│   ├── requirements.txt            # Python dependencies
│   ├── .env.example                # Example configuration template
│   └── .env                        # Local credentials (gitignored)
│
├── extension/                      # Chrome Extension (Manifest V3)
│   ├── src/                        # React UI Components (Vite App)
│   │   ├── components/             # UI Components (ReviewList, Settings, etc.)
│   │   ├── App.jsx                 # Popup Main Application
│   │   ├── main.jsx                # Popup entry point
│   │   └── index.css               # Popup premium UI styles
│   ├── content/                    # Injected scripts and styles for GitHub pages
│   │   ├── content.js              # Injector script & WebSockets connection
│   │   └── content.css             # Floating widget stylesheet
│   ├── background/                 # Extension background processes
│   │   └── background.js           # Chrome runtime event broker
│   ├── popup/                      # Built Vite output directory
│   │   ├── index.html              # Built popup template
│   │   ├── popup.css               # Bundled popup CSS
│   │   └── popup.js                # Bundled popup JS
│   ├── icons/                      # Extension icons
│   ├── manifest.json               # Extension configuration manifest
│   ├── package.json                # Node package script manager
│   └── vite.config.js              # Vite packaging & build configuration
│
├── SETUP.md                        # This file
└── README.md                       # High-level overview & backend flow
```
