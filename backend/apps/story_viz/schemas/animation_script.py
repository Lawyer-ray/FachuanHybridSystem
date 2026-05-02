from __future__ import annotations

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str = Field(default="")
    label: str = Field(default="")
    category: str = Field(default="person")


class GraphEdge(BaseModel):
    source: str = Field(default="")
    target: str = Field(default="")
    relation: str = Field(default="")


class MotionPlan(BaseModel):
    duration_ms: int = Field(default=1200)
    easing: str = Field(default="ease-in-out")


class ComparisonItem(BaseModel):
    claim: str = Field(default="")
    judgment: str = Field(default="")
    amount_claim: str = Field(default="")
    amount_judgment: str = Field(default="")
    supported: bool = Field(default=False)


class AnimationScript(BaseModel):
    title: str = Field(default="")
    viz_type: str = Field(default="timeline")
    theme: str = Field(default="glass-dark")
    highlights: list[str] = Field(default_factory=list)
    annotations: list[str] = Field(default_factory=list)
    timeline_nodes: list[dict[str, str]] = Field(default_factory=list)
    relationship_nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    comparison_nodes: list[ComparisonItem] = Field(default_factory=list)
    scene_order: list[str] = Field(default_factory=list)
    motion_plan: MotionPlan = Field(default_factory=MotionPlan)
    fragment_prompts: list[str] = Field(default_factory=list)
