# DRaft CLI

**DRaft keeps your repository history tidy by automatically grouping changes, preparing commit messages, and coordinating safe pushes.** It feels like autosave for git: the watcher batches edits, runs policy checks, commits with AI-assisted context, and—when allowed—asks before pushing.

---

## Quick Start

### Installation

```bash
# Clone or navigate to your project directory
cd your-project

# Create and activate a Python virtual environment
python3.10 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install DRaft
pip install -e path/to/draft

# Verify installation
draft --help
```

### 5-Minute Setup

```bash
# 1. Initialize git repository (if needed) and create .gitignore
draft git-setup

# 2. Configure DRaft with your preferred AI provider
draft setup --provider ollama --model qwen2.5-coder:14b --mode push

# 3. Start the watcher
draft on

# That's it! DRaft is now watching for changes.
```

---

## Initial Setup

### Step 1: Bootstrap Your Repository

The `git-setup` command initializes a git repository (if one doesn't exist) and creates a sensible `.gitignore`:

```bash
draft git-setup
```

This creates:
- `.git/` directory (if needed)
- `.gitignore` with common exclusions (`__pycache__/`, `.venv/`, `draft_audit.jsonl`)

### Step 2: Configure DRaft

Create a `.draft.yml` configuration file:

```bash
draft setup --provider ollama --model qwen2.5-coder:14b --mode push
```

**Configuration Options:**

| Option | Choices | Default | Description |
|--------|---------|---------|-------------|
| `--provider` | `ollama`, `openai`, `anthropic`, `google` | `ollama` | AI provider for commit grouping |
| `--model` | Provider-specific | `qwen2.5-coder:14b` | Model name |
| `--mode` | `plan`, `commit`, `push` | `push` | Default operation mode |
| `--smart-ask` / `--no-smart-ask` | boolean | `True` | Prompt before pushing |

**Example configurations:**

```bash
# Local Ollama (no API key needed)
draft setup --provider ollama --model qwen2.5-coder:14b --mode push

# OpenAI GPT-4
export OPENAI_API_KEY="sk-..."
draft setup --provider openai --model gpt-4 --mode push

# Anthropic Claude
export ANTHROPIC_API_KEY="sk-ant-..."
draft setup --provider anthropic --model claude-3-5-sonnet-20241022 --mode commit

# Google Gemini
export GOOGLE_API_KEY="..."
draft setup --provider google --model gemini-1.5-pro --mode plan
```

### Step 3: API Keys (Cloud Providers Only)

For cloud-based AI providers, set the appropriate environment variable:

```bash
# OpenAI
export OPENAI_API_KEY="sk-..."

# Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

# Google
export GOOGLE_API_KEY="..."
```

Add these to your shell profile (`~/.bashrc`, `~/.zshrc`) to persist them across sessions.

**Note:** If an API key is missing, DRaft gracefully falls back to heuristic grouping (no AI assistance).

---

## How It Works

### The DRaft Cycle

DRaft operates in **cycles**. Each cycle:

1. **Detects changes** in your working directory
2. **Groups files** logically (using heuristics + optional AI refinement)
3. **Runs policy checks** (secret scanning, diff size limits)
4. **Creates commits** (one per group) with meaningful messages
5. **Optionally pushes** to a remote branch (with confirmation)
6. **Records everything** in an audit log (`draft_audit.jsonl`)

### Operating Modes

DRaft has three modes that control how far each cycle goes:

| Mode | Behavior | Use Case |
|------|----------|----------|
| **`plan`** | Groups files and shows the plan, but doesn't commit | Review groupings before committing manually |
| **`commit`** | Creates commits locally but never pushes | Keep work local until you're ready |
| **`push`** | Commits and pushes to remote (with optional confirmation) | Hands-off autosave with remote backup |

Switch modes anytime:

```bash
draft switch --mode commit
```

### The Watcher

The watcher is a background process that monitors your repository for file changes:

```bash
draft on --status-port 8765
```

**How it works:**
1. Watches for file modifications (ignores `.git/` automatically)
2. Waits for an **idle window** (default: 30 seconds of no changes)
3. Waits for a **batch window** (default: 5 minutes between cycles)
4. Triggers a cycle when both conditions are met

**Stop the watcher:** Press `Ctrl+C` in the terminal where it's running.

### AI-Assisted Grouping

When an AI provider is configured, DRaft:
1. Starts with **heuristic groups** (by directory, file type, tests vs code)
2. Sends the file list and heuristic plan to the AI
3. Receives **refined groups** with better commit messages
4. Falls back to heuristics if AI is unavailable

**Heuristic-only mode** works offline without any API keys.

---

## Core Commands

### Watcher Commands

#### `draft on`
Start the file watcher in the current directory.

```bash
draft on                    # Start with auto-assigned port
draft on --status-port 8765 # Start with specific port for status API
```

The watcher exposes a JSON status endpoint at `http://127.0.0.1:<port>/status` for editor integrations.

#### `draft off`
Shows instructions for stopping the watcher (it runs in the foreground, so just press `Ctrl+C`).

```bash
draft off
```

### Manual Cycle Triggers

#### `draft plan-now`
Run a plan cycle immediately without committing.

```bash
draft plan-now              # Show grouped changes
draft plan-now --dry-run    # Show what would be planned (non-destructive)
```

**Output example:**
```
1. Backend Changes
   Updates to API handlers
      - backend/api/users.py
      - backend/api/auth.py

2. Test Updates
      - tests/test_users.py

Policy checks: OK
```

#### `draft push-now`
Run a full cycle: plan, commit, and (optionally) push.

```bash
draft push-now              # Run full cycle with push confirmation
draft push-now --dry-run    # Show what would happen without doing it
```

If `smart_push.ask` is enabled (default), you'll be prompted:

```
Push 2 commit(s) (Backend Changes, Test Updates) to origin/auto/yourusername?
[Y/n]:
```

### Status & History

#### `draft status`
Show the most recent cycle's status.

```bash
draft status
```

**Output:**
```
Timestamp: 2025-11-01T14:23:45.123456+00:00
Status:    pushed
Message:   Changes pushed to remote.
Commits:
  - Backend Changes
  - Test Updates
```

#### `draft timeline`
List recent cycles from the audit log.

```bash
draft timeline              # Show last 10 cycles
draft timeline --limit 25   # Show last 25 cycles
```

**Output:**
```
2025-11-01T14:23:45  pushed      Changes pushed to remote.
2025-11-01T13:15:22  committed   Committed grouped changes.
2025-11-01T12:05:10  blocked     Policy checks failed.
```

#### `draft show <cycle>`
Display full details for a specific cycle.

```bash
draft show draft-20251101-142345       # By tag
draft show 2025-11-01T14:23:45.123456  # By timestamp
```

Outputs the complete JSON record including groups, policy results, and commits.

#### `draft commits <cycle>`
List commits created during a specific cycle.

```bash
draft commits draft-20251101-142345
```

### Undo & Restore

#### `draft undo <cycle>`
Revert your working directory to the state before a cycle ran.

```bash
draft undo draft-20251101-142345       # Undo a cycle
draft undo draft-20251101-142345 --dry-run  # Preview what would be undone
```

**How it works:** DRaft stores snapshots of file contents before each cycle. Undo restores those snapshots.

**Warning:** This overwrites current working directory files. Commit or stash uncommitted changes first.

#### `draft restore <file> --at <cycle>`
Restore a single file from a previous cycle.

```bash
draft restore backend/api/users.py --at draft-20251101-142345
draft restore backend/api/users.py --at draft-20251101-142345 --dry-run
```

Useful for recovering accidentally deleted or modified files.

### Configuration Management

#### `draft switch --mode <mode>`
Change the default operating mode.

```bash
draft switch --mode plan    # Switch to plan-only mode
draft switch --mode commit  # Switch to commit-only mode
draft switch --mode push    # Switch to full push mode
```

Updates `.draft.yml` persistently.

#### `draft config`
Display the current configuration.

```bash
draft config
```

Shows the merged configuration (defaults + `.draft.yml` overrides).

#### `draft validate`
Validate configuration and check environment.

```bash
draft validate
```

Checks:
- `.draft.yml` syntax and values
- Git repository status
- API key availability (for cloud providers)
- AI provider connectivity

---

## Workflows & Recipes

### Workflow 1: Plan-First Development

**Scenario:** You want to review groupings before committing.

```bash
# Set mode to plan-only
draft switch --mode plan

# Start the watcher
draft on

# Edit files as usual...

# Check the plan via status
draft status

# When satisfied, commit manually
git add .
git commit -m "Your message"
```

**Pro tip:** Use the status API endpoint to display the plan in your editor.

### Workflow 2: Safe Local Commits

**Scenario:** Keep commits local until explicitly pushing.

```bash
# Set mode to commit-only
draft switch --mode commit

# Start the watcher
draft on

# DRaft will commit changes but never push
# Push manually when ready:
git push origin main
```

### Workflow 3: Hands-Off Autosave

**Scenario:** Fully automated with confirmation before push.

```bash
# Set mode to push with smart-ask enabled (default)
draft switch --mode push

# Start the watcher
draft on

# DRaft commits and asks before pushing:
# "Push 2 commit(s) to origin/auto/yourusername? [Y/n]:"
```

Pushes go to `origin/auto/$USER` by default (configurable).

### Workflow 4: Offline Development

**Scenario:** Working without internet or AI access.

```bash
# Configure with Ollama (local) or no provider
draft setup --provider ollama --model qwen2.5-coder:14b --mode commit

# Or just don't set API keys for cloud providers
# DRaft falls back to heuristic grouping automatically
```

### Workflow 5: Manual Triggers Only

**Scenario:** No watcher, manual control.

```bash
# Don't run 'draft on'
# Instead, trigger cycles manually when ready:

draft plan-now   # Review groupings
draft push-now   # Commit and push
```

---

## Configuration Reference

DRaft reads configuration from `.draft.yml` in your repository root. All settings are optional—defaults are used when not specified.

### Complete `.draft.yml` Example

```yaml
# Operating mode: plan, commit, or push
mode: push

# Remote branch pattern (${USER} replaced with username)
branch: auto/${USER}

# Idle duration before triggering a cycle
idle: 30s

# Minimum time between cycles
batch_window: 5m

# Enable secret scanning
secret_scan: true

# CI behavior: skip, run, or default
ci_default: skip

# Smart push settings
smart_push:
  ask: true                    # Prompt before pushing
  max_diff_lines: 1000         # Block commits exceeding this line count
  respect_protected: true      # Don't push to protected branches
  default_skip_ci: true        # Add [skip ci] to commit messages

# AI provider configuration
provider: ollama               # ollama, openai, anthropic, google
model: qwen2.5-coder:14b       # Provider-specific model name

# Logging level (DEBUG, INFO, WARNING, ERROR)
log_level: INFO

# Snapshot size limit for undo/restore (bytes)
snapshot_max_size: 10485760    # 10 MB per file

# Custom secret patterns (regex)
secret_patterns:
  - 'password\s*=\s*["\'][^"\']{8,}["\']'
  - 'secret_key\s*=\s*["\'][^"\']{16,}["\']'

# Protected branches (don't auto-push to these)
protected_branches:
  - main
  - master
  - production
```

### Duration Format

Use `s` (seconds), `m` (minutes), `h` (hours), or `d` (days):

```yaml
idle: 30s         # 30 seconds
batch_window: 5m  # 5 minutes
timeout: 2h       # 2 hours
retention: 7d     # 7 days
```

### Environment Variables

These override file-based configuration:

- `DRAFT_MODE` - Operating mode
- `DRAFT_PROVIDER` - AI provider
- `DRAFT_MODEL` - Model name
- `OPENAI_API_KEY` - OpenAI API key
- `ANTHROPIC_API_KEY` - Anthropic API key
- `GOOGLE_API_KEY` - Google API key

---

## Safety & Policy

DRaft includes built-in safety checks that run before every commit.

### Secret Scanning

DRaft scans diffs for common secret patterns:

- API keys (`api_key`, `apikey`, `api-key`)
- Tokens (`token`, `auth_token`)
- AWS access keys (`AKIA...`)
- Generic secrets (`secret`, `password` in assignments)

**Customize patterns** in `.draft.yml`:

```yaml
secret_patterns:
  - 'MY_SECRET\s*=\s*["\'][^"\']{8,}["\']'
  - 'custom_pattern_here'
```

**If secrets are detected:** The cycle is blocked, no commits are made, and details are logged in the audit trail.

### Diff Size Limits

Large diffs are risky and hard to review. DRaft blocks commits exceeding the configured limit:

```yaml
smart_push:
  max_diff_lines: 1000  # Block if diff exceeds 1000 lines
```

**Override** by splitting work into smaller changes or temporarily adjusting the limit.

### Protected Branches

Prevent accidental pushes to important branches:

```yaml
protected_branches:
  - main
  - master
  - production
```

DRaft will commit locally but skip pushing if the resolved branch is protected.

### Audit Trail

Every cycle is logged to `draft_audit.jsonl`:

```json
{
  "timestamp": "2025-11-01T14:23:45.123456+00:00",
  "status": "pushed",
  "message": "Changes pushed to remote.",
  "plan_source": "llm",
  "groups": [...],
  "policy": [],
  "commits": ["Backend Changes", "Test Updates"],
  "tag": "draft-20251101-142345",
  "pushed": true,
  "branch": "auto/danny"
}
```

The audit log:
- Tracks all cycle activity (success, failure, policy blocks)
- Stores file snapshots for undo/restore
- Provides a timeline of repository automation

**Never commit this file:** It's excluded in the default `.gitignore`.

---

## Advanced Features

### Dry-Run Mode

Preview what a command would do without making changes:

```bash
draft plan-now --dry-run
draft push-now --dry-run
draft undo draft-20251101-142345 --dry-run
draft restore file.py --at draft-20251101-142345 --dry-run
```

Dry-run mode:
- Shows grouped files
- Reports policy check results
- Displays commit messages that would be created
- Shows files that would be restored
- Makes **zero** modifications to git or the filesystem

### Verbose Logging

Control output verbosity:

```bash
draft on -v                 # Verbose mode (detailed logs)
draft on -vv                # Very verbose (debug level)
draft on --quiet            # Quiet mode (errors only)
```

Set default level in `.draft.yml`:

```yaml
log_level: DEBUG  # DEBUG, INFO, WARNING, ERROR
```

### Status API for Editor Integration

The watcher exposes a JSON HTTP endpoint:

```bash
draft on --status-port 8765
```

**Endpoint:** `GET http://127.0.0.1:8765/status`

**Response:**
```json
{
  "status": "pushed",
  "message": "Changes pushed to remote.",
  "commits": ["Backend Changes", "Test Updates"],
  "tag": "draft-20251101-142345",
  "pushed": true,
  "branch": "auto/danny",
  "plan_source": "llm",
  "groups": [...],
  "policy": []
}
```

Use this to:
- Show DRaft status in your editor's status bar
- Display recent commit groups in a sidebar
- Trigger notifications on cycle completion

### Custom Branch Naming

Customize the push target branch:

```yaml
branch: feature/${USER}/auto
branch: wip/${USER}
branch: auto-save
```

The `${USER}` placeholder is replaced with your system username.

### Skip CI on Commits

Prevent CI from running on automated commits:

```yaml
smart_push:
  default_skip_ci: true
```

Appends `[skip ci]` to commit messages (works with most CI systems).

---

## Architecture

### Component Overview

DRaft is organized into modular components:

```
draft/
├── cli.py           # Command-line interface (Click)
├── config.py        # Configuration loading and validation
├── cycle.py         # Core orchestration (plan → policy → commit → push)
├── plan.py          # LLM-assisted planning
├── group.py         # Heuristic file grouping
├── policy.py        # Safety checks (secrets, diff limits)
├── vcs.py           # Git wrapper (subprocess-based)
├── audit.py         # Audit logging and snapshots
├── watcher.py       # Filesystem watcher (watchdog)
├── ext_api.py       # Status HTTP server
├── bootstrap.py     # Repository initialization
├── util.py          # Shared utilities
├── logging.py       # Centralized logging setup
└── adapters/
    ├── __init__.py      # Adapter protocol
    ├── factory.py       # Adapter factory
    ├── ollama.py        # Ollama adapter
    ├── openai.py        # OpenAI adapter
    ├── anthropic.py     # Anthropic adapter
    └── google.py        # Google adapter
```

### Extending with Custom Adapters

Add a new AI provider:

1. **Create an adapter** in `draft/adapters/yourprovider.py`:

```python
from . import Adapter, AdapterError, LLMRequest

class YourProviderAdapter(Adapter):
    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self.api_key = api_key

    def generate(self, request: LLMRequest) -> str:
        # Call your provider's API
        # Return the response text
        pass
```

2. **Register in factory** (`draft/adapters/factory.py`):

```python
from .yourprovider import YourProviderAdapter

def build_adapter(config: DraftConfig) -> Adapter:
    # ...
    if provider == "yourprovider":
        api_key = env_first("YOURPROVIDER_API_KEY")
        if not api_key:
            raise AdapterError("YOURPROVIDER_API_KEY is not set.")
        return YourProviderAdapter(model=config.model, api_key=api_key)
```

3. **Update CLI choices** in `cli.py`:

```python
@click.option("--provider", type=click.Choice([
    "ollama", "openai", "anthropic", "google", "yourprovider"
]), default="ollama")
```

### The Cycle Pipeline

Each cycle follows this flow:

1. **Detect changes** (`Git.changed_files()`)
2. **Build plan** (`PlanGenerator.build_plan()`)
   - Start with heuristics (`heuristic_groups()`)
   - Optionally refine with LLM (`Adapter.generate()`)
3. **Run policy checks** (`run_checks()`)
   - Secret scanning
   - Diff size limits
   - Protected branch checks
4. **Commit groups** (if policy passes)
   - Stage files per group
   - Create commits with AI-generated messages
   - Tag cycle for reference
5. **Push** (if mode is `push` and user confirms)
6. **Record audit entry** (`record_cycle()`)

### Testing & Development

**Run DRaft in development:**

```bash
# Install in editable mode
pip install -e .

# Run with verbose logging
draft on -vv

# Test without side effects
draft plan-now --dry-run
```

**Key files for debugging:**
- `draft_audit.jsonl` - Full cycle history
- `.draft.yml` - Current configuration
- Git reflog - Commit and tag history

---

## Troubleshooting

### Common Issues

#### "No module named 'draft'"

**Solution:** Install DRaft in editable mode:

```bash
pip install -e /path/to/draft
```

Verify with `draft --help`.

#### "OPENAI_API_KEY is not set"

**Solution:** Export the API key:

```bash
export OPENAI_API_KEY="sk-..."
```

Or switch to Ollama (local, no key needed):

```bash
draft setup --provider ollama --model qwen2.5-coder:14b
```

#### Watcher not triggering cycles

**Possible causes:**
1. **Idle timeout not elapsed** - Wait 30s after last file change (default)
2. **Batch window active** - Only one cycle per 5 minutes (default)
3. **No git changes detected** - DRaft only triggers when `git status` shows changes

**Debug:**

```bash
draft on -vv  # Verbose mode shows watcher activity
```

#### Policy check blocked my cycle

**Secret detected:**

```
Policy checks:
  [error] Secret pattern match (api_key): api_key="abc123..."
```

**Solution:** Remove or redact the secret, commit manually, then re-run.

**Diff too large:**

```
Policy checks:
  [error] Diff adds/removes 1234 lines (limit 1000).
```

**Solution:**
- Split changes into smaller commits
- Temporarily increase limit in `.draft.yml`:

```yaml
smart_push:
  max_diff_lines: 2000
```

#### "No changes detected" but I have uncommitted changes

DRaft only sees changes in the git working tree. Check:

```bash
git status
```

If files are gitignored, they won't appear in DRaft cycles.

#### Undo fails with "Snapshot not found"

Undo only works for cycles created after implementing the snapshot feature. Older cycles don't have snapshots stored.

**Solution:** Use git directly:

```bash
git reflog           # Find the commit before the cycle
git reset --hard <commit>
```

### Debug Commands

```bash
# Check configuration
draft config

# Validate environment
draft validate

# View audit log
cat draft_audit.jsonl | jq

# Check watcher status
curl http://127.0.0.1:8765/status | jq

# Git status
git status
git log --oneline -10
```

### Getting Help

1. **Check logs:** Run with `-vv` for detailed output
2. **Review audit log:** `draft timeline` shows recent activity
3. **Test in isolation:** Use `--dry-run` flags to debug without side effects
4. **Inspect git state:** `git status`, `git log`, `git reflog`

---

## Contributing & License

DRaft is an automation tool designed to make git workflows effortless. Contributions, bug reports, and feature requests are welcome!

**License:** MIT
