from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from app.services.network_topology_service import NetworkTopologyService


def _line(
    *,
    line_id: str,
    category: str,
    name: str,
    quantity: int,
    vendor: str = 'Meraki',
    sku: str | None = None,
    source_type: str = 'excel',
) -> dict:
    return {
        'line_id': line_id,
        'item_id': f'item-{line_id}',
        'sku': sku or f'SKU-{line_id}',
        'source_type': source_type,
        'name': name,
        'vendor': vendor,
        'category': category,
        'quantity': quantity,
        'unit_price': 100.0,
        'line_total': float(quantity * 100),
        'selection_reason': 'test fixture',
    }


class TestNetworkTopologyService(unittest.TestCase):
    def setUp(self):
        self.service = NetworkTopologyService()

    def _has_edge(self, edges: list[dict], source: str, target: str) -> bool:
        return any(edge['source'] == source and edge['target'] == target for edge in edges)

    def test_topology_ap_switch_firewall(self):
        bom = {
            'line_items': [
                _line(line_id='1', category='firewall', name='MX Firewall', quantity=1),
                _line(line_id='2', category='switch', name='MS Switch', quantity=1),
                _line(line_id='3', category='wifi_ap', name='MR AP', quantity=4),
            ],
            'assumptions': [],
        }

        topology = self.service.generate_topology_from_bom(bom)
        nodes_by_id = {node['id']: node for node in topology['nodes']}
        edges = topology['edges']

        self.assertIn('node-internet', nodes_by_id)
        self.assertIn('node-firewall', nodes_by_id)
        self.assertIn('node-switch', nodes_by_id)
        self.assertIn('node-wifi_ap', nodes_by_id)

        self.assertTrue(self._has_edge(edges, 'node-internet', 'node-firewall'))
        self.assertTrue(self._has_edge(edges, 'node-firewall', 'node-switch'))
        self.assertTrue(self._has_edge(edges, 'node-switch', 'node-wifi_ap'))
        self.assertEqual(nodes_by_id['node-wifi_ap']['quantity'], 4)

    def test_topology_ap_switch_only_adds_assumption(self):
        bom = {
            'line_items': [
                _line(line_id='1', category='switch', name='MS Switch', quantity=1),
                _line(line_id='2', category='wifi_ap', name='MR AP', quantity=2),
            ],
            'assumptions': [],
        }

        topology = self.service.generate_topology_from_bom(bom)
        assumptions = topology['metadata']['assumptions']

        self.assertTrue(self._has_edge(topology['edges'], 'node-internet', 'node-gateway-assumed'))
        self.assertTrue(self._has_edge(topology['edges'], 'node-gateway-assumed', 'node-switch'))
        self.assertTrue(self._has_edge(topology['edges'], 'node-switch', 'node-wifi_ap'))
        self.assertTrue(any('inserted an assumed gateway' in text for text in assumptions))

    def test_topology_groups_endpoints_via_switch(self):
        bom = {
            'line_items': [
                _line(line_id='1', category='switch', name='MS Switch', quantity=1),
                _line(line_id='2', category='wifi_ap', name='MR AP', quantity=3),
                _line(line_id='3', category='camera', name='MV Camera', quantity=2),
                _line(line_id='4', category='sensor', name='MT Sensor', quantity=5),
            ],
            'assumptions': [],
        }

        topology = self.service.generate_topology_from_bom(bom)
        nodes_by_id = {node['id']: node for node in topology['nodes']}

        self.assertEqual(nodes_by_id['node-wifi_ap']['quantity'], 3)
        self.assertEqual(nodes_by_id['node-security_cameras']['quantity'], 2)
        self.assertEqual(nodes_by_id['node-iot_devices']['quantity'], 5)
        self.assertTrue(self._has_edge(topology['edges'], 'node-switch', 'node-wifi_ap'))
        self.assertTrue(self._has_edge(topology['edges'], 'node-switch', 'node-security_cameras'))
        self.assertTrue(self._has_edge(topology['edges'], 'node-switch', 'node-iot_devices'))

    def test_topology_includes_staff_and_mobile_devices_from_bom(self):
        bom = {
            'line_items': [
                _line(line_id='1', category='firewall', name='MX Firewall', quantity=1),
                _line(line_id='2', category='switch', name='MS Switch', quantity=1),
                _line(line_id='3', category='wifi_ap', name='MR AP', quantity=3),
                _line(line_id='4', category='laptop', name='PAPI Laptop', quantity=10, vendor='PAPI'),
                _line(line_id='5', category='phone', name='PAPI Phone', quantity=12, vendor='PAPI'),
            ],
            'assumptions': [],
        }

        topology = self.service.generate_topology_from_bom(bom)
        nodes_by_id = {node['id']: node for node in topology['nodes']}

        self.assertIn('node-staff_devices', nodes_by_id)
        self.assertIn('node-mobile_devices', nodes_by_id)
        self.assertEqual(nodes_by_id['node-staff_devices']['quantity'], 10)
        self.assertEqual(nodes_by_id['node-mobile_devices']['quantity'], 12)
        self.assertTrue(self._has_edge(topology['edges'], 'node-wifi_ap', 'node-staff_devices'))
        self.assertTrue(self._has_edge(topology['edges'], 'node-wifi_ap', 'node-mobile_devices'))

    def test_topology_infers_business_groups_from_line_names(self):
        bom = {
            'line_items': [
                _line(line_id='1', category='switch', name='PoE Switch', quantity=1),
                _line(line_id='2', category='wifi_ap', name='Store Wi-Fi AP', quantity=3),
                _line(line_id='3', category='other', name='POS checkout terminals', quantity=4),
                _line(line_id='4', category='other', name='Digital signage displays', quantity=2),
                _line(line_id='5', category='other', name='Self-order kiosks', quantity=2),
            ],
            'assumptions': [],
        }

        topology = self.service.generate_topology_from_bom(bom)
        nodes_by_id = {node['id']: node for node in topology['nodes']}

        self.assertIn('node-pos_systems', nodes_by_id)
        self.assertIn('node-digital_signage', nodes_by_id)
        self.assertIn('node-kiosks', nodes_by_id)
        self.assertTrue(self._has_edge(topology['edges'], 'node-switch', 'node-pos_systems'))
        self.assertTrue(self._has_edge(topology['edges'], 'node-switch', 'node-digital_signage'))
        self.assertTrue(self._has_edge(topology['edges'], 'node-switch', 'node-kiosks'))

    def test_topology_uses_business_context_for_endpoint_groups(self):
        bom = {
            'line_items': [
                _line(line_id='1', category='switch', name='PoE Switch', quantity=1),
                _line(line_id='2', category='wifi_ap', name='Store Wi-Fi AP', quantity=3),
            ],
            'assumptions': [],
        }
        business_context = {
            'posTerminals': 6,
            'ipCameras': 8,
            'digitalSignageScreens': 3,
            'sensors': 5,
            'guestWifiRequired': 'Yes',
        }

        topology = self.service.generate_topology_from_bom(bom, business_context=business_context)
        nodes_by_id = {node['id']: node for node in topology['nodes']}

        self.assertIn('node-pos_systems', nodes_by_id)
        self.assertIn('node-security_cameras', nodes_by_id)
        self.assertIn('node-digital_signage', nodes_by_id)
        self.assertIn('node-iot_devices', nodes_by_id)
        self.assertIn('node-guest_wifi', nodes_by_id)
        self.assertEqual(nodes_by_id['node-pos_systems']['quantity'], 6)
        self.assertEqual(nodes_by_id['node-security_cameras']['quantity'], 8)
        self.assertEqual(nodes_by_id['node-digital_signage']['quantity'], 3)
        self.assertEqual(nodes_by_id['node-iot_devices']['quantity'], 5)
        self.assertTrue(self._has_edge(topology['edges'], 'node-switch', 'node-pos_systems'))
        self.assertTrue(self._has_edge(topology['edges'], 'node-switch', 'node-security_cameras'))

    def test_topology_adds_backup_internet_from_business_context(self):
        bom = {
            'line_items': [
                _line(line_id='1', category='firewall', name='MX Firewall', quantity=1),
                _line(line_id='2', category='switch', name='PoE Switch', quantity=1),
                _line(line_id='3', category='wifi_ap', name='Store Wi-Fi AP', quantity=3),
            ],
            'assumptions': [],
        }

        topology = self.service.generate_topology_from_bom(
            bom,
            business_context={'needsBackupInternet': 'Yes'},
        )
        nodes_by_id = {node['id']: node for node in topology['nodes']}

        self.assertIn('node-backup-internet', nodes_by_id)
        self.assertIn('5G Backup Internet', nodes_by_id['node-backup-internet']['label'])
        self.assertTrue(self._has_edge(topology['edges'], 'node-backup-internet', 'node-firewall'))

    def test_edge_labels_are_professional_and_connection_specific(self):
        bom = {
            'line_items': [
                _line(line_id='1', category='firewall', name='MX Firewall', quantity=1),
                _line(line_id='2', category='switch', name='MS Switch', quantity=1),
                _line(line_id='3', category='wifi_ap', name='MR AP', quantity=4),
                _line(line_id='4', category='camera', name='MV Camera', quantity=2),
                _line(line_id='5', category='phone', name='Employee Phone', quantity=12, vendor='PAPI'),
            ],
            'assumptions': [],
        }

        topology = self.service.generate_topology_from_bom(bom)
        labels_by_path = {
            (edge['source'], edge['target']): edge.get('label')
            for edge in topology['edges']
        }

        self.assertEqual(labels_by_path[('node-internet', 'node-firewall')], 'Wired link (WAN uplink)')
        self.assertEqual(labels_by_path[('node-firewall', 'node-switch')], 'Wired link')
        self.assertEqual(labels_by_path[('node-switch', 'node-wifi_ap')], 'Wired link')
        self.assertEqual(labels_by_path[('node-switch', 'node-security_cameras')], '')
        self.assertEqual(labels_by_path[('node-wifi_ap', 'node-mobile_devices')], 'Wireless link')

    def test_managed_services_are_attached_to_managed_infra(self):
        bom = {
            'line_items': [
                _line(line_id='1', category='firewall', name='MX Firewall', quantity=1),
                _line(line_id='2', category='switch', name='MS Switch', quantity=1),
                _line(line_id='3', category='wifi_ap', name='MR AP', quantity=4),
                _line(line_id='4', category='managed_service', name='Managed NOC', quantity=1, vendor='SecureOffice'),
            ],
            'assumptions': [],
        }

        topology = self.service.generate_topology_from_bom(bom)
        nodes_by_id = {node['id']: node for node in topology['nodes']}

        self.assertIn('node-managed-service', nodes_by_id)
        self.assertIn('node-cloud-management', nodes_by_id)
        self.assertTrue(self._has_edge(topology['edges'], 'node-managed-service', 'node-switch'))
        self.assertTrue(self._has_edge(topology['edges'], 'node-cloud-management', 'node-managed-service'))

        managed_scope = str((nodes_by_id['node-managed-service'].get('metadata') or {}).get('serviceScope') or '')
        self.assertIn('Firewall', managed_scope)
        self.assertIn('Switches', managed_scope)
        self.assertIn('Wi-Fi APs', managed_scope)

    def test_drawio_xml_generation_is_stable_and_contains_labels(self):
        bom = {
            'line_items': [
                _line(line_id='1', category='firewall', name='MX Firewall', quantity=1),
                _line(line_id='2', category='switch', name='MS Switch', quantity=1),
                _line(line_id='3', category='wifi_ap', name='MR AP', quantity=4),
            ],
            'assumptions': [],
        }
        topology = self.service.generate_topology_from_bom(bom)

        xml_first = self.service.topology_to_drawio_xml(topology)
        xml_second = self.service.topology_to_drawio_xml(topology)

        self.assertTrue(xml_first)
        self.assertEqual(xml_first, xml_second)
        self.assertIn('Internet', xml_first)
        self.assertIn('Gateway / Firewall', xml_first)
        self.assertIn('Network Switch', xml_first)
        self.assertIn('Wi-Fi Access Points', xml_first)
        self.assertIn('(4)', xml_first)
        self.assertIn('shape=image', xml_first)
        self.assertIn('data:image/svg+xml', xml_first)
        self.assertIn('source="node-switch"', xml_first)
        self.assertIn('target="node-wifi_ap"', xml_first)
        self.assertIn('Wired link', xml_first)
        ET.fromstring(xml_first)

    def test_grouped_quantity_behavior_for_same_category(self):
        bom = {
            'line_items': [
                _line(line_id='1', category='wifi_ap', name='MR AP', quantity=2),
                _line(line_id='2', category='wifi_ap', name='MR AP', quantity=2),
                _line(line_id='3', category='switch', name='MS Switch', quantity=1),
            ],
            'assumptions': [],
        }

        topology = self.service.generate_topology_from_bom(bom)
        ap_nodes = [node for node in topology['nodes'] if node['kind'] == 'wifi_ap']

        self.assertEqual(len(ap_nodes), 1)
        self.assertEqual(ap_nodes[0]['quantity'], 4)

    def test_topology_artifact_contract(self):
        bom = {
            'line_items': [
                _line(line_id='1', category='switch', name='MS Switch', quantity=1),
                _line(line_id='2', category='wifi_ap', name='MR AP', quantity=2),
            ],
            'assumptions': [],
        }

        artifact = self.service.generate_topology_artifact_from_bom(bom, design_id='design-123')

        self.assertIn('topology', artifact)
        self.assertIn('drawioXml', artifact)
        self.assertIn('summary', artifact)
        self.assertEqual(artifact['topology']['designId'], 'design-123')
        self.assertGreater(artifact['summary']['nodeCount'], 0)
        self.assertGreater(artifact['summary']['edgeCount'], 0)


if __name__ == '__main__':
    unittest.main()
