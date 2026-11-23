# Contributing to PanelPro

Thanks for considering a contribution!

## Ground rules

1. **Original code only.** Do not copy code, assets, or text from other
   control panels or closed sources. Everything in this repo must stay
   original and MIT-licensed.
2. Keep the module structure: OS work belongs in `services/`, HTTP in
   `api/`, shared logic in `core/`, config rendering in `templates/`.
3. Python 3.10+, type hints, `ruff check panelpro` must pass.
4. Add/adjust tests for pure-Python changes (`tests/`); OS-specific code
   paths should degrade gracefully and be skip-gated in tests.
5. Frontend changes: no build step — plain JS on the `PP.*` namespace,
   follow the existing CSS design system, keep i18n keys updated in
   `web/assets/js/i18n.js` for both `id` and `en`.

## Workflow

```bash
fork → branch (feat/… or fix/…) → commit → pull request
```

Run before submitting:

```bash
pytest
ruff check panelpro
python -m compileall panelpro
```

## Reporting issues

Include: OS/distro, how the panel was installed, `panelpro doctor` output,
and the relevant lines from `journalctl -u panelpro` or the panel log.
Never paste credentials or secret keys.
