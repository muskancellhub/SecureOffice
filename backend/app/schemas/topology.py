from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TopologyMetadataResponse(BaseModel):
    generated_at: datetime = Field(alias='generatedAt')
    design_type: Literal['smb_network'] = Field(alias='designType')
    assumptions: list[str]


class TopologyNodeResponse(BaseModel):
    id: str
    kind: str
    label: str
    vendor: str | None = None
    sku: str | None = None
    quantity: int | None = None
    icon_type: str | None = Field(default=None, alias='iconType')
    group: str | None = None
    metadata: dict[str, Any] | None = None


class TopologyEdgeResponse(BaseModel):
    id: str
    source: str
    target: str
    label: str | None = None
    kind: str | None = None


class TopologyLayoutGroupResponse(BaseModel):
    id: str
    label: str
    node_ids: list[str] = Field(alias='nodeIds')


class TopologyLayoutHintsResponse(BaseModel):
    direction: Literal['left-to-right', 'top-to-bottom'] | None = None
    groups: list[TopologyLayoutGroupResponse] = Field(default_factory=list)


class NetworkTopologyResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    design_id: str | None = Field(default=None, alias='designId')
    metadata: TopologyMetadataResponse
    nodes: list[TopologyNodeResponse]
    edges: list[TopologyEdgeResponse]
    layout_hints: TopologyLayoutHintsResponse | None = Field(default=None, alias='layoutHints')


class NetworkTopologySummaryResponse(BaseModel):
    node_count: int = Field(alias='nodeCount')
    edge_count: int = Field(alias='edgeCount')
    assumptions: list[str] = Field(default_factory=list)


class GenerateNetworkTopologyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    bom: dict
    design_id: str | None = Field(default=None, alias='designId')
    business_context: dict[str, Any] | None = Field(default=None, alias='businessContext')


class GenerateNetworkTopologyResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    topology: NetworkTopologyResponse
    drawio_xml: str = Field(alias='drawioXml')
    summary: NetworkTopologySummaryResponse
