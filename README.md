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
                       └──────────────────────┬───────────────────────┘
                                              │
                       ┌──────────────────────┴───────────────────────┐
                       ▼                                              ▼
         ┌───────────────────────────┐                  ┌───────────────────────────┐
         │   GitHub API Client       │                  │  SQLAlchemy + SQLite      │
         │   (Fetch Diff & Context)  │                  │  (Stores history/records) │
         └─────────────┬─────────────┘                  └───────────────────────────┘
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
                       │   Chrome Extension (MV3)  │
                       │   - Content Script UI     │
                       │   - React/Vite Popup UI   │
                       └───────────────────────────┘
```

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

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/webhook` | Receives GitHub push webhook payloads |
| `GET` | `/review/{commit_sha}` | Retrieves review findings for a specific commit |
| `GET` | `/reviews/{username}` | Retrieves recent reviews filtered by GitHub username |
| `GET` | `/review/repo/{owner}/{repo}/latest` | Fetches the latest review for a repository |
| `GET` | `/settings/{github_username}` | Retrieves strictness settings for a developer |
| `POST` | `/settings/{github_username}` | Saves strictness configurations |
| `GET` | `/health` | Server health check status |
| `GET` | `/docs` | Swagger interactive API docs |

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

