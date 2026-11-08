# Contrato de dados

A página (`web/index.html`) lê `GET /api/flow` a cada poucos segundos. O terminal completo usa `GET /api/terminal-stream` e `POST /api/prompt` (veja [NEON-FLOW.md](NEON-FLOW.md#terminal-completo)). Qualquer backend que devolva esse JSON pode alimentá-la, não só o Maestri. Com `?demo=1`, a página gera os próprios dados e não chama o backend.

## Resposta de `/api/flow`

```jsonc
{
  "workspace": "nome do workspace",
  "floors": [{"name": "Equipe Alfa", "active": true, "attention": 0, "status": "texto", "state": "working", "progress": 0.4}],
  "stages": [{"id": "triagem", "label": "Triagem"}, {"id": "analise", "label": "Análise"}, ...],
  "agents": [{
    "id": "terminal-id", "name": "Forja-1", "role": "Implementação",
    "kind": "stage | control", "slot": "triagem|analise|implementacao|revisao|integracao|orquestrador|consultor|vigia|auxiliar",
    "floor": "Equipe Alfa", "manager": false, "agentType": "codex|claude_code|custom|...",
    "state": "working | completed | interrupted | failed | unknown",
    "attention": false,                 // pedindo decisão ao usuário: abre o cartão de decisão
    "question": null,                   // opcional: texto da pergunta; sem ele, o cartão usa a cauda
    "task": "9.1 Ajustar pipeline", "tools": ["apply_patch"], "lastTools": [], "skills": [], "model": "claude-opus-5-5", "mode": null,
    "color": "#FF9500", "lastActiveAt": 1731000000000, "tail": ["últimas linhas do terminal"]
  }],
  "connections": [{"id": "c1", "kind": "crossFloor|note|...", "active": true, "from": "terminal-id", "to": "terminal-id", "note": null}],
  "notes": [{"id": "n1", "kind": "note", "title": "Painel", "subtitle": "", "lastModifiedAt": "...", "terminals": ["terminal-id"]}],
  "links": [{"from": "a", "to": "b", "kind": "message"}],
  "events": [{"at": 1731000000000, "kind": "state|attention|tool|machine|message|note|routine|card", "text": "...", "actors": ["id"]}],
  "routines": [{"name": "Triagem", "terminal": "id", "enabled": false, "lastFiredAt": 0, "every": 1200}],
  "laneRuns": {"Alfa": {"runId": "...", "card": "...", "status": "active", "open": true, "stages": [], "pr": false}},
  "shelves": {"a-triar": 0, "triados": 0, "andamento": 0, "revisao": 0, "revisado": 0, "concluido": 0},
  "columns": [{"name": "A fazer", "count": 3}],
  "attentionCount": 0, "activeRun": null, "boardError": null, "updatedAt": 1731000000000
}
```

Só `agents`, `connections`, `notes` e `stages` são essenciais. Os demais podem vir vazios.

## Entradas do backend Python

`build_flow(snapshot, runtime, board, memory)` em `neon_flow/flow.py`:

| Entrada | Origem | Campos usados |
|---|---|---|
| `snapshot` | feed do Maestri Wire (`/api/workspaces/{id}/feed`) ou `--snapshot` | `workspace.name/floors/attentionCount`, `items[].terminal` (`id, name, roleName, floorName, isActive, isManager, needsAttention, agentType, color, preview, lastActiveAt, status`), `items[].note`, `canvas.nodes`, `canvas.connections` (`fromNodeId, toNodeId, isActive, kind`) |
| `runtime` | `--runtime` (opcional) | `agents[]` por `roleName`: `status, activeTools, recentTools, lastTool, skills, model, cardId, taskCode, mode, updatedAt`; `lumen`; `routines.items` (lido de `~/.maestri/routines.json` se ausente) |
| `board` | `--board` (opcional) | `lists[]`, `cards[]` (`id, name, listId, labels`), `history.runs[]` (`runId, cardId, status, lane, stages, pr`), `activeRun` |
| `memory` | dicionário mantido pelo servidor | guarda o estado anterior para transformar mudanças em eventos |
