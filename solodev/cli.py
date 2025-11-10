"""Command-line interface for the SoloDev automation tool."""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Iterable

import click

from .adapters.factory import AdapterError, build_adapter
from .audit import DEFAULT_AUDIT_FILE, find_cycle_entry, latest_entry, restore_from_snapshot
from .bootstrap import git_setup as bootstrap_git_setup
from .config import CONFIG_FILENAME, SoloDevConfig, load_config, save_config
from .cycle import CycleManager, CycleReport
from .ext_api import StatusServer, StatusStore, serve_status
from .logging import setup_logging
from .util import format_timedelta
from .watcher import CycleWatcher


def _load_manager() -> tuple[SoloDevConfig, CycleManager]:
    config = load_config()
    adapter = None
    try:
        adapter = build_adapter(config)
    except AdapterError as exc:
        click.echo(f"[warn] {exc} Falling back to heuristic planning.")
    manager = CycleManager(config=config, adapter=adapter)
    return config, manager


def _format_plan(groups) -> str:
    lines = []
    for idx, group in enumerate(groups, start=1):
        lines.append(f"{idx}. {group.title}")
        if group.body:
            lines.append(f"   {group.body}")
        for file in group.files:
            lines.append(f"      - {file}")
    return "\n".join(lines)


def _build_ask_push(config: SoloDevConfig, manager: CycleManager):
    if not config.smart_push.ask:
        return lambda report: True

    def ask(report: CycleReport) -> bool:
        branch = report.branch or manager.resolve_branch_name()
        summary = ", ".join(report.commits) if report.commits else "no commits"
        return click.confirm(
            f"Push {len(report.commits)} commit(s) ({summary}) to origin/{branch}?",
            default=True,
        )

    return ask


def _start_watcher(config: SoloDevConfig, manager: CycleManager, status_port: int) -> None:
    status_store = StatusStore()
    status_server: StatusServer = serve_status(store=status_store, port=status_port)
    watcher = CycleWatcher(
        root=Path.cwd(),
        config=config,
        manager=manager,
        status_store=status_store,
        ask_push=_build_ask_push(config, manager),
    )

    click.echo(
        f"Watcher active. Idle {format_timedelta(config.idle_duration)}. "
        f"Status API on http://127.0.0.1:{status_server.port}/status"
    )
    watcher.start()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        click.echo("\nStopping watcher…")
    finally:
        watcher.stop()
        status_server.stop()


def _print_policy(policy) -> None:
    if not policy.messages:
        click.echo("Policy checks: OK")
        return
    click.echo("Policy checks:")
    for item in policy.messages:
        click.echo(f"  [{item.severity}] {item.message}")


def _read_timeline(entries: Iterable[dict], limit: int) -> None:
    count = 0
    for entry in entries:
        click.echo(f"{entry.get('timestamp')}  {entry.get('status')}  {entry.get('message')}")
        count += 1
        if 0 < limit == count:
            break


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("-v", "--verbose", count=True, help="Increase verbosity (-v for INFO, -vv for DEBUG)")
@click.option("-q", "--quiet", is_flag=True, help="Suppress all output except errors")
@click.pass_context
def cli(ctx: click.Context, verbose: int, quiet: bool) -> None:
    """SoloDev automates planning, committing, and pushing repository changes."""
    # Store logging options in context for commands to use
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet
    
    # Setup logging
    try:
        config = load_config()
        log_level = config.log_level
    except Exception:
        log_level = "INFO"
    
    setup_logging(level=log_level, verbose=verbose, quiet=quiet)


@cli.command()
@click.option("--provider", type=click.Choice(["ollama", "openai", "anthropic", "google"]), default="ollama")
@click.option("--mode", type=click.Choice(["plan", "commit", "push"]), default="push")
@click.option("--model", default="qwen2.5-coder:14b", show_default=True)
@click.option("--smart-ask/--no-smart-ask", default=True, show_default=True)
def setup(provider: str, mode: str, model: str, smart_ask: bool) -> None:
    """Write a baseline .solodev.yml configuration."""
    config_path = Path(CONFIG_FILENAME)
    if config_path.exists() and not click.confirm(f"{CONFIG_FILENAME} exists. Overwrite?", default=False):
        click.echo("Aborted.")
        return

    data = {
        "provider": provider,
        "mode": mode,
        "model": model,
        "smart_push": {"ask": smart_ask},
    }
    config = SoloDevConfig.from_dict(data)
    save_config(config)
    click.echo(f"Saved configuration to {config_path}")


@cli.command("git-setup")
def git_setup_cmd() -> None:
    """Initialize repository defaults for SoloDev."""
    bootstrap_git_setup(Path.cwd())
    click.echo("Repository bootstrapped for SoloDev.")


@cli.command()
@click.option("--status-port", default=0, type=int, help="Expose status API on this port.")
def on(status_port: int) -> None:
    """Start the SoloDev watcher."""
    config, manager = _load_manager()
    _start_watcher(config, manager, status_port)


@cli.command()
def off() -> None:
    """Help instructions for stopping the watcher."""
    click.echo("The watcher runs in the foreground. Stop it with Ctrl+C in the running terminal.")


@cli.command()
def status() -> None:
    """Print current SoloDev status information."""
    entry = latest_entry()
    if not entry:
        click.echo("No audit entries yet.")
        return
    click.echo(f"Timestamp: {entry.get('timestamp')}")
    click.echo(f"Status:    {entry.get('status')}")
    click.echo(f"Message:   {entry.get('message')}")
    if entry.get("commits"):
        click.echo("Commits:")
        for commit in entry["commits"]:
            click.echo(f"  - {commit}")


@cli.command()
@click.option("--mode", type=click.Choice(["plan", "commit", "push"]), required=True)
def switch(mode: str) -> None:
    """Switch SoloDev operating mode."""
    config, _ = _load_manager()
    data = dict(config.raw)
    data["mode"] = mode
    save_config(SoloDevConfig.from_dict(data))
    click.echo(f"Mode updated to {mode}.")


@cli.command()
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def config(output_format: str) -> None:
    """Show current SoloDev configuration."""
    try:
        cfg = load_config()
    except Exception as exc:
        click.echo(f"Error loading configuration: {exc}", err=True)
        sys.exit(1)
    
    if output_format == "json":
        click.echo(json.dumps(cfg.raw, indent=2))
    else:
        click.echo("SoloDev Configuration:")
        click.echo(f"  Mode:              {cfg.mode}")
        click.echo(f"  Branch:            {cfg.branch}")
        click.echo(f"  Idle:              {cfg.idle}")
        click.echo(f"  Batch Window:      {cfg.batch_window}")
        click.echo(f"  Provider:          {cfg.provider}")
        click.echo(f"  Model:             {cfg.model}")
        click.echo(f"  Log Level:         {cfg.log_level}")
        click.echo(f"  Secret Scan:       {cfg.secret_scan}")
        click.echo(f"  Snapshot Max Size: {cfg.snapshot_max_size} bytes")
        click.echo("\nSmart Push:")
        click.echo(f"  Ask:               {cfg.smart_push.ask}")
        click.echo(f"  Max Diff Lines:    {cfg.smart_push.max_diff_lines}")
        click.echo(f"  Respect Protected: {cfg.smart_push.respect_protected}")
        click.echo(f"  Default Skip CI:   {cfg.smart_push.default_skip_ci}")
        if cfg.protected_branches:
            click.echo(f"\nProtected Branches: {', '.join(cfg.protected_branches)}")
        if cfg.secret_patterns:
            click.echo(f"\nCustom Secret Patterns: {len(cfg.secret_patterns)} configured")


@cli.command()
def validate() -> None:
    """Validate SoloDev configuration and environment."""
    errors = []
    warnings = []
    
    # Check configuration file
    try:
        cfg = load_config()
        click.echo("✓ Configuration file loaded successfully")
    except Exception as exc:
        errors.append(f"Configuration error: {exc}")
        click.echo(f"✗ Configuration error: {exc}", err=True)
        sys.exit(1)
    
    # Check git repository
    try:
        from .vcs import Git
        git = Git()
        git.run(["rev-parse", "--git-dir"], check=True)
        click.echo("✓ Git repository found")
    except Exception:
        errors.append("Not a git repository")
        click.echo("✗ Not a git repository", err=True)
    
    # Check provider and API key
    provider = cfg.provider.lower()
    if provider == "ollama":
        click.echo("✓ Using Ollama (local, no API key needed)")
    elif provider == "openai":
        from .util import env_first
        api_key = env_first("OPENAI_API_KEY")
        if api_key:
            click.echo("✓ OPENAI_API_KEY is set")
        else:
            warnings.append("OPENAI_API_KEY not set - will fall back to heuristic grouping")
            click.echo("⚠ OPENAI_API_KEY not set", err=True)
    elif provider == "anthropic":
        from .util import env_first
        api_key = env_first("ANTHROPIC_API_KEY")
        if api_key:
            click.echo("✓ ANTHROPIC_API_KEY is set")
        else:
            warnings.append("ANTHROPIC_API_KEY not set - will fall back to heuristic grouping")
            click.echo("⚠ ANTHROPIC_API_KEY not set", err=True)
    elif provider == "google":
        from .util import env_first
        api_key = env_first("GOOGLE_API_KEY")
        if api_key:
            click.echo("✓ GOOGLE_API_KEY is set")
        else:
            warnings.append("GOOGLE_API_KEY not set - will fall back to heuristic grouping")
            click.echo("⚠ GOOGLE_API_KEY not set", err=True)
    
    # Test adapter connectivity
    if provider != "ollama":
        try:
            adapter = build_adapter(cfg)
            click.echo(f"✓ {provider.title()} adapter initialized")
        except AdapterError as exc:
            warnings.append(f"Adapter error: {exc}")
            click.echo(f"⚠ Adapter error: {exc}", err=True)
    
    # Check mode validity
    if cfg.mode in ["plan", "commit", "push"]:
        click.echo(f"✓ Mode '{cfg.mode}' is valid")
    else:
        errors.append(f"Invalid mode: {cfg.mode}")
        click.echo(f"✗ Invalid mode: {cfg.mode}", err=True)
    
    # Summary
    click.echo("\n" + "=" * 50)
    if errors:
        click.echo(f"Validation failed with {len(errors)} error(s)")
        sys.exit(1)
    elif warnings:
        click.echo(f"Validation passed with {len(warnings)} warning(s)")
    else:
        click.echo("✓ All validations passed")



@cli.command("plan-now")
@click.option("--dry-run", is_flag=True, help="Show what would be planned without making changes.")
def plan_now(dry_run: bool) -> None:
    """Trigger a plan cycle immediately."""
    config, manager = _load_manager()
    
    if dry_run:
        click.echo("[DRY RUN] Planning cycle (no changes will be made)")
        
    report = manager.execute(mode="plan")
    if report.status == "no_changes":
        click.echo("No changes detected.")
        return
    click.echo(_format_plan(report.plan.groups))
    _print_policy(report.policy)
    
    if dry_run:
        click.echo("\n[DRY RUN] No changes were made")


@cli.command("push-now")
@click.option("--dry-run", is_flag=True, help="Show what would be done without making changes.")
def push_now(dry_run: bool) -> None:
    """Trigger a push cycle immediately."""
    config, manager = _load_manager()
    
    if dry_run:
        click.echo("[DRY RUN] Push cycle (no changes will be made)")
        # In dry-run mode, we only execute in plan mode to show what would happen
        report = manager.execute(mode="plan")
        if report.status == "no_changes":
            click.echo("No changes detected.")
            return
        click.echo("\nProposed groups:")
        click.echo(_format_plan(report.plan.groups))
        _print_policy(report.policy)
        click.echo(f"\n[DRY RUN] Would create {len(report.plan.groups)} commit(s)")
        if config.mode == "push":
            branch = manager.resolve_branch_name()
            click.echo(f"[DRY RUN] Would push to origin/{branch}")
        click.echo("\n[DRY RUN] No changes were made")
        return
        
    report = manager.execute(mode="push", ask_push=_build_ask_push(config, manager))
    click.echo(report.message)
    if report.status == "no_changes":
        return
    if report.commits:
        click.echo("Commits:")
        for commit in report.commits:
            click.echo(f"  - {commit}")
    _print_policy(report.policy)


@cli.command()
@click.option("--limit", default=10, show_default=True, help="Number of entries to show.")
def timeline(limit: int) -> None:
    """Show the SoloDev timeline."""
    if not DEFAULT_AUDIT_FILE.exists():
        click.echo("No audit log yet.")
        return
    entries = (json.loads(line) for line in DEFAULT_AUDIT_FILE.read_text().splitlines() if line)
    _read_timeline(entries, limit)


@cli.command()
@click.argument("cycle")
def commits(cycle: str) -> None:
    """Show commits for a given cycle."""
    entry = find_cycle_entry(cycle)
    if not entry:
        click.echo(f"Cycle {cycle} not found.")
        return
    for commit in entry.get("commits", []):
        click.echo(f"- {commit}")


@cli.command()
@click.argument("cycle")
def show(cycle: str) -> None:
    """Show summary for a given cycle."""
    entry = find_cycle_entry(cycle)
    if not entry:
        click.echo(f"Cycle {cycle} not found.")
        return
    click.echo(json.dumps(entry, indent=2))


@cli.command()
@click.argument("cycle_id")
@click.option("--dry-run", is_flag=True, help="Show what would be undone without applying changes.")
def undo(cycle_id: str, dry_run: bool) -> None:
    """Undo a cycle by restoring files from the snapshot."""
    entry = find_cycle_entry(cycle_id)
    if not entry:
        click.echo(f"Cycle {cycle_id} not found.", err=True)
        sys.exit(1)
        
    snapshot = entry.get("snapshot")
    if not snapshot:
        click.echo(f"No snapshot found for cycle {cycle_id}. Snapshots are only available for recent cycles.", err=True)
        sys.exit(1)
        
    if dry_run:
        click.echo(f"Would restore {len(snapshot)} file(s) from cycle {cycle_id}:")
        for file_path in snapshot.keys():
            click.echo(f"  - {file_path}")
        return
        
    # Confirm before proceeding
    if not click.confirm(
        f"This will overwrite {len(snapshot)} file(s) in your working directory. Continue?",
        default=False,
    ):
        click.echo("Undo canceled.")
        return
        
    restored = restore_from_snapshot(snapshot, dry_run=False)
    click.echo(f"Restored {len(restored)} file(s) from cycle {cycle_id}:")
    for file_path in restored:
        click.echo(f"  - {file_path}")


@cli.command()
@click.argument("file_path")
@click.option("--at", "cycle_id", required=True, help="Cycle identifier to restore from.")
@click.option("--dry-run", is_flag=True, help="Show what would be restored without applying changes.")
def restore(file_path: str, cycle_id: str, dry_run: bool) -> None:
    """Restore a single file from a previous cycle snapshot."""
    entry = find_cycle_entry(cycle_id)
    if not entry:
        click.echo(f"Cycle {cycle_id} not found.", err=True)
        sys.exit(1)
        
    snapshot = entry.get("snapshot")
    if not snapshot:
        click.echo(f"No snapshot found for cycle {cycle_id}. Snapshots are only available for recent cycles.", err=True)
        sys.exit(1)
        
    if file_path not in snapshot:
        click.echo(f"File {file_path} not found in cycle {cycle_id} snapshot.", err=True)
        available = ", ".join(snapshot.keys())
        click.echo(f"Available files: {available}")
        sys.exit(1)
        
    if dry_run:
        click.echo(f"Would restore {file_path} from cycle {cycle_id}")
        return
        
    # Confirm before proceeding
    if not click.confirm(
        f"This will overwrite {file_path} in your working directory. Continue?",
        default=False,
    ):
        click.echo("Restore canceled.")
        return
        
    restored = restore_from_snapshot(snapshot, files=[file_path], dry_run=False)
    if restored:
        click.echo(f"Restored {file_path} from cycle {cycle_id}")
    else:
        click.echo(f"Failed to restore {file_path}", err=True)
        sys.exit(1)


def main() -> None:
    """Console script entry point."""
    try:
        cli(obj={})
    except KeyboardInterrupt:
        sys.exit(1)


if __name__ == "__main__":
    main()
