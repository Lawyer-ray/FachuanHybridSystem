# FaChuanAI Case Management System V26.16.2

Fully automated court document processing and generation. Less is more.

[中文版](README.md)

## Notes

- This system is updated almost every day; the codebase changes frequently and may not be beginner-friendly.
- For the latest updates from the author, follow the WeChat official account: 法穿.
- This project is an entry for the Guangzhou Legal Tech Innovation & Entrepreneurship Competition, shortlisted for the finals. Team name: GGBond.

## ✨ Features

- **Case Management** - Case creation, assignment, progress tracking, case number management
- **Client Management** - Client info, identity documents, asset clue management
- **Contract Management** - Contract creation, supplementary agreements, payment tracking, lawyer assignment
- **Organization Management** - Teams, lawyers, account credentials
- **Legal Research** - Joint keyword search, similar case matching, PDF archive/download
- **Automation**
  - Court SMS parsing and document download
  - Automated court document retrieval
  - Property preservation insurance inquiry
  - Feishu group message notifications
- **MCP Server** - Supports OpenClaw and other AI agents to operate the system in natural language

## 🛠 Tech Stack

- **Backend**: Django 6.0 + Django Ninja (API)
- **Database**: SQLite
- **Cache**: Django built-in cache
- **Task Queue**: Django-Q2
- **Browser Automation**: Playwright
- **Package Manager**: uv
- **MCP Server**: Based on [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

## 🚀 Quick Start

### 🍎 macOS (Recommended — uses Make)

```bash
# 1. Clone the repo
git clone https://github.com/Lawyer-ray/FachuanHybridSystem.git
cd FachuanHybridSystem/backend

# 2. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh
# or: brew install uv

# 3. View all available commands (optional)
make help

# 4. Create virtual environment (auto-downloads Python 3.12)
make venv
source .venv/bin/activate

# 5. Install dependencies
make install

# 6. Configure environment variables
cp .env.example .env

# 7. Database setup
make migrations

# 8. Collect static files (important!)
make collectstatic

# 9. Start services (⚠️ Start task queue FIRST, then Django)
make qcluster         # Terminal 1: start task queue first
make run              # Terminal 2: then start Django (default port 8002)
# or
make run-port PORT=8080

# 10. Start task queue (new terminal)
```

### 🐧 Linux / Windows

```bash
# 1. Clone the repo
git clone https://github.com/Lawyer-ray/FachuanHybridSystem.git
cd FachuanHybridSystem/backend

# 2. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Create virtual environment and install dependencies
uv sync

# 4. Activate virtual environment
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 5. Configure environment variables
cp .env.example .env

# 6. Run database migrations
cd apiSystem
python manage.py migrate

# 7. Create admin user
python manage.py createsuperuser

# 8. Collect static files (important!)
python manage.py collectstatic --noinput

# 9. Start the development server
python manage.py runserver 0.0.0.0:8002

# 10. Start task queue (new terminal)
python manage.py qcluster
```

## 🔧 Requirements

### Required
- **Package manager**: [uv](https://docs.astral.sh/uv/) (automatically manages Python 3.12 — no manual Python install needed)
- **OS**: macOS (recommended) / Linux / Windows

### Recommended (macOS)
- **Make**: pre-installed on macOS

### Install uv
```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# or via Homebrew
brew install uv

# verify
uv --version
```

## 🔎 Legal Case Research (`legal_research`)

- Entry: Django Admin `legal_research` task management
- Inputs: keywords + case summary
- Keyword separators: spaces, commas, semicolons, and newlines are all supported; they are normalized to spaces and sent as one combined query
- Configurable parameters:
  - `max_candidates` (default `100`)
  - `min_similarity_score` (default `0.9`)
  - `llm_model` (SiliconFlow model for similarity scoring)
- Reliability:
  - Pre-flight SiliconFlow connectivity/model check before queueing
  - Task-level retries for search/detail/PDF stages; failed single cases are skipped without crashing the whole task
- Output: matched cases are stored with PDF attachments and can be downloaded per-case or as a package

## 🤖 MCP Server (AI Agent Integration)

OpenClaw, Claude Desktop, and other AI agents can call FaChuan tools through MCP.

Basic env config in `backend/.env`:

```bash
FACHUAN_BASE_URL=http://127.0.0.1:8002/api/v1
FACHUAN_USERNAME=your_username
FACHUAN_PASSWORD=your_password
```

## 🤖 Got a question? Ask AI.

All source code is fully open. For any deployment, configuration, or usage questions, the most effective approach is to **give the project URL directly to an AI**:

```
https://github.com/Lawyer-ray/FachuanHybridSystem
```

Paste this URL along with your question into ChatGPT, Claude, Kiro, or any AI assistant. They can read the full codebase and give you precise, context-aware answers — far better than a search engine.

> Open source means you can read it, change it, and figure it out yourself. When you hit a problem, read the code first, then ask AI. Build the habit of solving things independently.

## 📚 Documentation

- [Changelog](CHANGELOG.md)
- [Django Docs](https://docs.djangoproject.com/)
- [Django Ninja Docs](https://django-ninja.rest-framework.com/)
- [uv Docs](https://docs.astral.sh/uv/)
- [Make Manual](https://www.gnu.org/software/make/manual/make.html)

## 📄 License

Custom commercial source license:

- ✅ **Free**: Individual (single user) or teams ≤ 10 people — free commercial use
- 💰 **Paid license**: Teams > 10 people — donate **¥200 per person**

**How to license**: Donate via the WeChat appreciation code below (note "commercial license + headcount"). The donation itself constitutes authorization — no further confirmation needed.

See [LICENSE](LICENSE) for details.

## 🤝 Contributing

Issues and Pull Requests are welcome.

## 💡 Open Source Philosophy

Those who came before did not light the way for me — but this project will light the way for those who come after. Open source benefits both the giver and the receiver. May this project help advance the legal tech industry in China.

## 💝 Acknowledgements

This project was primarily built with **[Kiro](https://kiro.dev)** and **[Trae](https://trae.ai)** — two AI-powered IDEs that dramatically accelerated development. Thank you.

## 💖 Support

If this project has been useful to you:

### WeChat Appreciation
<img src="backend/apps/core/static/core/images/赞赏码.png" width="200" alt="WeChat appreciation code">

### Crypto
- **USDT (TRC20)**: `TGs89x2uz1Qf7vALBboKcSFsZiP3J5T4h2`
- **Bitcoin**: `bc1p39an4kulcgl8ce6lc23zd6yjv3j29uctgkt7szaxlljwjlfsq6eqll7kk8`

## 📞 Contact

<img src="backend/apps/core/static/core/images/wechat.jpg" width="200" alt="WeChat QR code">

Scan to add the author on WeChat.
