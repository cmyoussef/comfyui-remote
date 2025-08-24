# Layered Config (ComfyUI Remote + ComfyUI)

## Controller
`default.json` defines two stacks:

- **layers**: JSON files merged into the **ComfyUI Remote** config (server, env, paths).  
  *I/O is intentionally not here anymore.*
- **yaml_layers**: YAML files merged into **ComfyUI** config (model paths + **io**).

Tokens:
- `${PKG}` → package root (`.../src/comfyui_remote`)
- `${OS}` → `windows|linux|darwin`
- `${HOME}` → user home
- `${ENV:FOO}` or `${FOO}` → env var `FOO`

## Merge Semantics
- **JSON**: deep merge; scalars/lists last‑wins; dicts recurse.
- **YAML**:
  - `comfyui` categories & `custom_nodes`: union + dedup (order preserved).
  - `io`: last‑wins by field.
  - other keys: last‑wins.

## Runtime
- YAML stack is written to a temp file and passed to Comfy via `--extra-model-paths-config`.
- I/O (input/output/temp/user) is sourced from **YAML io** and also passed as CLI flags.
- CLI args supplied to `server start` / `run` still override at the very end.
