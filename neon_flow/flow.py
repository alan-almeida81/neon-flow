"""Neon Flow: read-only agent-flow projection of the Maestri Wire feed.

Reuses the Pixel Office projection (states, links, transition events) and adds the SDD stage of
each agent, its team floor and a sanitized terminal tail. Never sends input to Maestri.
"""
import re
from datetime import datetime

from .office import build_office

# Pipeline order mirrors docs/FLUXO.md: triagem → análise → implementação → revisão → integração.
STAGES = [
    ("triagem", "Triagem", r"concierge|triagem"),
    ("analise", "Análise", r"prisma|an[aá]lise"),
    ("implementacao", "Implementação", r"forja|implementa"),
    ("revisao", "Revisão", r"sentinela|revis"),
    ("integracao", "Integração", r"integrador|integra"),
]
CONTROL = [
    ("orquestrador", r"orquestrador"),
    ("consultor", r"lumen|hermes|consultor"),
    ("vigia", r"vigia"),
]
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|[\x00-\x08\x0b-\x1f\x7f]")
TAIL_LINES, TAIL_WIDTH = 6, 160


def stage_of(name: str, role: str) -> tuple[str, str]:
    """(kind, id): kind 'stage' for pipeline roles, 'control' for coordination/support terminals."""
    text = f"{name} {role}"
    for stage_id, _, pattern in STAGES:
        if re.search(pattern, text, re.I):
            return "stage", stage_id
    for control_id, pattern in CONTROL:
        if re.search(pattern, text, re.I):
            return "control", control_id
    return "control", "auxiliar"


def tail(preview) -> list[str]:
    lines = [ANSI.sub("", str(line)).rstrip()[:TAIL_WIDTH] for line in (preview or [])]
    return [line for line in lines if line.strip()][-TAIL_LINES:]


LANE_FLOORS = {1: "Alfa", 2: "Beta", 3: "Gama"}  # docs/EQUIPES.md: Equipe Alfa = lane 1, ...
OPEN_RUNS = {"claiming", "active", "reviewing"}


def canvas_links(snapshot: dict, terminals: dict) -> tuple[list, list]:
    """Every Maestri canvas connection (active or not) and the notes wired to terminals."""
    by_node = {t.get("nodeId") or tid: tid for tid, t in terminals.items()}
    nodes = {n["id"]: n for n in snapshot.get("canvas", {}).get("nodes", [])}
    # A cross-floor link ends on a "connector" node that stands for a terminal on another floor.
    for nid, n in nodes.items():
        remote = (n.get("connector") or {}).get("remoteTerminalId")
        if n.get("kind") == "connector" and remote in terminals:
            by_node.setdefault(nid, remote)
    note_items = {item["note"]["nodeId"]: item["note"] for item in snapshot.get("items", []) if item.get("note")}
    links, notes = [], {}
    for c in snapshot.get("canvas", {}).get("connections", []):
        a, b = c.get("fromNodeId"), c.get("toNodeId")
        if a not in by_node and b not in by_node:
            continue
        link = {"id": c.get("id"), "kind": c.get("kind", ""), "active": bool(c.get("isActive")),
                "from": by_node.get(a), "to": by_node.get(b)}
        other = b if a in by_node and b not in by_node else a if b in by_node and a not in by_node else None
        if other:
            node, item = nodes.get(other, {}), note_items.get(other, {})
            note = notes.setdefault(other, {
                "id": other, "kind": node.get("kind", "note"),
                "title": item.get("displayName") or node.get("title") or "nota",
                "subtitle": node.get("subtitle") or "", "lastModifiedAt": item.get("lastModifiedAt"),
                "terminals": []})
            note["terminals"].append(by_node.get(a) or by_node.get(b))
            link["note"] = other
        links.append(link)
    return links, list(notes.values())


def lane_runs(board: dict) -> dict:
    """Latest queue run per team (lane), with card name and confirmed stage outcomes."""
    cards = {c["id"]: c.get("name", "") for c in board.get("cards", [])}
    result = {}
    for run in (board.get("history") or {}).get("runs", []):  # newest first
        floor = LANE_FLOORS.get(run.get("lane"))
        if not floor or floor in result:
            continue
        result[floor] = {"runId": run["runId"], "card": cards.get(run["cardId"]) or run["cardId"],
                         "status": run["status"], "open": run["status"] in OPEN_RUNS,
                         "stages": [{"role": s["role"], "outcome": s["outcome"]} for s in run.get("stages", [])],
                         "pr": bool(run.get("pr")), "updatedAt": run.get("updatedAt")}
    return result


def pending_triage(board: dict) -> list:
    """Cards the triage touched but left in "A analisar" (agents/porteiro-loop.md).

    `decision`: PENDENTE_SEM_IA done right (revisada, no ia) — the operator must answer.
    `fail`: anything else the Concierge left half-way — released but not moved, labels that contradict
    the result, or `revisada` with no triage comment. A description edited after the triage means the
    operator already answered (`reavaliar`) and raises nothing."""
    lists = {l["id"]: l["name"].casefold() for l in board.get("lists", [])}
    out = []
    for card in board.get("cards", []):
        if lists.get(card.get("listId")) != "a analisar":
            continue
        labels = {str(l.get("name", "")).casefold() for l in card.get("labels", [])}
        triage = card.get("triage") or {}
        result = str(triage.get("result", "")).upper()
        if result == "REAVALIAR" or not (triage or "revisada" in labels or "ia" in labels):
            continue
        if result == "PENDENTE_SEM_IA" and "revisada" in labels and "ia" not in labels:
            kind, how = "decision", "A triagem não liberou o card e aguarda sua decisão."
        elif result.startswith("ELEGIVEL") or ("ia" in labels and result != "PENDENTE_SEM_IA"):
            kind, how = "fail", "A triagem liberou o card, mas ele não foi movido para A fazer."
        elif result == "PENDENTE_SEM_IA":
            kind, how = "fail", ("A triagem deixou o card pendente, mas as etiquetas não conferem "
                                 f"(revisada: {'sim' if 'revisada' in labels else 'não'}, ia: {'sim' if 'ia' in labels else 'não'}).")
        elif not triage:
            kind, how = "fail", "O card foi marcado como revisado sem comentário de triagem e não foi movido."
        else:
            kind, how = "fail", f"A triagem registrou um resultado inesperado ({result or 'vazio'}) e não moveu o card."
        out.append({"kind": kind, "card": card.get("name", ""), "url": card.get("url", ""), "how": how,
                    "result": result, "reason": triage.get("reason", ""), "evidence": triage.get("evidence", ""),
                    "pending": triage.get("pending", ""), "at": triage.get("at", "")})
    return sorted(out, key=lambda p: p["kind"] != "fail")   # failures first


def triage_question(items: list) -> str:
    """Operator-facing text: which card, how it ended, why, and what is missing."""
    blocks = []
    for p in items[:2]:
        when = ""
        if p["at"]:
            try:
                when = f" (triagem às {datetime.fromisoformat(p['at'].replace('Z', '+00:00')).astimezone():%H:%M})"
            except ValueError:
                pass
        blocks.append("\n".join(filter(None, [
            f"{p['card']}{when}", p["how"],
            f"Motivo: {p['reason']}" if p["reason"] else "",
            f"Evidência: {p['evidence']}" if p["evidence"] else "",
            f"Pendência: {p['pending']}" if p["pending"] else ""])))
    if len(items) > 2:
        blocks.append(f"+{len(items) - 2} card(s) também parados na triagem.")
    return "\n\n".join(blocks)


def build_flow(snapshot: dict, runtime: dict, board: dict, memory: dict) -> dict:
    office = build_office(snapshot, runtime, board, memory)
    terminals = {item["terminal"]["id"]: item["terminal"]
                 for item in snapshot.get("items", []) if item.get("terminal")}
    agents = []
    for agent in office["agents"]:
        terminal = terminals.get(agent["id"], {})
        kind, slot = stage_of(agent["name"], agent["role"])
        agents.append({**agent, "kind": kind, "slot": slot, "agentType": terminal.get("agentType", ""),
                       "floor": terminal.get("floorName") or "Térreo",
                       "color": terminal.get("color") or "", "roleColor": terminal.get("roleColor") or "",
                       "maestriStatus": terminal.get("status", ""),
                       "tail": tail(terminal.get("preview"))})
    waiting = pending_triage(board)
    triage = next((a for a in agents if a["slot"] == "triagem"), None)
    if waiting and triage:   # stays up until the card moves, even after the Concierge's turn ended
        fail = waiting[0]["kind"] == "fail"
        triage["question"] = triage_question(waiting)
        triage["questionKind"] = "fail" if fail else "decision"
        triage["questionTitle"] = "TRIAGEM NÃO MOVEU O CARD" if fail else "DECISÃO PENDENTE NA TRIAGEM"
        triage["task"] = triage.get("task") or waiting[0]["card"].split(" ")[0]
    connections, notes = canvas_links(snapshot, terminals)
    runs = lane_runs(board)
    workspace = snapshot.get("workspace", {})
    floors = [{"name": floor.get("name"), "active": bool(floor.get("isActive")),
               "attention": floor.get("attentionCount", 0),
               "status": (floor.get("status") or {}).get("text", ""),
               "state": (floor.get("status") or {}).get("state", ""),
               "progress": (floor.get("status") or {}).get("progress")}
              for floor in workspace.get("floors", [])]
    return {
        "workspace": workspace.get("name", ""), "floors": floors,
        "stages": [{"id": s, "label": label} for s, label, _ in STAGES],
        "agents": agents, "links": office["links"], "connections": connections, "notes": notes,
        "laneRuns": runs, "events": office["events"], "pendingTriage": waiting,
        "routines": office["routines"], "shelves": office["shelves"],
        "columns": office["columns"], "attentionCount": office["attentionCount"],
        "activeRun": board.get("activeRun"), "boardError": board.get("error"),
        "updatedAt": office["updatedAt"],
    }
