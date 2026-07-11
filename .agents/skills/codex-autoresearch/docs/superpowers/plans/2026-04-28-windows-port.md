# Windows Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `codex-autoresearch` helper scripts and tests run reliably on Windows.

**Architecture:** Add `scripts/autoresearch_process.py` as the single home for cross-platform subprocess and process-management behavior. Wire existing scripts to that module with minimal call-site changes and cover the new behavior with focused tests.

**Tech Stack:** Python 3.11 standard library, `unittest`, Git, Codex helper scripts.

---

### Task 1: Add Process Compatibility Tests

**Files:**
- Create: `tests/autoresearch/test_process_compat.py`
- Modify: none

- [ ] Write tests for decoding invalid UTF-8 bytes without raising.
- [ ] Write tests for Windows-style executable lookup using `PATHEXT`.
- [ ] Write tests for process liveness using Python APIs instead of Unix `ps`.
- [ ] Run `python -m unittest tests.autoresearch.test_process_compat -q` and confirm the tests fail before implementation.

### Task 2: Implement Process Compatibility Layer

**Files:**
- Create: `scripts/autoresearch_process.py`
- Modify: `scripts/autoresearch_core.py`
- Modify: `scripts/autoresearch_launch_gate.py`
- Modify: `scripts/autoresearch_runtime_ops.py`
- Modify: hook/workspace helper call sites as needed

- [ ] Add `decode_output`, `run_text`, `popen_text`, `find_executable`, `pid_is_alive`, `inspect_process_identity`, and `terminate_process_tree`.
- [ ] Update command availability checks to use `find_executable`.
- [ ] Replace direct `ps` calls in launch gate with compatibility functions.
- [ ] Replace direct runtime `Popen` and `subprocess.run` text handling with the compatibility wrappers.
- [ ] Run the new process compatibility tests until green.

### Task 3: Stabilize Runtime Controller On Windows

**Files:**
- Modify: `scripts/autoresearch_runtime_ops.py`
- Modify: `scripts/autoresearch_launch_gate.py`
- Modify: `tests/autoresearch/test_runtime_controller.py`

- [ ] Add or adjust tests for missing Codex executable and stop/status behavior on Windows.
- [ ] Ensure missing Codex writes `runtime.json` with `needs_human` instead of crashing before persistence.
- [ ] Ensure `stop` uses cross-platform termination and returns a deterministic JSON summary.
- [ ] Run targeted runtime controller tests.

### Task 4: Verify And Install Skill

**Files:**
- Modify: local Codex skill directory under `%USERPROFILE%\.codex\skills\codex-autoresearch`

- [ ] Run `python -m unittest discover -s tests -q`.
- [ ] If full suite has environment-only shell limitations, run and report targeted Python suites that prove the Windows fixes.
- [ ] Copy the repo contents into the local Codex skills directory, excluding `.git` and transient artifacts.
- [ ] Confirm `SKILL.md`, `scripts/`, and `references/` exist in the installed skill directory.
