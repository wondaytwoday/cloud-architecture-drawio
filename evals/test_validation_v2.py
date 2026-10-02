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
        return json.loads((BASE/'cloud-architecture-drawio/assets/templates'/f'{name}.json').read_text(encoding='utf-8'))

    def validate(self, model):
        return validate_structure(model, c.CAT, c.wrapped, c.header_rect)

    def rejects(self, model, message):
        errors, _ = self.validate(model)
        self.assertTrue(any(message in error for error in errors), errors)

    def test_supplied_templates_and_examples_fit(self):
        models = sorted((BASE/'cloud-architecture-drawio/assets/templates').glob('*.json'))
        models += sorted((BASE/'examples').glob('*.model.json')) + sorted((BASE/'evals/fixtures').glob('*.model.json'))
        self.assertGreaterEqual(len(models), 9)
        for path in models:
            with self.subTest(model=path.name):
                self.assertEqual(c.validate(json.loads(path.read_text(encoding='utf-8'))), ([], []))

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
        self.rejects(m, 'shorten label to about 228px of text (a 244px caption box)')

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


class GeometryAndPlacementTests(unittest.TestCase):
    """v3: the drawn geometry, not only the declared parent, carries meaning."""

    def model(self, name='aws-three-tier'):
        return json.loads((BASE/'cloud-architecture-drawio/assets/templates'/f'{name}.json').read_text(encoding='utf-8'))

    def errors(self, model):
        return validate_structure(model, c.CAT, c.wrapped, c.header_rect)[0]

    def rejects(self, model, message):
        errors = self.errors(model)
        self.assertTrue(any(message in error for error in errors), errors)

    def node(self, m, node_id):
        return next(n for n in m['nodes'] if n['id'] == node_id)

    def box(self, m, box_id):
        return next(b for b in m['containers'] if b['id'] == box_id)

    def test_managed_service_drawn_in_subnet_is_rejected_whatever_its_parent(self):
        for parent in (None, 'vpc', 'cloud'):
            with self.subTest(parent=parent):
                m = self.model()
                s3 = self.node(m, 's3')
                s3.update(x=340, y=554)
                s3.pop('parent')
                if parent:
                    s3['parent'] = parent
                self.rejects(m, "drawn inside subnet public-a but its nearest declared parent")
                self.rejects(m, 'managed/global service')

    def test_misspelled_parent_cannot_bypass_placement(self):
        m = self.model()
        s3 = self.node(m, 's3')
        s3.update(x=340, y=554, parnet=s3.pop('parent'))
        self.rejects(m, "unknown key 'parnet'; did you mean 'parent'?")
        self.rejects(m, 'managed/global service')

    def test_containers_and_nodes_cannot_cross_borders(self):
        m = self.model()
        self.box(m, 'public-a')['h'] = 260
        self.rejects(m, 'Container overlap: public-a / web-a')
        m = self.model()
        s3 = self.node(m, 's3')
        s3.update(x=230, y=1000)
        self.rejects(m, 's3: straddles the border of')

    def test_resource_parented_to_overlay_is_judged_by_its_subnet(self):
        m = self.model()
        web = self.node(m, 'res-web-a')
        web.update(parent='web-asg', zone='b')
        self.rejects(m, "drawn inside subnet web-a but its nearest declared parent is vpc vpc")
        self.rejects(m, 'zone differs from subnet/AZ')

    def test_reserved_title_footer_and_side_bands(self):
        cases = [({'y': 20}, 'title band'), ({'y': 1700}, 'legend/notes footer'), ({'x': 4}, 'side margin')]
        for change, band in cases:
            with self.subTest(band=band):
                m = self.model()
                self.node(m, 'users').update(change)
                self.rejects(m, f'users: enters the reserved {band}')
        m = self.model()
        self.box(m, 'cloud')['h'] = m['height'] - self.box(m, 'cloud')['y'] - 5
        self.rejects(m, 'cloud: enters the reserved legend/notes footer')

    def test_policy_network_and_managed_services_stay_out_of_subnets(self):
        for name, icon, message in (
                ('aws-three-tier', 'aws.waf', 'policy association'),
                ('aws-three-tier', 'aws.shield', 'policy association'),
                ('aws-three-tier', 'aws.igw', 'attaches to the VPC/network'),
                ('gcp-regional', 'gcp.armor', 'policy association'),
                ('gcp-regional', 'gcp.vpc', 'attaches to the VPC/network'),
                ('gcp-regional', 'gcp.router', 'attaches to the VPC/network'),
                ('gcp-regional', 'gcp.nat', 'attaches to the VPC/network'),
                ('gcp-regional', 'gcp.memorystore', 'managed/global service'),
                ('azure-regional', 'azure.dns', 'managed/global service')):
            with self.subTest(icon=icon):
                m = self.model(name)
                hosted = next(n for n in m['nodes'] if n.get('icon') in ('aws.ec2', 'gcp.compute', 'azure.vm'))
                hosted['icon'] = icon
                self.rejects(m, message)

    def test_subnet_hosted_azure_resources_need_their_subnet(self):
        m = self.model('azure-regional')
        pe = self.node(m, 'pe')
        pe.update(parent='cloud', x=1100, y=1000)
        self.rejects(m, 'azure.privateendpoint takes an address in a subnet')

    def test_application_gateway_subnet_is_dedicated_and_not_gatewaysubnet(self):
        m = self.model('azure-regional')
        subnet = self.box(m, 'gateway-subnet')
        subnet['h'] = 420
        m['nodes'].append({'id': 'jump', 'icon': 'azure.vm', 'label': 'Jump host', 'parent': 'gateway-subnet',
                           'x': subnet['x']+17, 'y': subnet['y']+280, 'w': 156, 'h': 124})
        self.rejects(m, 'jump: subnet gateway-subnet hosts an Application Gateway')
        m = self.model('azure-regional')
        self.box(m, 'gateway-subnet')['label'] = 'GatewaySubnet'
        self.rejects(m, 'GatewaySubnet is reserved')

    def test_multi_provider_infers_unmarked_boundaries(self):
        m = self.model()
        m['provider'] = 'multi'
        for b in m['containers']:
            b.pop('provider', None)
        self.assertEqual(self.errors(m), [])
        self.box(m, 'public-a')['parent'] = 'vpc'
        self.rejects(m, 'public-a: AWS subnet needs an AZ ancestor')
        m = self.model()
        m['provider'] = 'multi'
        for b in m['containers']:
            b.pop('provider', None)
        self.node(m, 'res-web-a')['icon'] = 'azure.vm'
        self.rejects(m, 'vpc: vpc holds resources of several providers (aws, azure)')

    def test_explicit_provider_conflicts_with_ancestor_in_multi(self):
        m = self.model('azure-regional')
        m['provider'] = 'multi'
        m['containers'][0]['provider'] = 'azure'
        self.node(m, 'app-a').update(provider='aws', icon='aws.ec2')
        self.rejects(m, 'app-a: provider aws conflicts with cloud (azure)')

    def test_network_nesting(self):
        m = self.model('gcp-regional')
        frontend = self.box(m, 'frontend')
        m['containers'].append({'id': 'inner-vpc', 'kind': 'vpc', 'label': 'Nested VPC', 'parent': 'frontend',
                                'x': frontend['x']+180, 'y': frontend['y']+40, 'w': 200, 'h': 100})
        self.rejects(m, 'inner-vpc: a vpc cannot sit inside a subnet or AZ')

    def test_unknown_keys_typos_and_metadata(self):
        m = self.model()
        edge = m['edges'][0]
        edge['from'] = edge.pop('source')
        self.rejects(m, "unknown key 'from'; did you mean 'source'?")
        m = self.model()
        m['nodes'][0].update({'evidence': 'tfstate', 'x-owner': 'platform', 'owner': 'platform'})
        errors, warnings = validate_structure(m, c.CAT, c.wrapped, c.header_rect)
        self.assertEqual(errors, [])
        self.assertEqual([w for w in warnings if 'owner' in w], [f"{m['nodes'][0]['id']}: unknown key 'owner' is ignored; keep metadata in evidence, assumptions, members, meta or an x- key"])
        m = self.model()
        m['note'] = m.pop('notes')
        self.rejects(m, "model: unknown key 'note'; did you mean 'notes'?")
        # With the real key present, the near miss may be deliberate metadata.
        m['notes'] = m['note']
        errors, warnings = validate_structure(m, c.CAT, c.wrapped, c.header_rect)
        self.assertEqual(errors, [])
        self.assertIn("model: unknown key 'note' is ignored (did you mean 'notes'?)", warnings)

    def test_characters_xml_cannot_store_are_rejected(self):
        for path, value in ((('title',), 'Arch\x08'), (('edges', 0, 'label'), 'HTTPS\x0b443'),
                            (('notes',), ['note\x01']), (('containers', 0, 'label'), 'VPC\x0c'),
                            (('nodes', 0, 'label'), 'App\ud800')):
            with self.subTest(path=path):
                m = self.model()
                target = m
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                self.rejects(m, 'which a .drawio file cannot store')

    def test_containment_errors_say_how_far_a_shape_sticks_out(self):
        m = self.model()
        web = self.node(m, 'res-web-a')
        subnet = self.box(m, 'web-a')
        web['x'] = subnet['x']+subnet['w']-web['w']+20
        self.rejects(m, 'res-web-a: outside parent web-a (right edge 20px beyond)')
        m = self.model()
        web = self.node(m, 'res-web-a')
        web['y'] = self.box(m, 'web-a')['y']+30
        self.rejects(m, "res-web-a: overlaps parent header (starts 30px below web-a's top; needs 34px)")

    def test_overlay_is_only_for_membership_groups(self):
        m = self.model()
        self.box(m, 'az-a')['overlay'] = True
        self.rejects(m, 'az-a: overlay is supported only on kind=group')
        # On a node the key means nothing, so it cannot switch the geometry check off.
        m = self.model()
        s3 = self.node(m, 's3')
        s3.update(x=340, y=554, parent='vpc', overlay=True)
        self.rejects(m, 'drawn inside subnet public-a')

    def multi_region(self):
        boxes = [('seoul', 'region', 20, 100, 1460, 700, None), ('aws-vpc', 'vpc', 40, 140, 680, 640, 'seoul'),
                 ('aws-az', 'az', 60, 180, 640, 580, 'aws-vpc'), ('aws-sn', 'subnet', 80, 220, 600, 300, 'aws-az'),
                 ('gcp-vpc', 'vpc', 760, 140, 700, 640, 'seoul'), ('gcp-sn', 'subnet', 780, 220, 640, 300, 'gcp-vpc')]
        return {'provider': 'multi', 'title': 'Two clouds', 'width': 1500, 'height': 900,
                'containers': [dict(zip(('id', 'kind', 'x', 'y', 'w', 'h'), b[:6]), label=b[0], **({'parent': b[6]} if b[6] else {}))
                               for b in boxes],
                'nodes': [{'id': 'ec2', 'icon': 'aws.ec2', 'label': 'EC2', 'x': 100, 'y': 280, 'w': 156, 'h': 124, 'parent': 'aws-sn'},
                          {'id': 'gke', 'icon': 'generic', 'label': 'GKE nodes', 'provider': 'gcp',
                           'x': 800, 'y': 280, 'w': 156, 'h': 124, 'parent': 'gcp-sn'}],
                'edges': []}

    def test_multi_provider_inference_stays_inside_each_network(self):
        m = self.multi_region()
        self.assertEqual(self.errors(m), [])
        m['nodes'][1]['provider'] = 'azure'
        self.rejects(m, 'gcp-vpc: provider/container mismatch (azure / vpc)')
        m = self.multi_region()
        m['nodes'][1].update(parent='aws-sn', x=420, provider='azure')
        self.rejects(m, 'aws-sn: subnet holds resources of several providers (aws, azure)')

    def test_container_icon_key_never_crashes(self):
        for value in (None, 5, ['aws'], {}, 'azure.vnet'):
            with self.subTest(value=value):
                m = self.multi_region()
                m['containers'][1]['icon'] = value
                errors, warnings = validate_structure(m, c.CAT, c.wrapped, c.header_rect)
                self.assertEqual(errors, [])
                self.assertTrue(any("unknown key 'icon'" in w for w in warnings))

    def test_networks_and_subnets_do_not_nest_in_their_own_kind(self):
        m = self.model('azure-regional')
        frontend = self.box(m, 'frontend')
        m['containers'].append({'id': 'inner', 'kind': 'subnet', 'label': 'Inner', 'parent': 'frontend',
                                'x': frontend['x']+190, 'y': frontend['y']+40, 'w': 200, 'h': 100})
        self.rejects(m, 'inner: a subnet cannot sit inside a subnet')
        m = self.model('gcp-regional')
        region = self.box(m, 'region')
        m['containers'].append({'id': 'inner-vpc', 'kind': 'vpc', 'label': 'Peer', 'parent': 'region',
                                'x': region['x']+20, 'y': region['y']+420, 'w': 200, 'h': 120})
        self.rejects(m, 'inner-vpc: a vpc cannot sit inside another VPC/VNet')

    def test_metadata_may_hold_any_text(self):
        m = self.model()
        m['nodes'][0]['evidence'] = 'terraform plan: \x1b[32m+ aws_instance.web\x1b[0m'
        m['x-source'] = {'log': 'line1\x0cline2', 'deep': [[[['\x07']]]]}
        self.assertEqual(self.errors(m), [])

    def test_legend_locale_and_captions(self):
        m = self.model()
        m['locale'] = 'fr'
        self.rejects(m, 'locale: must be one of en, ko')
        m = self.model()
        m['legend'] = {'dns': 'DNS 질의', 'bogus': 'x'}
        self.rejects(m, 'legend.bogus: unknown edge kind')
        m = self.model()
        m['legend'] = {'traffic': '요청과 응답 데이터 흐름을 아주 길게 설명하는 범례 문구'}
        self.rejects(m, 'legend.traffic: exceeds 1 line')
        m = self.model()
        m.update(locale='ko', legend={'dns': 'DNS 질의'})
        self.assertEqual(self.errors(m), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
