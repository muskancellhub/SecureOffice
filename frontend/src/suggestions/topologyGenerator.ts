import type { BomItem, BusinessContext, TopologyDiagram, TopologyEdgeKind, TopologyNode, TopologyNodeType } from './types';

type GenerateTopologyInput = {
  bomItems: BomItem[];
  businessContext?: BusinessContext;
  title?: string;
};

type GenerateTopologyResult = {
  topology: TopologyDiagram;
  assumptions: string[];
};

const findLine = (bomItems: BomItem[], category: BomItem['category']): BomItem | undefined => {
  return bomItems.find((line) => line.category === category);
};

const includesUseCase = (useCases: string[] | undefined, tokens: string[]): boolean => {
  if (!useCases || useCases.length === 0) return false;
  const normalized = useCases.map((entry) => entry.trim().toLowerCase());
  return tokens.some((token) => normalized.some((entry) => entry.includes(token)));
};

const createNode = (
  id: string,
  type: TopologyNodeType,
  label: string,
  options?: {
    vendor?: string;
    model?: string;
    quantity?: number;
    iconKey?: string;
  },
): TopologyNode => {
  return {
    id,
    type,
    label,
    vendor: options?.vendor,
    model: options?.model,
    quantity: options?.quantity,
    iconKey: options?.iconKey || type,
  };
};

export const generateTopologyFromBom = (input: GenerateTopologyInput): GenerateTopologyResult => {
  const assumptions: string[] = [];
  const nodes: TopologyNode[] = [];
  const edges: TopologyDiagram['edges'] = [];

  const gatewayLine = findLine(input.bomItems, 'gateway');
  const switchLine = findLine(input.bomItems, 'switch');
  const apLine = findLine(input.bomItems, 'wifi_ap');
  const cellularLine = findLine(input.bomItems, 'cellular_backup');
  const managedServiceLine = findLine(input.bomItems, 'managed_service');

  nodes.push(createNode('internet', 'internet', 'Internet / WAN', { iconKey: 'internet' }));

  if (gatewayLine) {
    nodes.push(createNode('gateway', 'gateway', 'Gateway / Security', {
      vendor: gatewayLine.vendor,
      model: gatewayLine.model,
      quantity: gatewayLine.quantity,
      iconKey: 'gateway',
    }));
    edges.push({ id: 'edge-internet-gateway', source: 'internet', target: 'gateway', label: 'WAN uplink', kind: 'wan' });
  } else {
    assumptions.push('No dedicated gateway/firewall item in BOM; using Internet direct-to-switch path.');
  }

  if (switchLine) {
    nodes.push(createNode('switch', 'switch', 'PoE Switch Layer', {
      vendor: switchLine.vendor,
      model: switchLine.model,
      quantity: switchLine.quantity,
      iconKey: 'switch',
    }));

    edges.push({
      id: gatewayLine ? 'edge-gateway-switch' : 'edge-internet-switch',
      source: gatewayLine ? 'gateway' : 'internet',
      target: 'switch',
      label: 'Wired link (LAN core)',
      kind: 'wired',
    });
  } else {
    assumptions.push('No switch item in BOM; topology omits LAN aggregation layer.');
  }

  if (apLine) {
    nodes.push(createNode('wifi-ap', 'wifi_ap', 'Wi-Fi AP Group', {
      vendor: apLine.vendor,
      model: apLine.model,
      quantity: apLine.quantity,
      iconKey: 'wifi',
    }));

    if (switchLine) {
      edges.push({ id: 'edge-switch-ap', source: 'switch', target: 'wifi-ap', label: 'Wired link (PoE)', kind: 'wired' });
    }
  }

  if (cellularLine) {
    nodes.push(createNode('cellular-backup', 'cellular_backup', 'Backup Internet', {
      vendor: cellularLine.vendor,
      model: cellularLine.model,
      quantity: cellularLine.quantity,
      iconKey: 'cellular',
    }));

    if (gatewayLine) {
      edges.push({ id: 'edge-cellular-gateway', source: 'cellular-backup', target: 'gateway', label: 'Cellular failover (5G/LTE)', kind: 'failover' });
    } else if (switchLine) {
      edges.push({ id: 'edge-cellular-switch', source: 'cellular-backup', target: 'switch', label: 'Cellular backup uplink', kind: 'failover' });
    } else {
      assumptions.push('Cellular backup exists but no gateway/switch target is present in BOM.');
    }
  }

  const useCases = input.businessContext?.useCases;
  const shouldShowPos = includesUseCase(useCases, ['pos', 'point of sale', 'payment']);
  const shouldShowIot = includesUseCase(useCases, ['iot', 'sensor', 'smart', 'automation']);
  const shouldShowSignage = includesUseCase(useCases, ['signage', 'display', 'kiosk']);
  const shouldShowCamera = includesUseCase(useCases, ['camera', 'video', 'cctv', 'surveillance']);

  if (shouldShowPos) {
    nodes.push(createNode('pos', 'pos', 'POS Devices', { iconKey: 'pos' }));
    if (switchLine) edges.push({ id: 'edge-switch-pos', source: 'switch', target: 'pos', label: 'Wired link', kind: 'wired' });
  }

  if (shouldShowIot) {
    nodes.push(createNode('iot', 'iot', 'IoT Devices', { iconKey: 'sensor' }));
    // IoT may be wired or wireless — default to wireless since many sensors use Wi-Fi
    if (switchLine) edges.push({ id: 'edge-switch-iot', source: 'switch', target: 'iot', label: 'Wireless link', kind: 'wireless' });
  }

  if (shouldShowSignage) {
    nodes.push(createNode('signage', 'signage', 'Digital Signage', { iconKey: 'signage' }));
    if (switchLine) edges.push({ id: 'edge-switch-signage', source: 'switch', target: 'signage', label: 'Wired link', kind: 'wired' });
  }

  if (shouldShowCamera) {
    nodes.push(createNode('camera', 'camera', 'Camera Group', { iconKey: 'camera' }));
    // IP cameras typically use PoE (wired)
    if (switchLine) edges.push({ id: 'edge-switch-camera', source: 'switch', target: 'camera', label: 'Wired link (PoE)', kind: 'wired' });
  }

  if (managedServiceLine || input.businessContext?.needsManagedServices) {
    nodes.push(createNode('managed-service', 'managed_service', 'Managed Service Support', { iconKey: 'managed_service' }));
    if (switchLine) edges.push({ id: 'edge-managed-switch', source: 'managed-service', target: 'switch', label: 'Managed connection', kind: 'managed' });
  }

  if (!apLine) assumptions.push('No AP line found in BOM; Wi-Fi layer is not shown.');

  const topology: TopologyDiagram = {
    title: input.title || 'SMB Network Topology (V1)',
    nodes,
    edges,
    layoutHints: {
      direction: 'left_to_right',
    },
  };

  return { topology, assumptions };
};

