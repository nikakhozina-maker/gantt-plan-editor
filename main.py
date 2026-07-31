"""
Gantt Plan Editor — Backend (FastAPI + MCP + LLM)
====================================================
Запуск: python main.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Load .env file BEFORE import LLM clients ──────────────────────
def _load_dotenv():
    """Simple .env loader (no python-dotenv dependency)."""
    candidates = [
        Path(__file__).parent / ".env",
        Path(__file__).parent / ".env.txt",
        Path(__file__).parent / "env.txt",
    ]
    env_path = None
    for p in candidates:
        if p.exists():
            env_path = p
            break
    if env_path is None:
        # Search for any file starting with .env
        for f in Path(__file__).parent.iterdir():
            if f.is_file() and f.name.startswith(".env"):
                env_path = f
                break
    if env_path is None:
        print("[ENV] ⚠  .env файл не найден! Положи .env в папку с main.py", file=sys.stderr)
        return
    print(f"[ENV] ✅ Найден: {env_path.name}", file=sys.stderr)
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

_load_dotenv()

# CLI args for API keys (highest priority)
for arg in sys.argv[1:]:
    if arg.startswith("--openai-key="):
        os.environ["OPENAI_API_KEY"] = arg.split("=", 1)[1]
    elif arg.startswith("--anthropic-key="):
        os.environ["ANTHROPIC_API_KEY"] = arg.split("=", 1)[1]
    elif arg.startswith("--gemini-key="):
        os.environ["GEMINI_API_KEY"] = arg.split("=", 1)[1]
    elif arg.startswith("--openrouter-key="):
        os.environ["OPENROUTER_API_KEY"] = arg.split("=", 1)[1]
    elif arg.startswith("--openrouter-model="):
        os.environ["OPENROUTER_MODEL"] = arg.split("=", 1)[1]
    elif arg.startswith("--no-llm"):
        os.environ["OPENAI_API_KEY"] = ""
        os.environ["ANTHROPIC_API_KEY"] = ""
        os.environ["GEMINI_API_KEY"] = ""
        os.environ["OPENROUTER_API_KEY"] = ""

# ── httpx (for explicit http_client — fixes Windows proxy issue) ──
import httpx

# ── Optional: OpenAI / LLM client ──────────────────────────────────
try:
    from openai import AsyncOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# ── Optional: Anthropic ────────────────────────────────────────────
try:
    from anthropic import AsyncAnthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# ── Optional: Google Gemini ────────────────────────────────────────
try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

# ═══════════════════════════════════════════════════════════════════
# FastAPI App
# ═══════════════════════════════════════════════════════════════════

app = FastAPI(
    title="Gantt Plan Editor API",
    description="Backend for Gantt Editor with MCP + LLM integration",
    version="1.2.2",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════
# Models
# ═══════════════════════════════════════════════════════════════════

class Task(BaseModel):
    id: str
    task: str
    description: str = ""
    assignee: str = ""
    duration: int = 1
    color: str = ""
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    completed: bool = False
    manual_start: bool = False


class Dependency(BaseModel):
    id: str
    from_task_id: str
    to_task_id: str
    type: str = "FS"
    lag_days: int = 0


class ChatRequest(BaseModel):
    message: str
    tasks: list[dict]
    dependencies: list[dict]


class ChatResponse(BaseModel):
    reply: str
    tasks: Optional[list[dict]] = None
    dependencies: Optional[list[dict]] = None


# ═══════════════════════════════════════════════════════════════════
# MCP (Model Context Protocol) — tool registry
# ═══════════════════════════════════════════════════════════════════

MCP_TOOLS = [
    {
        "name": "add_task",
        "description": "Добавить новую задачу в план проекта",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Название задачи"},
                "duration": {"type": "integer", "description": "Длительность в днях"},
                "assignee": {"type": "string", "description": "Исполнитель"},
                "description": {"type": "string", "description": "Описание задачи"},
                "after_task_id": {"type": "string", "description": "ID задачи-предшественника (опционально)"},
            },
            "required": ["name", "duration"],
        },
    },
    {
        "name": "delete_task",
        "description": "Удалить задачу из плана",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "ID задачи"},
                "task_name": {"type": "string", "description": "Название задачи (если ID неизвестен)"},
            },
        },
    },
    {
        "name": "update_task",
        "description": "Изменить параметры существующей задачи",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "ID задачи"},
                "task_name": {"type": "string", "description": "Название задачи (для поиска)"},
                "duration": {"type": "integer", "description": "Новая длительность"},
                "assignee": {"type": "string", "description": "Новый исполнитель"},
                "completed": {"type": "boolean", "description": "Отметить выполненной"},
            },
        },
    },
    {
        "name": "add_dependency",
        "description": "Создать зависимость между задачами (связь). Первая указанная задача — предшественник, вторая — зависимая.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_task_id": {"type": "string", "description": "ID задачи-предшественника"},
                "from_task_name": {"type": "string", "description": "Название задачи-предшественника"},
                "to_task_id": {"type": "string", "description": "ID зависимой задачи"},
                "to_task_name": {"type": "string", "description": "Название зависимой задачи"},
                "type": {"type": "string", "description": "Тип связи: FS, SS, FF, SF"},
                "lag_days": {"type": "integer", "description": "Задержка в днях"},
            },
        },
    },
    {
        "name": "remove_dependency",
        "description": "Удалить связь между задачами",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_task_id": {"type": "string", "description": "ID первой задачи"},
                "to_task_id": {"type": "string", "description": "ID второй задачи"},
            },
        },
    },
    {
        "name": "assign_task",
        "description": "Назначить исполнителя на задачу",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "ID задачи"},
                "task_name": {"type": "string", "description": "Название задачи"},
                "assignee": {"type": "string", "description": "Имя исполнителя"},
            },
            "required": ["assignee"],
        },
    },
    {
        "name": "complete_task",
        "description": "Отметить задачу как выполненную",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "ID задачи"},
                "task_name": {"type": "string", "description": "Название задачи"},
            },
        },
    },
    {
        "name": "list_tasks",
        "description": "Показать список всех задач плана",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "reset_plan",
        "description": "Сбросить план к исходному состоянию",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "reschedule_tasks",
        "description": "Перенести все задачи после указанной на N дней вперёд или назад",
        "inputSchema": {
            "type": "object",
            "properties": {
                "after_task_id": {"type": "string", "description": "ID задачи, после которой сдвигать"},
                "after_task_name": {"type": "string", "description": "Название задачи, после которой сдвигать"},
                "shift_days": {"type": "integer", "description": "Сдвиг в днях (положительный = вперёд)"},
            },
            "required": ["shift_days"],
        },
    },
]


# ═══════════════════════════════════════════════════════════════════
# Seed Data
# ═══════════════════════════════════════════════════════════════════

COLORS = ["#4CAF50", "#2196F3", "#FF9800", "#9C27B0", "#F44336", "#00BCD4", "#FF5722", "#607D8B"]

SEED_TASKS = [
    {"id": "1", "task": "Анализ требований", "description": "", "assignee": "Анна", "duration": 3, "color": "#4CAF50", "completed": False},
    {"id": "2", "task": "Проектирование архитектуры", "description": "", "assignee": "Игорь", "duration": 5, "color": "#2196F3", "completed": False},
    {"id": "3", "task": "Разработка бэкенда", "description": "", "assignee": "", "duration": 10, "color": "#FF9800", "completed": False},
    {"id": "4", "task": "Разработка фронтенда", "description": "", "assignee": "Диана", "duration": 8, "color": "#9C27B0", "completed": False},
    {"id": "5", "task": "Тестирование", "description": "", "assignee": "Алексей", "duration": 4, "color": "#F44336", "completed": False},
    {"id": "6", "task": "Деплой", "description": "", "assignee": "Елена", "duration": 2, "color": "#00BCD4", "completed": False},
]

SEED_DEPENDENCIES = [
    {"id": "dep1", "from_task_id": "1", "to_task_id": "2", "type": "FS", "lag_days": 0},
    {"id": "dep2", "from_task_id": "2", "to_task_id": "3", "type": "FS", "lag_days": 0},
    {"id": "dep3", "from_task_id": "2", "to_task_id": "4", "type": "FS", "lag_days": 0},
    {"id": "dep4", "from_task_id": "3", "to_task_id": "5", "type": "FS", "lag_days": 0},
    {"id": "dep5", "from_task_id": "4", "to_task_id": "5", "type": "FS", "lag_days": 0},
    {"id": "dep6", "from_task_id": "5", "to_task_id": "6", "type": "FS", "lag_days": 0},
]


# ═══════════════════════════════════════════════════════════════════
# MCP Tools Implementation
# ═══════════════════════════════════════════════════════════════════

def _find_task(task_id: str, task_name: str, tasks: list[dict]) -> Optional[dict]:
    """Find task by ID or name."""
    if task_id:
        for t in tasks:
            if t["id"] == task_id:
                return t
    if task_name:
        name_lower = task_name.lower()
        # Exact match first
        for t in tasks:
            if t["task"].lower() == name_lower:
                return t
        # Partial match
        for t in tasks:
            if name_lower in t["task"].lower() or t["task"].lower() in name_lower:
                return t
    return None


def mcp_call_tool(tool_name: str, arguments: dict, tasks: list[dict], deps: list[dict]) -> dict:
    """Execute an MCP tool and return updated tasks/deps + reply."""
    new_tasks = [dict(t) for t in tasks]
    new_deps = [dict(d) for d in deps]
    reply = ""

    if tool_name == "add_task":
        name = arguments.get("name", "Новая задача")
        duration = int(arguments.get("duration", 3))
        assignee = arguments.get("assignee", "")
        description = arguments.get("description", "")
        after_id = arguments.get("after_task_id", "")

        ids = [int(t["id"]) for t in new_tasks if t["id"].isdigit()]
        new_id = str(max(ids) + 1 if ids else 1)
        new_task = {
            "id": new_id, "task": name, "description": description,
            "assignee": assignee, "duration": duration,
            "color": COLORS[len(new_tasks) % len(COLORS)],
            "completed": False,
        }
        new_tasks.append(new_task)
        reply = f"✅ Добавил задачу **«{name}»** (ID: {new_id}, {duration} дн.)"
        if assignee:
            reply += f"\n👤 Исполнитель: **{assignee}**"
        if after_id:
            dep_ids = [int(d["id"].replace("dep", "")) for d in new_deps if d["id"].startswith("dep")]
            new_dep_id = f"dep{max(dep_ids) + 1 if dep_ids else 1}"
            new_deps.append({"id": new_dep_id, "from_task_id": after_id, "to_task_id": new_id, "type": "FS", "lag_days": 0})
            reply += f"\n🔗 Связана с задачей ID {after_id}"

    elif tool_name == "delete_task":
        found = _find_task(arguments.get("task_id", ""), arguments.get("task_name", ""), new_tasks)
        if found:
            rid = found["id"]
            new_tasks = [t for t in new_tasks if t["id"] != rid]
            new_deps = [d for d in new_deps if d["from_task_id"] != rid and d["to_task_id"] != rid]
            reply = f"🗑️ Удалил задачу **«{found['task']}»** и все её связи."
        else:
            reply = "🤔 Задача не найдена для удаления."

    elif tool_name == "update_task":
        found = _find_task(arguments.get("task_id", ""), arguments.get("task_name", ""), new_tasks)
        if found:
            if "duration" in arguments:
                found["duration"] = int(arguments["duration"])
                reply = f"✅ Длительность **«{found['task']}»** → {found['duration']} дн."
            if "assignee" in arguments:
                found["assignee"] = arguments["assignee"]
                reply = f"👤 Задача **«{found['task']}»** → **{arguments['assignee']}**"
            if arguments.get("completed"):
                found["completed"] = True
                reply = f"✅ Задача **«{found['task']}»** отмечена выполненной!"
        else:
            reply = "🤔 Задача не найдена."

    elif tool_name == "add_dependency":
        f1 = _find_task(arguments.get("from_task_id", ""), arguments.get("from_task_name", ""), new_tasks)
        f2 = _find_task(arguments.get("to_task_id", ""), arguments.get("to_task_name", ""), new_tasks)
        if f1 and f2:
            dep_type = arguments.get("type", "FS").upper()
            lag = int(arguments.get("lag_days", 0))
            # Remove existing duplicate
            new_deps = [d for d in new_deps if not (
                d["from_task_id"] == f1["id"] and d["to_task_id"] == f2["id"]
            )]
            dep_ids = [int(d["id"].replace("dep", "")) for d in new_deps if d["id"].startswith("dep")]
            new_id = f"dep{max(dep_ids) + 1 if dep_ids else 1}"
            new_deps.append({"id": new_id, "from_task_id": f1["id"], "to_task_id": f2["id"], "type": dep_type, "lag_days": lag})
            reply = f"🔗 Связь {dep_type}: **«{f1['task']}»** → **«{f2['task']}»**"
            if lag:
                reply += f" (задержка: {lag} дн.)"
        else:
            reply = "🤔 Укажите две задачи для связи."

    elif tool_name == "remove_dependency":
        found = None
        f1 = _find_task(arguments.get("from_task_id", ""), "", new_tasks)
        f2 = _find_task(arguments.get("to_task_id", ""), "", new_tasks)
        if f1 and f2:
            before = len(new_deps)
            new_deps = [d for d in new_deps if not (
                (d["from_task_id"] == f1["id"] and d["to_task_id"] == f2["id"]) or
                (d["from_task_id"] == f2["id"] and d["to_task_id"] == f1["id"])
            )]
            if len(new_deps) < before:
                reply = f"✂️ Разорвал связь между **«{f1['task']}»** и **«{f2['task']}»**."
            else:
                reply = "🤔 Связи между этими задачами нет."
        else:
            reply = "🤔 Укажите две задачи."

    elif tool_name == "assign_task":
        found = _find_task(arguments.get("task_id", ""), arguments.get("task_name", ""), new_tasks)
        if found and arguments.get("assignee"):
            found["assignee"] = arguments["assignee"]
            reply = f"👤 Задача **«{found['task']}»** → **{arguments['assignee']}**"
        else:
            reply = "🤔 Задача или исполнитель не указаны."

    elif tool_name == "complete_task":
        found = _find_task(arguments.get("task_id", ""), arguments.get("task_name", ""), new_tasks)
        if found:
            found["completed"] = True
            reply = f"✅ Задача **«{found['task']}»** отмечена выполненной! 🎉"
        else:
            reply = "🤔 Задача не найдена."

    elif tool_name == "list_tasks":
        lines = ["📋 **Текущий план:**\n"]
        for t in new_tasks:
            tdeps = [d for d in new_deps if d["to_task_id"] == t["id"]]
            dep_str = ""
            if tdeps:
                parts = []
                for d in tdeps:
                    f = next((x for x in new_tasks if x["id"] == d["from_task_id"]), None)
                    parts.append(f"{f['task'] if f else d['from_task_id']} ({d['type']})")
                dep_str = " ← " + ", ".join(parts)
            status = "✅" if t.get("completed") else "⬜"
            lines.append(f"{status} **{t['id']}**: {t['task']} ({t['assignee'] or '—'}, {t['duration']} дн.){dep_str}")
        total = sum(t["duration"] for t in new_tasks)
        lines.append(f"\n📊 Всего: **{len(new_tasks)}** задач, **{len(new_deps)}** связей, **{total}** дн.")
        reply = "\n".join(lines)

    elif tool_name == "reset_plan":
        new_tasks = [dict(t) for t in SEED_TASKS]
        new_deps = [dict(d) for d in SEED_DEPENDENCIES]
        reply = "🔄 План сброшен к исходным данным."

    elif tool_name == "reschedule_tasks":
        found = _find_task(arguments.get("after_task_id", ""), arguments.get("after_task_name", ""), new_tasks)
        shift = int(arguments.get("shift_days", 0))
        if found and shift:
            # Find tasks topologically after 'found'
            after_ids = {found["id"]}
            changed = True
            while changed:
                changed = False
                for d in new_deps:
                    if d["from_task_id"] in after_ids and d["to_task_id"] not in after_ids:
                        after_ids.add(d["to_task_id"])
                        changed = True
            count = 0
            for t in new_tasks:
                if t["id"] in after_ids and t["id"] != found["id"]:
                    t["duration"] = max(1, t["duration"] + shift)
                    count += 1
            reply = f"✅ Сдвинул {count} задач после **«{found['task']}»** на {shift} дн."
        else:
            reply = "🤔 Укажите задачу и сдвиг."

    else:
        reply = f"⚠️ Инструмент '{tool_name}' не реализован."

    return {"reply": reply, "tasks": new_tasks, "dependencies": new_deps}


# ═══════════════════════════════════════════════════════════════════
# System Prompt
# ═══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """Ты — AI-агент планирования проектов. Твоя задача — помогать пользователю управлять планом через вызов инструментов MCP.

ПРАВИЛА:
1. Всегда используй ТОЛЬКО предоставленные инструменты (function calling).
2. НЕ ВЫДУМЫВАЙ task_id — ищи задачи по названию в текущем плане.
3. Если не можешь найти задачу по названию — спроси пользователя или используй list_tasks.
4. Для связывания задач (add_dependency): ПЕРВАЯ упомянутая задача = предшественник (from), ВТОРАЯ = зависимая (to).
5. Отвечай кратко на русском языке.
6. Если команда простая (привет, помощь) — отвечай текстом без вызова инструментов.
7. Если план пустой — предложи создать задачи.
"""


# ═══════════════════════════════════════════════════════════════════
# LLM clients — OpenAI, Anthropic, Gemini, OpenRouter
# ═══════════════════════════════════════════════════════════════════

def _build_tasks_deps_summary(tasks: list[dict], deps: list[dict]) -> str:
    """Build structured summary of current plan for LLM context."""
    if not tasks:
        return "План пуст. Задач нет."
    tasks_summary = "\n".join(
        f"  [{t['id']}] {t['task']} (исп: {t.get('assignee') or '—'}, "
        f"{t.get('duration', 1)}дн, start={t.get('start_date','—')}, "
        f"completed={t.get('completed', False)})"
        for t in tasks
    )
    deps_summary = "\n".join(
        f"  {d['from_task_id']} → {d['to_task_id']} ({d['type']}"
        f"{'+' + str(d.get('lag_days')) + 'д' if d.get('lag_days') else ''})"
        for d in deps
    ) if deps else "  (нет связей)"
    return (
        f"Текущий план:\nЗадачи:\n{tasks_summary}\n\nСвязи:\n{deps_summary}\n\n"
        f"Всего: {len(tasks)} задач, {len(deps)} связей"
    )


def _build_tool_list_for_openai() -> list[dict]:
    """Convert MCP tools to OpenAI-compatible function definitions."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["inputSchema"],
            },
        }
        for tool in MCP_TOOLS
    ]


async def llm_openai(message: str, tasks: list[dict], deps: list[dict]) -> dict:
    """Process via OpenAI API."""
    client = AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY", ""),
        http_client=httpx.AsyncClient(timeout=httpx.Timeout(60.0)),
    )
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"{_build_tasks_deps_summary(tasks, deps)}\n\n"
                f"Сообщение пользователя: {message}"
            )},
        ],
        tools=_build_tool_list_for_openai(),
        tool_choice="auto",
        temperature=0.3,
    )
    msg = response.choices[0].message
    tool_calls = []
    reply = msg.content or ""
    if msg.tool_calls:
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            tool_calls.append({"name": tc.function.name, "arguments": args})
    return {"tool_calls": tool_calls, "reply": reply}


async def llm_anthropic(message: str, tasks: list[dict], deps: list[dict]) -> dict:
    """Process via Anthropic Claude API."""
    client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_tools = [
        {"name": t["name"], "description": t["description"], "input_schema": t["inputSchema"]}
        for t in MCP_TOOLS
    ]
    response = await client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"{_build_tasks_deps_summary(tasks, deps)}\n\n"
                f"Сообщение пользователя: {message}"
            ),
        }],
        tools=anthropic_tools,
        temperature=0.3,
    )
    tool_calls = []
    reply = ""
    for block in response.content:
        if block.type == "text":
            reply += block.text
        elif block.type == "tool_use":
            tool_calls.append({"name": block.name, "arguments": dict(block.input)})
    return {"tool_calls": tool_calls, "reply": reply}


async def llm_openrouter(message: str, tasks: list[dict], deps: list[dict]) -> dict:
    """Process via OpenRouter API (OpenAI-compatible)."""
    http_client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
    client = AsyncOpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
        base_url="https://openrouter.ai/api/v1",
        http_client=http_client,
    )
    model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    print(f"[OpenRouter] Trying model: {model}", file=sys.stderr)

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"{_build_tasks_deps_summary(tasks, deps)}\n\n"
                f"Сообщение пользователя: {message}"
            )},
        ],
        tools=_build_tool_list_for_openai(),
        tool_choice="auto",
        temperature=0.3,
    )
    msg = response.choices[0].message
    tool_calls = []
    reply = msg.content or ""

    print(f"[OpenRouter] finish_reason={response.choices[0].finish_reason}, "
          f"tool_calls={len(msg.tool_calls or [])}, reply_len={len(reply)}",
          file=sys.stderr)

    if msg.tool_calls:
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            tool_calls.append({"name": tc.function.name, "arguments": args})
            print(f"[OpenRouter] tool_call: {tc.function.name}({args})", file=sys.stderr)

    return {"tool_calls": tool_calls, "reply": reply}


async def llm_gemini(message: str, tasks: list[dict], deps: list[dict]) -> dict:
    """Process via Google Gemini API."""
    genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))
    function_declarations = [
        {"name": t["name"], "description": t["description"], "parameters": t["inputSchema"]}
        for t in MCP_TOOLS
    ]
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        tools=[{"function_declarations": function_declarations}],
    )
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"{_build_tasks_deps_summary(tasks, deps)}\n\n"
        f"Сообщение пользователя: {message}"
    )
    response = model.generate_content(prompt)
    tool_calls = []
    reply = ""
    if response.candidates:
        candidate = response.candidates[0]
        if candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if part.function_call:
                    tool_calls.append({
                        "name": part.function_call.name,
                        "arguments": dict(part.function_call.args),
                    })
                elif part.text:
                    reply += part.text
    return {"tool_calls": tool_calls, "reply": reply}


# ═══════════════════════════════════════════════════════════════════
# Local NLP fallback (mirrors frontend aiProcessCommand — FIXED)
# ═══════════════════════════════════════════════════════════════════

def local_nlp_process(message: str, tasks: list[dict], deps: list[dict]) -> dict:
    """Local NLP when no LLM API is available. Mirrors frontend logic."""
    m = message.strip()
    ml = m.lower()
    new_tasks = [dict(t) for t in tasks]
    new_deps = [dict(d) for d in deps]
    changed = False
    reply = ""

    # Help
    if ml in ("помощь", "help", "?", "команды"):
        reply = (
            "📋 **Доступные команды:**\n\n"
            "• **Добавить:** «Добавь задачу «Название» на N дней, исполнитель Имя»\n"
            "• **Изменить:** «Перенеси Название задачи на N дней»\n"
            "• **Удалить:** «Удали задачу Название»\n"
            "• **Связать:** «Свяжи Задачу А с Задачей Б»\n"
            "• **Разорвать связь:** «Разорви связь между А и Б»\n"
            "• **Назначить:** «Назначь Задачу на Имя»\n"
            "• **Список:** «Покажи план»\n"
            "• **Выполнить:** «Отметь задачу Название выполненной»\n"
            "• **Сбросить:** «Сбрось план»\n\n"
            "⚙️ Работаю через FastAPI + MCP.\n"
        )

    # Add
    elif re.search(r"добав|созда|нов(ая|ую)", ml) or re.search(r"\badd\b", ml):
        nm = re.search(r'[\xab"]([^\xbb"]+)[\xbb"]', m) or re.search(r'"([^"]+)"', m)
        task_name = nm.group(1) if nm else "Новая задача"
        dm = re.search(r"(\d+)\s*(дн|day|день|дня|дней)", ml)
        duration = int(dm.group(1)) if dm else 3
        assignee = ""
        for name in ["Анна", "Игорь", "Диана", "Алексей", "Елена"]:
            if name.lower() in ml:
                assignee = name
                break
        ids = [int(t["id"]) for t in new_tasks if t["id"].isdigit()]
        new_id = str(max(ids) + 1 if ids else 1)
        new_tasks.append({
            "id": new_id, "task": task_name, "description": "",
            "assignee": assignee, "duration": duration,
            "color": COLORS[len(new_tasks) % len(COLORS)],
        })
        changed = True
        reply = f"✅ Добавил задачу **«{task_name}»** (ID: {new_id}, {duration} дн.)"
        if assignee:
            reply += f"\n👤 Исполнитель: **{assignee}**"

    # Delete
    elif re.search(r"удал|убер|delete|remove", ml) and not re.search(r"связ", ml):
        found = _find_task("", _extract_name(m), new_tasks)
        if found:
            rid = found["id"]
            new_tasks = [t for t in new_tasks if t["id"] != rid]
            new_deps = [d for d in new_deps if d["from_task_id"] != rid and d["to_task_id"] != rid]
            changed = True
            reply = f"🗑️ Удалил задачу **«{found['task']}»** и все её связи."
        else:
            reply = "🤔 Не нашёл задачу для удаления."

    # Update duration
    elif re.search(r"перенес|передвин|сдвин|измени|move", ml):
        found = _find_task("", _extract_name(m), new_tasks)
        if found:
            dm = re.search(r"(\d+)\s*(дн|day|день|дня|дней)", ml)
            if dm:
                found["duration"] = int(dm.group(1))
                changed = True
                reply = f"✅ Длительность **«{found['task']}»** → {found['duration']} дн."
            else:
                reply = f"🤔 Укажите длительность для **«{found['task']}»**."
        else:
            reply = "🤔 Не нашёл задачу."

    # Complete
    elif re.search(r"выполн|заверш|готово|закрыт|complete|done", ml):
        found = _find_task("", _extract_name(m), new_tasks)
        if found:
            found["completed"] = True
            changed = True
            reply = f"✅ Задача **«{found['task']}»** отмечена выполненной! 🎉"
        else:
            reply = "🤔 Не нашёл задачу."

    # Unlink
    elif re.search(r"разорв|удали связь|убрать связь|remove dep", ml):
        names = re.findall(r'[\xab"]([^\xbb"]+)[\xbb"]', m)
        if len(names) < 2:
            names = _extract_two_names(m, new_tasks)
        f1 = _find_task("", names[0], new_tasks) if len(names) > 0 else None
        f2 = _find_task("", names[1], new_tasks) if len(names) > 1 else None
        if f1 and f2:
            before = len(new_deps)
            new_deps = [d for d in new_deps if not (
                (d["from_task_id"] == f1["id"] and d["to_task_id"] == f2["id"]) or
                (d["from_task_id"] == f2["id"] and d["to_task_id"] == f1["id"])
            )]
            if len(new_deps) < before:
                changed = True
                reply = f"✂️ Разорвал связь между **«{f1['task']}»** и **«{f2['task']}»**."
            else:
                reply = "🤔 Связи между этими задачами нет."
        else:
            reply = "🤔 Укажите две задачи."

    # Link — FIXED: first mentioned = predecessor, second = successor
    elif re.search(r"свяж|зависим|depend", ml):
        names = re.findall(r'[\xab"]([^\xbb"]+)[\xbb"]', m)
        if len(names) < 2:
            names = _extract_two_names_ordered(m, new_tasks)
        f1 = _find_task("", names[0], new_tasks) if len(names) > 0 else None
        f2 = _find_task("", names[1], new_tasks) if len(names) > 1 else None
        if f1 and f2:
            dep_type = "FS"
            tm = re.search(r"тип[:\s]*([SF]+)", m, re.I) or re.search(r"\b(FS|SS|FF|SF)\b", m, re.I)
            if tm:
                dep_type = tm.group(1).upper()
            lag = 0
            lm = re.search(r"задержк[аой]?\s*(\d+)", ml) or re.search(r"лаг\s*(\d+)", ml)
            if lm:
                lag = int(lm.group(1))
            new_deps = [d for d in new_deps if not (
                d["from_task_id"] == f2["id"] and d["to_task_id"] == f1["id"]
            )]
            new_deps = [d for d in new_deps if not (
                d["from_task_id"] == f1["id"] and d["to_task_id"] == f2["id"]
            )]
            dep_ids = [int(d["id"].replace("dep", "")) for d in new_deps if d["id"].startswith("dep")]
            new_id = f"dep{max(dep_ids) + 1 if dep_ids else 1}"
            new_deps.append({"id": new_id, "from_task_id": f1["id"], "to_task_id": f2["id"], "type": dep_type, "lag_days": lag})
            changed = True
            reply = f"🔗 Связь {dep_type}: **«{f1['task']}»** → **«{f2['task']}»**"
            if lag:
                reply += f"\n⏱️ Задержка: {lag} дн."
        else:
            reply = "🤔 Укажите две задачи для связи."

    # Assign
    elif re.search(r"назнач|исполнител|assign|делает", ml):
        found = _find_task("", _extract_name(m), new_tasks)
        if found:
            new_assignee = ""
            for name in ["Анна", "Игорь", "Диана", "Алексей", "Елена"]:
                if name.lower() in ml:
                    new_assignee = name
                    break
            if new_assignee:
                found["assignee"] = new_assignee
                changed = True
                reply = f"👤 Задача **«{found['task']}»** → **{new_assignee}**"
            else:
                reply = "🤔 Укажите исполнителя."
        else:
            reply = "🤔 Не нашёл задачу."

    # List
    elif re.search(r"покаж|список|list|show", ml):
        lines = ["📋 **Текущий план:**\n"]
        for t in new_tasks:
            tdeps = [d for d in new_deps if d["to_task_id"] == t["id"]]
            dep_str = ""
            if tdeps:
                parts = []
                for d in tdeps:
                    f = next((x for x in new_tasks if x["id"] == d["from_task_id"]), None)
                    parts.append(f"{f['task'] if f else d['from_task_id']} ({d['type']})")
                dep_str = " ← " + ", ".join(parts)
            lines.append(f"• **{t['id']}**: {t['task']} ({t['assignee'] or '—'}, {t['duration']} дн.){dep_str}")
        total = sum(t["duration"] for t in new_tasks)
        lines.append(f"\n📊 Всего: **{len(new_tasks)}** задач, **{len(new_deps)}** связей, **{total}** дн.")
        reply = "\n".join(lines)

    # Reset
    elif re.search(r"сброс|reset|изначаль", ml):
        new_tasks = [dict(t) for t in SEED_TASKS]
        new_deps = [dict(d) for d in SEED_DEPENDENCIES]
        changed = True
        reply = "🔄 План сброшен к исходным данным."

    # Greeting
    elif re.search(r"приве|hi|hello|здрав", ml):
        reply = "👋 Привет! Я AI-агент. Напишите **«помощь»** для списка команд."

    # Fallback
    else:
        reply = (
            "🤔 Не совсем понял. Попробуйте:\n"
            "• «Добавь задачу ...»\n"
            "• «Удали задачу ...»\n"
            "• «Перенеси ... на N дней»\n"
            "• «Свяжи ... с ...»\n"
            "• «Разорви связь ...»\n"
            "Напишите **«помощь»** для полного списка."
        )

    result = {"reply": reply}
    if changed:
        result["tasks"] = new_tasks
        result["dependencies"] = new_deps
    return result


def _extract_name(text: str) -> str:
    """Extract task name from text."""
    m = re.search(r'[\xab"]([^\xbb"]+)[\xbb"]', text)
    if m:
        return m.group(1)
    for kw in ["задачу", "задачи", "задача"]:
        idx = text.lower().find(kw)
        if idx >= 0:
            rest = text[idx + len(kw):].strip()
            end = re.search(r"[,.;!?]|\s+на\s+|\s+исполнитель|\s*$", rest)
            if end:
                return rest[:end.start()].strip()
    return ""


def _extract_two_names(text: str, tasks: list[dict]) -> list[str]:
    """Extract two task names from text using task list."""
    found = []
    text_lower = text.lower()
    for t in tasks:
        if t["task"].lower() in text_lower:
            found.append(t["task"])
    if len(found) < 2:
        tokens = set(re.findall(r"[а-яa-z0-9]+", text_lower))
        for t in tasks:
            if t["task"] in found:
                continue
            t_tokens = set(re.findall(r"[а-яa-z0-9]+", t["task"].lower()))
            if len(tokens & t_tokens) >= max(1, len(t_tokens) * 0.5):
                found.append(t["task"])
    return found[:2]


def _extract_two_names_ordered(text: str, tasks: list[dict]) -> list[str]:
    """Extract two task names preserving ORDER in text (first mentioned = predecessor)."""
    text_lower = text.lower()
    positions = []
    for t in tasks:
        pos = text_lower.find(t["task"].lower())
        if pos >= 0:
            positions.append((pos, t["task"]))
    positions.sort(key=lambda x: x[0])
    result = [name for _, name in positions]
    if len(result) < 2:
        tokens = re.findall(r"[а-яa-z0-9]+", text_lower)
        for t in tasks:
            if t["task"] in result:
                continue
            t_tokens = set(re.findall(r"[а-яa-z0-9]+", t["task"].lower()))
            if len(set(tokens) & t_tokens) >= max(1, len(t_tokens) * 0.5):
                result.append(t["task"])
    return result[:2]


# ═══════════════════════════════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {
        "service": "Gantt Plan Editor API",
        "version": "1.2.2",
        "stack": ["FastAPI", "MCP", "LLM (OpenRouter/OpenAI/Anthropic/Gemini)"],
        "endpoints": ["/api/chat", "/api/health", "/api/mcp/tools"],
    }


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "llm_providers": {
            "openrouter": bool(os.getenv("OPENROUTER_API_KEY")),
            "openai": HAS_OPENAI and bool(os.getenv("OPENAI_API_KEY")),
            "anthropic": HAS_ANTHROPIC and bool(os.getenv("ANTHROPIC_API_KEY")),
            "gemini": HAS_GEMINI and bool(os.getenv("GEMINI_API_KEY")),
        },
    }


@app.get("/api/mcp/tools")
async def list_mcp_tools():
    """MCP-compatible tool listing endpoint."""
    return {"tools": MCP_TOOLS}


@app.post("/api/mcp/call")
async def mcp_call(request: dict):
    """MCP-compatible tool execution endpoint."""
    tool_name = request.get("tool_name") or request.get("name")
    arguments = request.get("arguments") or request.get("params") or {}
    tasks = request.get("tasks", [])
    deps = request.get("dependencies", [])

    if not tool_name:
        raise HTTPException(status_code=400, detail="tool_name is required")

    valid_tools = {t["name"] for t in MCP_TOOLS}
    if tool_name not in valid_tools:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}. Available: {valid_tools}")

    result = mcp_call_tool(tool_name, arguments, tasks, deps)
    return result


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Обработка сообщения чата.
    Пробует LLM API в порядке: OpenRouter → OpenAI → Anthropic → Gemini → локальный NLP.
    """
    tasks = request.tasks
    deps = request.dependencies

    # ── Try LLM chain: OpenRouter → OpenAI → Anthropic → Gemini ──
    llm_result = None
    llm_provider = None

    # 0) OpenRouter (tried first — OpenAI-compatible)
    if os.getenv("OPENROUTER_API_KEY"):
        try:
            print(f"[LLM] Trying OpenRouter...", file=sys.stderr)
            llm_result = await llm_openrouter(request.message, tasks, deps)
            llm_provider = "openrouter"
            print(f"[LLM] OpenRouter OK — tool_calls={len(llm_result.get('tool_calls',[]))}, reply={bool(llm_result.get('reply'))}", file=sys.stderr)
        except Exception as e:
            print(f"❌ Ошибка OpenRouter: {e}", file=sys.stderr)

    # 1) OpenAI
    if llm_result is None and HAS_OPENAI and os.getenv("OPENAI_API_KEY"):
        try:
            print(f"[LLM] Trying OpenAI...", file=sys.stderr)
            llm_result = await llm_openai(request.message, tasks, deps)
            llm_provider = "openai"
        except Exception as e:
            print(f"❌ Ошибка OpenAI: {e}", file=sys.stderr)

    # 2) Anthropic
    if llm_result is None and HAS_ANTHROPIC and os.getenv("ANTHROPIC_API_KEY"):
        try:
            print(f"[LLM] Trying Anthropic...", file=sys.stderr)
            llm_result = await llm_anthropic(request.message, tasks, deps)
            llm_provider = "anthropic"
        except Exception as e:
            print(f"❌ Ошибка Anthropic: {e}", file=sys.stderr)

    # 3) Gemini
    if llm_result is None and HAS_GEMINI and os.getenv("GEMINI_API_KEY"):
        try:
            print(f"[LLM] Trying Gemini...", file=sys.stderr)
            llm_result = await llm_gemini(request.message, tasks, deps)
            llm_provider = "gemini"
        except Exception as e:
            print(f"❌ Ошибка Gemini: {e}", file=sys.stderr)

    # ── Process LLM result ──
    if llm_result and llm_result.get("tool_calls"):
        combined_tasks = [dict(t) for t in tasks]
        combined_deps = [dict(d) for d in deps]
        replies = [llm_result.get("reply", "")]

        for tc in llm_result["tool_calls"]:
            result = mcp_call_tool(tc["name"], tc["arguments"], combined_tasks, combined_deps)
            if result.get("tasks"):
                combined_tasks = result["tasks"]
            if result.get("dependencies"):
                combined_deps = result["dependencies"]
            replies.append(result.get("reply", ""))

        final_reply = "\n\n".join(filter(None, replies))
        if llm_provider:
            final_reply = f"🤖 [{llm_provider.upper()}]\n{final_reply}"

        tasks_changed = combined_tasks != tasks
        deps_changed = combined_deps != deps

        return ChatResponse(
            reply=final_reply,
            tasks=combined_tasks if tasks_changed else None,
            dependencies=combined_deps if deps_changed else None,
        )
    elif llm_result and llm_result.get("reply"):
        # LLM returned text without tool calls
        prefix = f"🤖 [{llm_provider.upper()}]\n" if llm_provider else ""
        return ChatResponse(reply=prefix + llm_result["reply"])

    # ── Fallback: local NLP ──
    print(f"[LLM] All LLMs failed/unavailable — using local NLP", file=sys.stderr)
    result = local_nlp_process(request.message, tasks, deps)
    return ChatResponse(
        reply="⚙️ [Локальный NLP]\n" + result["reply"],
        tasks=result.get("tasks"),
        dependencies=result.get("dependencies"),
    )


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    openrouter_ok = bool(os.getenv("OPENROUTER_API_KEY"))
    openai_ok = HAS_OPENAI and bool(os.getenv("OPENAI_API_KEY"))
    anthropic_ok = HAS_ANTHROPIC and bool(os.getenv("ANTHROPIC_API_KEY"))
    gemini_ok = HAS_GEMINI and bool(os.getenv("GEMINI_API_KEY"))
    has_llm = openrouter_ok or openai_ok or anthropic_ok or gemini_ok

    print("=" * 60)
    print("  Gantt Plan Editor — Backend v1.2.2")
    print("  FastAPI + MCP + LLM (OpenRouter/OpenAI/Anthropic/Gemini)")
    print("=" * 60)
    print(f"  OpenRouter: {'✅ ready' if openrouter_ok else '⚠  not set'}")
    print(f"  OpenAI:     {'✅ ready' if openai_ok else '⚠  not set'}")
    print(f"  Anthropic:  {'✅ ready' if anthropic_ok else '⚠  not set'}")
    print(f"  Gemini:     {'✅ ready' if gemini_ok else '⚠  not set'}")
    print(f"  Fallback:   ✅ local NLP engine")
    print("=" * 60)

    if not has_llm:
        print()
        print("  ⚠  НИ ОДИН LLM-ключ не найден! Бот работает без ИИ (regex).")
        print()
        print("  Способы задать ключ:")
        print()
        print("  1) .env файл (рекомендуется):")
        print("     OPENROUTER_API_KEY=sk-or-v1-ваш_ключ")
        print()
        print("  2) Командная строка:")
        print("     python main.py --openrouter-key=sk-or-v1-...")
        print()
        print("  3) Переменная окружения:")
        print("     cmd:  set OPENROUTER_API_KEY=sk-or-v1-...")
        print()
        print("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
