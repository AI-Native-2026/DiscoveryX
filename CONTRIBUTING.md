# Contributing to DiscoveryX

Thanks for your interest! DiscoveryX is an enterprise-grade open-source project;
contributions of all kinds are welcome.

## Development setup

```bash
git clone <repo> && cd discoveryx
cp .env.example .env            # add DEEPSEEK_API_KEY for LLM-backed paths

# backend
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt

# frontend
cd ../frontend && npm install
```

## Quality gates

All pull requests must pass:

```bash
cd backend && ruff check . && pytest -q
cd frontend && npm run build
```

## Conventions

* **Type hints everywhere**; Pydantic models for all I/O.
* **Docstrings** on modules, public classes and functions.
* **No mock data** — new features must integrate real sources (PDB, MoleculeNet,
  PMC, ChEMBL) or clearly documented heuristics.
* **Security first** — any new outbound call that can carry sensitive content
  must go through `app.core.guardrails.Guardrails.check_outbound`.
* **Structured logging** — use `app.core.logging.get_logger` and include a
  `trace_id`; never log secrets.
* Keep the core (`app/core`) free of web-framework imports.

## Adding a new agent node

1. Add the node function in `app/core/agent_graph.py` (async, returns a partial
   state dict).
2. Register it in the `StateGraph` and wire the edges.
3. If it calls the LLM, pass `principal=` and `guard=` so DLP and metering apply.
4. Add a test under `backend/tests/`.

## Adding a new data source

1. Create a client in `app/core/datasources/` using `httpx`, with caching and
   clear error handling (`ExternalServiceError`).
2. Register it in `data/download_data.py` so it is reproducible.
3. Document the source and license in the README.

## Commit style

Short imperative subject lines, e.g. `add PMC rate limiting`, `fix RBAC
clearance check for datasets`.

## Reporting security issues

Please do **not** open a public issue for security problems. Contact the
maintainers privately.
