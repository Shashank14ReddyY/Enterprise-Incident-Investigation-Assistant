"""
mcp_server/server.py
MCP (Model Context Protocol) server for the Incident Investigation Assistant.
Exposes three tools that Claude Desktop can call:

  search_incidents(query, top_k)     — search incident log chunks
  list_logs()                        — list available log files
  investigate_incident(query, mode)  — run the full agent pipeline

Run with:
    python -m mcp_server.server

Then add to Claude Desktop's config:
    {
      "mcpServers": {
        "incident-investigation": {
          "command": "python",
          "args": ["-m", "mcp_server.server"],
          "cwd": "/path/to/incident-investigation"
        }
      }
    }
"""

from __future__ import annotations
import json
import logging
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("mcp_server")

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp import types
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.warning(
        "mcp package not installed. Run: pip install mcp\n"
        "Server will start in stub mode for development."
    )

from agents.orchestrator import investigate
from Backend.rag_pipeline import search_chunks, list_sources
from Backend.document_loader import load_directory


# ── Tool implementations ─────────────────────────────────────────────────────

def _tool_search_incidents(query: str, top_k: int = 5) -> str:
    """Search incident log chunks for relevant evidence."""
    results = search_chunks(query, top_k=top_k, scope="logs")
    if not results:
        return f"No log evidence found for query: '{query}'"
    lines = [f"Found {len(results)} result(s) for '{query}':\n"]
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. [{r['source']}] score={r['score']:.3f}\n"
            f"   {r['text'][:200].replace(chr(10), ' ')}"
        )
    return "\n".join(lines)


def _tool_list_logs() -> str:
    """List all available incident log files."""
    logs_dir = Path(os.getenv("LOGS_PATH", "./logs"))
    if not logs_dir.is_dir():
        return "Logs directory not found."
    files = sorted(logs_dir.glob("*.txt"))
    if not files:
        return "No log files found."
    lines = [f"Available incident logs ({len(files)} files):\n"]
    for f in files:
        size_kb = f.stat().st_size / 1024
        line_count = sum(1 for _ in open(f, encoding="utf-8", errors="replace"))
        lines.append(f"  • {f.name}  ({size_kb:.1f} KB, {line_count} lines)")
    sources = list_sources()
    lines.append(f"\nIndexed sources in vector store: {', '.join(sources)}")
    return "\n".join(lines)


def _tool_investigate_incident(query: str, mode: str = "sequential") -> str:
    """Run the full multi-agent investigation pipeline and return the report."""
    if mode not in ("sequential", "parallel"):
        mode = "sequential"
    logger.info("MCP tool: investigate_incident — query='%s' mode=%s", query, mode)
    try:
        state = investigate(query, mode=mode)
        report = state.get("final_report", "")
        findings_count = len(state.get("findings", []))
        trace = state.get("execution_trace", [])
        total_time = sum(t.get("duration", 0) for t in trace)

        header = (
            f"Investigation complete — {findings_count} finding(s) "
            f"in {total_time:.1f}s\n\n"
        )
        return header + report
    except Exception as exc:
        logger.error("investigate_incident failed: %s", exc)
        return f"Investigation failed: {exc}"


# ── MCP server setup ─────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_incidents",
        "description": (
            "Search the incident log database for relevant evidence. "
            "Returns the most semantically similar log entries for a given query."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query, e.g. 'failed login brute force'",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default 5, max 20)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_logs",
        "description": "List all available incident log files and indexed sources.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "investigate_incident",
        "description": (
            "Run a full AI-powered incident investigation using the multi-agent pipeline. "
            "Produces a complete Incident Investigation Report covering findings, root causes, "
            "risk assessment, and remediation recommendations."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The investigation query, e.g. "
                        "'Investigate failed login incidents and brute force attacks'"
                    ),
                },
                "mode": {
                    "type": "string",
                    "enum": ["sequential", "parallel"],
                    "description": "Pipeline mode — sequential (default) or parallel (faster)",
                    "default": "sequential",
                },
            },
            "required": ["query"],
        },
    },
]


async def _handle_tool_call(name: str, arguments: dict) -> str:
    if name == "search_incidents":
        return _tool_search_incidents(
            query=arguments["query"],
            top_k=arguments.get("top_k", 5),
        )
    elif name == "list_logs":
        return _tool_list_logs()
    elif name == "investigate_incident":
        return _tool_investigate_incident(
            query=arguments["query"],
            mode=arguments.get("mode", "sequential"),
        )
    else:
        return f"Unknown tool: {name}"


def run_server() -> None:
    """Start the MCP server (requires mcp package)."""
    if not MCP_AVAILABLE:
        print("ERROR: mcp package not installed. Run: pip install mcp")
        print("\nRunning in stub mode — tool outputs printed to stdout for testing:\n")
        _run_stub()
        return

    server = Server("incident-investigation")

    @server.list_tools()
    async def list_tools():
        return [
            types.Tool(
                name=t["name"],
                description=t["description"],
                inputSchema=t["inputSchema"],
            )
            for t in TOOLS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        result = await _handle_tool_call(name, arguments)
        return [types.TextContent(type="text", text=result)]

    import asyncio
    logger.info("MCP Incident Investigation Server starting…")
    asyncio.run(stdio_server(server))


def _run_stub() -> None:
    """
    Stub mode: prints tool definitions and a sample output.
    Used for testing without the mcp package.
    """
    print("Available MCP tools:")
    for tool in TOOLS:
        print(f"\n  Tool: {tool['name']}")
        print(f"  Desc: {tool['description'][:80]}")

    print("\n--- Sample: list_logs ---")
    print(_tool_list_logs())

    print("\n--- Sample: search_incidents ---")
    print(_tool_search_incidents("failed login brute force", top_k=3))


if __name__ == "__main__":
    run_server()
