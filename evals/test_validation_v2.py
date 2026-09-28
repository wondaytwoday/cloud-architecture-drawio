"""Regressions for malformed models, text clipping and CSP placement bypasses."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest


BASE = Path(__file__).resolve().parents[1]
SCRIPTS = BASE/'cloud-architecture-drawio/scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('validation_compiler', SCRIPTS/'cloud_drawio.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
from model_validation import validate_structure


class ModelValidationTests(unittest.TestCase):
    def model(self, name='azure-regional'):
        return json.loads((BASE/'cloud-architecture-drawio/assets/templates'/f'{name}.json').read_text())

    def validate(self, model):
        return validate_structure(model, c.CAT, c.wrapped, c.header_rect)

    def rejects(self, model, message):
        errors, _ = self.validate(model)
        self.assertTrue(any(message in error for error in errors), errors)

    def test_supplied_templates_fit(self):
        for name in ('aws-three-tier', 'azure-regional', 'gcp-regional'):
            with self.subTest(name=name):
                self.assertEqual(self.validate(self.model(name)), ([], []))

    def test_rejects_reserved_drawio_ids(self):
        for reserved in ('0', '1', '__generated'):
            with self.subTest(reserved=reserved):
                m = self.model()
                m['nodes'][0]['id'] = reserved
                self.rejects(m, 'reserved ID')

    def test_duplicate_ids_remain_rejected(self):
        m = self.model()
        m['nodes'][0]['id'] = m['nodes'][1]['id']
        self.rejects(m, 'Duplicate IDs')

    def test_nonobject_models_and_collections_never_raise(self):
        for value in (None, [], 'bad', 7):
            self.rejects(value, 'Model must be a JSON object')
        for collection in ('containers', 'nodes', 'edges'):
            for value in (None, {}, 'bad', [None], [17], ['bad']):
                with self.subTest(collection=collection, value=value):
                    m = self.model()
                    m[collection] = value
                    self.rejects(m, collection)

    def test_bad_coordinates_never_reach_geometry(self):
        for value in ('oops', None, [], {}, True, float('nan'), float('inf'), 10**1000):
            with self.subTest(value=str(value)[:30]):
                m = self.model()
                m['nodes'][0]['x'] = value
                self.rejects(m, 'finite numbers')
        m = self.model()
        m['nodes'][0]['w'] = 0
        self.rejects(m, 'nonpositive size')

    def test_canvas_dimensions_are_required_and_finite(self):
        for field in ('width', 'height'):
            m = self.model()
            del m[field]
            self.rejects(m, f'{field}: mandatory')
            for value in (True, None, '1320', 0, -1, float('inf')):
                m = self.model()
                m[field] = value
                self.rejects(m, f'{field}: mandatory')

    def test_missing_and_malformed_labels(self):
        for collection in ('nodes', 'containers'):
            m = self.model()
            del m[collection][0]['label']
            self.rejects(m, 'label must be a nonempty string')
        for value in (None, [], 3, ''):
            m = self.model()
            m['containers'][0]['label'] = value
            self.rejects(m, 'label must be a nonempty string')

    def test_invalid_strings_rejected_before_hashing_or_wrapping(self):
        mutations = [
            ('nodes', 'id', []), ('nodes', 'parent', {}), ('nodes', 'icon', []),
            ('nodes', 'detail', 1), ('nodes', 'zone', []), ('containers', 'kind', []),
            ('containers', 'provider', {}), ('edges', 'source', []),
            ('edges', 'target', None), ('edges', 'kind', []), ('edges', 'label', {}),
            ('edges', 'sourcePort', []),
        ]
        for collection, key, value in mutations:
            with self.subTest(collection=collection, key=key):
                m = self.model()
                m[collection][0][key] = value
                self.assertTrue(self.validate(m)[0])

    def test_title_subtitle_container_and_notes_fit(self):
        for key in ('title', 'subtitle'):
            m = self.model()
            m[key] = '한'*400
            self.rejects(m, f'{key}: exceeds 1 line')
        m = self.model()
        m['containers'][0]['label'] = '한'*200
        self.rejects(m, 'container label: exceeds 1 line')
        m = self.model()
        m['notes'] = ['한'*1000]
        self.rejects(m, 'notes: exceeds 2 line')
        m = self.model()
        m['title'] = 'First line\nSecond line'
        self.rejects(m, 'title: exceeds 1 line')

    def test_bad_notes_and_page_text_types(self):
        for value in (None, 'not a list', [None], [[]]):
            m = self.model()
            m['notes'] = value
            self.rejects(m, 'notes: must be a list of strings')
        for field in ('title', 'subtitle'):
            m = self.model()
            m[field] = []
            self.rejects(m, f'{field}: must be a string')

    def test_long_edge_label_rejected_instead_of_clipped(self):
        m = self.model()
        m['edges'][0]['label'] = '상세 연결 설명이 너무 길어서 연결선 라벨의 제한된 너비에 들어가지 않습니다'
        self.rejects(m, 'shorten label to fit a 240px box')

    def test_legend_width_and_page_footer_space(self):
        m = {'provider': 'multi', 'width': 400, 'height': 900, 'title': 'Legend',
             'containers': [], 'nodes': [
                 {'id': 'a', 'label': 'A', 'icon': 'generic', 'x': 20, 'y': 100, 'w': 156, 'h': 124},
                 {'id': 'b', 'label': 'B', 'icon': 'generic', 'x': 220, 'y': 400, 'w': 156, 'h': 124}],
             'edges': [{'id': 'traffic', 'source': 'a', 'target': 'b', 'kind': 'traffic'},
                       {'id': 'dns', 'source': 'a', 'target': 'b', 'kind': 'dns'}]}
        self.rejects(m, 'legend: exceeds canvas width')
        m['height'] = 150
        self.rejects(m, '90px footer')

    def test_managed_service_cannot_hide_in_subnet_child_group(self):
        m = self.model()
        m['containers'].append({'id': 'sql-group', 'kind': 'group', 'overlay': True,
                                'label': 'SQL', 'parent': 'data', 'x': 790,
                                'y': 774, 'w': 176, 'h': 180})
        n = next(n for n in m['nodes'] if n['id'] == 'database')
        n.update(parent='sql-group', x=800, y=808)
        self.rejects(m, 'managed/global service')

    def test_gcp_cloud_sql_cannot_move_into_customer_subnet(self):
        m = self.model('gcp-regional')
        n = next(n for n in m['nodes'] if n['id'] == 'database')
        n.update(parent='data', x=800)
        self.rejects(m, 'managed/global service')

    def test_provider_network_container_mismatch(self):
        for name, wrong_kind in (('azure-regional', 'vpc'), ('gcp-regional', 'vnet')):
            m = self.model(name)
            next(b for b in m['containers'] if b['id'] == 'network')['kind'] = wrong_kind
            self.rejects(m, 'provider/container mismatch')

    def test_multi_provider_checks_inherit_explicit_scope(self):
        m = self.model('azure-regional')
        m['provider'] = 'multi'
        m['containers'][0]['provider'] = 'azure'
        next(b for b in m['containers'] if b['id'] == 'network')['kind'] = 'vpc'
        self.rejects(m, 'provider/container mismatch (azure / vpc)')
        next(n for n in m['nodes'] if n['id'] == 'app-a')['icon'] = 'aws.ec2'
        self.rejects(m, 'provider/icon mismatch')

    def test_explicit_provider_cannot_bypass_single_provider_diagram(self):
        m = self.model()
        n = next(n for n in m['nodes'] if n['id'] == 'app-a')
        n.update(provider='aws', icon='aws.ec2')
        self.rejects(m, 'provider differs from single-provider diagram')

    def test_parent_cycle_and_unknown_container(self):
        m = self.model()
        m['containers'][0]['parent'] = 'network'
        self.rejects(m, 'parent cycle')
        m = self.model()
        m['nodes'][0]['parent'] = 'unknown'
        self.rejects(m, 'unknown container')

    def test_routing_fields_and_attachment_offsets(self):
        for routing in (None, [], {'clearance': -1}, {'clearance': True}, {'stub': 0}, {'stub': float('nan')}):
            m = self.model()
            m['routing'] = routing
            self.rejects(m, 'routing')
        for field in ('sourceOffset', 'targetOffset'):
            for value in (-1, 0, .95, 1, None, [], True, float('nan')):
                m = self.model()
                m['edges'][0][field] = value
                self.rejects(m, field)
        m = self.model()
        m['routing'] = {'clearance': 0, 'stub': 16}
        m['edges'][0].update(sourceOffset=.1, targetOffset=.9, priority=-2)
        self.assertEqual(self.validate(m), ([], []))
        m['edges'][0]['priority'] = float('inf')
        self.rejects(m, 'priority must be a finite number')

    def test_self_loop_has_actionable_error(self):
        m = self.model()
        m['edges'][0]['target'] = m['edges'][0]['source']
        self.rejects(m, 'separate detail view')

    def test_header_alignment_and_offset(self):
        for value in ('invalid', None, []):
            m = self.model()
            m['containers'][0]['labelAlign'] = value
            self.rejects(m, 'labelAlign')
        for value in (-1, True, None, float('nan')):
            m = self.model()
            m['containers'][0]['labelOffset'] = value
            self.rejects(m, 'labelOffset must be a finite number >= 0')
        m = self.model()
        m['containers'][0]['labelOffset'] = m['containers'][0]['w']
        self.rejects(m, 'container label: exceeds 1 line')
        for alignment in ('center', 'right'):
            m = self.model()
            m['containers'][0].update(labelAlign=alignment, labelOffset=12)
            self.rejects(m, 'labelOffset is supported only with labelAlign=left')

    def test_validation_does_not_mutate_model(self):
        m = self.model()
        original = copy.deepcopy(m)
        self.validate(m)
        self.assertEqual(m, original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
