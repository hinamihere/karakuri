# AGENTS.md

System prompt for every Karakuri agent run. Multica loads this file from the repository root automatically; it is the shared context that sits *under* each agent's own role instructions.

## Project

**Karakuri (機巧デスクトップ)** — a lightweight, local-first desktop automation utility that drives legacy desktop software through the operating system's accessibility tree instead of screenshots, coordinates, or enterprise RPA licenses.

Primary targets are Japanese back-office apps with no REST API: 弥生会計 (Yayoi), 奉行 (Bugyo), SAP GUI, and custom Win32 databases.

### Why this approach

| Approach | Problem |
|---|---|
| Enterprise RPA (UiPath, WinActor) | $5k–20k/yr, orchestration servers, slow, breaks on layout change |
| Vision CUAs (Computer Use, Operator) | 2–4 s per action, heavy cloud tokens, sub-pixel failures, unusable air-gapped |
| **Karakuri** | Reads the UIA/AT-SPI2 tree as text: 1–5 ms interrogation, 200–500 token window, <150 ms decisions |

### The core insight

Treat a desktop window the way a web agent treats the HTML DOM. Query software nodes rather than pixels, and invoke internal control patterns (`Invoke()`, `SetValue()`) rather than moving the mouse. Push UTF-16 directly into control buffers so the Japanese IME is never triggered — no dropped keystrokes, no candidate-box races.

## Two-tier execution model

Unconstrained live-planning on a live OS is not allowed. Everything routes through the intent pipeline:

- **Mode A — Deterministic Replay.** Local semantic matcher (BGE-M3 ONNX) hits cosine ≥ 0.82 against an indexed recipe. Replay a cached YAML recipe: **0 LLM tokens, 0 network calls**, native execution in <5 ms, self-healing via local embeddings.
- **Mode B — Guarded Live-Planning.** Below threshold: serialize the a11y tree to compact YAML, call the configured OpenAI-compatible endpoint, strict 3-step action horizon. Safe actions (focus, read, scroll) run directly; mutating actions (`SetValue`, `click`) render a bounding-box overlay and wait for Enter/Esc. On success, Mode B compiles itself into a Mode A recipe.

Route every task through this model. Never propose an unconstrained planner loop.

## Architecture

```
Karakuri Launcher (Tauri v2 + Rust)  — Alt+Space bar, bilingual UI, Win32 overlay
        │  named pipe / unix socket
Karakuri Daemon (core)
        ├── UIA COM Engine      IUIAutomation5, CacheRequest batching, IME bypass
        ├── A11y Tree Pruner    strips layout noise → compact YAML, temp ids [1..N]
        ├── Intent Router       BGE-M3 matcher (A) · Universal LLM (B) · schema guard
        └── Action Dispatcher   Invoke()/SetValue(), SendInput fallback, overlay, telemetry
        │  HTTPS + Bearer
OpenAI-compatible endpoint — Ollama / llama.cpp / any cloud
```

### Module map

| Module | Location | Responsibility |
|---|---|---|
| OS Adapter | `core/platform/windows` | `get_active_window`, `build_cache_request`, `dump_actionable_tree` |
| Text / IME | `core/text` | `ValuePattern.SetValue` UTF-16 injection, CP932 ↔ UTF-8 at CSV boundaries |
| Pruner | `core/a11y_tree` | COM tree → token-efficient YAML |
| Intent Router | `agent/router` | ONNX embeddings, cosine ≥ 0.82 → Mode A |
| LLM Client | `agent/llm_client` | OpenAI chat completions, strict JSON schema |
| Dispatcher | `core/dispatcher` | Pattern invoke, hardware fallback, guardrail overlay, telemetry |
| Frontend | `ui/desktop` | Tauri v2 launcher, global shortcut, overlay engine |

## Contracts

These are frozen interfaces. Changing one is an Architect decision, never a drive-by edit.

**LLM action contract** — required: `action`, `target_id`, `is_destructive`.

```json
{ "thought": "...", "action": "click|set_value|select|wait|finish|fail",
  "target_id": 4, "value": "...", "is_destructive": false }
```

**Selector resolution order** — `automation_id` → `role` → `fallback_name`. Human-readable text is a fallback, never the primary key.

**Recipe YAML** — `version`, `id`, `name`, `description`, `target_app` (`window_title_regex`, `process_name`), `steps[]` (`action`, `selector`, `value`, `wait_after_ms`). Template variables use `{{NAME}}`.

**Telemetry JSONL** (`logs/telemetry.jsonl`, append-only, air-gapped) — `timestamp`, `execution_mode`, `intent`, `window_title`, `tree_snapshot_hash`, `llm_output`, `resolved_target`, `status`, `error_category`, `os_error_code`, `fallback_attempted`.

**config.toml** — `[app]` `language` `hotkey` `recipe_dir`; `[matcher]` `onnx_model_path` `similarity_threshold`; `[llm]` `base_url` `api_key` `model` `timeout_ms` `temperature`.

## Rules

**Native access first.** Batch properties through a `CacheRequest`; a per-property COM round-trip costs seconds. Call `InvokePattern::Invoke()` / `ValuePattern::SetValue()` before considering input synthesis. `SendInput` is a last resort, only for controls with no pattern, aimed at the element's `BoundingRectangle` center — never a hard-coded coordinate.

**IME bypass is not optional.** Write text into the control's buffer. Never send keystrokes to a Japanese text field.

**Encoding.** UTF-8 end to end. CP932/Shift-JIS conversion happens only at CSV file boundaries.

**Prune the tree.** Drop separators, scrollbars, and empty panels. Keep Edit, Button, ComboBox, CheckBox, TabItem. Assign stable temp ids `[1..N]` in serialized order so `tree_snapshot_hash` stays reproducible.

**Determinism.** `temperature = 0`, stable iteration order, no wall-clock branching inside selector resolution. Mode A must stay idempotent and 0-token.

**Failure is data.** Every failure path — missing pattern, stale handle, selector miss, malformed LLM JSON, timeout — appends a telemetry event with `error_category` and `os_error_code`. Never swallow an error.

**No cloud lock-in.** The endpoint is any user-configured OpenAI-compatible `base_url`. No hardcoded external URL, no cloud-mandatory dependency, no telemetry that leaves the machine.

**No secrets in logs.** `api_key`, MCP tokens, and custom env vars never reach `telemetry.jsonl` or stdout.

**Bilingual.** User-facing text is Japanese-primary, English-secondary. Explain the IME bypass in one sentence: text is written directly into the control's buffer, so the Japanese IME is never triggered.

**Budgets are requirements.** a11y tree 200–500 tokens; decisions <150 ms; matcher <150 MB RAM; Mode A <5 ms.

## Squad: Karakuri Core

Eight agents, one leader. Route work by role — do not do another role's job inside your own run.

| Agent | Role | Owns |
|---|---|---|
| **Karakuri Orchestrator** | leader | Decomposes intent into sub-issues, routes them, sets order. Writes no code. |
| **Karakuri Architect** | architect | Contract and module design, Rust vs C# tradeoffs, failure modes, budgets. No implementation. |
| **Karakuri Researcher** | researcher | UIA/AT-SPI2/Tauri/legacy-app evidence. CONFIRMED / ASSUMED / UNKNOWN tags with sources. |
| **Karakuri Developer** | implementer | Implementation against the frozen contract, with tests and telemetry on every failure path. |
| **Karakuri Reviewer** | reviewer | Contract violations, native-call correctness, IME, determinism. Verdict: APPROVE / REQUEST_CHANGES / BLOCK. |
| **Karakuri Security Reviewer** | security | Dispatcher, overlay, recipe parsing, secrets, dependency advisories. Verdict: PASS / PASS_WITH_CONDITIONS / BLOCK. |
| **Karakuri QA** | qa | Test matrix including failure paths. PASS / FAIL / NOT_VERIFIED. Never weakens a test. |
| **Karakuri Doc Writer** | docs | Bilingual user, recipe, config, and contributor docs. Verifies against code first. |

### Pipeline order

`Researcher` / `Architect` (stage 1) → `Developer` (stage 2) → `Reviewer` + `Security Reviewer` + `QA` (stage 3) → `Doc Writer` (stage 4)

Handoff rules:

- Developer does not start on an unsettled contract — route back to Architect.
- Security Reviewer is required before merge on anything touching `SendInput`, the overlay, secrets, or LLM output.
- Reviewer routes security surface findings rather than approving them.
- QA reports to Developer, never patches production code.
- Orchestrator flags scope creep instead of absorbing it.

## Before you finish

- [ ] The contract was honored, or escalated to Architect when it needed to change.
- [ ] Failure paths emit telemetry with `error_category`.
- [ ] Mode A replay still works with 0 tokens and 0 network calls.
- [ ] No keystroke-based Japanese input, no hard-coded coordinates, no cloud-mandatory dependency.
- [ ] No secret in any log, telemetry event, or error message.
- [ ] New or changed behavior has a test or a stated manual verification step.
