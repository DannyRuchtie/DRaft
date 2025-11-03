# DRaft CLI

DRaft keeps your repository history tidy by automatically grouping changes, preparing commit messages, and coordinating safe pushes. It is designed to feel like autosave for git while staying transparent and asking before it pushes.

## Status

This repository currently contains the project scaffolding, initial configuration helpers, and placeholder modules for future functionality. Core automation, grouping, policy checks, and provider integrations are still under development.

## Local Development

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Once installed you can confirm the CLI is wired up:

```bash
draft --help
```

## Planned Features

- Watch repository changes and group them into logical cycles.
- Generate commit plans with local or cloud-hosted LLMs.
- Enforce policy checks, secret scanning, and diff size guards.
- Offer an interactive push confirmation flow.
- Maintain an audit trail and expose a lightweight status API for editor integrations.
