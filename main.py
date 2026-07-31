"""
FastAPI backend for REPKA Project — Gantt chart AI agent.
Uses OpenRouter (OpenAI-compatible) API for LLM calls.
MCP tools: parse_command, get_tasks, add_task, delete_task, 
           update_task, add_dependency, remove_dependency.
"""

import json
import os
import re
import logging
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from openai import OpenAI

load_dotenv()

# ── Config ──────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")
SITE_NAME = os.getenv("SITE_NAME", "REPKA Gantt AI")

if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY not set in environment or .env")

client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("repka-backend")

# ── App ─────────────────────────────────────────────────────────────
app = FastAPI(title="REPKA Gantt AI Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Serve frontend ─────────────────────────────────────────────────
FRONTEND_FILE = "gantt_editor_final.html"

@app.get("/app", response_class=HTMLResponse)
def serve_frontend():
    """Serve the Gantt editor HTML from the same origin — no CORS needed."""
    import os as _os
    if _os.path.exists(FRONTEND_FILE):
        with open(FRONTEND_FILE, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    raise HTTPException(404, f"Frontend file '{FRONTEND_FILE}' not found")

# ── Models ──────────────────────────────────────────────────────────
class Task(BaseModel):
    id: str
    task: str
    description: str = ""
    assignee: str = ""
    duration: int = 3
    color: str = "#4a90d9"
    completed: bool = False
    start_date: Optional[str] = None
    end_date: Optional[str] = None

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


# ── Helper: build task/dep lookup ───────────────────────────────────
def build_context(tasks: list[dict], deps: list[dict]) -> str:
    """Build a compact text representation of current plan for the LLM."""
    lines = ["## Текущий план (задачи):"]
    for t in tasks:
        comp = "✅" if t.get("completed") else "⬜"
        lines.append(
            f"- id={t['id']} | {comp} {t['task']} | исп: {t.get('assignee','-')} | "
            f"длит: {t.get('duration','?')}д | "
            f"начало: {t.get('start_date','?')} | конец: {t.get('end_date','?')}"
        )
    lines.append("\n## Текущие зависимости:")
    for d in deps:
        from_name = next((t['task'] for t in tasks if t['id'] == d['from_task_id']), d['from_task_id'])
        to_name = next((t['task'] for t in tasks if t['id'] == d['to_task_id']), d['to_task_id'])
        lines.append(
            f"- {from_name} → {to_name} (тип={d.get('type','FS')}, лаг={d.get('lag_days',0)}д)"
        )
    if not deps:
        lines.append("- (нет зависимостей)")
    return "\n".join(lines)


# ── MCP Tool definitions (passed as system prompt) ──────────────────
SYSTEM_PROMPT = """Ты — AI-агент управления проектным планом (диаграмма Гантта). 
Твоя задача — понимать команды пользователя на русском (или английском) языке 
и возвращать ИЗМЕНЁННЫЙ план в JSON.

## Доступные действия (MCP tools):
1. **add_task** — добавить новую задачу:
   `{"action":"add_task","task":"Название","description":"...","assignee":"...","duration":N,"color":"#hex"}`
2. **update_task** — изменить существующую задачу (поиск по id или названию):
   `{"action":"update_task","task_id":"...","changes":{"task":"...","assignee":"...","duration":N,...}}`
3. **delete_task** — удалить задачу:
   `{"action":"delete_task","task_id":"..."}`
4. **add_dependency** — добавить зависимость:
   `{"action":"add_dependency","from_task_id":"...","to_task_id":"...","type":"FS|SS|FF|SF","lag_days":N}`
5. **remove_dependency** — удалить зависимость:
   `{"action":"remove_dependency","dep_id":"..."}`
6. **complete_task** — отметить задачу выполненной/вернуть в работу:
   `{"action":"complete_task","task_id":"...","completed":true/false}`
7. **help** — показать справку: `{"action":"help"}`

## Правила:
- Типы зависимостей: FS (Finish-to-Start), SS (Start-to-Start), FF (Finish-to-Finish), SF (Start-to-Finish).
- Если пользователь просит "связать А с Б" без указания типа — используй FS.
- Если задача не найдена по названию — ищи частичное совпадение (без учёта регистра).
- Для новых задач генерируй id = "new_" + номер по порядку.
- Цвета новых задач: #00b894, #6c5ce7, #fdcb6e, #e17055, #4a90d9 (по кругу).
- Длительность по умолчанию — 3 дня.
- Если пользователь пишет просто "помощь" или "help" — верни `{"action":"help"}`.
- ВСЕГДА возвращай JSON-массив действий, даже если действие одно: `[{...}]`.
- После массива действий добавь короткий дружелюбный комментарий на русском.

## Формат ответа:
```
[{"action":"...",...}]
Комментарий: твой ответ пользователю.
```
"""


# ── LLM call ────────────────────────────────────────────────────────
def call_llm(user_message: str, tasks: list[dict], deps: list[dict]) -> dict:
    """Send message to LLM, parse the response for actions."""
    context = build_context(tasks, deps)

    full_prompt = f"""{SYSTEM_PROMPT}

{context}

## Сообщение пользователя:
{user_message}

Ответ (JSON-массив действий + комментарий):"""

    logger.info("Calling LLM with %d tasks, %d deps, message: %s", len(tasks), len(deps), user_message[:80])

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": full_prompt},
            ],
            temperature=0.3,
            max_tokens=2048,
            extra_headers={
                "HTTP-Referer": SITE_URL,
                "X-Title": SITE_NAME,
            },
        )
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        raise HTTPException(status_code=502, detail=f"LLM API error: {str(e)}")

    raw = completion.choices[0].message.content.strip()
    logger.info("LLM raw response (first 300 chars): %s", raw[:300])

    return parse_llm_response(raw, tasks, deps)


def parse_llm_response(raw: str, tasks: list[dict], deps: list[dict]) -> dict:
    """Parse LLM response into actions, apply them, return {reply, tasks, dependencies}."""
    # Try to extract JSON array from response
    json_match = re.search(r'\[.*?\]', raw, re.DOTALL)
    actions = []
    parse_error = None

    if json_match:
        try:
            actions = json.loads(json_match.group(0))
        except json.JSONDecodeError as e:
            parse_error = str(e)
            logger.warning("JSON parse error: %s", e)

    # Extract comment (everything after the JSON array or after "Комментарий:")
    comment = ""
    comment_match = re.search(r'Комментарий\s*[:：]\s*(.+)', raw, re.DOTALL | re.IGNORECASE)
    if comment_match:
        comment = comment_match.group(1).strip()
    elif json_match:
        # Use text after JSON array
        after = raw[json_match.end():].strip()
        if after:
            comment = after
    else:
        # No JSON found — treat entire response as comment
        comment = raw

    if parse_error and not actions:
        return {
            "reply": f"⚠️ Не удалось разобрать ответ модели. Попробуйте переформулировать.\n\nОтвет модели:\n{raw[:500]}",
            "tasks": None,
            "dependencies": None,
        }

    # Apply actions
    new_tasks = [dict(t) for t in tasks]
    new_deps = [dict(d) for d in deps]
    reply_parts = []
    color_idx = len(new_tasks)
    COLORS = ["#00b894", "#6c5ce7", "#fdcb6e", "#e17055", "#4a90d9"]
    new_task_counter = len(new_tasks) + 1

    for action in actions:
        act = action.get("action", "")

        if act == "help":
            reply_parts.append(
                "📋 **Что я умею:**\n"
                "• «Добавь задачу X на N дней, исполнитель Y»\n"
                "• «Перенеси задачу X на N дней»\n"
                "• «Удали задачу X»\n"
                "• «Свяжи A с B, тип FS»\n"
                "• «Назначь задачу X на Y»\n"
                "• «Отметь задачу X выполненной»\n"
                "• «Покажи критический путь»"
            )

        elif act == "add_task":
            name = action.get("task", "Новая задача")
            new_id = f"new_{new_task_counter}"
            new_task_counter += 1
            new_tasks.append({
                "id": new_id,
                "task": name,
                "description": action.get("description", ""),
                "assignee": action.get("assignee", ""),
                "duration": action.get("duration", 3),
                "color": action.get("color", COLORS[color_idx % len(COLORS)]),
                "completed": False,
                "start_date": None,
                "end_date": None,
            })
            color_idx += 1
            reply_parts.append(f"✅ Добавлена задача «{name}» (id={new_id})")

        elif act == "update_task":
            tid = action.get("task_id", "")
            changes = action.get("changes", {})
            # Find task by id or name (fuzzy)
            found = None
            for t in new_tasks:
                if t["id"] == tid or t["task"].lower() == tid.lower():
                    found = t
                    break
            if not found:
                # Fuzzy search
                for t in new_tasks:
                    if tid.lower() in t["task"].lower():
                        found = t
                        break
            if found:
                old_name = found["task"]
                for k, v in changes.items():
                    if k in found:
                        found[k] = v
                reply_parts.append(f"✏️ Задача «{old_name}» обновлена: {json.dumps(changes, ensure_ascii=False)}")
            else:
                reply_parts.append(f"⚠️ Задача не найдена: «{tid}»")

        elif act == "delete_task":
            tid = action.get("task_id", "")
            found = None
            for t in new_tasks:
                if t["id"] == tid or t["task"].lower() == tid.lower():
                    found = t
                    break
            if not found:
                for t in new_tasks:
                    if tid.lower() in t["task"].lower():
                        found = t
                        break
            if found:
                new_tasks = [t for t in new_tasks if t["id"] != found["id"]]
                # Remove orphan dependencies
                new_deps = [
                    d for d in new_deps
                    if d["from_task_id"] != found["id"] and d["to_task_id"] != found["id"]
                ]
                reply_parts.append(f"🗑️ Задача «{found['task']}» удалена")
            else:
                reply_parts.append(f"⚠️ Задача не найдена для удаления: «{tid}»")

        elif act == "add_dependency":
            fid = action.get("from_task_id", "")
            tid = action.get("to_task_id", "")
            dtype = action.get("type", "FS")
            lag = action.get("lag_days", 0)

            # Resolve by name if needed
            def resolve_id(ref, task_list):
                for t in task_list:
                    if t["id"] == ref or t["task"].lower() == ref.lower():
                        return t["id"]
                for t in task_list:
                    if ref.lower() in t["task"].lower():
                        return t["id"]
                return ref

            fid_resolved = resolve_id(fid, new_tasks)
            tid_resolved = resolve_id(tid, new_tasks)

            # Check duplicate
            dup = any(
                d["from_task_id"] == fid_resolved
                and d["to_task_id"] == tid_resolved
                for d in new_deps
            )
            if not dup:
                dep_id = f"dep_llm_{len(new_deps) + 1}"
                new_deps.append({
                    "id": dep_id,
                    "from_task_id": fid_resolved,
                    "to_task_id": tid_resolved,
                    "type": dtype,
                    "lag_days": lag,
                })
                reply_parts.append(f"🔗 Добавлена зависимость: {fid} → {tid} (тип={dtype})")
            else:
                reply_parts.append(f"⚠️ Зависимость {fid} → {tid} уже существует")

        elif act == "remove_dependency":
            did = action.get("dep_id", "")
            before = len(new_deps)
            new_deps = [d for d in new_deps if d["id"] != did]
            if len(new_deps) < before:
                reply_parts.append(f"🔓 Зависимость удалена (id={did})")
            else:
                reply_parts.append(f"⚠️ Зависимость не найдена: {did}")

        elif act == "complete_task":
            tid = action.get("task_id", "")
            comp = action.get("completed", True)
            found = None
            for t in new_tasks:
                if t["id"] == tid or t["task"].lower() == tid.lower():
                    found = t
                    break
            if not found:
                for t in new_tasks:
                    if tid.lower() in t["task"].lower():
                        found = t
                        break
            if found:
                found["completed"] = comp
                status = "✅ выполнена" if comp else "🔄 возвращена в работу"
                reply_parts.append(f"{status}: «{found['task']}»")
            else:
                reply_parts.append(f"⚠️ Задача не найдена: «{tid}»")

        else:
            reply_parts.append(f"⚠️ Неизвестное действие: {act}")

    # Compose final reply
    final_reply = "\n".join(reply_parts) if reply_parts else comment or "Готово!"
    if comment and reply_parts:
        final_reply += f"\n\n💬 {comment}"

    changed = (new_tasks != [dict(t) for t in tasks]) or (new_deps != [dict(d) for d in deps])

    return {
        "reply": final_reply,
        "tasks": new_tasks if changed else None,
        "dependencies": new_deps if changed else None,
    }


# ── Routes ──────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "service": "REPKA Gantt AI Backend", "version": "1.0.0"}

@app.get("/api/health")
def health():
    return {"status": "healthy", "model": MODEL_NAME}

@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """Main chat endpoint — processes natural language commands via LLM."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message is empty")

    result = call_llm(req.message, req.tasks, req.dependencies)
    return ChatResponse(**result)


# ── Entrypoint ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
