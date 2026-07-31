"""
REPKA Gantt AI Backend v5
- FastAPI + OpenRouter + MCP
- Serves gantt_editor_final.html at localhost:8000
- Compatible with frontend field names (task, from_task_id, to_task_id)
"""

import os
import re
import json
import uuid
import logging
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

# Config
load_dotenv()

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")
SITE_NAME = os.getenv("SITE_NAME", "REPKA Gantt AI")

if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "sk-or-v1-...":
    raise RuntimeError(
        "OPENROUTER_API_KEY not set. "
        "Edit .env with your key from https://openrouter.ai/keys"
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("gantt")

client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)

# Serve Vite build (frontend/dist/) or fallback to single HTML
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend", "dist")
FRONTEND_INDEX = os.path.join(FRONTEND_DIR, "index.html")
FRONTEND_FILE = "gantt_editor_final.html"

# App
app = FastAPI(title="REPKA Gantt AI", version="5.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models - accept both frontend ("task", "from_task_id") and backend ("name", "from_id")
class Task(BaseModel):
    id: str
    task: str = ""
    name: str = ""
    description: str = ""
    assignee: str = ""
    duration: int = 0
    progress: int = 0
    color: str = ""
    links: list[str] = []

class Dependency(BaseModel):
    id: str = ""
    from_task_id: str = ""
    to_task_id: str = ""
    from_id: str = ""
    to_id: str = ""
    type: str = "FS"

class ChatRequest(BaseModel):
    message: str
    tasks: list[Task]
    dependencies: list[Dependency]

class ChatResponse(BaseModel):
    reply: str
    tasks: Optional[list[Task]] = None
    dependencies: Optional[list[Dependency]] = None

# Helpers
def t_name(t):
    return t.get("task") or t.get("name", "")

def d_from(d):
    return d.get("from_id") or d.get("from_task_id", "")

def d_to(d):
    return d.get("to_id") or d.get("to_task_id", "")

def norm_task(t):
    return {
        "id": str(t.get("id", "")),
        "name": t_name(t),
        "description": t.get("description", ""),
        "assignee": t.get("assignee", ""),
        "duration": t.get("duration", 0),
        "progress": t.get("progress", 0),
        "color": t.get("color", ""),
    }

def norm_dep(d):
    return {
        "id": d.get("id", ""),
        "from_id": d_from(d),
        "to_id": d_to(d),
        "type": d.get("type", "FS"),
    }

def build_context(tasks, dependencies):
    lines = ["## Current plan"]
    for t in tasks:
        dur = t.get("duration", 0)
        assignee = t.get("assignee", "-")
        lines.append(
            "  " + t["id"] + ": " + t["name"] +
            " (" + assignee + ", " + str(dur) + " days)"
        )
    lines.append("## Dependencies")
    for d in dependencies:
        from_name = ""
        to_name = ""
        for t in tasks:
            if t["id"] == d["from_id"]:
                from_name = t["name"]
            if t["id"] == d["to_id"]:
                to_name = t["name"]
        did = d.get("id", "") or ""
        dtype = d.get("type", "FS")
        lines.append("  " + did + ": " + from_name + " -> " + to_name + " (" + dtype + ")")
    return "\n".join(lines)

def apply_actions(actions, tasks, dependencies):
    new_tasks = [dict(t) for t in tasks]
    new_deps = [dict(d) for d in dependencies]
    messages = []

    for a in actions:
        action = a.get("action", "")
        try:
            if action == "add_task":
                max_id = max(
                    (int(t["id"]) for t in new_tasks if str(t["id"]).isdigit()),
                    default=0
                )
                new_id = str(max_id + 1)
                nt = {
                    "id": new_id,
                    "name": a.get("name", "New task"),
                    "description": a.get("description", ""),
                    "assignee": a.get("assignee", ""),
                    "duration": a.get("duration", 1),
                    "progress": 0,
                    "color": "",
                }
                new_tasks.append(nt)
                msg = "Task '" + nt["name"] + "' (#" + new_id + ", " + str(nt["duration"]) + " days) added"
                messages.append(msg)

            elif action == "update_task":
                tid = str(a.get("id", ""))
                for t in new_tasks:
                    if t["id"] == tid:
                        if "name" in a:
                            t["name"] = a["name"]
                        if "duration" in a:
                            t["duration"] = a["duration"]
                        if "assignee" in a:
                            t["assignee"] = a["assignee"]
                        if "description" in a:
                            t["description"] = a["description"]
                        messages.append("Task '" + t_name(t) + "' updated")
                        break

            elif action == "delete_task":
                tid = str(a.get("id", ""))
                removed = [t for t in new_tasks if t["id"] == tid]
                new_tasks[:] = [t for t in new_tasks if t["id"] != tid]
                new_deps[:] = [
                    d for d in new_deps
                    if d_from(d) != tid and d_to(d) != tid
                ]
                if removed:
                    messages.append("Task '" + t_name(removed[0]) + "' deleted")

            elif action == "add_dependency":
                from_id = str(a.get("from_id", ""))
                to_id = str(a.get("to_id", ""))
                dep_id = "dep_" + uuid.uuid4().hex[:6]
                nd = {
                    "id": dep_id,
                    "from_id": from_id,
                    "to_id": to_id,
                    "type": a.get("type", "FS"),
                }
                new_deps.append(nd)
                messages.append("Dependency " + from_id + " -> " + to_id + " added")

            elif action == "remove_dependency":
                did = a.get("id", "")
                new_deps[:] = [d for d in new_deps if d.get("id") != did]
                messages.append("Dependency removed")

            elif action == "complete_task":
                tid = str(a.get("id", ""))
                for t in new_tasks:
                    if t["id"] == tid:
                        t["progress"] = 100
                        messages.append("Task '" + t_name(t) + "' completed")
                        break
        except Exception as e:
            messages.append("Error: " + str(e))

    return new_tasks, new_deps, "\n".join(messages)

MCP_PROMPT = (
    "You are an AI assistant for a Gantt chart editor.\n"
    "You can modify the project plan. Reply with a JSON array of actions.\n\n"
    "Available actions:\n"
    '- {"action":"add_task","name":"Task name","description":"...","assignee":"...","duration":N}\n'
    '- {"action":"update_task","id":"1","name":"...","duration":N,"assignee":"..."}\n'
    '- {"action":"delete_task","id":"1"}\n'
    '- {"action":"add_dependency","from_id":"1","to_id":"2","type":"FS"}\n'
    '- {"action":"remove_dependency","id":"dep_abc123"}\n'
    '- {"action":"complete_task","id":"1"}\n\n'
    "Rules:\n"
    "1. Reply in Russian language.\n"
    "2. If the user asks to modify the plan - return JSON with actions.\n"
    "3. If just asking a question - reply with plain text, no JSON.\n"
    "4. Duration is integer number of days.\n"
    "5. Work only with tasks present in the context."
)

# Routes
@app.get("/api/health")
async def health():
    return {"status": "ok", "model": MODEL_NAME}

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    raw_tasks = [t.model_dump() for t in req.tasks]
    raw_deps = [d.model_dump() for d in req.dependencies]
    nt = [norm_task(t) for t in raw_tasks]
    nd = [norm_dep(d) for d in raw_deps]
    ctx = build_context(nt, nd)

    logger.info("-> OpenRouter: " + req.message[:100])

    try:
        completion = client.chat.completions.create(
            extra_headers={"HTTP-Referer": SITE_URL, "X-Title": SITE_NAME},
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": MCP_PROMPT},
                {"role": "user", "content": ctx + "\n\n## Request\n" + req.message}
            ],
            temperature=0.3,
            max_tokens=2000,
        )
        raw = completion.choices[0].message.content.strip()
        logger.info("<- OpenRouter: " + raw[:150])
    except Exception as e:
        logger.error("OpenRouter error: " + str(e))
        return ChatResponse(reply="OpenRouter error: " + str(e))

    # Try to parse JSON actions
    try:
        cleaned = raw
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        actions = json.loads(cleaned)
        if isinstance(actions, dict):
            actions = [actions]
        if isinstance(actions, list) and len(actions) > 0 and "action" in actions[0]:
            new_tasks, new_deps, reply = apply_actions(actions, nt, nd)
            ft = [
                Task(
                    id=t["id"], task=t["name"],
                    description=t.get("description", ""),
                    assignee=t.get("assignee", ""),
                    duration=t.get("duration", 0),
                    progress=t.get("progress", 0),
                    color=t.get("color", "")
                )
                for t in new_tasks
            ]
            fd = [
                Dependency(
                    id=d.get("id", ""),
                    from_task_id=d.get("from_id", ""),
                    to_task_id=d.get("to_id", ""),
                    type=d.get("type", "FS")
                )
                for d in new_deps
            ]
            return ChatResponse(reply=reply, tasks=ft, dependencies=fd)
    except (json.JSONDecodeError, KeyError) as e:
        logger.info("Plain text response: " + str(e))

    return ChatResponse(reply=raw)

@app.get("/{path:path}")
async def serve_spa(path: str):
    # First, try API routes - skip for known paths
    file_path = os.path.join(FRONTEND_DIR, path) if FRONTEND_DIR and os.path.exists(FRONTEND_DIR) else None
    if file_path and os.path.isfile(file_path):
        return FileResponse(file_path)
    # Serve index.html (SPA routing)
    if os.path.exists(FRONTEND_INDEX):
        return FileResponse(FRONTEND_INDEX, media_type="text/html")
    # Fallback to old single-file HTML
    if os.path.exists(FRONTEND_FILE):
        return FileResponse(FRONTEND_FILE, media_type="text/html")
    return {"error": "No frontend found"}

@app.get("/")
async def serve_root():
    if os.path.exists(FRONTEND_INDEX):
        return FileResponse(FRONTEND_INDEX, media_type="text/html")
    if os.path.exists(FRONTEND_FILE):
        return FileResponse(FRONTEND_FILE, media_type="text/html")
    return {"error": "No frontend found"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
