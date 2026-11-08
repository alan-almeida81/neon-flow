import unittest

from neon_flow.flow import build_flow, stage_of, tail


def terminal(i, name, role='', floor='Térreo', live=False, manager=False, preview=None):
    return {'kind': 'terminal', 'terminal': {
        'id': i, 'name': name, 'roleName': role, 'floorName': floor, 'isActive': live,
        'isManager': manager, 'needsAttention': False, 'agentType': 'codex', 'roleColor': '#FF9500',
        'preview': preview or []}}


class StageTests(unittest.TestCase):
    def test_pipeline_roles_and_control_terminals(self):
        self.assertEqual(stage_of('Concierge', 'Triagem de Demandas Tooling'), ('stage', 'triagem'))
        self.assertEqual(stage_of('Prisma-2', 'Análise Tooling'), ('stage', 'analise'))
        self.assertEqual(stage_of('Forja-1', 'Implementação Tooling'), ('stage', 'implementacao'))
        self.assertEqual(stage_of('Sentinela-3', 'Revisão Tooling'), ('stage', 'revisao'))
        self.assertEqual(stage_of('Integrador', ''), ('stage', 'integracao'))
        self.assertEqual(stage_of('Orquestrador', 'Orquestrador Tooling'), ('control', 'orquestrador'))
        self.assertEqual(stage_of('Lumen', 'Consultor Hermes Tooling'), ('control', 'consultor'))
        self.assertEqual(stage_of('Claude Code', ''), ('control', 'auxiliar'))

    def test_tail_strips_ansi_and_control_characters(self):
        lines = ['\x1b[32mok\x1b[0m', '', '  ', 'a\x07b', *[f'l{i}' for i in range(10)]]
        self.assertEqual(tail(lines)[-1], 'l9')
        self.assertEqual(len(tail(lines)), 6)
        self.assertEqual(tail(['\x1b[1;31mfalha\x1b[0m']), ['falha'])
        self.assertEqual(tail(['x' * 500])[0], 'x' * 160)


class BuildFlowTests(unittest.TestCase):
    def test_projection_adds_stage_floor_and_team_status(self):
        snapshot = {
            'workspace': {'name': 'tooling-core', 'floors': [
                {'name': 'Térreo', 'isActive': True, 'status': {'text': '3.6 em curso', 'progress': .4}},
                {'name': 'Equipe Alfa', 'isActive': False}]},
            'items': [terminal('o', 'Orquestrador', 'Orquestrador Tooling', manager=True),
                      terminal('f', 'Forja-1', 'Implementação Tooling', 'Equipe Alfa', live=True,
                               preview=['\x1b[33mtestando\x1b[0m'])],
            'canvas': {'nodes': [], 'connections': [{'fromNodeId': 'o', 'toNodeId': 'f', 'isActive': True}]}}
        board = {'activeRun': {'runId': 'r1', 'cardId': 'c', 'status': 'active'}}
        flow = build_flow(snapshot, {'agents': []}, board, {})
        agents = {a['id']: a for a in flow['agents']}
        self.assertEqual((agents['f']['kind'], agents['f']['slot'], agents['f']['floor']),
                         ('stage', 'implementacao', 'Equipe Alfa'))
        self.assertEqual(agents['f']['state'], 'working')
        self.assertEqual(agents['f']['tail'], ['testando'])
        self.assertEqual(agents['o']['kind'], 'control')
        self.assertEqual(flow['floors'][0]['status'], '3.6 em curso')
        self.assertEqual(flow['links'], [{'from': 'o', 'to': 'f', 'kind': 'message'}])
        self.assertEqual(flow['activeRun']['runId'], 'r1')
        self.assertEqual([s['id'] for s in flow['stages']],
                         ['triagem', 'analise', 'implementacao', 'revisao', 'integracao'])
        self.assertEqual(flow['connections'], [{'id': None, 'kind': '', 'active': True, 'from': 'o', 'to': 'f'}])

    def test_real_canvas_connections_notes_and_lane_runs(self):
        snapshot = {
            'workspace': {'name': 'w', 'floors': []},
            'items': [terminal('o', 'Orquestrador', 'Orquestrador Tooling', manager=True),
                      terminal('s', 'Sentinela-2', 'Revisão Tooling', 'Equipe Beta'),
                      {'kind': 'note', 'note': {'nodeId': 'n', 'displayName': 'Painel — Operação',
                                                'lastModifiedAt': '2026-11-07T10:00:00Z'}}],
            'canvas': {'nodes': [{'id': 'stack', 'kind': 'noteStack', 'title': 'Histórico', 'subtitle': 'Fila 3.2'}],
                       'connections': [
                           {'id': 'c1', 'kind': 'crossFloor', 'fromNodeId': 'o', 'toNodeId': 's', 'isActive': False},
                           {'id': 'c2', 'kind': 'note', 'fromNodeId': 'o', 'toNodeId': 'n', 'isActive': True},
                           {'id': 'c3', 'kind': 'note', 'fromNodeId': 'o', 'toNodeId': 'stack', 'isActive': False},
                           {'id': 'c4', 'kind': 'note', 'fromNodeId': 'x', 'toNodeId': 'y', 'isActive': True}]}}
        board = {'cards': [{'id': 'card1', 'name': '3.6 Ajuste'}], 'history': {'runs': [
            {'runId': 'new', 'cardId': 'card1', 'status': 'reviewing', 'lane': 2, 'stages': [
                {'role': 'implementation', 'outcome': 'ready', 'at': 't'}], 'pr': 'https://github.com/a/b/pull/1',
             'updatedAt': '2026-11-07'},
            {'runId': 'old', 'cardId': 'gone', 'status': 'reviewed', 'lane': 2, 'stages': [], 'pr': None},
            {'runId': 'a1', 'cardId': 'gone', 'status': 'failed', 'lane': 1, 'stages': [], 'pr': None},
            {'runId': 'nolane', 'cardId': 'gone', 'status': 'active', 'lane': None, 'stages': [], 'pr': None}]}}
        flow = build_flow(snapshot, {'agents': []}, board, {})
        self.assertEqual([(c['id'], c['kind'], c['active'], c['from'], c['to'], c.get('note')) for c in flow['connections']],
                         [('c1', 'crossFloor', False, 'o', 's', None), ('c2', 'note', True, 'o', None, 'n'),
                          ('c3', 'note', False, 'o', None, 'stack')])
        notes = {n['id']: n for n in flow['notes']}
        self.assertEqual(notes['n']['title'], 'Painel — Operação')
        self.assertEqual((notes['stack']['title'], notes['stack']['subtitle']), ('Histórico', 'Fila 3.2'))
        self.assertEqual(notes['n']['terminals'], ['o'])
        beta = flow['laneRuns']['Beta']
        self.assertEqual((beta['runId'], beta['card'], beta['open'], beta['pr']), ('new', '3.6 Ajuste', True, True))
        self.assertEqual(beta['stages'], [{'role': 'implementation', 'outcome': 'ready'}])
        self.assertEqual(flow['laneRuns']['Alfa']['card'], 'gone')
        self.assertEqual(set(flow['laneRuns']), {'Alfa', 'Beta'})
        self.assertEqual(next(a for a in flow['agents'] if a['id'] == 's')['color'], '')


if __name__ == '__main__':
    unittest.main()
