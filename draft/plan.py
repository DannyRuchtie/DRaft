"""LLM-assisted planning for DRaft commit cycles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, List, Optional

from .adapters import Adapter, AdapterError, LLMRequest
from .group import GroupPlan, heuristic_groups

SYSTEM_PROMPT = """You are DRaft, a tool that prepares commit plans.
Group the provided file paths into logical commits. Respond as JSON:
{"groups":[{"title":"","body":"","files":[]}]}"""


@dataclass
class PlanResult:
    groups: List[GroupPlan]
    raw_response: Optional[str] = None
    source: str = "heuristic"


class PlanGenerator:
    """
    Combine heuristics with LLM refinement to produce commit groups.
    
    Uses a two-stage approach:
    1. Generate baseline groups using file-based heuristics
    2. Optionally refine with an LLM adapter for better messages
    3. Gracefully fall back to heuristics if LLM is unavailable
    """

    def __init__(self, adapter: Adapter | None = None) -> None:
        """
        Initialize the plan generator.
        
        Args:
            adapter: Optional LLM adapter for AI-assisted planning
        """
        self.adapter = adapter

    def build_plan(self, files: Iterable[str]) -> PlanResult:
        """
        Build a commit plan from a list of changed files.
        
        Strategy:
        1. Start with heuristic grouping (fast, works offline)
        2. If LLM adapter available, refine the groups
        3. Fall back to heuristics on LLM errors
        
        Args:
            files: List of changed file paths
            
        Returns:
            PlanResult with grouped files and source indicator
        """
        files_list = list(files)
        # Always generate heuristic baseline
        heuristic = heuristic_groups(files_list)
        
        if not files_list:
            return PlanResult(groups=[], source="empty")

        # Use heuristics if no adapter configured
        if not self.adapter:
            return PlanResult(groups=heuristic, source="heuristic")

        # Prepare LLM request with heuristic as context
        request_payload = {
            "files": files_list,
            "heuristic_plan": [group.to_dict() for group in heuristic],
        }
        prompt = (
            "Files changed:\n"
            + "\n".join(f"- {path}" for path in files_list)
            + "\n\nProposed groups:\n"
            + json.dumps(request_payload["heuristic_plan"], indent=2)
        )
        
        # Try LLM refinement, fall back on errors
        try:
            response = self.adapter.generate(LLMRequest(prompt=prompt, system=SYSTEM_PROMPT))
            plan = self._parse_response(response)
            if plan:
                return PlanResult(groups=plan, raw_response=response, source="llm")
        except AdapterError:
            # LLM failed - fall back to heuristics
            pass

        return PlanResult(groups=heuristic, source="heuristic")

    def _parse_response(self, payload: str) -> List[GroupPlan]:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return []

        groups_data = data.get("groups")
        if not isinstance(groups_data, list):
            return []

        groups: List[GroupPlan] = []
        for entry in groups_data:
            title = str(entry.get("title") or "Draft Change")
            body = str(entry.get("body") or "")
            files = entry.get("files") or []
            if not isinstance(files, list):
                continue
            groups.append(GroupPlan(title=title, body=body, files=[str(f) for f in files]))
        return groups
