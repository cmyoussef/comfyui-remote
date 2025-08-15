````md
## Running tests

This repo ships with a layered test suite:

- **Unit tests**: fast, mocked.
- **Steps**: incremental bring-up (server, ws, compile, submit).
- **E2E** (optional): full end-to-end with a real ComfyUI.

Quick start:

```bash
# Unit tests only
pytest -q tests/unit

# Step-by-step (run a single step)
python tests/steps/test_01_server.py

# All steps
pytest -q tests/steps
````

For full instructions (environment variables, PyCharm tips, troubleshooting), see
[`tests/README.md`](tests/README.md).

````

---

# Draft 2 — `tests/README.md` (detailed)

```md
# Tests for comfyui-remote

This suite is organized to help you **bring the system up gradually** and then keep it stable.

````

tests/\
├─ pytest.ini\
├─ utils/\
│  └─ bootstrap.py          # path/env helpers used by all tests\
├─ resources/\
│  └─ workflows/            # sample workflows used by tests\
│     ├─ txt2img.json\
│     ├─ img2img.json\
│     └─ zdepth.json\
├─ steps/                   # incremental integration checkpoints\
│  ├─ test\_01\_server.py     # start/stop ComfyUI; healthcheck\
│  ├─ test\_02\_connect\_ws.py # open/close WebSocket\
│  ├─ test\_03\_post\_prompt.py# POST minimal prompt; subscribe\
│  ├─ test\_04\_load\_workflow\.py\
│  ├─ test\_05\_update\_params.py\
│  ├─ test\_06\_compile\_payload.py\
│  ├─ test\_07\_submit\_local.py\
│  ├─ test\_08\_remote\_executor.py (optional)\
│  ├─ test\_09\_workflow\_manager\_local.py\
│  └─ test\_10\_cli\_and\_validate.py\
└─ unit/                    # fast, mocked, regression-safe\
├─ test\_00\_graph\_compiler.py\
├─ test\_01\_rest\_client.py\
├─ test\_02\_ws\_client.py\
├─ test\_03\_connector\_flow\.py\
├─ test\_04\_workflow\_loader\_params.py\
└─ test\_05\_validation\_output\_handler.py

````

> All tests are standard `unittest` files with a `__main__` runner.
> You can:
> - **Run one file**: `python tests/steps/test_01_server.py`
> - **Run in PyCharm**: right-click the test method/file → *Run…*
> - **Run with pytest**: `pytest -q tests/steps`

---

## Environments & prerequisites

- Python 3.9+ (or your project’s baseline)
- Dependencies: `pytest`, `websocket-client`, `requests`, `PyQt5` (for UI smoke)
- Optional env vars:
  - `COMFY_CMD` — command to start ComfyUI (e.g., `comfyui` or absolute path)
  - `COMFY_REMOTE_URL` — base URL of a remote ComfyUI for the remote step
  - `COMFY_PORT` — fixed port for local server (otherwise an ephemeral free port is used)
  - `QT_QPA_PLATFORM=offscreen` — set automatically by tests for UI smoke

> Server-dependent tests **skip** automatically if `COMFY_CMD` isn’t set.

Install test deps:
```bash
pip install pytest pytest-qt requests websocket-client
````

---

## How to use the suite

### 1) Bring-up (steps/)

Run these **in order** as you wire up the code:

1. `test_01_server.py` — start/stop ComfyUI and GET `/object_info`
2. `test_02_connect_ws.py` — open/close WebSocket
3. `test_03_post_prompt.py` — POST a minimal payload; subscribe (best-effort)
4. `test_04_load_workflow.py` — load JSON workflow (no server)
5. `test_05_update_params.py` — apply in-memory param overrides
6. `test_06_compile_payload.py` — compile Graph → Comfy prompt JSON
7. `test_07_submit_local.py` — compile + submit via `LocalExecutor` (best-effort)
8. `test_08_remote_executor.py` — optional; uses `COMFY_REMOTE_URL`
9. `test_09_workflow_manager_local.py` — end-to-end via `WorkflowManager`
10. `test_10_cli_and_validate.py` — run CLI commands (validate + local run)

Each file:

* can be run alone (`python tests/steps/test_06_compile_payload.py`)
* is pytest-compatible (`pytest -q tests/steps/test_06_compile_payload.py`)

### 2) Regression (unit/)

Once the steps pass, run the fast suite:

```bash
pytest -q tests/unit
```

These tests mock I/O and network and verify logic: graph construction, payload compilation, connector flow, validation, output handling.

---

## E2E (what it is, when you may add it)

**E2E** (end‑to‑end) tests boot **a real ComfyUI**, send **real** workflows, and verify **real** artifacts. They’re slower and may be flaky on busy machines, so we keep them **optional** and **separate** (e.g., in a `tests/e2e/` folder).

You can add them later when:

* the steps pass reliably,
* you want hard guarantees about end results (e.g., images saved where expected),
* your CI has GPUs/time.

Gate them behind `COMFY_E2E=1` so they don’t run by default.

---

## Running examples

**Run one step from PyCharm**

1. Open `tests/steps/test_03_post_prompt.py`
2. Set `COMFY_CMD` in Run/Debug Configuration (Environment)
3. Right-click the test → *Run*

**Run one step from CLI**

```bash
COMFY_CMD=comfyui python tests/steps/test_03_post_prompt.py
```

**Run unit tests**

```bash
pytest -q tests/unit
```

**Run all steps**

```bash
COMFY_CMD=comfyui pytest -q tests/steps
```

---

## Troubleshooting

* **“Missing env ‘COMFY\_CMD’”**
  Set it to your ComfyUI launcher (`comfyui` or a full path).
  On Windows, point to your `.bat`; on Linux/Mac, the binary/script on `PATH`.

* **Port already in use**
  Set `COMFY_PORT` to an open port. The server manager chooses a free port by default.

* **WebSocket events aren’t arriving**
  Give the step a second or two; minimal payloads may finish instantly. These tests treat WS subscriptions as **connectivity checks**, not output assertions.

* **UI smoke fails in headless**
  Ensure `QT_QPA_PLATFORM=offscreen`. The tests set it automatically if not present.

---

## Why this structure?

* **Steps** isolate each layer so you can fix issues in place, quickly.
* **Unit** keeps your core logic stable and fast to test.
* The **same files** are usable **both** for single-run debugging and CI (pytest). You don’t have to maintain two sets.

---

