"""Neon Flow: read-only agent-flow projection of the Maestri Wire feed.

Reuses the Pixel Office projection (states, links, transition events) and adds the SDD stage of
each agent, its team floor and a sanitized terminal tail. Never sends input to Maestri.
"""
import re

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
        "laneRuns": runs, "events": office["events"],
        "routines": office["routines"], "shelves": office["shelves"],
        "columns": office["columns"], "attentionCount": office["attentionCount"],
        "activeRun": board.get("activeRun"), "boardError": board.get("error"),
        "updatedAt": office["updatedAt"],
    }
