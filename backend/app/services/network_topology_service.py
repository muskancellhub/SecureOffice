from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Any
from urllib.parse import quote
import xml.etree.ElementTree as ET

from app.core.exceptions import AppError


class NetworkTopologyService:
    CORE_CATEGORY_PRIORITY = ['firewall', 'security_appliance', 'gateway', 'router', 'cellular_gateway']

    CATEGORY_NORMALIZATION = {
        'internet': 'internet',
        'wan': 'internet',
        'gateway': 'gateway',
        'router': 'router',
        'firewall': 'firewall',
        'security appliance': 'security_appliance',
        'security_appliance': 'security_appliance',
        'cellular gateway': 'cellular_gateway',
        'cellular_gateway': 'cellular_gateway',
        'cellular backup': 'cellular_backup',
        'cellular_backup': 'cellular_backup',
        'switch': 'switch',
        'wifi_ap': 'wifi_ap',
        'wireless ap': 'wifi_ap',
        'camera': 'camera',
        'smart camera': 'camera',
        'sensor': 'sensor',
        'iot': 'sensor',
        'antenna': 'antenna',
        'pos': 'pos_systems',
        'point_of_sale': 'pos_systems',
        'signage': 'digital_signage',
        'kiosk': 'kiosks',
        'kitchen': 'kitchen_systems',
        'guest_wifi': 'guest_wifi',
        'laptop': 'laptop',
        'desktop': 'desktop',
        'tablet': 'tablet',
        'phone': 'phone',
        'mobile': 'phone',
        'mobile_phone': 'phone',
        'accessory': 'accessory',
        'managed_service': 'managed_service',
        'managed_service_candidate': 'managed_service',
    }

    ICON_TYPE_BY_KIND = {
        'internet': 'internet',
        'backup_internet': 'cellular',
        'gateway': 'router',
        'router': 'router',
        'firewall': 'firewall',
        'security_appliance': 'firewall',
        'cellular_gateway': 'router',
        'switch': 'switch',
        'wifi_ap': 'wifi',
        'security_cameras': 'camera',
        'iot_devices': 'sensor',
        'pos_systems': 'pos',
        'digital_signage': 'display',
        'kiosks': 'kiosk',
        'kitchen_systems': 'kitchen',
        'guest_wifi': 'wifi',
        'staff_devices': 'laptop',
        'mobile_devices': 'phone',
        'antenna': 'antenna',
        'managed_service': 'cloud',
        'cloud_management': 'cloud',
    }

    LABEL_BY_KIND = {
        'internet': 'Internet',
        'backup_internet': '5G Backup Internet',
        'gateway': 'Gateway / Router',
        'router': 'Gateway / Router',
        'firewall': 'Gateway / Firewall',
        'security_appliance': 'Gateway / Firewall',
        'cellular_gateway': 'Cellular Gateway',
        'switch': 'Network Switch',
        'wifi_ap': 'Wi-Fi Access Points',
        'security_cameras': 'Security Cameras',
        'iot_devices': 'IoT / Smart Devices',
        'pos_systems': 'POS Systems',
        'digital_signage': 'Digital Signage',
        'kiosks': 'Kiosks',
        'kitchen_systems': 'Kitchen Systems',
        'guest_wifi': 'Guest Wi-Fi',
        'staff_devices': 'Staff Devices',
        'mobile_devices': 'Mobile Devices',
        'antenna': 'Antenna Systems',
        'managed_service': 'Managed Services',
        'cloud_management': 'Cloud Management',
    }

    ENDPOINT_TOKEN_KIND = [
        (('pos', 'point of sale', 'checkout', 'payment terminal'), 'pos_systems'),
        (('camera', 'cctv', 'surveillance'), 'security_cameras'),
        (('signage', 'display', 'menu board'), 'digital_signage'),
        (('iot', 'sensor', 'smart', 'rfid'), 'iot_devices'),
        (('kiosk', 'self-order'), 'kiosks'),
        (('kitchen', 'kds'), 'kitchen_systems'),
        (('guest wifi', 'guest wi-fi'), 'guest_wifi'),
        (('laptop', 'desktop', 'workstation', 'pc'), 'staff_devices'),
        (('mobile', 'smartphone', 'handset', 'phone'), 'mobile_devices'),
    ]

    def _as_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _normalize_category(self, raw_category: Any, name: str) -> str:
        category = str(raw_category or '').strip().lower().replace('-', ' ')
        if category in self.CATEGORY_NORMALIZATION:
            return self.CATEGORY_NORMALIZATION[category]

        lowered_name = (name or '').lower()
        if 'firewall' in lowered_name:
            return 'firewall'
        if 'gateway' in lowered_name and 'cell' in lowered_name:
            return 'cellular_gateway'
        if 'gateway' in lowered_name:
            return 'gateway'
        if 'router' in lowered_name:
            return 'router'
        if 'switch' in lowered_name:
            return 'switch'
        if 'wifi' in lowered_name or 'access point' in lowered_name:
            return 'wifi_ap'
        if 'laptop' in lowered_name or 'desktop' in lowered_name or 'workstation' in lowered_name:
            return 'laptop'
        if 'tablet' in lowered_name:
            return 'tablet'
        if 'phone' in lowered_name or 'mobile' in lowered_name or 'smartphone' in lowered_name:
            return 'phone'
        if 'camera' in lowered_name:
            return 'camera'
        if 'sensor' in lowered_name or 'iot' in lowered_name:
            return 'sensor'
        if 'antenna' in lowered_name:
            return 'antenna'
        if 'managed' in lowered_name or 'service' in lowered_name:
            return 'managed_service'
        return category.replace(' ', '_') if category else 'accessory'

    def _group_bom_lines_by_category(self, bom_line_items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for line in bom_line_items:
            quantity = max(1, self._as_int(line.get('quantity'), 1))
            if quantity <= 0:
                continue

            name = str(line.get('name') or '').strip()
            category = self._normalize_category(line.get('category'), name)
            grouped.setdefault(category, []).append(line)
        return grouped

    @staticmethod
    def _line_matches_tokens(line: dict[str, Any], tokens: tuple[str, ...]) -> bool:
        haystack = ' '.join(
            [
                str(line.get('name') or ''),
                str(line.get('category') or ''),
                str(line.get('selection_reason') or ''),
            ]
        ).lower()
        return any(token in haystack for token in tokens)

    def _aggregate_node_from_lines(
        self,
        *,
        node_id: str,
        kind: str,
        lines: list[dict[str, Any]],
        group: str,
    ) -> dict[str, Any]:
        quantity = sum(max(1, self._as_int(line.get('quantity'), 1)) for line in lines)
        vendors = sorted({str(line.get('vendor') or '').strip() for line in lines if str(line.get('vendor') or '').strip()})
        skus = sorted({str(line.get('sku') or '').strip() for line in lines if str(line.get('sku') or '').strip()})

        base_label = self.LABEL_BY_KIND.get(kind, kind.replace('_', ' ').title())
        label = f'{base_label} ({quantity})' if quantity > 1 else base_label

        metadata = {
            'sourceLineIds': [str(line.get('line_id') or '') for line in lines],
            'selectionReasons': [str(line.get('selection_reason') or '') for line in lines if line.get('selection_reason')],
            'lineCount': len(lines),
        }

        return {
            'id': node_id,
            'kind': kind,
            'label': label,
            'vendor': vendors[0] if len(vendors) == 1 else ('Mixed' if vendors else None),
            'sku': skus[0] if len(skus) == 1 else None,
            'quantity': quantity,
            'iconType': self.ICON_TYPE_BY_KIND.get(kind, 'router'),
            'group': group,
            'metadata': metadata,
        }

    CABLE_LABEL_BY_TARGET_AND_KIND = {
        ('switch', 'wired'): 'Wired link',
        ('wifi_ap', 'wired'): 'Wired link',
        ('pos_systems', 'wired'): 'Wired link',
        ('security_cameras', 'wired'): 'Wired link',
        ('digital_signage', 'wired'): 'Wired link',
        ('iot_devices', 'wired'): 'Wired link',
        ('kiosks', 'wired'): 'Wired link',
        ('kitchen_systems', 'wired'): 'Wired link',
        ('guest_wifi', 'wireless'): 'Wireless link',
        ('staff_devices', 'wireless'): 'Wireless link',
        ('mobile_devices', 'wireless'): 'Wireless link',
        ('managed_service', 'management'): 'Managed connection',
        ('cloud_management', 'management'): 'Managed connection',
    }

    SERVICE_SCOPE_LABEL_BY_KIND = {
        'gateway': 'Gateway / Router',
        'router': 'Gateway / Router',
        'firewall': 'Gateway / Firewall',
        'security_appliance': 'Gateway / Firewall',
        'cellular_gateway': 'Cellular Gateway',
        'switch': 'Switching',
        'wifi_ap': 'Wi-Fi APs',
    }
    SERVICE_SCOPE_SHORT_LABEL = {
        'Gateway / Router': 'Gateway',
        'Gateway / Firewall': 'Firewall',
        'Cellular Gateway': 'Cellular GW',
        'Switching': 'Switches',
        'Wi-Fi APs': 'Wi-Fi APs',
    }

    MANAGED_INFRA_TARGET_KINDS = {
        'gateway',
        'router',
        'firewall',
        'security_appliance',
        'cellular_gateway',
        'switch',
        'wifi_ap',
    }

    WIRELESS_ENDPOINT_KINDS = {'guest_wifi', 'staff_devices', 'mobile_devices'}

    def _service_scope_labels_for_nodes(self, nodes: list[dict[str, Any]]) -> list[str]:
        labels: list[str] = []
        seen: set[str] = set()
        for node in nodes:
            kind = str(node.get('kind') or '')
            label = self.SERVICE_SCOPE_LABEL_BY_KIND.get(kind)
            if not label or label in seen:
                continue
            seen.add(label)
            labels.append(label)
        return labels

    def _compact_scope_summary(self, labels: list[str], *, prefix: str) -> str:
        compact: list[str] = []
        seen: set[str] = set()
        for label in labels:
            short = self.SERVICE_SCOPE_SHORT_LABEL.get(label, label)
            if short in seen:
                continue
            seen.add(short)
            compact.append(short)
        if not compact:
            return ''
        if len(compact) > 4:
            return f"{prefix}: {', '.join(compact[:4])} +{len(compact) - 4}"
        return f"{prefix}: {', '.join(compact)}"

    def _get_cable_label(self, source_kind: str, target_kind: str, edge_kind: str, fallback: str) -> str:
        source_kind_normalized = str(source_kind or '').lower()
        target_kind_normalized = str(target_kind or '').lower()
        edge_kind_normalized = str(edge_kind or '').lower()

        if edge_kind_normalized == 'uplink':
            if source_kind_normalized == 'internet':
                return 'Wired link (WAN uplink)'
            if source_kind_normalized == 'backup_internet':
                return 'Wireless link (5G failover)'

        if edge_kind_normalized == 'management':
            return 'Managed connection'

        label = self.CABLE_LABEL_BY_TARGET_AND_KIND.get((target_kind_normalized, edge_kind_normalized))
        if label:
            return label
        if edge_kind_normalized == 'wired':
            return 'Wired link'
        if edge_kind_normalized == 'wireless':
            return 'Wireless link'
        if edge_kind_normalized == 'management':
            return 'Managed connection'
        return fallback

    def _apply_professional_edge_labels(self, *, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
        kind_by_id = {
            str(node.get('id') or ''): str(node.get('kind') or '')
            for node in nodes
        }
        for edge in edges:
            source_id = str(edge.get('source') or '')
            target_id = str(edge.get('target') or '')
            source_kind = kind_by_id.get(source_id, '')
            target_kind = kind_by_id.get(target_id, '')
            edge_kind = str(edge.get('kind') or '')
            fallback = str(edge.get('label') or '').strip() or 'Network Link'
            edge['label'] = self._get_cable_label(source_kind, target_kind, edge_kind, fallback)

    def _reduce_redundant_edge_labels(self, *, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
        kind_by_id = {
            str(node.get('id') or ''): str(node.get('kind') or '')
            for node in nodes
        }
        seen: set[tuple[str, str, str]] = set()
        for edge in edges:
            edge_kind = str(edge.get('kind') or '').lower()
            label = str(edge.get('label') or '').strip()
            if not label:
                continue
            if edge_kind not in {'wired', 'wireless'}:
                continue
            source_kind = kind_by_id.get(str(edge.get('source') or ''), '')
            if source_kind not in {'switch', 'wifi_ap'}:
                continue
            dedupe_key = (source_kind, edge_kind, label)
            if dedupe_key in seen:
                edge['label'] = ''
                continue
            seen.add(dedupe_key)

    def _append_edge(
        self,
        edges: list[dict[str, Any]],
        *,
        source: str,
        target: str,
        label: str | None = None,
        kind: str | None = None,
    ) -> None:
        edge_id = f'edge-{len(edges) + 1}'
        edge = {
            'id': edge_id,
            'source': source,
            'target': target,
        }
        if label:
            edge['label'] = label
        if kind:
            edge['kind'] = kind
        edges.append(edge)

    def _collect_business_endpoint_lines(
        self,
        line_items: list[dict[str, Any]],
        business_context: dict[str, Any] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        buckets: dict[str, list[dict[str, Any]]] = {}
        for line in line_items:
            for tokens, kind in self.ENDPOINT_TOKEN_KIND:
                if self._line_matches_tokens(line, tokens):
                    buckets.setdefault(kind, []).append(line)
                    break

        if not isinstance(business_context, dict):
            return buckets

        def qty(*keys: str) -> int:
            total = 0
            for key in keys:
                total += max(0, self._as_int(business_context.get(key), 0))
            return total

        def flag(*keys: str) -> bool:
            for key in keys:
                value = business_context.get(key)
                if isinstance(value, bool) and value:
                    return True
                if isinstance(value, str) and value.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}:
                    return True
            return False

        def add_context_line(kind: str, quantity: int, *, label: str) -> None:
            if quantity <= 0:
                return
            buckets.setdefault(kind, []).append(
                {
                    'line_id': f'context-{kind}',
                    'item_id': None,
                    'sku': None,
                    'source_type': 'context',
                    'name': label,
                    'vendor': 'Customer Environment',
                    'category': kind,
                    'quantity': quantity,
                    'unit_price': 0.0,
                    'line_total': 0.0,
                    'selection_reason': 'Derived from business intake context.',
                }
            )

        add_context_line(
            'pos_systems',
            qty('posTerminals', 'handheldPosDevices', 'selfCheckoutMachines'),
            label='POS Systems',
        )
        add_context_line(
            'security_cameras',
            qty('ipCameras'),
            label='Security Cameras',
        )
        add_context_line(
            'digital_signage',
            qty('digitalSignageScreens'),
            label='Digital Signage',
        )
        add_context_line(
            'kiosks',
            qty('selfOrderKiosks'),
            label='Kiosks',
        )
        add_context_line(
            'kitchen_systems',
            qty('kitchenDisplaySystems', 'onlineOrderingTablets', 'driveThruSystems'),
            label='Kitchen Systems',
        )
        add_context_line(
            'iot_devices',
            qty(
                'sensors',
                'smartRefrigerators',
                'smartCoffeeMachines',
                'vendingMachines',
                'lightingControllers',
                'inventoryScanners',
                'facilityManagementSystems',
                'deliveryRobots',
                'inventoryRobots',
                'smartShelves',
                'rfidGates',
            ),
            label='IoT / Smart Devices',
        )

        guest_wifi_users = qty('guestWifiUsers')
        needs_guest_wifi = flag('guestWifiRequired', 'needsGuestWifi')
        add_context_line(
            'guest_wifi',
            guest_wifi_users if guest_wifi_users > 0 else (1 if needs_guest_wifi else 0),
            label='Guest Wi-Fi',
        )
        add_context_line(
            'staff_devices',
            qty('laptops', 'desktops', 'tablets', 'customerTablets'),
            label='Staff Devices',
        )
        add_context_line(
            'mobile_devices',
            qty('mobilePhones'),
            label='Mobile Devices',
        )
        return buckets

    def generate_topology_from_bom(
        self,
        bom: dict[str, Any],
        *,
        design_id: str | None = None,
        business_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        line_items = bom.get('line_items') or bom.get('lineItems') or []
        if not isinstance(line_items, list):
            raise AppError('BOM line_items must be a list', 400)

        grouped = self._group_bom_lines_by_category(line_items)
        inferred_business = self._collect_business_endpoint_lines(line_items, business_context=business_context)

        assumptions = [str(item) for item in (bom.get('assumptions') or [])]
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        internet_node = {
            'id': 'node-internet',
            'kind': 'internet',
            'label': self.LABEL_BY_KIND['internet'],
            'iconType': 'internet',
            'group': 'wan',
            'metadata': {},
        }
        nodes.append(internet_node)

        core_node = None
        core_kind_used = None
        for core_kind in self.CORE_CATEGORY_PRIORITY:
            lines = grouped.get(core_kind) or []
            if not lines:
                continue
            core_kind_used = core_kind
            core_node = self._aggregate_node_from_lines(
                node_id=f'node-{core_kind}',
                kind=core_kind,
                lines=lines,
                group='core',
            )
            nodes.append(core_node)
            break

        if core_node:
            self._append_edge(
                edges,
                source=internet_node['id'],
                target=core_node['id'],
                kind='uplink',
            )
        else:
            assumptions.append('No explicit gateway/firewall found in BOM; inserted an assumed gateway for customer-friendly preview.')
            core_node = {
                'id': 'node-gateway-assumed',
                'kind': 'gateway',
                'label': 'Gateway / Router',
                'iconType': 'router',
                'group': 'core',
                'metadata': {'assumed': True},
            }
            nodes.append(core_node)
            self._append_edge(
                edges,
                source=internet_node['id'],
                target=core_node['id'],
                kind='uplink',
            )

        backup_lines = grouped.get('cellular_backup') or []
        if not backup_lines and core_kind_used != 'cellular_gateway':
            backup_lines = grouped.get('cellular_gateway') or []
        if not backup_lines:
            backup_lines = [
                line
                for line in line_items
                if self._line_matches_tokens(line, ('5g', 'cellular backup', 'backup internet', 'mifi', 'lte'))
            ]
        if not backup_lines and isinstance(business_context, dict):
            backup_flag = str(
                business_context.get('needsBackupInternet')
                or business_context.get('needsCellularBackup')
                or ''
            ).strip().lower()
            if backup_flag in {'1', 'true', 'yes', 'y', 'on'}:
                backup_lines = [
                    {
                        'line_id': 'context-backup-internet',
                        'item_id': None,
                        'sku': None,
                        'source_type': 'context',
                        'name': '5G Backup Internet',
                        'vendor': 'Carrier',
                        'category': 'cellular_backup',
                        'quantity': 1,
                        'unit_price': 0.0,
                        'line_total': 0.0,
                        'selection_reason': 'Derived from business intake context.',
                    }
                ]

        if backup_lines:
            backup_node = self._aggregate_node_from_lines(
                node_id='node-backup-internet',
                kind='backup_internet',
                lines=backup_lines,
                group='wan',
            )
            nodes.append(backup_node)
            self._append_edge(
                edges,
                source=backup_node['id'],
                target=core_node['id'],
                kind='uplink',
            )

        switch_node = None
        if grouped.get('switch'):
            switch_node = self._aggregate_node_from_lines(
                node_id='node-switch',
                kind='switch',
                lines=grouped['switch'],
                group='switching',
            )
            nodes.append(switch_node)
            self._append_edge(edges, source=core_node['id'], target=switch_node['id'], kind='wired')
        else:
            assumptions.append('No switch line found in BOM; endpoints connect directly to gateway for preview.')

        downstream_id = switch_node['id'] if switch_node else core_node['id']

        wifi_lines = grouped.get('wifi_ap') or []
        if wifi_lines:
            wifi_node = self._aggregate_node_from_lines(
                node_id='node-wifi_ap',
                kind='wifi_ap',
                lines=wifi_lines,
                group='access',
            )
            nodes.append(wifi_node)
            self._append_edge(edges, source=downstream_id, target=wifi_node['id'], kind='wired')

        explicit_business_mapping = {
            'camera': 'security_cameras',
            'sensor': 'iot_devices',
            'pos_systems': 'pos_systems',
            'digital_signage': 'digital_signage',
            'kiosks': 'kiosks',
            'kitchen_systems': 'kitchen_systems',
            'guest_wifi': 'guest_wifi',
            'laptop': 'staff_devices',
            'desktop': 'staff_devices',
            'tablet': 'staff_devices',
            'phone': 'mobile_devices',
        }

        combined_business: dict[str, list[dict[str, Any]]] = {}
        for category, mapped_kind in explicit_business_mapping.items():
            if grouped.get(category):
                combined_business.setdefault(mapped_kind, []).extend(grouped[category])

        existing_line_ids_by_kind: dict[str, set[str]] = {
            kind: {str(line.get('line_id') or '') for line in lines}
            for kind, lines in combined_business.items()
        }
        for kind, lines in inferred_business.items():
            bucket = combined_business.setdefault(kind, [])
            seen = existing_line_ids_by_kind.setdefault(kind, set())
            for line in lines:
                line_id = str(line.get('line_id') or '')
                if line_id and line_id in seen:
                    continue
                bucket.append(line)
                if line_id:
                    seen.add(line_id)

        for kind in [
            'pos_systems',
            'security_cameras',
            'digital_signage',
            'iot_devices',
            'kiosks',
            'kitchen_systems',
            'guest_wifi',
            'staff_devices',
            'mobile_devices',
        ]:
            lines = combined_business.get(kind) or []
            if not lines:
                continue
            node = self._aggregate_node_from_lines(
                node_id=f'node-{kind}',
                kind=kind,
                lines=lines,
                group='business_devices',
            )
            nodes.append(node)
            is_wireless_endpoint = kind in self.WIRELESS_ENDPOINT_KINDS and wifi_lines
            connection_source = wifi_node['id'] if (is_wireless_endpoint and wifi_node) else downstream_id
            connection_kind = 'wireless' if is_wireless_endpoint else 'wired'
            self._append_edge(edges, source=connection_source, target=node['id'], kind=connection_kind)

        managed_service_node = None
        managed_service_lines = grouped.get('managed_service') or []
        if managed_service_lines:
            managed_targets = [node for node in nodes if str(node.get('kind') or '') in self.MANAGED_INFRA_TARGET_KINDS]
            managed_scope_labels = self._service_scope_labels_for_nodes(managed_targets)
            managed_service_node = self._aggregate_node_from_lines(
                node_id='node-managed-service',
                kind='managed_service',
                lines=managed_service_lines,
                group='services',
            )
            if managed_scope_labels:
                managed_service_node['metadata'] = {
                    **(managed_service_node.get('metadata') or {}),
                    'serviceScope': self._compact_scope_summary(managed_scope_labels, prefix='Covers'),
                    'managedDeviceKinds': [str(node.get('kind') or '') for node in managed_targets],
                }
            nodes.append(managed_service_node)
            if switch_node:
                self._append_edge(
                    edges,
                    source=managed_service_node['id'],
                    target=switch_node['id'],
                    kind='management',
                )
            elif managed_targets:
                primary_target = managed_targets[0]
                self._append_edge(
                    edges,
                    source=managed_service_node['id'],
                    target=primary_target['id'],
                    kind='management',
                )
            else:
                self._append_edge(
                    edges,
                    source=managed_service_node['id'],
                    target=switch_node['id'] if switch_node else core_node['id'],
                    kind='management',
                )

        include_cloud_node = bool(any(grouped.get(k) for k in ['wifi_ap', 'switch', 'firewall', 'router', 'gateway', 'security_appliance', 'cellular_gateway']))
        if include_cloud_node:
            managed_targets = [node for node in nodes if str(node.get('kind') or '') in self.MANAGED_INFRA_TARGET_KINDS]
            cloud_scope_labels = self._service_scope_labels_for_nodes(managed_targets)
            cloud_node = {
                'id': 'node-cloud-management',
                'kind': 'cloud_management',
                'label': self.LABEL_BY_KIND['cloud_management'],
                'iconType': 'cloud',
                'group': 'services',
                'metadata': {
                    'serviceScope': self._compact_scope_summary(cloud_scope_labels, prefix='Telemetry') or 'Telemetry & policy',
                },
            }
            nodes.append(cloud_node)
            if managed_service_node:
                self._append_edge(
                    edges,
                    source=cloud_node['id'],
                    target=managed_service_node['id'],
                    kind='management',
                )
            else:
                self._append_edge(
                    edges,
                    source=cloud_node['id'],
                    target=switch_node['id'] if switch_node else (core_node['id'] if core_node else (managed_targets[0]['id'] if managed_targets else '')),
                    kind='management',
                )

        self._apply_professional_edge_labels(nodes=nodes, edges=edges)
        self._reduce_redundant_edge_labels(nodes=nodes, edges=edges)

        groups = []
        group_labels = {
            'wan': 'Internet',
            'core': 'Gateway / Security',
            'switching': 'Switching',
            'access': 'Wi-Fi',
            'business_devices': 'Business Devices',
            'services': 'Cloud / Services',
        }

        for group_id in ['wan', 'core', 'switching', 'access', 'business_devices', 'services']:
            node_ids = [node['id'] for node in nodes if node.get('group') == group_id]
            if not node_ids:
                continue
            groups.append({'id': group_id, 'label': group_labels[group_id], 'nodeIds': node_ids})

        topology = {
            'metadata': {
                'generatedAt': datetime.now(timezone.utc).isoformat(),
                'designType': 'smb_network',
                'assumptions': assumptions,
            },
            'nodes': nodes,
            'edges': edges,
            'layoutHints': {
                'direction': 'left-to-right',
                'groups': groups,
            },
        }
        if design_id:
            topology['designId'] = design_id

        return topology

    def create_layout_plan(self, topology: dict[str, Any]) -> dict[str, dict[str, int]]:
        plan: dict[str, dict[str, int]] = {}
        nodes = sorted(topology.get('nodes') or [], key=lambda n: str(n.get('id') or ''))
        by_kind: dict[str, list[dict[str, Any]]] = {}
        for node in nodes:
            by_kind.setdefault(str(node.get('kind') or ''), []).append(node)

        def place_kind(kind: str, *, x: int, y: int, width: int = 190, height: int = 120) -> None:
            for node in by_kind.get(kind, []):
                plan[node['id']] = {'x': x, 'y': y, 'width': width, 'height': height}

        place_kind('backup_internet', x=80, y=30)
        place_kind('internet', x=80, y=220)
        place_kind('gateway', x=360, y=220)
        place_kind('router', x=360, y=220)
        place_kind('firewall', x=360, y=220)
        place_kind('security_appliance', x=360, y=220)
        place_kind('cellular_gateway', x=360, y=220)
        place_kind('switch', x=660, y=220)
        place_kind('wifi_ap', x=660, y=430)
        place_kind('managed_service', x=1020, y=50, width=240, height=130)
        place_kind('cloud_management', x=1320, y=50, width=240, height=130)

        wireless_order = ['guest_wifi', 'mobile_devices', 'staff_devices']
        wireless_nodes: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for kind in wireless_order:
            for node in by_kind.get(kind, []):
                if node['id'] in seen_ids:
                    continue
                seen_ids.add(node['id'])
                wireless_nodes.append(node)

        wireless_x_positions: list[int] = []
        if len(wireless_nodes) == 1:
            wireless_x_positions = [660]
        elif len(wireless_nodes) == 2:
            wireless_x_positions = [420, 900]
        else:
            wireless_x_positions = [280 + idx * 280 for idx in range(len(wireless_nodes))]

        for index, node in enumerate(wireless_nodes):
            plan[node['id']] = {
                'x': wireless_x_positions[index],
                'y': 640,
                'width': 190,
                'height': 120,
            }

        wired_order = ['pos_systems', 'security_cameras', 'digital_signage', 'iot_devices', 'kiosks', 'kitchen_systems']
        wired_nodes: list[dict[str, Any]] = []
        for kind in wired_order:
            for node in by_kind.get(kind, []):
                if node['id'] in seen_ids:
                    continue
                seen_ids.add(node['id'])
                wired_nodes.append(node)
        for kind, kind_nodes in by_kind.items():
            if kind in set(wireless_order + wired_order):
                continue
            for node in kind_nodes:
                if node.get('group') != 'business_devices':
                    continue
                if node['id'] in seen_ids:
                    continue
                seen_ids.add(node['id'])
                wired_nodes.append(node)

        for index, node in enumerate(wired_nodes):
            col = index % 5
            row = index // 5
            plan[node['id']] = {
                'x': 360 + col * 260,
                'y': 860 + row * 180,
                'width': 190,
                'height': 120,
            }

        unplaced = [node for node in nodes if node['id'] not in plan]
        for index, node in enumerate(unplaced):
            plan[node['id']] = {
                'x': 60 + (index % 6) * 220,
                'y': 760 + (index // 6) * 140,
                'width': 180,
                'height': 120,
            }

        return plan

    def _attach_edge_fanout_slots(self, edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
        routed_edges = [dict(edge) for edge in edges]
        kind_by_id: dict[str, str] = {}
        for edge in routed_edges:
            source = str(edge.get('source') or '')
            target = str(edge.get('target') or '')
            if source and source.startswith('node-'):
                kind_by_id[source] = source.removeprefix('node-')
            if target and target.startswith('node-'):
                kind_by_id[target] = target.removeprefix('node-')

        by_source: dict[str, list[dict[str, Any]]] = {}
        by_target: dict[str, list[dict[str, Any]]] = {}
        for edge in routed_edges:
            by_source.setdefault(str(edge.get('source') or ''), []).append(edge)
            by_target.setdefault(str(edge.get('target') or ''), []).append(edge)

        for bucket in by_source.values():
            stable = sorted(bucket, key=lambda edge: (str(edge.get('kind') or ''), str(edge.get('target') or ''), str(edge.get('id') or '')))
            total = len(stable)
            if total <= 1:
                continue
            for slot, edge in enumerate(stable):
                edge['_sourceSlot'] = slot
                edge['_sourceTotal'] = total

        for bucket in by_target.values():
            stable = sorted(bucket, key=lambda edge: (str(edge.get('kind') or ''), str(edge.get('source') or ''), str(edge.get('id') or '')))
            total = len(stable)
            if total <= 1:
                continue
            for slot, edge in enumerate(stable):
                edge['_targetSlot'] = slot
                edge['_targetTotal'] = total

        for edge in routed_edges:
            source_id = str(edge.get('source') or '')
            target_id = str(edge.get('target') or '')
            edge['_sourceKind'] = kind_by_id.get(source_id, source_id.removeprefix('node-'))
            edge['_targetKind'] = kind_by_id.get(target_id, target_id.removeprefix('node-'))

        return routed_edges

    def _icon_svg_markup(self, icon_type: str) -> str:
        icon = (icon_type or '').lower()
        svg_by_icon = {
            'wifi': (
                '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
                '<defs><linearGradient id="wA" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#23262c"/><stop offset="65%" stop-color="#3a3d43"/><stop offset="100%" stop-color="#1b1e23"/></linearGradient>'
                '<linearGradient id="wB" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#4f545d"/><stop offset="100%" stop-color="#252831"/></linearGradient>'
                '<filter id="wS" x="-20%" y="-20%" width="140%" height="180%"><feDropShadow dx="0" dy="2.2" stdDeviation="1.6" flood-color="#000" flood-opacity="0.33"/></filter></defs>'
                '<rect x="6" y="6" width="84" height="84" rx="16" fill="#f4f6f9" stroke="#d8e0ea" stroke-width="2"/>'
                '<rect x="25" y="21" width="8" height="37" rx="3" fill="url(#wB)" filter="url(#wS)"/><rect x="63" y="21" width="8" height="37" rx="3" fill="url(#wB)" filter="url(#wS)"/>'
                '<polygon points="18,54 78,54 72,66 24,66" fill="url(#wB)" filter="url(#wS)"/><rect x="16" y="56" width="64" height="18" rx="4" fill="url(#wA)" filter="url(#wS)"/>'
                '<rect x="42" y="66" width="12" height="3.5" rx="1.6" fill="#49c5ff"/><circle cx="29" cy="27" r="1.2" fill="#d9e2ee"/><circle cx="67" cy="27" r="1.2" fill="#d9e2ee"/>'
                '</svg>'
            ),
            'router': (
                '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
                '<defs><linearGradient id="rA" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#2d3138"/><stop offset="100%" stop-color="#171a1f"/></linearGradient>'
                '<linearGradient id="rB" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#585f6a"/><stop offset="100%" stop-color="#2a2e36"/></linearGradient>'
                '<filter id="rS" x="-20%" y="-20%" width="140%" height="180%"><feDropShadow dx="0" dy="2" stdDeviation="1.5" flood-color="#000" flood-opacity="0.3"/></filter></defs>'
                '<rect x="6" y="6" width="84" height="84" rx="16" fill="#f3f6fa" stroke="#d9e2ee" stroke-width="2"/>'
                '<rect x="27" y="23" width="7" height="30" rx="3" fill="url(#rB)"/><rect x="62" y="23" width="7" height="30" rx="3" fill="url(#rB)"/>'
                '<rect x="17" y="52" width="62" height="20" rx="4.2" fill="url(#rA)" filter="url(#rS)"/>'
                '<circle cx="30" cy="62" r="2" fill="#5ad0ff"/><circle cx="37" cy="62" r="2" fill="#7ee787"/><circle cx="44" cy="62" r="2" fill="#facc15"/>'
                '</svg>'
            ),
            'switch': (
                '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
                '<defs><linearGradient id="sA" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#2f3440"/><stop offset="100%" stop-color="#1b1f28"/></linearGradient>'
                '<filter id="sS" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="2" stdDeviation="1.5" flood-color="#000" flood-opacity="0.3"/></filter></defs>'
                '<rect x="6" y="6" width="84" height="84" rx="16" fill="#f3f6fa" stroke="#d9e2ee" stroke-width="2"/>'
                '<rect x="14" y="42" width="68" height="24" rx="4" fill="url(#sA)" filter="url(#sS)"/>'
                '<g fill="#9fb0c7"><rect x="20" y="48" width="5" height="4" rx="1"/><rect x="27" y="48" width="5" height="4" rx="1"/><rect x="34" y="48" width="5" height="4" rx="1"/><rect x="41" y="48" width="5" height="4" rx="1"/><rect x="48" y="48" width="5" height="4" rx="1"/><rect x="55" y="48" width="5" height="4" rx="1"/><rect x="62" y="48" width="5" height="4" rx="1"/><rect x="69" y="48" width="5" height="4" rx="1"/></g>'
                '<g fill="#6ee7b7"><circle cx="22" cy="58" r="1.2"/><circle cx="29" cy="58" r="1.2"/><circle cx="36" cy="58" r="1.2"/></g>'
                '</svg>'
            ),
            'firewall': (
                '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
                '<defs><linearGradient id="fA" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#2d3038"/><stop offset="100%" stop-color="#1a1d24"/></linearGradient>'
                '<linearGradient id="fB" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#f97316"/><stop offset="100%" stop-color="#dc2626"/></linearGradient></defs>'
                '<rect x="6" y="6" width="84" height="84" rx="16" fill="#f7f8fb" stroke="#dce3ee" stroke-width="2"/>'
                '<rect x="16" y="46" width="64" height="24" rx="4" fill="url(#fA)"/>'
                '<path d="M48 20 L62 26 V40 C62 49 56 56 48 59 C40 56 34 49 34 40 V26 Z" fill="url(#fB)" stroke="#7f1d1d" stroke-width="1.2"/>'
                '<path d="M43 39 L47 43 L54 34" fill="none" stroke="#fff7ed" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
                '</svg>'
            ),
            'cellular': (
                '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
                '<defs><linearGradient id="cA" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#6366f1"/><stop offset="100%" stop-color="#1d4ed8"/></linearGradient></defs>'
                '<rect x="6" y="6" width="84" height="84" rx="16" fill="#f2f6ff" stroke="#d8e2f4" stroke-width="2"/>'
                '<line x1="48" y1="26" x2="48" y2="72" stroke="#334155" stroke-width="4.2" stroke-linecap="round"/>'
                '<line x1="48" y1="26" x2="30" y2="68" stroke="#334155" stroke-width="4.2" stroke-linecap="round"/><line x1="48" y1="26" x2="66" y2="68" stroke="#334155" stroke-width="4.2" stroke-linecap="round"/>'
                '<rect x="37" y="72" width="22" height="6.5" rx="3" fill="#334155"/>'
                '<path d="M56 34 Q68 46 56 58" fill="none" stroke="url(#cA)" stroke-width="3.6" stroke-linecap="round"/><path d="M60 30 Q76 46 60 62" fill="none" stroke="url(#cA)" stroke-width="3.6" stroke-linecap="round"/>'
                '</svg>'
            ),
            'camera': (
                '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
                '<defs><linearGradient id="camA" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#374151"/><stop offset="100%" stop-color="#111827"/></linearGradient></defs>'
                '<rect x="6" y="6" width="84" height="84" rx="16" fill="#f6f8fb" stroke="#dce4ee" stroke-width="2"/>'
                '<rect x="17" y="42" width="44" height="21" rx="6" fill="url(#camA)"/><circle cx="39" cy="52.5" r="6.4" fill="#0ea5e9"/><circle cx="39" cy="52.5" r="2.4" fill="#dbeafe"/>'
                '<polygon points="61,47 79,41 79,64 61,58" fill="#1f2937"/><rect x="14" y="58" width="7" height="14" rx="2" fill="#9ca3af"/>'
                '</svg>'
            ),
            'pos': (
                '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
                '<defs><linearGradient id="pA" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#4b5563"/><stop offset="100%" stop-color="#1f2937"/></linearGradient></defs>'
                '<rect x="6" y="6" width="84" height="84" rx="16" fill="#f5f8fb" stroke="#dbe4ef" stroke-width="2"/>'
                '<rect x="24" y="18" width="32" height="19" rx="4" fill="#111827"/><rect x="27" y="22" width="26" height="11" rx="2" fill="#60a5fa"/>'
                '<rect x="21" y="38" width="40" height="36" rx="7" fill="url(#pA)"/><rect x="27" y="45" width="28" height="8" rx="2" fill="#93c5fd"/>'
                '<g fill="#cbd5e1"><rect x="28" y="58" width="6" height="6" rx="1"/><rect x="36" y="58" width="6" height="6" rx="1"/><rect x="44" y="58" width="6" height="6" rx="1"/><rect x="52" y="58" width="6" height="6" rx="1"/></g>'
                '</svg>'
            ),
            'display': (
                '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
                '<defs><linearGradient id="dA" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#0ea5e9"/><stop offset="100%" stop-color="#1d4ed8"/></linearGradient></defs>'
                '<rect x="6" y="6" width="84" height="84" rx="16" fill="#f6f8fb" stroke="#dce4ee" stroke-width="2"/>'
                '<rect x="16" y="22" width="64" height="40" rx="6" fill="#111827"/><rect x="20" y="26" width="56" height="31" rx="3" fill="url(#dA)"/>'
                '<line x1="48" y1="62" x2="48" y2="73" stroke="#374151" stroke-width="4" stroke-linecap="round"/><rect x="35" y="73" width="26" height="5" rx="2.5" fill="#4b5563"/>'
                '</svg>'
            ),
            'laptop': (
                '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
                '<defs><linearGradient id="lA" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#60a5fa"/><stop offset="100%" stop-color="#1d4ed8"/></linearGradient></defs>'
                '<rect x="6" y="6" width="84" height="84" rx="16" fill="#f4f7fc" stroke="#dce4ef" stroke-width="2"/>'
                '<rect x="24" y="22" width="48" height="30" rx="4.5" fill="#111827"/><rect x="28" y="26" width="40" height="22" rx="2.5" fill="url(#lA)"/>'
                '<path d="M18 58 H78 L72 70 H24 Z" fill="#374151"/><rect x="42" y="61" width="12" height="2.8" rx="1.4" fill="#93c5fd"/>'
                '</svg>'
            ),
            'phone': (
                '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
                '<defs><linearGradient id="mA" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#38bdf8"/><stop offset="100%" stop-color="#2563eb"/></linearGradient></defs>'
                '<rect x="6" y="6" width="84" height="84" rx="16" fill="#f4f7fc" stroke="#dce4ef" stroke-width="2"/>'
                '<rect x="33" y="16" width="30" height="60" rx="7" fill="#111827"/><rect x="37" y="23" width="22" height="45" rx="3" fill="url(#mA)"/>'
                '<circle cx="48" cy="72" r="2.3" fill="#cbd5e1"/><rect x="43" y="19" width="10" height="1.9" rx="1" fill="#94a3b8"/>'
                '</svg>'
            ),
            'kiosk': (
                '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
                '<defs><linearGradient id="kA" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#9ca3af"/><stop offset="100%" stop-color="#4b5563"/></linearGradient></defs>'
                '<rect x="6" y="6" width="84" height="84" rx="16" fill="#f6f8fb" stroke="#dce4ee" stroke-width="2"/>'
                '<rect x="34" y="16" width="28" height="44" rx="5" fill="url(#kA)"/><rect x="38" y="22" width="20" height="14" rx="2.5" fill="#60a5fa"/>'
                '<rect x="43" y="60" width="10" height="13" rx="2" fill="#374151"/><rect x="35" y="73" width="26" height="5" rx="2.5" fill="#4b5563"/>'
                '</svg>'
            ),
            'kitchen': (
                '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
                '<defs><linearGradient id="ktA" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#4b5563"/><stop offset="100%" stop-color="#1f2937"/></linearGradient></defs>'
                '<rect x="6" y="6" width="84" height="84" rx="16" fill="#f6f8fb" stroke="#dce4ee" stroke-width="2"/>'
                '<rect x="21" y="22" width="54" height="38" rx="7" fill="url(#ktA)"/><rect x="26" y="27" width="44" height="26" rx="3" fill="#e5e7eb"/>'
                '<line x1="31" y1="34" x2="53" y2="34" stroke="#475569" stroke-width="2.2"/><line x1="31" y1="40" x2="64" y2="40" stroke="#475569" stroke-width="2.2"/><line x1="31" y1="46" x2="58" y2="46" stroke="#475569" stroke-width="2.2"/>'
                '<rect x="43" y="60" width="10" height="12" rx="2" fill="#374151"/><rect x="35" y="72" width="26" height="5" rx="2.5" fill="#4b5563"/>'
                '</svg>'
            ),
            'sensor': (
                '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
                '<rect x="6" y="6" width="84" height="84" rx="16" fill="#f5f7fb" stroke="#dbe4ef" stroke-width="2"/>'
                '<circle cx="48" cy="48" r="11" fill="#2563eb"/><circle cx="48" cy="48" r="4.2" fill="#dbeafe"/>'
                '<circle cx="30" cy="34" r="4.6" fill="#93c5fd"/><circle cx="66" cy="34" r="4.6" fill="#93c5fd"/><circle cx="30" cy="62" r="4.6" fill="#93c5fd"/><circle cx="66" cy="62" r="4.6" fill="#93c5fd"/>'
                '<line x1="48" y1="48" x2="30" y2="34" stroke="#3b82f6" stroke-width="2.3"/><line x1="48" y1="48" x2="66" y2="34" stroke="#3b82f6" stroke-width="2.3"/><line x1="48" y1="48" x2="30" y2="62" stroke="#3b82f6" stroke-width="2.3"/><line x1="48" y1="48" x2="66" y2="62" stroke="#3b82f6" stroke-width="2.3"/>'
                '</svg>'
            ),
            'internet': (
                '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
                '<defs><linearGradient id="iA" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#93c5fd"/><stop offset="100%" stop-color="#2563eb"/></linearGradient></defs>'
                '<rect x="6" y="6" width="84" height="84" rx="16" fill="#f2f7ff" stroke="#d8e4f4" stroke-width="2"/>'
                '<circle cx="48" cy="47" r="18" fill="url(#iA)"/><ellipse cx="48" cy="47" rx="15" ry="6" fill="none" stroke="#dbeafe" stroke-width="2"/><line x1="33" y1="47" x2="63" y2="47" stroke="#dbeafe" stroke-width="2"/>'
                '<path d="M41 32 Q48 47 41 62" fill="none" stroke="#dbeafe" stroke-width="2"/><path d="M55 32 Q48 47 55 62" fill="none" stroke="#dbeafe" stroke-width="2"/>'
                '<ellipse cx="48" cy="66" rx="18" ry="8" fill="#000" opacity="0.08"/>'
                '</svg>'
            ),
            'antenna': (
                '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
                '<defs><linearGradient id="aA" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#64748b"/><stop offset="100%" stop-color="#334155"/></linearGradient></defs>'
                '<rect x="6" y="6" width="84" height="84" rx="16" fill="#f5f8fd" stroke="#dce5f1" stroke-width="2"/>'
                '<line x1="48" y1="24" x2="48" y2="71" stroke="url(#aA)" stroke-width="4.2" stroke-linecap="round"/><line x1="48" y1="24" x2="30" y2="68" stroke="url(#aA)" stroke-width="4.2" stroke-linecap="round"/><line x1="48" y1="24" x2="66" y2="68" stroke="url(#aA)" stroke-width="4.2" stroke-linecap="round"/>'
                '<rect x="38" y="71" width="20" height="6.5" rx="3.2" fill="#334155"/>'
                '<path d="M56 34 Q68 46 56 58" fill="none" stroke="#2563eb" stroke-width="3.3" stroke-linecap="round"/><path d="M60 30 Q76 46 60 62" fill="none" stroke="#2563eb" stroke-width="3.3" stroke-linecap="round"/>'
                '<path d="M40 34 Q28 46 40 58" fill="none" stroke="#2563eb" stroke-width="3.3" stroke-linecap="round"/><path d="M36 30 Q20 46 36 62" fill="none" stroke="#2563eb" stroke-width="3.3" stroke-linecap="round"/>'
                '</svg>'
            ),
            'cloud': (
                '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
                '<defs><linearGradient id="clA" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#a78bfa"/><stop offset="100%" stop-color="#6d28d9"/></linearGradient></defs>'
                '<rect x="6" y="6" width="84" height="84" rx="16" fill="#f6f3ff" stroke="#dfd7f7" stroke-width="2"/>'
                '<path d="M28 58 C20 58 18 45 28 43 C30 35 38 31 45 35 C50 28 61 29 64 38 C72 37 78 43 76 51 C74 58 68 58 63 58 Z" fill="url(#clA)"/>'
                '<circle cx="48" cy="48" r="7" fill="#ede9fe"/><circle cx="48" cy="48" r="3.2" fill="#6d28d9"/><g stroke="#ede9fe" stroke-width="2"><line x1="48" y1="37" x2="48" y2="41"/><line x1="48" y1="55" x2="48" y2="59"/><line x1="37" y1="48" x2="41" y2="48"/><line x1="55" y1="48" x2="59" y2="48"/></g>'
                '</svg>'
            ),
        }

        if icon in svg_by_icon:
            return svg_by_icon[icon]
        return svg_by_icon['router']

    def _icon_data_uri(self, icon_type: str) -> str:
        svg = self._icon_svg_markup(icon_type)
        return f'data:image/svg+xml,{quote(svg, safe="")}'

    def _format_node_label_for_drawio(self, node: dict[str, Any]) -> str:
        text = str(node.get('label') or '').strip()
        if not text:
            return ''

        metadata = node.get('metadata')
        service_scope = ''
        if isinstance(metadata, dict):
            service_scope = str(metadata.get('serviceScope') or '').strip()
        if service_scope:
            return (
                '<div style="text-align:center;line-height:1.2;">'
                f'{escape(text)}'
                '<br/>'
                f'<span style="color:#475569;font-size:11px;">{escape(service_scope)}</span>'
                '</div>'
            )

        if text.endswith(')') and ' (' in text:
            base, maybe_count = text.rsplit(' (', 1)
            count = maybe_count[:-1]
            if count.isdigit():
                return (
                    '<div style="text-align:center;line-height:1.2;">'
                    f'{escape(base)}'
                    '<br/>'
                    f'<span style="color:#475569;font-size:11px;">({escape(count)})</span>'
                    '</div>'
                )
        return escape(text)

    def _node_style(self, node: dict[str, Any]) -> str:
        icon_type = str(node.get('iconType') or '').lower()
        image_data_uri = self._icon_data_uri(icon_type or 'router')
        return (
            'shape=image;html=1;imageAspect=0;aspect=fixed;align=center;'
            'verticalLabelPosition=bottom;verticalAlign=top;whiteSpace=wrap;spacingTop=6;'
            'fontSize=12;fontColor=#111827;labelBackgroundColor=#ffffff;strokeColor=none;fillColor=none;'
            f'image={image_data_uri};'
        )

    def map_node_to_drawio_cell(self, *, node: dict[str, Any], geometry: dict[str, int]) -> ET.Element:
        cell = ET.Element(
            'mxCell',
            {
                'id': str(node['id']),
                'value': self._format_node_label_for_drawio(node),
                'style': self._node_style(node),
                'vertex': '1',
                'parent': '1',
            },
        )
        ET.SubElement(
            cell,
            'mxGeometry',
            {
                'x': str(geometry['x']),
                'y': str(geometry['y']),
                'width': str(geometry['width']),
                'height': str(geometry['height']),
                'as': 'geometry',
            },
        )
        return cell

    def map_edge_to_drawio_cell(self, edge: dict[str, Any]) -> ET.Element:
        edge_kind = str(edge.get('kind') or '').lower()
        source_kind = str(edge.get('_sourceKind') or '').lower()
        target_kind = str(edge.get('_targetKind') or '').lower()
        style = (
            'html=1;endArrow=classic;endFill=1;fontSize=10;fontColor=#0f172a;labelBackgroundColor=#ffffff;'
            'edgeStyle=orthogonalEdgeStyle;orthogonalLoop=1;jettySize=22;rounded=0;jumpStyle=arc;jumpSize=10;'
        )
        manual_ports = False
        if edge_kind == 'uplink':
            style += 'strokeColor=#1d4ed8;strokeWidth=2.4;'
        elif edge_kind == 'wireless':
            style += 'strokeColor=#0f766e;dashed=1;dashPattern=7 5;'
        elif edge_kind == 'management':
            style += 'strokeColor=#7c3aed;dashed=1;dashPattern=2 5;endArrow=open;endFill=0;'
        else:
            style += 'strokeColor=#334155;strokeWidth=1.8;'

        if edge_kind == 'wired' and source_kind == 'switch' and target_kind == 'wifi_ap':
            style += 'exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;'
            manual_ports = True
        elif edge_kind == 'wired' and source_kind == 'switch' and target_kind != 'wifi_ap':
            source_center = float(edge.get('_sourceCenterX') or 0)
            target_center = float(edge.get('_targetCenterX') or 0)
            go_right = target_center >= source_center
            side_x = '1' if go_right else '0'
            side_dx = 120 if go_right else -120
            style += (
                f'exitX={side_x};exitY=0.58;exitDx={side_dx};exitDy=0;'
                'entryX=0.5;entryY=0;entryDx=0;entryDy=0;'
            )
            manual_ports = True

        if not manual_ports:
            source_total = int(edge.get('_sourceTotal') or 0)
            if source_total > 1:
                source_slot = int(edge.get('_sourceSlot') or 0)
                source_x = 0.5 if source_total == 1 else (0.15 + (0.7 * source_slot / max(1, source_total - 1)))
                style += f'exitX={source_x:.3f};exitY=1;exitDx=0;exitDy=0;'

            target_total = int(edge.get('_targetTotal') or 0)
            if target_total > 1:
                target_slot = int(edge.get('_targetSlot') or 0)
                target_x = 0.5 if target_total == 1 else (0.15 + (0.7 * target_slot / max(1, target_total - 1)))
                style += f'entryX={target_x:.3f};entryY=0;entryDx=0;entryDy=0;'

        edge_cell = ET.Element(
            'mxCell',
            {
                'id': str(edge['id']),
                'value': str(edge.get('label') or ''),
                'style': style,
                'edge': '1',
                'parent': '1',
                'source': str(edge['source']),
                'target': str(edge['target']),
            },
        )
        ET.SubElement(edge_cell, 'mxGeometry', {'relative': '1', 'as': 'geometry'})
        return edge_cell

    def topology_to_drawio_xml(self, topology: dict[str, Any]) -> str:
        layout = self.create_layout_plan(topology)

        mxfile = ET.Element('mxfile', {'host': 'app.diagrams.net', 'agent': 'secureoffice2', 'version': '24.7.17'})
        diagram = ET.SubElement(mxfile, 'diagram', {'id': 'secureoffice2-network-diagram', 'name': 'SMB Network'})
        graph_model = ET.SubElement(
            diagram,
            'mxGraphModel',
            {
                'dx': '1200',
                'dy': '800',
                'grid': '1',
                'gridSize': '10',
                'guides': '1',
                'tooltips': '1',
                'connect': '1',
                'arrows': '1',
                'fold': '1',
                'page': '1',
                'pageScale': '1',
                'pageWidth': '2800',
                'pageHeight': '1700',
                'math': '0',
                'shadow': '0',
            },
        )
        root = ET.SubElement(graph_model, 'root')
        ET.SubElement(root, 'mxCell', {'id': '0'})
        ET.SubElement(root, 'mxCell', {'id': '1', 'parent': '0'})

        ordered_edges = sorted(topology.get('edges') or [], key=lambda e: str(e.get('id') or ''))
        routed_edges = self._attach_edge_fanout_slots(ordered_edges)
        for edge in routed_edges:
            source_geo = layout.get(str(edge.get('source') or ''))
            target_geo = layout.get(str(edge.get('target') or ''))
            if source_geo and target_geo:
                edge['_sourceCenterX'] = source_geo['x'] + (source_geo['width'] / 2)
                edge['_targetCenterX'] = target_geo['x'] + (target_geo['width'] / 2)
            root.append(self.map_edge_to_drawio_cell(edge))
        
        for node in sorted(topology.get('nodes') or [], key=lambda n: str(n.get('id') or '')):
            geometry = layout.get(node['id']) or {'x': 40, 'y': 40, 'width': 180, 'height': 120}
            root.append(self.map_node_to_drawio_cell(node=node, geometry=geometry))

        xml_body = ET.tostring(mxfile, encoding='unicode')
        return f'<?xml version="1.0" encoding="UTF-8"?>{xml_body}'

    def generate_topology_artifact_from_bom(
        self,
        bom: dict[str, Any],
        *,
        design_id: str | None = None,
        business_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        topology = self.generate_topology_from_bom(bom, design_id=design_id, business_context=business_context)
        drawio_xml = self.topology_to_drawio_xml(topology)

        return {
            'topology': topology,
            'drawioXml': drawio_xml,
            'summary': {
                'nodeCount': len(topology.get('nodes') or []),
                'edgeCount': len(topology.get('edges') or []),
                'assumptions': list((topology.get('metadata') or {}).get('assumptions') or []),
            },
        }
