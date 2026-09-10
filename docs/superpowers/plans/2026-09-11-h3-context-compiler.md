# H3 Universal Context Compiler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the obsolete Ref2VA-only prototype with a generic five-mode MiniMax H3 Context-IR compiler for ComfyUI/RunningHub.

**Architecture:** Parse a stable Chinese director draft into trusted IR; validate real media sockets and H3 mode limits; ask an external LLM only for English semantic enrichment; deterministically render the selected official H3 prompt contract; hard-audit before output.

**Tech Stack:** Python 3.10+, ComfyUI node API, standard library, optional Pillow/torch already present in ComfyUI for contact-sheet generation.

**Spec:** `docs/superpowers/specs/2026-09-11-h3-context-compiler-design.md`

## Global Constraints
- Modes: AUTO, T2VA, I2VA, FL2VA, L2VA, Ref2VA.
- Ref2VA: <=9 images, <=3 videos, <=3 standalone audios, <=12 user input files; paired video soundtracks follow their V slots; standalone audio cannot be sole modality.
- User-facing director draft stays Chinese.
- Final H3 generated prose is English; dialogue/lyrics/visible text preserve original language.
- Dialogue text and punctuation are immutable.
- LLM never owns H3 syntax, IDs, timings, task types, retention markers, or reference labels.
- Model checkpoint filename is irrelevant to prompt contract selection.

---

### Task 1: Lock mode resolution and Chinese director-draft IR
**Files:** `h3_prompt_compiler/modes.py`, `h3_prompt_compiler/draft.py`, tests in `tests/test_modes.py`, `tests/test_draft.py`.
**Interfaces:** `resolve_mode(requested, assets) -> Mode`; `validate_mode_assets(mode, assets)`; `DirectorDraftParser.parse(text) -> dict`.
- [x] Write failing tests for all five AUTO mode cases and invalid mixed modes.
- [x] Run tests and confirm expected failures.
- [x] Implement mode resolution and draft parsing.
- [x] Run tests to green.

### Task 2: Lock LLM enrichment boundary
**Files:** `h3_prompt_compiler/llm_ir.py`, `tests/test_llm_ir_and_audit.py`.
**Interfaces:** `build_enrichment_request(mode, draft) -> (role, prompt)`; `parse_enrichment_response(text, draft) -> dict`.
- [x] Test rejection of structural keys/H3 syntax/Chinese generated prose and shot mismatches.
- [x] Implement minimal schema validator and request builder.
- [x] Run tests to green.

### Task 3: Render official base/keyframe and Ref2VA contracts
**Files:** `h3_prompt_compiler/renderers.py`, `tests/test_renderers.py`.
**Interfaces:** `render_prompt(mode, draft, enrichment) -> str`.
- [x] Test exact I2VA/FL2VA/L2VA instructions, base 3-field structure, Ref2VA 6-field structure, speaker/dialogue locking.
- [x] Implement deterministic renderers.
- [x] Test Ref2VA task-type derivation and multi-asset subject grouping.
- [x] Run tests to green.

### Task 4: Hard audit rendered prompts
**Files:** `h3_prompt_compiler/audit.py`, `tests/test_llm_ir_and_audit.py`.
**Interfaces:** `audit_prompt(mode, draft, prompt) -> str`.
- [x] Test dialogue mutation, wrong section order, invalid refs, wrong timestamps, and CJK leakage.
- [x] Implement audit.
- [x] Run tests to green.

### Task 5: Add physical media sockets and deterministic image vision sheet
**Files:** `h3_prompt_compiler/nodes.py`, new `h3_prompt_compiler/media.py`, `tests/test_nodes.py`, new `tests/test_media.py`.
**Interfaces:** `connected_media_manifest(**media) -> dict`; `validate_physical_media(draft, mode, manifest)`; `make_labeled_contact_sheet(...) -> IMAGE|None`.
- [x] Write failing tests proving declared media must be physically connected and labels keep P1..P9 stable.
- [x] Verify failures.
- [x] Implement socket-presence validation and labeled contact sheet, including labeled video preview frames and non-semantic audio metadata.
- [x] Run tests to green.

### Task 6: Package and documentation for v1.2.0
**Files:** root `__init__.py`, root `nodes.py` compatibility shim, `README.md`, `pyproject.toml`, `examples/*.txt`.
**Interfaces:** ComfyUI `NODE_CLASS_MAPPINGS` and `NODE_DISPLAY_NAME_MAPPINGS`.
- [x] Write/adjust package import tests.
- [x] Add examples for T2VA/I2VA/FL2VA/L2VA/Ref2VA and RunningHub wiring example.
- [x] Set version 1.2.0 and keep PublisherId `h3-tools`.
- [x] Run pytest, compileall, and Python 3.10 AST parse.

### Task 7: Push and verify GitHub repository
**Files:** all above.
- [ ] Update/create files in `wanski24hours-cmyk/h3-prompt-compiler`.
- [ ] Fetch files back from GitHub and verify version, node mappings, and no obsolete monolithic logic remains active.
- [ ] Do not publish Registry without the user-held Registry API key.
