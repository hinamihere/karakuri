# Karakuri Public Contracts — Frozen Specification

**Document version:** 1.0  
**Status:** Frozen — changes require Architect decision  
**Issued by:** Karakuri Architect (KARA-4)  
**Handoff target:** Karakuri Developer (stage 2)

---

## 1. Recipe YAML Schema

A recipe is a deterministic, replayable automation script. Mode A loads and replays recipes with zero LLM tokens and zero network calls.

### 1.1 Top-level fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | integer | yes | Schema version. Current: `1`. Increment when a field is added/removed/renamed. Reader must reject unknown future versions with a clear error, never silently degrade. |
| `id` | string | yes | Stable unique identifier, `kara-` prefix convention (e.g. `kara-yayoi-invoice-new`). Used as the embedding index key. Immutable once published. |
| `name` | string (JA/EN) | yes | Human-readable label shown in the launcher UI. Japanese-primary. |
| `description` | string (JA/EN) | no | One to three sentences. Used as additional embedding context for the matcher. |
| `target_app` | object | yes | Window matching criteria. See §1.2. |
| `steps` | array of object | yes | Ordered action list. See §1.3. Minimum 1 step. |
| `template_vars` | object | no | Named substitution variables. Keys are identifiers; values are strings. Referenced as `{{KEY}}` in step `value` and `selector` fields. Missing a variable at replay time is a fatal recipe error (telemetry: `error_category: "template_missing_var"`). |
| `wait_after_ms` | integer | no | Default post-step wait applied to every step that does not specify its own `wait_after_ms`. Range 0–30000. Default: `0`. |

### 1.2 `target_app` object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `window_title_regex` | string | no | Ruby-compatible regex matched against the foreground window title (case-insensitive). Either this or `process_name` must be present; both may be set, in which case both must match. |
| `process_name` | string | no | Executable name without path or extension (e.g. `Yayoi2024`). Case-insensitive match against the foreground process. |
| `launch_command` | string | no | Shell command to launch the app if no matching window is found. Optional — recipes for already-running apps need not set it. |

**Validation rule:** At least one of `window_title_regex` or `process_name` must be non-empty. A recipe with both empty is invalid and must be rejected at load time.

### 1.3 `steps[]` item

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `action` | string (enum) | yes | One of: `click`, `set_value`, `select`, `wait`, `finish`, `fail`. See §4 for the full action contract. |
| `selector` | object | conditional | Selector for `click`, `set_value`, `select`. Required when `action` is one of those three. Forbidden for `wait` and `finish`. `fail` may carry a selector for context or omit it. See §1.4. |
| `value` | string | conditional | Value to set (`set_value`), option value to select (`select`), or timeout in ms (`wait`). Required for `set_value` and `select`; for `wait` it is the timeout (integer as string, e.g. `"500"`); for `click`, `finish`, `fail` it is optional (clicked element's extra context, or fail reason). |
| `wait_after_ms` | integer | no | Per-step override of the recipe-level `wait_after_ms`. Range 0–30000. |
| `is_destructive` | boolean | no | Defaults to `false`. When `true`, the step is a mutating action (sets a value, clicks a submit button). The dispatcher renders an overlay confirmation before executing. Overrides the action-type default: `click` and `set_value` default to `true`, `select` defaults to `false` unless the selected option is known to trigger a state change. |

### 1.4 Selector object (selector resolution order)

A selector identifies one node in the a11y tree. Resolution tries each strategy in order and stops at the first match. If all strategies fail, the step fails with `error_category: "selector_miss"`.

| Field | Type | Required | Resolution order | Description |
|-------|------|----------|-----------------|-------------|
| `automation_id` | string | no | 1st | Exact match against the element's `AutomationId` (UIA) / `object-name` (AT-SPI2). Deterministic, stable across layout changes. Preferred key. |
| `control_type` | string | no | 2nd | Combined with `name` below. Matches the UIA `ControlType` (e.g. `Button`, `Edit`, `ComboBox`, `CheckBox`, `TabItem`) or AT-SPI2 role. |
| `name` | string | no | 3rd (fallback) | Substring match against the element's localized name/role-description. Human-readable; fragile across language and layout changes. Used only when `automation_id` and `control_type` are absent or unmatched. |

**Rule:** A selector MUST NOT rely on `name` alone when `automation_id` or `control_type` is available. Templates should prefer `automation_id` wherever the target app exposes it.

**Selector resolution algorithm (pseudocode):**

```
for node in tree:
  if selector.automation_id and node.automation_id == selector.automation_id:
    return node
for node in tree:
  if selector.control_type and node.control_type == selector.control_type:
    if not selector.name or contains(node.name, selector.name):
      return node
for node in tree:
  if selector.name and contains(node.name, selector.name):
    return node
return NO_MATCH
```

### 1.5 Template variable substitution

`{{KEY}}` patterns in `value` and `selector` fields are replaced at replay time with the corresponding value from `template_vars`. Substitution happens before selector resolution and before value injection. Unresolved `{{...}}` (no matching key) is a fatal error.

---

## 2. Telemetry JSONL Schema

File: `logs/telemetry.jsonl` (append-only, one JSON object per line, air-gapped — never written to any network destination).

### 2.1 Common fields (every event)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `timestamp` | string (ISO 8601 UTC) | yes | Wall-clock at event creation, e.g. `2026-09-29T18:44:43.123Z`. |
| `execution_mode` | string (enum) | yes | `mode_a` or `mode_b`. |
| `intent` | string | yes | The user's natural-language intent that triggered this execution, as entered in the launcher. Truncated to 500 chars. |
| `window_title` | string | yes | Foreground window title at execution start. Truncated to 200 chars. |
| `tree_snapshot_hash` | string (SHA-256 hex, 64 chars) | yes | Hash of the compact YAML a11y tree serialized for this execution. Enables later reconstruction of the tree from the recipe index. `0000...` (all zeros) is forbidden — every real execution must produce a real hash. |
| `llm_output` | object or null | no | Mode B only. The raw parsed LLM response (the action contract object). Null or absent in Mode A. |
| `resolved_target` | object or null | no | The a11y node the dispatcher actually acted on: `{temp_id, automation_id, control_type, name, bounding_rectangle}`. Null when no target was resolved (e.g. `wait`, `finish`, or a failure before resolution). |
| `status` | string (enum) | yes | `success`, `failure`, `fallback_applied`, `user_aborted`. |
| `error_category` | string (enum) or null | conditional | Required when `status` is `failure` or `fallback_applied`. One of the categories in §2.2. Null when `status` is `success` or `user_aborted`. |
| `os_error_code` | integer or null | no | Win32 error code (GetLastError) or COM HRESULT (decimal) when the failure originated in the OS adapter. Null otherwise. |
| `fallback_attempted` | boolean | no | `true` when the dispatcher fell back from a native pattern invocation to `SendInput` (or from one pattern to another). `false` otherwise. |

### 2.2 `error_category` enum

| Value | Meaning |
|-------|---------|
| `selector_miss` | No tree node matched the step's selector after exhausting all resolution strategies. |
| `pattern_missing` | Target node found but does not expose the required pattern (`InvokePattern` for `click`, `ValuePattern` for `set_value`, `SelectionPattern` for `select`). |
| `stale_handle` | Target node was valid at resolution time but became invalid before the action executed (window closed, element destroyed). |
| `llm_malformed_json` | Mode B: the LLM response could not be parsed as valid JSON, or was valid JSON but missing required action-contract fields. |
| `llm_unknown_action` | Mode B: the `action` field contained a value outside the known enum. |
| `llm_schema_violation` | Mode B: the response failed the JSON schema guard (wrong types, missing `target_id`, `is_destructive` absent). |
| `llm_timeout` | Mode B: the LLM endpoint did not respond within `config.timeout_ms`. |
| `llm_unreachable` | Mode B: the endpoint returned a non-2xx status or connection failed. |
| `template_missing_var` | Recipe `{{KEY}}` had no matching entry in `template_vars`. |
| `recipe_invalid` | Recipe failed schema validation at load time (missing required field, bad enum value, etc.). |
| `matcher_below_threshold` | Mode B entry point: BGE-M3 cosine similarity was below `config.similarity_threshold` and no cached recipe matched. Not a failure per se — it is the normal gateway to Mode B. Logged as `status: "fallback_applied"` with `fallback_attempted: true`. |
| `overlay_rejected` | Mode B mutating action: the user pressed Esc on the overlay confirmation dialog. |
| `user_aborted` | The user cancelled the execution from the launcher UI before it completed. |
| `os_generic` | Catch-all for OS-level failures not covered above (COM error, access denied, etc.). Always prefer a more specific category when one applies. |

### 2.3 Mode A vs Mode B field differences

| Field | Mode A | Mode B |
|-------|--------|--------|
| `llm_output` | absent / null | populated with the parsed action-contract object |
| `tree_snapshot_hash` | hash of the tree as indexed for the matched recipe | hash of the live tree serialized for the LLM call |
| `error_category` | only recipe/matcher/selector categories apply | all categories apply, including `llm_*` |
| `resolved_target` | the node matched by the recipe selector during replay | the node matched by the recipe selector (Mode A fallback) or by the LLM-selected `target_id` (Mode B) |

---

## 3. Compact YAML A11y Tree (model input)

The tree is what the pruner emits and what the LLM sees in Mode B. It is also what gets hashed for `tree_snapshot_hash`.

### 3.1 Design goals

- **Token budget:** 200–500 tokens per tree for a typical business app window. The pruner MUST drop nodes that do not contribute to actionability.
- **Stable addressing:** Every kept node gets a `temp_id` in serialization order, `1..N`, so the LLM's `target_id` references are unambiguous and the hash is reproducible.
- **Deterministic output:** Same tree input → same YAML output + same hash, every time. No wall-clock, no random ordering.

### 3.2 Node fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `temp_id` | integer | yes | `1..N`, assigned in depth-first serialization order. |
| `control_type` | string | yes | UIA `ControlType` or AT-SPI2 role name, e.g. `Button`, `Edit`, `ComboBox`, `CheckBox`, `TabItem`, `ListItem`, `Pane`, `Window`. |
| `name` | string | yes | Localized name/role-description. Truncated to 120 chars. |
| `automation_id` | string | no | The `AutomationId` if present. Absent nodes omit the key. |
| `is_enabled` | boolean | yes | Whether the control is interactable. |
| `is_selected` | boolean | no | Present only for `CheckBox`, `RadioButton`, `ListItem` (selection state). |
| `value` | string | no | Present only for `Edit`, `ComboBox` (current text/value). Truncated to 200 chars. |
| `children_count` | integer | yes | Number of immediate children kept after pruning. `0` for leaves. |
| `bounding_rect` | object | yes | `{x, y, width, height}` in screen coordinates. Used by the overlay and by `SendInput` fallback. |

### 3.3 Pruning rules (what gets dropped)

Drop these node types entirely (they do not appear in the output):

- Separators, splitters
- Scrollbars (vertical/horizontal)
- Menu bars and menu items (handled by a separate shortcut-flow, not by the general tree)
- Empty panels with no actionable children (a `Pane` whose entire subtree prunes to nothing)
- Groupings with `children_count == 0` after pruning

Keep these (actionable controls):

- `Button`, `Edit`, `ComboBox`, `CheckBox`, `RadioButton`, `TabItem`, `ListItem`, `Hyperlink`, `Spinner`, `Slider`

For container nodes (`Window`, `Pane`, `ToolBar`, `Group`), keep them only if they have at least one kept child — they provide structural context but are not directly actionable.

### 3.4 Example (illustrative, not normative)

```yaml
tree:
  temp_id: 1
  control_type: Window
  name: "弥生会計 2024 - 仕訳入力"
  automation_id: ""
  is_enabled: true
  children_count: 3
  bounding_rect: {x: 0, y: 0, width: 1280, height: 720}
  children:
    - temp_id: 2
      control_type: Edit
      name: "借方科目"
      automation_id: "borrow-side-code"
      is_enabled: true
      value: ""
      children_count: 0
      bounding_rect: {x: 24, y: 80, width: 180, height: 24}
    - temp_id: 3
      control_type: Button
      name: "保存"
      automation_id: "btn-save"
      is_enabled: true
      children_count: 0
      bounding_rect: {x: 1100, y: 640, width: 100, height: 32}
    - temp_id: 4
      control_type: Button
      name: "キャンセル"
      automation_id: "btn-cancel"
      is_enabled: true
      children_count: 0
      bounding_rect: {x: 980, y: 640, width: 100, height: 32}
```

Token count of the above: roughly 80–120 tokens (well within budget for this tiny window; real business apps with tabbed dialogs and list views will grow toward the 500 ceiling, at which point the pruner applies additional depth limiting).

### 3.5 Depth and breadth limits

- **Max depth:** 8 levels from the window root. Nodes deeper than 8 are dropped with an `error_category: "pruner_depth_cut"` telemetry event only if they would otherwise have been actionable (have an `automation_id`); silent drop otherwise.
- **Max breadth per level:** 40 siblings. If a level has more than 40 kept children, keep the first 40 in serialization order and drop the rest. Drop is silent (no telemetry) unless a dropped node had an `automation_id` that a recipe later tries to match — in that case the recipe's `selector_miss` telemetry covers it.

---

## 4. LLM Action Contract

The JSON object the LLM returns in Mode B. The LLM client MUST validate this schema before dispatching. A response that fails validation is logged as `llm_schema_violation` or `llm_malformed_json` and the step is not executed.

### 4.1 Schema

```json
{
  "type": "object",
  "required": ["action", "target_id", "is_destructive"],
  "properties": {
    "thought": {
      "type": "string",
      "description": "Natural-language reasoning for this step. Shown in the launcher log. Max 500 chars.",
      "maxLength": 500
    },
    "action": {
      "type": "string",
      "enum": ["click", "set_value", "select", "wait", "finish", "fail"],
      "description": "The action to perform."
    },
    "target_id": {
      "type": "integer",
      "minimum": 1,
      "description": "temp_id from the compact YAML a11y tree. Must be an integer ≥ 1. References the node the dispatcher will act on."
    },
    "value": {
      "type": ["string", "null"],
      "description": "Action-specific payload. For set_value: the text to inject. For select: the option value. For wait: timeout ms as a string. For click/finish/fail: optional context or reason."
    },
    "is_destructive": {
      "type": "boolean",
      "description": "True when this action mutates application state (sets a value, clicks a submit/save button). The dispatcher renders an overlay confirmation before executing a destructive action. Non-destructive actions (wait, read, finish) bypass the overlay."
    }
  },
  "additionalProperties": false
}
```

### 4.2 Action semantics

| Action | Required fields | Behavior | Destructive by default? |
|--------|-----------------|----------|------------------------|
| `click` | `target_id` | Invoke `InvokePattern` on the resolved node. Fall back to `SendInput` on the node's `bounding_rect` center if no pattern is available. Overlay confirmation if `is_destructive` is true. | Yes |
| `set_value` | `target_id`, `value` | Call `ValuePattern.SetValue(value)` with UTF-16 injection. Bypasses IME. Overlay confirmation if `is_destructive` is true (always true for this action unless explicitly overridden — setting text is always mutating). | Yes |
| `select` | `target_id`, `value` | For `ComboBox`: select the option matching `value`. For `ListItem`/`RadioButton`: invoke selection. Overlay confirmation only if `is_destructive` is true (rare — most selection is non-destructive). | No (unless overridden) |
| `wait` | `target_id` (optional), `value` (timeout ms) | Sleep for the specified milliseconds. `target_id` is optional; if present, re-resolve the node and verify it still exists before returning (liveness check). | No |
| `finish` | none required | Signal the end of the recipe / plan. Returns control to the launcher with a success status. `target_id` and `value` are optional (may carry a final message). | No |
| `fail` | `value` (reason string, optional) | Abort the current execution with a failure status. The `value` is the human-readable reason logged to telemetry and shown in the launcher. `target_id` is optional. | No |

### 4.3 Schema guard rules

1. `action` must be one of the six enum values. Anything else → `llm_unknown_action`.
2. `target_id` must be a positive integer. String `"4"` is rejected; only `4` is valid. Missing or non-integer → `llm_schema_violation`.
3. `is_destructive` must be a boolean. Missing → `llm_schema_violation`.
4. `value` must be a string or null. A number, array, or object → `llm_schema_violation`.
5. `thought` must be a string if present; max 500 chars. Truncated silently if longer.
6. No additional properties allowed. Extra keys → `llm_schema_violation`.
7. `target_id` must reference a node that exists in the tree. If the id is out of range or the node was pruned → `selector_miss` (the LLM chose a target the tree does not contain).

---

## 5. config.toml

### 5.1 Top-level structure

```toml
[app]
language = "ja"
hotkey = "Alt+Space"
recipe_dir = "recipes"

[matcher]
onnx_model_path = "models/bge-m3.onnx"
similarity_threshold = 0.82

[llm]
base_url = "http://localhost:11434/v1"
api_key = ""
model = "llama3"
timeout_ms = 5000
temperature = 0.0
```

### 5.2 `[app]` section

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `language` | string (enum: `ja`, `en`) | no | `ja` | UI language. Affects launcher text and error messages. |
| `hotkey` | string | no | `Alt+Space` | Global shortcut to raise the launcher. Must be parseable as a modifier+key combination. Invalid values fall back to `Alt+Space` with a warning logged to telemetry (`error_category: "config_invalid_hotkey"`). |
| `recipe_dir` | string (path) | no | `recipes` (relative to working dir) | Directory containing `*.yaml` recipe files. Must exist at startup or be creatable. Missing and non-creatable → startup failure with `error_category: "config_recipe_dir_missing"`. |
| `recipe_index_path` | string (path) | no | `models/recipe_index.faiss` (relative to working dir) | Path to the on-disk embedding index. If absent at startup, the matcher initializes an empty index and logs `status: "fallback_applied"` with `error_category: "matcher_index_missing"` on the first execution that needs it. |

### 5.3 `[matcher]` section

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `onnx_model_path` | string (path) | yes | — | Path to the BGE-M3 ONNX weights. Must exist at startup. Missing → startup failure (`error_category: "config_onnx_model_missing"`). |
| `similarity_threshold` | float | no | `0.82` | Cosine similarity threshold above which a recipe is considered a match (Mode A). Range: `0.0`–`1.0`. Values outside this range are clamped with a warning. The threshold `0.82` is the Mode A/Mode B boundary — a change to this value is an Architect decision because it shifts the replay/planning tradeoff. |

### 5.4 `[llm]` section

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `base_url` | string (URL) | yes | — | OpenAI-compatible endpoint base URL, e.g. `http://localhost:11434/v1`. Must be a valid http(s) URL. Missing or invalid → Mode B is unavailable; executions that would route to Mode B fail with `error_category: "llm_unreachable"` at the routing stage. |
| `api_key` | string | no | `""` | Bearer token sent as `Authorization: Bearer <api_key>`. Empty string means no auth header. Never logged, never written to telemetry. |
| `model` | string | no | `llama3` | Model name sent in the `model` field of the chat completions request. |
| `timeout_ms` | integer | no | `5000` | Per-request timeout in milliseconds. Range: `1000`–`60000`. Out-of-range values are clamped. |
| `temperature` | float | no | `0.0` | Sampling temperature. Must be `0.0` for determinism. Non-zero values are rejected at startup with `error_category: "config_non_zero_temperature"`. |

### 5.5 Absent keys and validation

- A config file that is missing the `[llm]` section entirely makes Mode B unavailable (the matcher still works for Mode A).
- A config file that is missing `[matcher].onnx_model_path` is a fatal startup error.
- Unknown keys in any section are ignored with a warning logged once at startup (`error_category: "config_unknown_key"`). This allows forward-compatibility without rejecting older config files that lack new keys.

---

## 6. Mode A / Mode B Boundary

### 6.1 Routing logic

```
on user intent:
  tree = pruner.prune(current_window)
  hash = hash(tree)
  embedding = matcher.embed(intent)
  candidates = index.similarity_search(embedding, top_k=3)
  best = candidates[0]
  if best.similarity >= config.similarity_threshold (0.82):
    recipe = load_recipe(best.recipe_id)
    execute_mode_a(recipe, tree)
  else:
    execute_mode_b(intent, tree, hash)
```

### 6.2 Mode A — Deterministic Replay

- **Tokens:** 0 LLM tokens.
- **Network:** 0 calls.
- **Latency budget:** < 5 ms from matched recipe to first action dispatch (excludes the matcher embedding+search, which has its own budget).
- **Behavior:** Walk `recipe.steps[]` in order. For each step, resolve the selector against the current tree, execute the action, wait `wait_after_ms`, repeat. If any step fails, abort the recipe, log the failure to telemetry, and return to the launcher.
- **Self-healing:** If the matcher later finds a different recipe with a higher similarity score, that becomes the new cached match for future executions. The index is updated lazily on success.
- **Determinism requirement:** Same intent + same window → same recipe selection → same action sequence. No wall-clock branching, no randomness.

### 6.3 Mode B — Guarded Live-Planning

- **Tokens:** One chat completions call per step, strict 3-step action horizon (the LLM may return `finish` earlier; it may never return more than 3 non-`finish` actions without a `finish`/`fail`).
- **Network:** One HTTPS call per step to `config.llm.base_url`.
- **Latency budget:** < 150 ms end-to-end per step decision (embedding + tree serialization + LLM call + schema validation + dispatch). The LLM call itself is bounded by `config.llm.timeout_ms` (default 5000 ms) — the 150 ms budget assumes a local endpoint; a cloud endpoint will exceed it, in which case the timeout is the governing constraint and the user sees a "waiting for LLM" indicator.
- **3-step horizon:** The dispatcher counts non-`finish`/`non-fail` actions returned. On the third such action, it forces a `finish` after execution regardless of what the LLM returns for a fourth call. This prevents runaway planning loops.
- **Overlay guard:** Any action with `is_destructive == true` renders a Win32 overlay with a bounding-box highlight on the target element and two buttons: Execute (Enter) / Cancel (Esc). The dispatcher blocks until the user responds. The overlay timeout is 30 seconds; expiry counts as `user_aborted`.
- **Recipe compilation:** On a successful Mode B execution (all steps completed, last action `finish`), the orchestrator compiles the executed action sequence into a Mode A recipe, writes it to `recipe_dir`, indexes it, and offers it to the user as a saved shortcut. Compilation is an Orchestrator responsibility, not a Developer one.

---

## 7. Alternatives Considered

### 7.1 Recipe schema: JSON vs YAML

- **Chosen:** YAML. Human-readable, editor-friendly, supports comments (developers can annotate recipes), and the existing AGENTS.md already sketches YAML. JSON would be equally machine-parseable but less approachable for the recipe authoring workflow (which is partly manual and partly compiled from Mode B).
- **Rejected:** JSON — no comments, harder for non-technical users to inspect. TOML — over-engineered for a hierarchical action list; no clear advantage over YAML.

### 7.2 Selector: automation_id-only vs multi-strategy

- **Chosen:** Three-strategy fallback (`automation_id` → `control_type`+`name` → `name`). Real-world legacy apps (Yayoi, Bugyo, SAP GUI) do not consistently expose `AutomationId` on every control. A single-strategy selector would make many targets unreachable.
- **Rejected:** `automation_id`-only — too brittle for the target app set. Name-only — too fragile; a Japanese app's localized control names change across versions and OS locale.

### 7.3 Telemetry: JSONL vs SQLite vs structured log

- **Chosen:** JSONL (append-only text). Air-gapped by construction (no network path), trivially greppable, human-readable in any editor, and easy to rotate. Matches the "failure is data" principle — every failure is a queryable event.
- **Rejected:** SQLite — adds a runtime dependency and a file that can lock/corrupt; overkill for an append-only event log. Structured logging (e.g. zap/logrus) — couples the schema to a logging library; JSONL is library-agnostic.

### 7.4 LLM action: free-form vs constrained enum

- **Chosen:** Constrained enum with required `target_id` and `is_destructive`. The 3-step horizon and schema guard make the output predictable and safe. The dispatcher does not interpret arbitrary actions.
- **Rejected:** Free-form action strings — would require the dispatcher to understand an unbounded action vocabulary, which defeats the guardrail purpose. Open-ended tool calling — same problem, plus it invites the LLM to invent actions the OS adapter does not support.

### 7.5 Tree representation: YAML vs JSON vs XML

- **Chosen:** YAML. Concise, low token count, matches the recipe format (so the whole pipeline is one serialization style), and the pruner's depth-first temp-id assignment maps naturally to YAML lists.
- **Rejected:** JSON — more verbose (braces, quotes), higher token count for the same tree. XML — far too verbose for a 200–500 token budget.

### 7.6 Language: Rust vs C# for the COM layer

This is a module-boundary decision, captured here for Developer reference. The contract doc does not mandate one — see the trade-off table below.

| Criterion | Rust (windows-rs) | C# (.NET AOT) |
|-----------|-------------------|---------------|
| UIA COM interop | Good via windows-rs; manual lifetime management for COM pointers | Excellent — UIA is a first-class .NET citizen; `AutomationElement` is the standard entry point |
| IME bypass | Same Win32 `SendMessage`/pattern calls either way; no language advantage | Same |
| Binary size | Small (static link, tree-shaking) | Larger (runtime + AOT), but AOT has improved significantly |
| Deployment | Single binary, no runtime install | Requires .NET runtime or AOT publish; AOT publish is a single binary but larger |
| Team profile | Rust may be unfamiliar to some squad members | .NET is more common in the Japanese enterprise dev pool |
| Maturity for this use case | windows-rs is mature for UIA; CacheRequest batching requires care | `System.Windows.Automation` is battle-tested; CacheRequest equivalent is `AutomationElement.FromHandle` with `CacheRequest` |
| **Recommendation** | Viable; pick if the team leans Rust and accepts the COM lifetime burden | Viable; pick if the team leans .NET and wants the most direct UIA API surface |

**Decision mechanism:** The Architect does not mandate Rust or C# in this contract. The choice is made at implementation time by the Karakuri Developer in consultation with the squad, recorded in a sub-issue, and frozen as part of the implementation contract. The contracts in §§1–6 are language-agnostic and hold regardless of which runtime is chosen.

---

## 8. Failure Modes

### 8.1 Missing UIA pattern

- **Scenario:** `click` step resolves to a node that has no `InvokePattern`.
- **Handling:** Dispatcher attempts `SendInput` fallback on the node's `bounding_rect` center. If `SendInput` also fails (e.g. window obscured, no focus), the step fails with `error_category: "pattern_missing"`, `os_error_code` set to the failing `GetLastError`.
- **Telemetry:** One event appended. Recipe execution aborts.

### 8.2 Selector miss

- **Scenario:** No node matches the selector after all three resolution strategies.
- **Handling:** Step fails immediately. No fallback. `error_category: "selector_miss"`.
- **Telemetry:** `resolved_target` is null; `error_category` is `"selector_miss"`.

### 8.3 Stale element handle

- **Scenario:** Node resolved at step start, but the window or element is destroyed before the action executes (another app closes the window, a dialog dismisses itself).
- **Handling:** The dispatcher re-validates the node's existence immediately before acting. If it is gone, the step fails with `error_category: "stale_handle"`.
- **Telemetry:** `resolved_target` carries the node info as it was at resolution time; `error_category` is `"stale_handle"`.

### 8.4 Malformed LLM JSON

- **Scenario:** Mode B LLM response is not valid JSON, or is valid JSON but fails the schema guard.
- **Handling:** The LLM client logs the raw response (truncated to 1000 chars, with `api_key` and any Bearer token redacted) and returns a failure to the dispatcher without executing anything. `error_category` is `"llm_malformed_json"` or `"llm_schema_violation"` as appropriate.
- **Telemetry:** `llm_output` is the raw (redacted) response string; `status` is `"failure"`.

### 8.5 LLM timeout / unreachable

- **Scenario:** The endpoint does not respond within `config.llm.timeout_ms`, or returns a non-2xx status.
- **Handling:** The step fails; the dispatcher does not retry. `error_category: "llm_timeout"` or `"llm_unreachable"`.
- **Telemetry:** `llm_output` is null; `status` is `"failure"`.

### 8.6 Template variable missing at replay

- **Scenario:** A recipe references `{{FUND_CODE}}` but `template_vars` has no `FUND_CODE` entry.
- **Handling:** Recipe load fails before any step executes. `error_category: "template_missing_var"`.
- **Telemetry:** The recipe is not executed; the error is logged at load time, not per-step.

### 8.7 Overlay rejection

- **Scenario:** User presses Esc on a destructive-action overlay.
- **Handling:** The step is skipped (not executed), the recipe/plan continues to the next step if one exists, or finishes with `status: "user_aborted"` if this was the last step.
- **Telemetry:** `status: "user_aborted"`, `error_category: "overlay_rejected"`, `fallback_attempted: false`.

### 8.8 Pruner depth/breadth cut removing an actionable node

- **Scenario:** A node with an `automation_id` exists at depth 9 (beyond the 8-level limit) or as the 41st sibling.
- **Handling:** The node is absent from the tree. If a recipe later targets it by `automation_id`, the selector resolves to no match and the step fails with `selector_miss`. The pruner does not emit a separate telemetry event for silent drops; the recipe's `selector_miss` is the visible signal.
- **Telemetry:** Covered by the recipe's `selector_miss` event.

---

## 9. Token and Latency Budgets

### 9.1 A11y tree

| Metric | Budget | Notes |
|--------|--------|-------|
| Compact YAML tree | 200–500 tokens | Measured with a standard tokenizer (cl100k_base or equivalent). The pruner targets the lower end for simple windows; complex multi-tab dialogs may reach 500. |
| Per-node name truncation | 120 chars | Keeps individual nodes small. |
| Per-node value truncation | 200 chars | Edit fields rarely need more; long values are truncated with no ellipsis (the value is a hint for the LLM, not a data dump). |

### 9.2 Matcher (Mode A gate)

| Metric | Budget | Notes |
|--------|--------|-------|
| Embedding + search | < 150 ms | BGE-M3 ONNX inference on the intent string + FAISS top-k search. |
| RAM | < 150 MB | ONNX model weights + FAISS index. |
| Cosine threshold | 0.82 | The Mode A/Mode B boundary. Frozen in `[matcher]`. |

### 9.3 Mode A execution

| Metric | Budget | Notes |
|--------|--------|-------|
| Recipe → first action | < 5 ms | Excludes matcher time. Selector resolution + dispatch. |
| Per-step dispatch | < 10 ms | Pattern invoke or `SendInput` fallback. |
| Total recipe | Scales with step count × per-step budget + `wait_after_ms` | No LLM overhead. |

### 9.4 Mode B execution

| Metric | Budget | Notes |
|--------|--------|-------|
| Per-step decision (end to end) | < 150 ms | Tree serialization + LLM call + schema validation + dispatch. Assumes local endpoint. |
| LLM per-request timeout | `config.llm.timeout_ms` (default 5000 ms) | Governing constraint for cloud endpoints. |
| Action horizon | 3 steps max | Forces `finish` after the third non-terminal action. |
| Overlay timeout | 30 seconds | Expiry → `user_aborted`. |

### 9.5 Budget interaction

- The 150 ms Mode B budget is aspirational for a local endpoint (Ollama, llama.cpp). A cloud endpoint will exceed it; in that case the user-facing indicator is "waiting for LLM" and the governing constraint is `config.llm.timeout_ms`. The 150 ms figure is a target for local-first operation, not a hard assert.
- The 200–500 token tree budget is a hard pruner target. If a window consistently exceeds 500 tokens after pruning, the pruner applies additional depth limiting (see §3.5) until the budget is met. A tree that still exceeds 500 tokens after all pruning is a rare edge case; the LLM call proceeds with the oversized tree and the excess is logged as a warning once per execution (`error_category: "pruner_budget_exceeded"`).

---

## 10. Handoff to Developer

### 10.1 What is frozen

The following are frozen by this document and may not be changed without an Architect decision (a new issue, parented to KARA-4 or its parent, with the change described and the rationale given):

1. Recipe YAML schema (§1) — field names, types, required/optional, selector resolution order.
2. Telemetry JSONL schema (§2) — field names, types, `error_category` enum.
3. Compact YAML a11y tree format (§3) — node fields, pruning rules, depth/breadth limits.
4. LLM action contract (§4) — required fields, action enum, schema guard rules.
5. config.toml sections and keys (§5) — section names, key names, types, defaults.
6. Mode A/Mode B boundary (§6) — routing logic, threshold value, 3-step horizon, overlay guard.
7. Token/latency budgets (§9) — the numbers in the tables.

### 10.2 What is left to the Developer

The Developer picks:
- **Language/runtime** for the COM layer (Rust vs C# — see §7.6 trade-off table). Record the choice in a sub-issue.
- **具体的な UIA API calls** within the contract — e.g. exactly which `CacheRequest` properties to batch, how to enumerate children, how to handle COM pointer lifetimes. The contract says *what* must happen; the Developer decides *how* within those bounds.
- **Pruner implementation details** — the exact traversal order, how to detect "empty panel", how to assign temp_ids. The contract specifies the output format and the pruning rules; the implementation is free to optimize within those constraints.
- **FAISS index configuration** — index type (Flat, HNSW), metric, dimension. The contract says the index must support `similarity_search(embedding, top_k=3)` returning `(recipe_id, similarity)` pairs.
- **Overlay implementation** — Win32 overlay rendering approach. The contract says it must highlight the target's bounding rectangle and offer Execute/Cancel with Enter/Esc; the rendering technique is the Developer's choice.

### 10.3 What the Developer receives

From this document, the Developer receives:
- Exact JSON/YAML schemas for every data structure the implementation must produce or consume.
- The full `error_category` enum with the handling rule for each category.
- The selector resolution algorithm (§1.4) as a deterministic spec, not a suggestion.
- The Mode A/Mode B routing logic (§6.1) as a pseudocode entry point.
- The budgets (§9) as hard targets with notes on which are aspirational vs hard.

### 10.4 What the Developer must produce

Against this contract, the Developer's stage-2 deliverables are:

1. A working UIA COM adapter (Windows) that exposes `get_active_window`, `build_cache_request`, `dump_actionable_tree` matching §3's output format.
2. A pruner that emits the compact YAML tree within the 200–500 token budget, with temp_ids `1..N` in deterministic order.
3. A matcher that loads the ONNX model, embeds the intent, queries the FAISS index, and returns the top candidate with similarity score.
4. A recipe loader that validates the YAML schema (§1) and rejects invalid recipes with `recipe_invalid` telemetry.
5. A Mode A executor that walks recipe steps, resolves selectors, dispatches actions, and logs telemetry on every failure path.
6. An LLM client that calls the configured endpoint, validates the response against §4's schema, and returns the parsed action contract or a failure.
7. A Mode B dispatcher that enforces the 3-step horizon, renders the overlay for destructive actions, and compiles successful executions into Mode A recipes.
8. A telemetry logger that appends JSONL events to `logs/telemetry.jsonl` with every field from §2 populated correctly.
9. A config loader that reads `config.toml` and validates the sections from §5, rejecting invalid configs at startup.

### 10.5 What the Developer must NOT do

- Do not add fields to any schema without an Architect issue.
- Do not change the selector resolution order.
- Do not relax the `temperature = 0` requirement.
- Do not introduce a cloud-mandatory dependency or a hardcoded endpoint URL.
- Do not log `api_key`, Bearer tokens, or any secret to telemetry or stdout.
- Do not exceed the 200–500 token tree budget without logging `pruner_budget_exceeded`.
- Do not make Mode A require any network call or LLM token.

---

*End of contract document. This is the frozen spec. Changes require KARA-4 (or its parent) issue with Architect sign-off.*
