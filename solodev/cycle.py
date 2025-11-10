"""Cycle orchestration for SoloDev."""

from __future__ import annotations

import getpass
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .adapters import Adapter
from .audit import record_cycle, snapshot_files
from .config import SoloDevConfig
from .plan import PlanGenerator, PlanResult
from .policy import PolicyResult, run_checks
from .util import now_utc
from .vcs import DiffStat, Git, GitError


@dataclass
class CycleReport:
    status: str
    plan: PlanResult
    policy: PolicyResult
    diff_text: str
    diff_stat: DiffStat
    commits: List[str] = field(default_factory=list)
    tag: str | None = None
    pushed: bool = False
    branch: str | None = None
    errors: List[str] = field(default_factory=list)
    message: str = ""
    snapshot: dict[str, str] = field(default_factory=dict)

    @property
    def diff_line_count(self) -> int:
        return self.diff_stat.total


class CycleManager:
    """Manage plan/commit/push cycles for SoloDev."""

    def __init__(
        self,
        config: SoloDevConfig,
        *,
        git: Git | None = None,
        adapter: Adapter | None = None,
    ) -> None:
        self.config = config
        self.git = git or Git()
        self.plan_generator = PlanGenerator(adapter)
        self._last_report: CycleReport | None = None

    @property
    def last_report(self) -> CycleReport | None:
        return self._last_report

    def resolve_branch_name(self) -> str:
        """Expose resolved branch for CLI and status reporting."""
        return self._resolve_branch_name()

    def execute(
        self,
        mode: str | None = None,
        *,
        ask_push: Callable[[CycleReport], bool] | None = None,
    ) -> CycleReport:
        """
        Execute a full SoloDev cycle according to the requested mode.
        
        Orchestrates the complete workflow:
        1. Detect changed files
        2. Build a plan (group files for commits)
        3. Run policy checks (secrets, diff size, protected branches)
        4. Capture snapshots (for undo capability)
        5. Create commits (if mode is commit or push)
        6. Push to remote (if mode is push and user confirms)
        7. Record audit entry
        
        Args:
            mode: Override configured mode (plan, commit, or push)
            ask_push: Optional callback to confirm before pushing
            
        Returns:
            CycleReport with status, commits, and metadata
        """
        effective_mode = (mode or self.config.mode).lower()
        files = self.git.changed_files()
        target_branch = self.resolve_branch_name()
        plan_result = self.plan_generator.build_plan(files)
        diff_text = self.git.diff()
        diff_stat = self.git.diff_stat()
        policy_result = run_checks(
            diff_text=diff_text,
            diff_line_limit=self.config.smart_push.max_diff_lines,
            files=files,
            secret_patterns=self.config.secret_patterns,
            protected_branches=self.config.protected_branches,
            current_branch=target_branch,
            large_file_threshold=500,
        )

        if not files:
            report = CycleReport(
                status="no_changes",
                plan=plan_result,
                policy=policy_result,
                diff_text=diff_text,
                diff_stat=diff_stat,
                branch=target_branch,
                message="No changes detected.",
            )
            self._finalize(report)
            return report

        if not policy_result.passed:
            report = CycleReport(
                status="blocked",
                plan=plan_result,
                policy=policy_result,
                diff_text=diff_text,
                diff_stat=diff_stat,
                branch=target_branch,
                message="Policy checks failed.",
                errors=[msg.message for msg in policy_result.messages if msg.severity == "error"],
            )
            self._finalize(report)
            return report

        if effective_mode == "plan":
            report = CycleReport(
                status="planned",
                plan=plan_result,
                policy=policy_result,
                diff_text=diff_text,
                diff_stat=diff_stat,
                branch=target_branch,
                message="Plan generated (plan-only mode).",
            )
            self._finalize(report)
            return report

        # Capture snapshot before committing
        snapshot = snapshot_files(files, max_size=self.config.snapshot_max_size)
        
        commits = self._commit_groups(plan_result)
        tag_name = self._tag_cycle()

        report = CycleReport(
            status="committed",
            plan=plan_result,
            policy=policy_result,
            diff_text=diff_text,
            diff_stat=diff_stat,
            commits=commits,
            tag=tag_name,
            branch=target_branch,
            message="Committed grouped changes.",
            snapshot=snapshot,
        )

        if effective_mode == "push":
            report.branch = target_branch
            if ask_push is None or ask_push(report):
                pushed = self._push(report.branch)
                report.pushed = pushed
                report.status = "pushed" if pushed else "commit_only"
                report.message = "Changes pushed to remote." if pushed else "Push skipped."
            else:
                report.status = "commit_only"
                report.message = "Push canceled by user."

        self._finalize(report)
        return report

    # Internal helpers --------------------------------------------------------------

    def _commit_groups(self, plan_result: PlanResult) -> List[str]:
        """
        Create git commits for each group in the plan.
        
        Args:
            plan_result: Plan with file groups
            
        Returns:
            List of commit subject lines created
        """
        files_remaining = set(self.git.changed_files())
        commits: List[str] = []

        # Process each planned group
        for group in plan_result.groups:
            # Filter to files that still have changes
            relevant = [path for path in group.files if path in files_remaining]
            if not relevant:
                continue

            # Stage only this group's files
            self.git.reset_index()
            self.git.stage(relevant)

            # Skip if no actual diff (e.g., whitespace-only changes)
            if not self.git.diff(staged=True).strip():
                continue

            # Create commit with AI-generated or heuristic message
            message = self._format_commit_message(group.title, group.body)
            self.git.commit(message)
            commits.append(message.splitlines()[0])
            
            # Mark these files as committed
            for path in relevant:
                files_remaining.discard(path)

        # Handle any ungrouped files (safety net)
        if files_remaining:
            self.git.reset_index()
            self.git.stage(files_remaining)
            if self.git.diff(staged=True).strip():
                message = "chore: miscellaneous updates"
                self.git.commit(message)
                commits.append(message)

        return commits

    def _format_commit_message(self, title: str, body: str) -> str:
        """
        Format a commit message from title and body.
        
        Args:
            title: Commit subject line
            body: Optional commit body text
            
        Returns:
            Formatted commit message (subject + optional body)
        """
        # Ensure subject is not empty and within conventional limit
        subject = title.strip() or "chore: automated update"
        subject = subject[:72]

        # Append body if provided
        if body.strip():
            return subject + "\n\n" + body.strip()
        return subject

    def _tag_cycle(self) -> str:
        """
        Create a git tag marking this cycle.
        
        Tags use the format: solodev-YYYYMMDD-HHMMSS
        
        Returns:
            Tag name created
        """
        timestamp = now_utc().strftime("%Y%m%d-%H%M%S")
        name = f"solodev-{timestamp}"
        self.git.tag(name, message="SoloDev cycle tag")
        return name

    def _push(self, branch: str) -> bool:
        """
        Push to the remote branch.
        
        Attempts a direct push first, then tries with set-upstream if
        the branch doesn't exist on remote.
        
        Args:
            branch: Branch name to push to
            
        Returns:
            True if push succeeded, False otherwise
        """
        try:
            # Try direct push (branch exists on remote)
            self.git.push("origin", branch)
            return True
        except GitError:
            try:
                # Try with set-upstream (new branch)
                self.git.push("origin", f"HEAD:{branch}", set_upstream=True)
                return True
            except GitError:
                # Push failed (network, permissions, etc.)
                return False

    def _resolve_branch_name(self) -> str:
        """
        Resolve the configured branch pattern to an actual branch name.
        
        Replaces ${USER} placeholder with the current system username.
        
        Returns:
            Resolved branch name
        """
        branch = self.config.branch.replace("${USER}", getpass.getuser())
        return branch

    def _finalize(self, report: CycleReport) -> None:
        self._last_report = report
        record_cycle(
            {
                "status": report.status,
                "message": report.message,
                "plan_source": report.plan.source,
                "groups": [group.to_dict() for group in report.plan.groups],
                "policy": [{"severity": msg.severity, "message": msg.message} for msg in report.policy.messages],
                "commits": report.commits,
                "tag": report.tag,
                "pushed": report.pushed,
                "branch": report.branch,
                "snapshot": report.snapshot,
            }
        )
