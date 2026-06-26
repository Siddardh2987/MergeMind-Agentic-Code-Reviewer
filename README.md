# 🧠 MergeMind

**An Agentic AI Code Reviewer powered by GitHub Webhooks and a Chrome Extension.**

MergeMind automatically reviews your GitHub commits using multiple specialized AI agents, identifying bugs, security vulnerabilities, performance issues, and code quality concerns — then displays the results directly on GitHub via a sleek Chrome extension.

---

## ✨ Features

- **🔗 GitHub Webhook Integration** — Automatically triggers on every push event to analyze incoming changes.
- **🤖 Multi-Agent AI Review** — Four specialist agents analyze code in parallel using Google Gemini API:
  - 🐞 **Bug Detection Agent** — Analyzes logical flow, edge cases, type safety, and runtime exceptions.
  - 🔒 **Security Agent** — Scans for vulnerabilities, OWASP Top 10 risks, hardcoded credentials, and unsafe library usage.
  - ⚡ **Performance Agent** — Flags resource leaks, redundant operations, suboptimal queries, and high time/space complexity.
  - ✨ **Code Quality Agent** — Evaluates readability, maintainability, naming conventions, docstrings, and adherence to clean code principles.
- **📊 Smart Aggregator** — Synthesizes, de-duplicates, and prioritizes findings from the four specialist agents.
- **⚙️ Configurable Strictness** — Settings for **Lenient**, **Moderate**, or **Strict** code reviews to adapt to different development phases.
- **⚡ Real-Time WebSocket Updates** — Replaces traditional polling with WebSocket connections (`/ws/review/{commit_sha}`) to instantly push review status updates (pending ➔ processing ➔ completed) directly to the GitHub page widget.
- **🧩 Manifest V3 Chrome Extension** — Beautiful floating widget injected directly into GitHub commit/PR pages:
  - Responsive floating review widget with loading animations.
  - Interactive popup to configure backend server URL, review strictness, and see recent commits.
  - Seamless communication between content scripts, background workers, and the React-based popup.
- **💾 Persistent SQLite Storage** — Tracks review history, commits, settings, and findings.
- **🎯 Rich Context Analysis** — Pulls complete function definitions and file context from GitHub, avoiding naive line-by-line diff assessments.

---

## 🏗️ Architecture

```
                       ┌──────────────────────────────────────────────┐
                       │               GitHub Webhook                 │
                       └──────────────────────┬───────────────────────┘
                                              │ (POST /webhook)
                                              ▼
                       ┌──────────────────────────────────────────────┐
                       │               FastAPI Backend                │
                       └──────────────┬──────────────┬────────────────┘
                                      │              │
               ┌──────────────────────┘              └──────────────────────┐
               │                                                            │
               ▼                                                            ▼
 ┌───────────────────────────┐                                ┌───────────────────────────┐
 │   GitHub API Client       │                                │  SQLAlchemy + SQLite      │
 │   (Fetch Diff & Context)  │                                │  (Stores history/records) │
 └─────────────┬─────────────┘                                └───────────────────────────┘
               │
               ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                       Multi-Agent Pipeline (Gemini)                      │
 │                                                                          │
 │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────────┐  │
 │  │🐞 Bug Detect │ │🔒 Security   │ │⚡ Performance│ │✨ Code Quality  │  │
 │  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └────────┬────────┘  │
 │         │                │                │                  │           │
 │         └────────────────┼────────────────┼──────────────────┘           │
 │                          ▼                                               │
 │                   ┌──────────────┐                                       │
 │                   │ Aggregator   │                                       │
 │                   └──────┬───────┘                                       │
 └──────────────────────────┼───────────────────────────────────────────────┘
                            │
                            ▼
               ┌───────────────────────────┐
               │    WebSocket Broadcaster  │
               └────────────┬──────────────┘
                            │ (Real-time events)
                            ▼
               ┌───────────────────────────┐
               │   Chrome Extension (MV3)  │
               │   - Injected Widget UI    │
               │   - React/Vite Popup UI   │
               └───────────────────────────┘
```

---

## 🔄 Backend Pipeline Flow

This diagram illustrates the step-by-step logic executed by the FastAPI backend when reviewing a commit:

```
                      ┌────────────────────────────────────────┐
                      │          GitHub Push Webhook           │
                      └───────────────────┬────────────────────┘
                                          │ POST /webhook
                                          ▼
                      ┌────────────────────────────────────────┐
                      │          FastAPI Webhook Route         │
                      │   - Validates webhook secret signature │
                      │   - Creates a 'pending' Review in DB   │
                      │   - Broadcasts 'pending' via WebSockets│
                      └───────────────────┬────────────────────┘
                                          │ Launches Async Task
                                          ▼
                      ┌────────────────────────────────────────┐
                      │    Async Review Pipeline Task (BG)     │
                      │   - Updates database status to 'active'│
                      │   - Broadcasts 'active' via WebSockets  │
                      └───────────────────┬────────────────────┘
                                          │
                   ┌──────────────────────┴──────────────────────┐
                   │                                             │
                   ▼                                             ▼
     ┌───────────────────────────┐                 ┌───────────────────────────┐
     │    Fetch Commit Diff      │                 │   Fetch Settings          │
     │    from GitHub API        │                 │   for Committer           │
     └─────────────┬─────────────┘                 │   (Lenient/Moderate/Strict)   │
                   │                               └─────────────┬─────────────┘
                   ▼                                             │
     ┌───────────────────────────┐                               │
     │    Parse Diff             │                               │
     │    Identify modified lines│                               │
     └─────────────┬─────────────┘                               │
                   │                                             │
                   ▼                                             │
     ┌───────────────────────────┐                               │
     │    Fetch File Content     │                               │
     │    Fetch full source files│                               │
     └─────────────┬─────────────┘                               │
                   │                                             │
                   ▼                                             │
     ┌───────────────────────────┐                               │
     │    Build Context          │                               │
     │    Extract functions, AST │                               │
     │    surrounding diff lines │                               │
     └─────────────┬─────────────┘                               │
                   │                                             │
                   └──────────────────────┬──────────────────────┘
                                          │
                                          ▼
                      ┌────────────────────────────────────────┐
                      │      Parallel Multi-Agent Stage        │
                      │  (Requests concurrent Gemini LLM runs) │
                      │                                        │
                      │  ┌──────────────┐    ┌──────────────┐  │
                      │  │ 🐞 Bug Agent │    │ 🔒 Sec Agent │  │
                      │  └──────┬───────┘    └──────┬───────┘  │
                      │         │                   │          │
                      │  ┌──────┴───────┐    ┌──────┴───────┐  │
                      │  │ ⚡ Perf Agent │    │ ✨ Quality Ag │  │
                      │  └──────┬───────┘    └──────┬───────┘  │
                      │         │                   │          │
                      │         └─────────┬─────────┘          │
                      │                   ▼                    │
                      │             Findings List              │
                      └───────────────────┬────────────────────┘
                                          │
                                          ▼
                      ┌────────────────────────────────────────┐
                      │          Aggregator Agent              │
                      │   - De-duplicates overlaps/redundancies│
                      │   - Synthesizes summary metrics        │
                      │   - Formats final JSON payload         │
                      └───────────────────┬────────────────────┘
                                          │
                                          ▼
                      ┌────────────────────────────────────────┐
                      │          Completion & Broadcast        │
                      │   - Saves summary/issues JSON to SQLite│
                      │   - Updates status to 'completed'      │
                      │   - Pushes final payload to WebSocket  │
                      │     subscribers in real-time           │
                      └────────────────────────────────────────┘
```

### Flow Breakdown:
1. **Ingestion & Validation**: The webhook router validates GitHub signature headers for security. If valid, a new review record is initialized as `pending`, and the review pipeline runs asynchronously in the background so GitHub receives a `200 OK` response instantly.
2. **Context Enrichment**: The review service parses the diff, fetches full file content around changes, and packages it into enriched context (including parent/surrounding methods and imports) rather than raw, isolated diff segments.
3. **Strictness Check**: Committer strictness settings (Lenient, Moderate, Strict) are pulled from SQLite database to customize review criteria.
4. **Specialist Agents execution**: Concurrently triggers Bug Detection, Security, Performance, and Code Quality agents to critique the code base based on strictness.
5. **Aggregation & Deduplication**: The Aggregator agent cleans, de-duplicates, and prioritizes findings from the specialists.
6. **Real-time Push**: Results are committed to the database, status changes to `completed`, and the final review payload is broadcast to connected WebSockets to render instantly in the Chrome extension.

---

## 📁 Repository Structure

```
MergeMind/
├── backend/                  # FastAPI Application
│   ├── app/
│   │   ├── agents/          # AI Agent prompt definitions & orchestrator
│   │   │   ├── base_agent.py
│   │   │   ├── bug_detection.py
│   │   │   ├── security.py
│   │   │   ├── performance.py
│   │   │   ├── code_quality.py
│   │   │   └── aggregator.py
│   │   ├── routers/         # API endpoints (webhook, reviews, settings)
│   │   ├── services/        # Business logic (GitHub & AI communication)
│   │   ├── models.py        # SQLAlchemy Database models
│   │   ├── schemas.py       # Pydantic schemas
│   │   ├── database.py      # SQLite connection & session management
│   │   └── main.py          # FastAPI application entrypoint
│   ├── requirements.txt     # Python dependencies
│   └── .env.example         # Example configuration
│
├── extension/                # Chrome Extension (Manifest V3)
│   ├── src/                 # React UI Components (Vite App)
│   │   ├── components/      # UI Elements (ReviewList, Settings, etc.)
│   │   ├── App.jsx          # Popup Main Application
│   │   └── index.css        # Premium UI styles
│   ├── content/             # Injected scripts and stylesheets for GitHub
│   │   ├── content.js       # Context detector & floating widget injector
│   │   └── content.css      # Floating widget stylesheet
│   ├── background/          # Extension service worker
│   │   └── background.js    # Event and message proxy
│   ├── icons/               # Extension branding assets
│   ├── popup/               # Built Vite assets (Popup destination)
│   ├── manifest.json        # Extension manifest configuration
│   ├── package.json         # Extension build scripts and package dependencies
│   └── vite.config.js       # Vite bundler configuration
│
└── SETUP.md                 # Detailed step-by-step setup guides
```

---

## 🚀 Quick Start

### 1. Set Up and Run the Backend

```bash
# Navigate to the backend folder
cd backend

# Create a virtual environment
python -m venv venv
# Activate virtual environment
venv\Scripts\activate       # On Windows
source venv/bin/activate    # On macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your Google Gemini API key and GitHub credentials!

# Run the FastAPI server
uvicorn app.main:app --reload --port 8000
```

### 2. Build and Load the Chrome Extension

```bash
# Navigate to the extension folder
cd extension

# Install package dependencies
npm install

# Build the React Popup using Vite
npm run build

# Load into Chrome:
# 1. Open chrome://extensions/ in Google Chrome.
# 2. Toggle "Developer mode" in the top-right corner.
# 3. Click "Load unpacked" in the top-left.
# 4. Choose the "extension/" directory inside the project.
```

---

## 📡 API Endpoints

### HTTP Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/webhook` | Receives GitHub push webhook payloads |
| `POST` | `/review` | Manually requests a review for a commit |
| `GET` | `/review/{commit_sha}` | Retrieves review findings for a specific commit |
| `POST` | `/review/{review_id}/displayed` | Marks a review as displayed in UI |
| `GET` | `/reviews/{username}` | Retrieves recent reviews filtered by GitHub username |
| `GET` | `/review/repo/{owner}/{repo}/latest` | Fetches the latest review for a repository |
| `GET` | `/settings/{github_username}` | Retrieves strictness settings for a developer |
| `POST` | `/settings/{github_username}` | Saves strictness configurations |
| `GET` | `/health` | Server health check status |
| `GET` | `/docs` | Swagger interactive API docs |

### WebSocket Endpoints

| Protocol | Endpoint | Description |
|----------|----------|-------------|
| `WS` | `/ws/review/{commit_sha}` | Real-time subscription to review updates for a specific commit |
| `WS` | `/ws/repo/{owner}/{repo}` | Real-time subscription to all reviews for a repository |

---

## ⚙️ AI Review Strictness

Adjust the critique level from the Extension Popup depending on your needs:
- **Lenient**: Ignores styling and minor complaints. Focuses only on high-severity bugs and critical security vulnerabilities.
- **Moderate**: Balanced approach tracking common performance bottlenecks, bugs, security practices, and clean code guidelines.
- **Strict**: Thorough audit checking detailed naming patterns, edge-cases, optimization tweaks, documentation, and exhaustive security standards.

---

## 📄 License & Setup Detail

- For step-by-step setup, tunnels (using ngrok), and webhook registration, read the [SETUP.md](SETUP.md).
- Distributed under the MIT License. See `LICENSE` for more details.

