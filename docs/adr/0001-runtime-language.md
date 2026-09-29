# ADR 0001: implementation language for Karakuri core modules

- Status: Accepted (KARA-7 scope)
- Decision owner: Karakuri Developer, recorded here because contracts.md §7.6 delegates the
  Rust-vs-C# choice to the Developer and asks for it to be recorded.
- Scope: `core/text` (this issue). Other stage-2 modules are not bound by this ADR; if they land
  in a different runtime, escalate to Architect before integration rather than mixing silently.

## Context

contracts.md §7.6 leaves the COM-layer language open and offers Rust (windows-rs) and C#
(.NET AOT) as the two candidates. AGENTS.md names Rust only for the launcher (`ui/desktop`,
Tauri v2) and describes the module map (`core/text`, `core/dispatcher`, …) as plain directories.
No language-freeze issue exists on the board.

What the implementation host actually offers, verified on this machine:

| Toolchain | Present |
|---|---|
| `rustc` / `cargo` | no |
| .NET SDK (`dotnet`) | no |
| .NET Framework 4.8 in-box compiler (`csc.exe`) | yes |
| `System.Windows.Automation` (UIA client/provider) in the GAC | yes |
| `Encoding.GetEncoding(932)` — CP932 / Shift-JIS | yes, no package needed |
| MinGW `gcc`, `node`, `python` | yes (not used by this module) |

## Decision

`core/text` is written in C# targeting .NET Framework 4.8, compiled with the in-box
`csc.exe`. No SDK install, no NuGet restore, no network access, no runtime install on the
target machine (.NET Framework 4.8 ships with Windows 10/11).

## Why

1. **It is the API contracts.md itself describes for this option.** §7.6's C# row reads
   "*`System.Windows.Automation` is battle-tested; CacheRequest equivalent is
   `AutomationElement.FromHandle` with `CacheRequest`*" — that is exactly the surface used here
   (`ValuePattern`, `AutomationElement.TryGetCurrentPattern`).
2. **The CSV boundary needs CP932 for free.** `Encoding.GetEncoding(932, …)` is Windows code
   page 932 — Shift-JIS with the Microsoft extensions — in the box. A Rust port would need a
   third-party codec crate and a decision about CP932-vs-JIS mapping fidelity.
3. **Zero new dependencies**, which is a hard project rule: no cloud-mandatory dependency and
   nothing installed on an air-gapped back-office PC.
4. **Reproducible verification.** "Code compiles and the behaviour is demonstrated" is only
   meaningful if the compiler is already there. `build/build-text.cmd` runs offline in ~1 s.

## Consequences

- Build: `build/build-text.cmd` → `bin/karakuri-text.dll` + `bin/karakuri-text-tests.exe`.
- Test: `build/run-text-tests.cmd` → writes `tests/text/test-results.txt`, exit code 0 = pass.
- The module is Windows-only. The product is Windows-only, so this costs nothing today.
- A future port must carry two things across: the `ValuePattern.SetValue` call and the
  `CsvBoundary` encode/decode pair. The rest is result types and telemetry formatting.

## Alternatives rejected

- **Rust + windows-rs** — right long-term fit for a Tauri v2 product, but the host has no Rust
  toolchain and no MSVC link.exe; installing a toolchain would have made this module the only
  one in the repo that can be compiled, and its tests could not have been run here.
- **.NET SDK (8.x) + WinUI/COM interop** — .NET 8 does not ship `System.Windows.Automation`;
  it would need a NuGet package (network, extra dependency) or hand-rolled COM interop.
- **PowerShell probes** — adequate for research (KARA-3 used them) but not a library the
  dispatcher can call.
