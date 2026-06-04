# sofunny-character-gif Skill Package

This repository is a complete snapshot of the local Codex skill:

`sofunny-character-gif`

It includes:

- `SKILL.md`
- `references/`
- `scripts/`
- `scripts/sofunny_anim/`
- `profiles/`
- `agents/`
- `regression_cases/`
- current generated audit/regression reports
- dependency and install notes

## Install

Clone this repository, then copy or symlink it into a Codex skill root:

```bash
mkdir -p ~/.codex/skills
ln -s "$(pwd)" ~/.codex/skills/sofunny-character-gif
```

Or use it directly from this repository:

```bash
python3 scripts/quick_validate_skill.py
python3 scripts/run_regression_suite.py
```

## Python Dependencies

Use Python 3.10+.

Install runtime dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Core dependencies:

- Pillow
- numpy
- scikit-image

Most scripts otherwise use only the Python standard library.

## Validation

Run:

```bash
python3 scripts/quick_validate_skill.py
python3 scripts/validate_profile.py --profile sofunny
python3 scripts/run_regression_suite.py
```

Expected current result:

```text
run_regression_suite.py -> pass
```

## Notes For Engineers

This is the full skill package, not a minimized bug repro.

The package intentionally includes the current regression cases and references because they are part of the skill contract. Generated `regression_report.*` and `admission_enforcement_audit.*` are included as current evidence snapshots.

Provider execution may require external tools or environment variables, for example `OPENAI_API_KEY` for the optional `execute_provider_packet.py` path. No secrets are included in this repository.

