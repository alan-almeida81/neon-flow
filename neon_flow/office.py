"""Maestri Wire feed -> agents, live links and a transition event feed (read-only)."""
from __future__ import annotations

from collections import deque
from datetime import datetime
import re
import time


LOOP_PAUSE = 20   # s a Maestro shows its finished turn before reading as in loop again


def _ts(value) -> float:
    """Wire ISO timestamps or runtime epoch-ms → epoch seconds."""
    if isinstance(value, (int, float)):
        return value / 1000
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


# Office machines (max 10): first matching pattern wins; plain desk tools map to None.
MACHINES = [
    ("trello", "Trello", r"trello"),
    ("banco", "Banco", r"firebird|banco|sql|database|\bdb\b|mcp__db"),
    ("git", "Git", r"\bgit\b|github|\bgh\b|pull.?request"),
    ("maestri", "Maestri", r"maestri"),
    ("contexto", "Contexto", r"context-mode|ctx[-_]|context_mode"),
    ("qualidade", "Qualidade", r"ponytail|review|revis|simplify|lint|test"),
    ("web", "Web", r"web|fetch|search|docs|browser|chrome"),
    ("documentos", "Documentos", r"pdf|docx|xlsx|pptx|document|spreadsheet|presentation|canva"),
]
DESK_TOOLS = re.compile(r"^(bash|powershell|exec(_command)?|read|write|edit|multiedit|grep|glob|skill|"
                        r"todowrite|update_plan|apply_patch|shell|notebookedit|agent|task)$", re.I)


def machine_for(name: str, skill: bool = False) -> str | None:
    """Tool or skill name → machine id; None = stays at the desk."""
    if not name or (not skill and DESK_TOOLS.match(name)):
        return None
    for machine_id, _, pattern in MACHINES:
        if re.search(pattern, name, re.I):
            return machine_id
    return "outras" if skill or name.startswith("mcp") else None


def shelf_counts(board: dict) -> dict:
    """Card shelves: A Fazer splits by the Concierge `revisada` label."""
    lists = {l["id"]: l["name"].casefold() for l in board.get("lists", [])}
    counts = dict.fromkeys(("a-triar", "triados", "andamento", "revisao", "revisado", "concluido"), 0)
    for card in board.get("cards", []):
        column = lists.get(card.get("listId"), "")
        if "analisar" in column or "fazer" in column:
            counts["triados" if "revisada" in str(card.get("labels", "")).casefold() else "a-triar"] += 1
        elif "andamento" in column:
            counts["andamento"] += 1
        elif "revisão" in column or "revisao" in column:
            counts["revisao"] += 1
        elif "revisado" in column:
            counts["revisado"] += 1
        elif "conclu" in column:
            counts["concluido"] += 1
    return counts


def build_office(snapshot: dict, runtime: dict, board: dict, memory: dict) -> dict:
    """Project Maestri state into office agents, live links and a transition feed.

    `memory` persists between calls so transitions, not snapshots, become events.
    """
    now = time.time()
    events: deque = memory.setdefault("events", deque(maxlen=60))

    def event(kind: str, text: str, actors: list) -> None:
        events.appendleft({"at": int(now * 1000), "kind": kind, "text": text, "actors": actors})

    # Role-level records (no agentName) plus one per team agent: Prisma-1..3 share a role but not a task.
    records = {a["roleName"]: a for a in runtime.get("agents", []) if not a.get("agentName")}
    by_agent = {(a["roleName"], a["agentName"].casefold()): a for a in runtime.get("agents", []) if a.get("agentName")}
    cards = {c["id"]: c for c in board.get("cards", [])}
    lists = {l["id"]: l["name"] for l in board.get("lists", [])}
    nodes = {n["id"]: n for n in snapshot.get("canvas", {}).get("nodes", [])}
    known = memory.setdefault("agents", {})
    agents, names = [], {}
    for item in snapshot.get("items", []):
        terminal = item.get("terminal")
        if not terminal:
            continue
        name = terminal.get("name") or "Agente"
        names[terminal["id"]] = name
        record = by_agent.get((terminal.get("roleName"), name.casefold())) or records.get(terminal.get("roleName"), {})
        if not record and not terminal.get("roleName"):   # roleless shells (Integrador) report under their own name
            record = next((r for (_, n), r in by_agent.items() if n == name.casefold()), {})
        if name.casefold() == "lumen":
            record = runtime.get("lumen") or {}
        status = record.get("status", "unknown")
        live = bool(terminal.get("isActive"))
        # Wire isActive is the live signal; runtime can lag and misses roleless terminals.
        state = "working" if live or status == "working" else (
            status if status in {"completed", "interrupted"} else "unknown")
        attention = bool(terminal.get("needsAttention")) and state != "working"
        card = cards.get(record.get("cardId")) or {}
        tools = record.get("activeTools") or record.get("recentTools") or (
            [record["lastTool"]] if record.get("lastTool") else [])
        # Publish every destination; the browser queues each machine once per working cycle.
        machines = []
        if state == "working":
            machines = list(dict.fromkeys(m for m in (
                *[machine_for(s, True) for s in record.get("skills", [])],
                *[machine_for(t) for t in tools],
            ) if m))
        machine = machines[0] if machines else None
        # The Maestro (Orquestrador) runs an agent loop: a finished turn shows as completed for a moment,
        # then the loop reads as running again until it is interrupted or stops answering.
        loop = bool(terminal.get("isManager")) and state == "completed" and (
            time.time() - _ts(terminal.get("lastActiveAt") or record.get("updatedAt") or 0) > LOOP_PAUSE)
        if loop:
            state = "working"
        # Wire activity alone cannot attach a completed turn's card to a new turn.
        task = card.get("name") or record.get("taskCode")
        if state == "working" and status != "working":
            task = None
        agent = {
            "id": terminal["id"], "name": name, "role": terminal.get("roleName", ""),
            "machine": machine, "machines": machines, "mode": record.get("mode"),
            "kind": terminal.get("agentType", ""), "manager": bool(terminal.get("isManager")),
            "state": state, "loop": loop, "attention": attention, "live": live,
            "runtimeStatus": status,   # what the agent itself reports (Integrador: working = merge running)
            "watching": record.get("watching") or [],   # Vigia: team agents under watch this cycle
            "nextAt": record.get("nextAt"), "interval": record.get("interval"),
            "analyzed": record.get("analyzed") or [], "cycleAt": record.get("cycleAt"),   # Vigia: agents checked in the last cycle   # Vigia/Integrador: next cycle (epoch ms, s)
            "task": task,
            "column": lists.get(card.get("listId")) if task else None,
            "tools": tools if state == "working" and not loop else [], "lastTools": tools,
            "skills": record.get("skills", []), "model": (record.get("models") or {}).get(terminal.get("agentType")) or record.get("model"),
            "lastActiveAt": int(max(_ts(terminal.get("lastActiveAt")),
                                    _ts(record.get("updatedAt") or 0)) * 1000),
        }
        agents.append(agent)
        before = known.get(terminal["id"])
        if before:
            if before["state"] != state:
                label = "voltou ao loop" if loop else {"working": "começou a trabalhar", "completed": "concluiu o turno",
                         "interrupted": "foi interrompido"}.get(state, "ficou sem execução confirmada")
                suffix = f" · {agent['task']}" if state == "working" and agent["task"] else ""
                event("state", f"{name} {label}{suffix}", [terminal["id"]])
            if attention and not before["attention"]:
                event("attention", f"{name} sinalizou atenção no Maestri", [terminal["id"]])
            if state == "working" and agent["tools"] and before["tools"] != agent["tools"]:
                event("tool", f"{name} usa {', '.join(agent['tools'][:3])}", [terminal["id"]])
            if machine and before.get("machine") != machine:
                label = next(l for m, l, _ in MACHINES + [("outras", "Outras", "")] if m == machine)
                event("machine", f"{name} leva o card à máquina {label}", [terminal["id"]])
        known[terminal["id"]] = {"state": state, "attention": attention, "tools": agent["tools"], "machine": machine}

    links, active = [], set()
    seen = memory.get("links", set())
    for connection in snapshot.get("canvas", {}).get("connections", []):
        # a cross-floor link ends on a "connector" node standing for a terminal on another floor
        a, b = ((nodes.get(n, {}).get("connector") or {}).get("remoteTerminalId") or n
                for n in (connection.get("fromNodeId"), connection.get("toNodeId")))
        if not connection.get("isActive") or not (a in names or b in names):
            continue
        if a in names and b in names:
            key = ("message", a, b)
            links.append({"from": a, "to": b, "kind": "message"})
            text, actors = f"{names[a]} → {names[b]}: troca de mensagens", [a, b]
        else:
            who, other = (a, b) if a in names else (b, a)
            title = nodes.get(other, {}).get("title", "nota")
            key = ("note", who, other)
            links.append({"from": who, "to": None, "kind": "note", "label": title})
            text, actors = f"{names[who]} usa a nota “{title}”", [who]
        if key not in seen:
            event(key[0], text, actors)
        active.add(key)
    memory["links"] = active

    notes = memory.setdefault("notes", {})
    for item in snapshot.get("items", []):
        note = item.get("note")
        if not note:
            continue
        stamp = note.get("lastModifiedAt")
        if note["nodeId"] in notes and notes[note["nodeId"]] != stamp:
            event("note", f"Nota “{note.get('displayName', 'nota')}” atualizada", [])
        notes[note["nodeId"]] = stamp

    fired = memory.setdefault("routines", {})
    routines = []
    for routine in (runtime.get("routines") or {}).get("items", []):
        stamp, target = routine.get("lastFiredAt"), routine.get("terminalId")
        if stamp and routine["id"] in fired and fired[routine["id"]] != stamp:
            event("routine", f"Rotina “{routine.get('name')}” disparou em {names.get(target, 'terminal')}",
                  [target] if target in names else [])
        fired[routine["id"]] = stamp
        routines.append({"name": routine.get("name"), "terminal": target,
                         "enabled": routine.get("isEnabled"),
                         "lastFiredAt": int(_ts(stamp or 0) * 1000),
                         "every": (routine.get("schedule") or {}).get("seconds")})

    columns = memory.setdefault("cards", {})
    for card in board.get("cards", []):
        column = lists.get(card.get("listId"))
        if card["id"] in columns and columns[card["id"]] != column:
            event("card", f"Card “{card.get('name')}” → {column}", [])
        columns[card["id"]] = column

    return {
        "agents": agents, "links": links, "events": list(events), "routines": routines,
        "shelves": shelf_counts(board),
        "attentionCount": snapshot.get("workspace", {}).get("attentionCount", 0),
        "columns": [{"name": column["name"], "count": sum(c.get("listId") == column["id"]
                     for c in board.get("cards", []))} for column in board.get("lists", [])],
        "updatedAt": int(now * 1000),
    }
