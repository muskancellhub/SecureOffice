import type { DrawioOutput, TopologyDiagram, TopologyEdgeKind, TopologyNode } from './types';

type LayoutCell = {
  x: number;
  y: number;
  width: number;
  height: number;
};

const escapeXml = (value: string): string => {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
};

const iconStyle = (type: TopologyNode['type']): string => {
  switch (type) {
    case 'internet':
      return 'shape=cloud;whiteSpace=wrap;html=1;strokeColor=#1f2937;fillColor=#dbeafe;fontSize=12;';
    case 'gateway':
      return 'rounded=1;whiteSpace=wrap;html=1;strokeColor=#111827;fillColor=#fde68a;fontSize=12;';
    case 'switch':
      return 'rounded=1;whiteSpace=wrap;html=1;strokeColor=#111827;fillColor=#bfdbfe;fontSize=12;';
    case 'wifi_ap':
      return 'rounded=1;whiteSpace=wrap;html=1;strokeColor=#111827;fillColor=#bbf7d0;fontSize=12;';
    case 'cellular_backup':
      return 'rounded=1;whiteSpace=wrap;html=1;strokeColor=#111827;fillColor=#fed7aa;fontSize=12;';
    case 'managed_service':
      return 'rounded=1;dashed=1;whiteSpace=wrap;html=1;strokeColor=#374151;fillColor=#e5e7eb;fontSize=12;';
    default:
      return 'rounded=1;whiteSpace=wrap;html=1;strokeColor=#374151;fillColor=#f3f4f6;fontSize=12;';
  }
};

const nodeRank = (node: TopologyNode): number => {
  switch (node.type) {
    case 'internet':
      return 1;
    case 'gateway':
      return 2;
    case 'switch':
      return 3;
    case 'wifi_ap':
      return 4;
    case 'cellular_backup':
      return 5;
    default:
      return 6;
  }
};

export const createLayoutPlan = (topology: TopologyDiagram): Map<string, LayoutCell> => {
  const direction = topology.layoutHints?.direction || 'left_to_right';
  const sortedNodes = [...topology.nodes].sort((a, b) => nodeRank(a) - nodeRank(b));

  const map = new Map<string, LayoutCell>();
  const mainLaneIds = new Set(['internet', 'gateway', 'switch', 'wifi-ap']);

  if (direction === 'top_to_bottom') {
    let mainIndex = 0;
    let sideIndex = 0;
    for (const node of sortedNodes) {
      if (mainLaneIds.has(node.id)) {
        map.set(node.id, { x: 380, y: 80 + mainIndex * 150, width: 180, height: 72 });
        mainIndex += 1;
      } else {
        map.set(node.id, { x: sideIndex % 2 === 0 ? 120 : 640, y: 100 + Math.floor(sideIndex / 2) * 130, width: 180, height: 72 });
        sideIndex += 1;
      }
    }
    return map;
  }

  let mainIndex = 0;
  let sideIndex = 0;
  for (const node of sortedNodes) {
    if (mainLaneIds.has(node.id)) {
      map.set(node.id, { x: 80 + mainIndex * 230, y: 140, width: 190, height: 76 });
      mainIndex += 1;
    } else {
      map.set(node.id, { x: 560 + (sideIndex % 2) * 230, y: 20 + Math.floor(sideIndex / 2) * 120, width: 190, height: 72 });
      sideIndex += 1;
    }
  }

  return map;
};

export const mapNodeToDrawioCell = (node: TopologyNode, cell: LayoutCell): string => {
  const labelParts = [node.label];
  if (node.vendor && node.model) labelParts.push(`${node.vendor} ${node.model}`);
  if (node.quantity && node.quantity > 1) labelParts.push(`Qty: ${node.quantity}`);

  const label = escapeXml(labelParts.join('\n'));

  return [
    `<mxCell id="node-${escapeXml(node.id)}" value="${label}" style="${iconStyle(node.type)}" vertex="1" parent="1">`,
    `<mxGeometry x="${cell.x}" y="${cell.y}" width="${cell.width}" height="${cell.height}" as="geometry"/>`,
    '</mxCell>',
  ].join('');
};

/** Edge style varies by connection kind for visual clarity */
const edgeStyleByKind = (kind?: TopologyEdgeKind): string => {
  switch (kind) {
    case 'wired':
      // Solid dark line — physical cable
      return 'endArrow=block;rounded=0;html=1;strokeColor=#1f2937;strokeWidth=2;';
    case 'wireless':
      // Dashed blue line — Wi-Fi
      return 'endArrow=block;rounded=0;html=1;strokeColor=#3b82f6;strokeWidth=1;dashed=1;dashPattern=8 4;';
    case 'managed':
      // Dotted gray line — managed/service relationship
      return 'endArrow=open;rounded=0;html=1;strokeColor=#9ca3af;strokeWidth=1;dashed=1;dashPattern=3 3;';
    case 'failover':
      // Dashed orange line — backup/failover path
      return 'endArrow=block;rounded=0;html=1;strokeColor=#f59e0b;strokeWidth=1;dashed=1;dashPattern=6 3;';
    case 'wan':
      // Solid medium line — WAN uplink
      return 'endArrow=block;rounded=0;html=1;strokeColor=#6366f1;strokeWidth=2;';
    default:
      return 'endArrow=block;rounded=0;html=1;strokeColor=#4b5563;';
  }
};

export const mapEdgeToDrawioCell = (
  edgeId: string,
  sourceNodeId: string,
  targetNodeId: string,
  label?: string,
  kind?: TopologyEdgeKind,
): string => {
  const escapedLabel = escapeXml(label || '');
  return [
    `<mxCell id="edge-${escapeXml(edgeId)}" value="${escapedLabel}" style="${edgeStyleByKind(kind)}" edge="1" parent="1" source="node-${escapeXml(sourceNodeId)}" target="node-${escapeXml(targetNodeId)}">`,
    '<mxGeometry relative="1" as="geometry"/>',
    '</mxCell>',
  ].join('');
};

export const topologyToDrawioXml = (topology: TopologyDiagram): DrawioOutput => {
  const layout = createLayoutPlan(topology);
  const nodeCells = topology.nodes.map((node) => mapNodeToDrawioCell(node, layout.get(node.id) || { x: 80, y: 80, width: 180, height: 72 }));
  const edgeCells = topology.edges.map((edge) => mapEdgeToDrawioCell(edge.id, edge.source, edge.target, edge.label, edge.kind));

  const xml = [
    '<mxfile host="app.diagrams.net" version="22.1.0">',
    `<diagram id="diagram-1" name="${escapeXml(topology.title || 'SMB Network')}">`,
    '<mxGraphModel dx="1290" dy="790" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1600" pageHeight="900" math="0" shadow="0">',
    '<root>',
    '<mxCell id="0"/>',
    '<mxCell id="1" parent="0"/>',
    ...nodeCells,
    ...edgeCells,
    '</root>',
    '</mxGraphModel>',
    '</diagram>',
    '</mxfile>',
  ].join('');

  return {
    xml,
    meta: {
      nodeCount: topology.nodes.length,
      edgeCount: topology.edges.length,
    },
  };
};
