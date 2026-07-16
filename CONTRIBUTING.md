# Contributing

Thanks for helping improve Museon CLI.

## Set up

Museon CLI uses Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Museon-AI/museon-cli.git
cd museon-cli
uv sync --frozen --all-groups
```

## Before opening a pull request

```bash
uv run ruff check .
uv run pytest -q
uv run python scripts/gen_command_docs.py --check
uv run python scripts/gen_command_contract.py --check
uv build
```

When adding or changing a command:

1. Keep its definition in the appropriate module under `museoncli/domains/`.
2. Declare its input and output schema, risk level, execution mode, and examples.
3. Add focused parser, payload, execution, and workspace-scope tests.
4. Regenerate both generated artifacts:

   ```bash
   uv run python scripts/gen_command_docs.py
   uv run python scripts/gen_command_contract.py
   ```

5. Do not add Museon service credentials, private host prompts, customer data,
   internal runbooks, or server implementation code to this repository.

## Pull requests

Keep changes focused and explain the user-visible behavior. Include tests for a
behavior change. Breaking command-contract changes must call out migration
impact and should be released with an appropriate version bump.
