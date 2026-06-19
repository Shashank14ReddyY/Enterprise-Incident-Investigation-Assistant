<div align="center">

# 🔍 Enterprise Incident Investigation Assistant

**An AI-powered multi-agent system that investigates security incidents, analyses logs and knowledge-base documents, and produces structured investigation reports.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://www.python.org/)
[![Anthropic](https://img.shields.io/badge/Powered%20by-Claude%20Sonnet-orange?logo=anthropic)](https://www.anthropic.com/)
[![Streamlit](https://img.shields.io/badge/Dashboard-Streamlit-red?logo=streamlit)](https://streamlit.io/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![MCP](https://img.shields.io/badge/MCP-Claude%20Desktop-purple)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[Features](#-features) • [Architecture](#-architecture) • [Quick Start](#-quick-start) • [How to Run](#-how-to-run-each-component) • [MCP Setup](#-connecting-to-claude-desktop-mcp) • [Project Structure](#-project-structure)

---

![Dashboard Preview](https://img.shields.io/badge/Dashboard-Live%20Preview-brightgreen)

</div>

---

## 🚀 Features

| Feature | Description |
|---|---|
| **Multi-Agent Pipeline** | 6 specialised AI agents working in sequence or parallel |
| **RAG-Powered Evidence** | TF-IDF vector store searches across incident logs and policy documents |
| **Structured Reports** | Full Incident Investigation Reports with executive summary, findings, root causes, risk assessment, and remediation steps |
| **Reliability Layer** | Retry, timeout, and RAG-only fallback — survives API outages |
| **Streamlit Dashboard** | Live agent progress, severity charts, Gantt timeline, investigation history |
| **FastAPI REST API** | Async job-based investigation endpoint with Swagger docs |
| **MCP Server** | Connect directly to Claude Desktop — investigate incidents in natural language |
| **Structured Logging** | Every agent event written to JSONL for audit and debugging |

---

## 🏗 Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────────────────┐
│           Entry Points                       │
│  run.py │ FastAPI │ Streamlit │ MCP Server   │
└─────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────┐
│              Orchestrator                    │
│    Sequential Mode  │  Parallel Mode         │
└─────────────────────────────────────────────┘
    │
    ├──► Researcher Agent    (RAG evidence retrieval)
    │
    ├──► Incident Agent      (suspicious event detection)
    ├──► Root Cause Agent    (why did it happen?)      ◄─ parallel in parallel mode
    ├──► Risk Agent          (severity + business impact)
    │
    ├──► Reviewer Agent      (quality gate + gap analysis)
    │
    └──► Report Writer Agent (final structured report)
         │
         ▼
    AgentState → final_report + findings + trace
         │
         ▼
┌─────────────────────────────────────────────┐
│           Reliability Layer                  │
│  Retry │ Timeout │ Fallback │ Tracing │ JSONL│
└─────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│              RAG Backend                     │
│  TF-IDF Vector Store  │  search_chunks()     │
│  Incident Logs        │  Policy Documents    │
└─────────────────────────────────────────────┘
```

### Agent Pipeline

| # | Agent | Role | Input | Output |
|---|---|---|---|---|
| 1 | **Researcher** | Expands query → multi-angle RAG search | User query | `retrieved_chunks` |
| 2 | **Incident Agent** | Finds suspicious events in logs | Chunks | Incident findings |
| 3 | **Root Cause Agent** | Determines why incidents happened | Findings + policy chunks | Root cause findings |
| 4 | **Risk Agent** | Scores severity, assesses impact | All findings | Risk findings |
| 5 | **Reviewer** | Quality-gates findings, flags gaps | All findings + chunks | Review comments |
| 6 | **Report Writer** | Synthesises everything into a report | Full state | Final report |

---

## 📋 Prerequisites

- Python 3.10 or higher
- An [Anthropic API key](https://console.anthropic.com/)
- Git

---

## ⚡ Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/enterprise-incident-investigation.git
cd enterprise-incident-investigation

# 2. Create and activate virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure your API key
# Edit .env and set your Anthropic API key:
ANTHROPIC_API_KEY=sk-ant-your-key-here

# 5. Ingest documents into the vector store
python -m Backend.ingest

# 6. Launch the dashboard
streamlit run Frontend/app.py
# Opens at http://localhost:8501
```

---

## 🔧 How to Run Each Component

### Option 1 — Streamlit Dashboard (recommended)
```bash
streamlit run Frontend/app.py
```
Opens at **http://localhost:8501** — full UI with live agent progress, charts, and report download.

---

### Option 2 — CLI (`run.py`)
```bash
# Interactive prompt
python run.py

# With a query
python run.py --query "Investigate failed login incidents"

# Parallel mode (faster)
python run.py --query "Analyze the firewall disable event" --mode parallel

# Save report to file
python run.py --query "Investigate insider threat activity" --output report.md
```

---

### Option 3 — FastAPI REST Server
```bash
# Start the server
python -m Backend.main
# API live at http://localhost:8000
# Swagger docs at http://localhost:8000/docs

# Test with curl:
curl -X POST http://localhost:8000/investigate \
  -H "Content-Type: application/json" \
  -d '{"query": "Investigate brute force login attempts", "mode": "sequential"}'

# Returns: {"job_id": "...", "status": "pending", ...}

# Poll for result:
curl http://localhost:8000/investigate/{job_id}
```

Available endpoints:

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Server liveness check |
| POST | `/investigate` | Start an investigation (async, returns job_id) |
| GET | `/investigate/{job_id}` | Get result or poll status |
| GET | `/sources` | List all indexed document sources |
| GET | `/logs` | List incident log files |
| POST | `/search` | Raw RAG search |

---

### Option 4 — MCP Server (Claude Desktop)

> See [Connecting to Claude Desktop](#-connecting-to-claude-desktop-mcp) below.

```bash
python -m mcp_server.server
```

---

## 🤖 Connecting to Claude Desktop (MCP)

The MCP server lets you use Claude Desktop to investigate incidents in natural language — just talk to Claude and it calls your local server.

### Step 1 — Find your Claude Desktop config file

| OS | Location |
|---|---|
| **Windows** | `%APPDATA%\Claude\claude_desktop_config.json` |
| **macOS** | `~/Library/Application Support/Claude/claude_desktop_config.json` |

### Step 2 — Add the MCP server config

Open `claude_desktop_config.json` (create it if it doesn't exist) and add:

```json
{
  "mcpServers": {
    "incident-investigation": {
      "command": "C:/path/to/your/project/.venv/Scripts/python.exe",
      "args": ["-m", "mcp_server.server"],
      "cwd": "C:/path/to/your/incident-investigation"
    }
  }
}
```

> ⚠️ **Important:** Use the full absolute path to the **`.venv` Python executable**, not just `python`. This ensures the right virtual environment is used and all packages are found.
>
> **Windows example:**
> ```json
> "command": "C:/Users/YourName/PycharmProjects/incident-investigation/.venv/Scripts/python.exe"
> ```
>
> **macOS/Linux example:**
> ```json
> "command": "/Users/yourname/projects/incident-investigation/.venv/bin/python"
> ```

### Step 3 — Restart Claude Desktop

Fully quit and reopen Claude Desktop. You should see the 🔧 tools icon in the chat input bar.

### Step 4 — Use it

Ask Claude things like:
- *"List the available incident log files"*
- *"Search for brute force login attacks in the logs"*
- *"Investigate suspicious admin activity and privilege escalation"*
- *"Run a full investigation on the firewall disable incident"*

### Available MCP Tools

| Tool | What it does |
|---|---|
| `list_logs` | Lists all log files and indexed sources |
| `search_incidents` | Searches the vector store for relevant log evidence |
| `investigate_incident` | Runs the full 6-agent pipeline and returns a complete report |

### Troubleshooting MCP Disconnection

If the server connects then immediately disconnects, these are the most common causes:

**1. Wrong Python path** — Claude Desktop can't find your packages.
Fix: use the full absolute path to `.venv/Scripts/python.exe`.

**2. Missing `.env` file or API key** — the server crashes on startup.
Fix: confirm `.env` exists in the project root with `ANTHROPIC_API_KEY=sk-ant-...`

**3. Vector store not built** — `Backend/ingest.py` was never run.
Fix: run `python -m Backend.ingest` once before starting the MCP server.

**4. Check the server log** — all MCP server output goes to `logs/mcp_server.log` (stdout is reserved for the JSON-RPC protocol). Open this file to see the actual error.

**5. Windows event loop** — already fixed in `server.py` with `WindowsSelectorEventLoopPolicy`.

---

## 📁 Project Structure

```
enterprise-incident-investigation/
│
├── agents/                         # 🤖 Phase 2 — AI agent pipeline
│   ├── state.py                    # AgentState TypedDict (shared pipeline state)
│   ├── llm_client.py               # Anthropic API wrapper (retry + timeout)
│   ├── researcher.py               # Agent 1: RAG evidence retrieval
│   ├── analyst.py                  # Agent 2: Incident event detection
│   ├── root_cause_agent.py         # Agent 3: Root cause analysis
│   ├── risk_agent.py               # Agent 4: Risk & severity scoring
│   ├── reviewer.py                 # Agent 5: Quality gate
│   ├── report_writer.py            # Agent 6: Final report generation
│   ├── orchestrator.py             # Sequential + parallel pipeline runner
│   └── execution_log.py            # Run logging + terminal trace printer
│
├── Backend/                        # 🗄 Phase 1 & 3 — RAG + REST API
│   ├── document_loader.py          # Load .txt and .pdf files
│   ├── chunker.py                  # Smart text chunking (log-aware)
│   ├── vector_store.py             # TF-IDF vector store with pickle persistence
│   ├── rag_pipeline.py             # search_chunks() — the public RAG interface
│   ├── ingest.py                   # One-command ingestion CLI
│   ├── search_test.py              # RAG smoke test (6 queries)
│   ├── api.py                      # FastAPI route handlers
│   ├── app.py                      # FastAPI app factory + CORS + lifespan
│   └── main.py                     # Uvicorn entry point
│
├── Frontend/                       # 🖥 Phase 4 — Streamlit dashboard
│   └── app.py                      # Full dashboard (charts, findings, history)
│
├── reliability/                    # 🛡 Phase 3 — Reliability layer
│   ├── retry_handler.py            # Exponential backoff retry decorator
│   ├── timeout_handler.py          # Per-agent wall-clock timeout enforcement
│   ├── fallback_handler.py         # LLM → retry → RAG-only fallback chain
│   ├── structured_logger.py        # JSONL structured event logger
│   └── tracing.py                  # Span-based execution tracing
│
├── mcp_server/                     # 🔌 Phase 3 — MCP server
│   └── server.py                   # Tools: search_incidents, list_logs, investigate_incident
│
├── mcp_client/                     # 📡 Phase 3 — HTTP client
│   └── client.py                   # InvestigationClient for scripts + frontend
│
├── KnowledgeBase/                  # 📚 Security policy documents
│   ├── Information-Security-Policy.txt
│   └── ISO_IEC_270012022.txt
│
├── logs/                           # 📋 Incident log files + run history
│   ├── Incident_Log_1.txt          # Brute force + privilege escalation
│   ├── Incident_Log_2.txt          # Firewall disable + data exfiltration
│   ├── Incident_Log_3.txt          # APT lateral movement + ransomware attempt
│   ├── Incident_Log_4.txt          # Insider threat + USB/email exfil
│   ├── Incident_Log_5.txt          # Secret exposure + API key breach
│   ├── agent_structured_logs.jsonl # Structured JSONL event log (auto-created)
│   └── mcp_server.log              # MCP server log (auto-created)
│
├── vector_db/                      # 🗃 Auto-created by ingest.py
│   └── tfidf_index.pkl             # Persisted TF-IDF vector index
│
├── run.py                          # 🚀 CLI entry point
├── .env                            # 🔑 API key + config (edit this)
├── requirements.txt                # 📦 All Python dependencies
└── README.md
```

---

## 🌍 Environment Variables

Edit `.env` in the project root:

```env
# Required
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Paths (defaults work if you run from project root)
CHROMA_DB_PATH=./vector_db
KNOWLEDGE_BASE_PATH=./KnowledgeBase
LOGS_PATH=./logs

# Chunking
CHUNK_SIZE=500
CHUNK_OVERLAP=50
TOP_K_RESULTS=5

# API server
API_HOST=0.0.0.0
API_PORT=8000
```

---

## 📊 Sample Investigation Output

```
=================================================
INCIDENT INVESTIGATION REPORT
=================================================
Date: 2024-06-18 10:45:22
Classification: CONFIDENTIAL

EXECUTIVE SUMMARY
-----------------
Three consecutive failed login attempts were detected from IP 192.168.1.105,
followed immediately by a successful admin login from the same IP, privilege
escalation, and SSH key injection — indicating a CRITICAL account compromise.
Immediate account suspension and forensic review are required.

INCIDENT FINDINGS
-----------------
1. [CRITICAL] SSH key added to root account by service_account_x
2. [HIGH]     Privilege escalation: service_account_x granted ADMIN role
3. [HIGH]     Admin login from unusual IP (192.168.1.105) — normal IP: 10.0.0.5
4. [MEDIUM]   Brute force detected: 6 failed login attempts for user1
5. [MEDIUM]   Audit log entries deleted (47 entries) by admin_user

ROOT CAUSE ANALYSIS
-------------------
1. [HIGH] No MFA enforced on admin accounts [Policy ref: Section 1.1]
2. [HIGH] Account lockout triggered only after 6 attempts — policy mandates 3
3. [MEDIUM] Insufficient monitoring of off-hours admin activity

RISK ASSESSMENT
---------------
Overall Severity: CRITICAL
Affected Systems: server01, root account
Data at Risk: System credentials, SSH access
Compliance: ISO 27001 A.8.2, A.8.5 — privileged access controls violated

RECOMMENDATIONS
---------------
1. [IMMEDIATE] Suspend admin_user and service_account_x — SOC
2. [IMMEDIATE] Rotate all SSH keys on server01 — IT Operations
3. [URGENT]    Enable MFA on all admin accounts — IT Operations
4. [URGENT]    Reduce account lockout threshold to 3 attempts — IT Operations
5. [SCHEDULED] Review and re-instate audit logging — Compliance Team
=================================================
```

---

## 🧩 Adding Your Own Log Files

Drop any `.txt` or `.pdf` file into `KnowledgeBase/` or `logs/` and re-run:

```bash
python -m Backend.ingest
# Use --clear to wipe and rebuild from scratch:
python -m Backend.ingest --clear
```

Log files in `logs/` are chunked line-by-line. Policy PDFs in `KnowledgeBase/` are chunked by character with overlap.

---

## 🔬 Running Tests

```bash
# Verify the RAG pipeline works end-to-end
python -m Backend.search_test

# Quick import check for all modules
python -c "from agents.orchestrator import investigate; print('All imports OK')"
```

---

## 🗺 Build Phases

| Phase | What was built | Files |
|---|---|---|
| **Phase 1** | RAG backend — document loading, chunking, TF-IDF vector store | `Backend/` |
| **Phase 2** | Agent pipeline — 6 agents, orchestrator, shared state | `agents/` |
| **Phase 3** | Reliability layer, FastAPI REST API, MCP server | `reliability/`, `Backend/api.py`, `mcp_server/` |
| **Phase 4** | Streamlit dashboard with live progress, charts, history | `Frontend/app.py` |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'Add some feature'`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<div align="center">
Built with ❤️ using <a href="https://www.anthropic.com/">Claude by Anthropic</a>
</div>
