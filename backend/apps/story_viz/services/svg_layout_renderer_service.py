from __future__ import annotations

from apps.story_viz.schemas import AnimationScript


class SvgLayoutRendererService:
    def render(self, *, script: AnimationScript, viz_type: str) -> dict[str, object]:
        if viz_type == "relationship":
            nodes = [node.model_dump() for node in script.relationship_nodes]
            edges = [edge.model_dump() for edge in script.edges]
            return {
                "viz_type": viz_type,
                "theme": script.theme,
                "nodes": nodes,
                "edges": edges,
                "motion": script.motion_plan.model_dump(),
                "annotations": script.annotations,
            }

        return {
            "viz_type": "timeline",
            "theme": script.theme,
            "nodes": script.timeline_nodes,
            "annotations": script.annotations,
            "motion": script.motion_plan.model_dump(),
        }
