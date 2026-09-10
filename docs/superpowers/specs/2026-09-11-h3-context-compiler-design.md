# H3 Universal Context Compiler Design

## Purpose
Build a generic ComfyUI prompt-compiler layer for MiniMax H3 that accepts one stable Chinese director-draft format and renders the correct official H3 prompt contract for T2VA, I2VA, FL2VA, L2VA, or Ref2VA. The plugin must remain independent of a specific H3 checkpoint filename or quantization.

## Core rule
The upstream director AI writes only Chinese intent: asset plan, shot durations, cast, visual direction, sound direction, and locked dialogue. It does not write H3 syntax. Structural truth is owned by deterministic code; an external LLM may only enrich English semantic descriptions.

## Modes and contracts
- T2VA: no media anchors; render `integrated_multimodal_description`, `overall_soundscape`, `non_diegetic_music`.
- I2VA: dedicated first-frame input; prepend the exact official first-frame instruction, then the three base fields.
- FL2VA: dedicated first-frame + last-frame inputs; prepend the exact official alignment instruction, then the three base fields.
- L2VA: dedicated last-frame input; prepend the exact official last-frame instruction, then the three base fields.
- Ref2VA: up to P1-P9, V1-V3, A1-A3, total files <=12; audio cannot be the only modality; render exactly six sections: `subject_definitions`, `summary`, `retention_analysis`, `detailed_description`, `overall_soundscape`, `non_diegetic_music`.

## Trusted IR
Program-owned:
- mode and contract profile
- shot order, duration, cumulative cut timestamps
- asset slot bindings and physical-connection presence
- subject IDs and speaker IDs
- exact dialogue and language tags
- task type and retention markers
- final section names/order and reference syntax

LLM-owned enrichment only:
- style_en
- per-shot visual_en, camera_en, diegetic_sound_en
- overall_soundscape_en
- non_diegetic_music_en
- subject_descriptions_en
- asset_notes_en

The LLM is forbidden from returning H3 labels, shot syntax, dialogue, IDs, task types, retention markers, timings, or final H3 sections.

## Physical media inputs
The workbench exposes optional real ComfyUI media sockets:
- first_frame, last_frame (IMAGE)
- p1..p9 (IMAGE)
- v1..v3 (IMAGE frame sequences, matching current H3 ref_video_N inputs)
- va1..va3 (AUDIO synchronized soundtracks paired with v1..v3)
- a1..a3 (AUDIO standalone references)

The Chinese draft declares the same slots. The workbench validates that every declared slot is physically connected and that no connected slot is silently treated as a different slot. This gives Codex a deterministic upload plan.

For visual enrichment, the workbench produces one labeled low-resolution vision sheet from active IMAGE references plus 10/50/90% preview frames from connected V-slot IMAGE frame sequences. The sheet is only an LLM-view aid; original reference media still connect separately to H3 and are never replaced by the sheet. Every tile is burned with a stable ASCII label (`FIRST_FRAME`, `LAST_FRAME`, `P1`..`P9`, `V1@10%` etc.) so ordering cannot be confused. Audio is not semantically guessed from waveform statistics: only technical metadata is serialized, while the locked Chinese director draft defines the audio reference role and the original AUDIO remains connected to H3.

## Nodes
1. `H3_ContextWorkbench`: parse Chinese director draft, resolve/validate mode and physical slots, build trusted context JSON, produce LLM role/prompt, optional labeled vision sheet, and Chinese upload plan.
2. `H3_ContextCompiler`: accept trusted context JSON plus external LLM enrichment JSON; validate enrichment and render the exact mode-specific H3 prompt.
3. `H3_PromptAudit`: hard-audit prompt against trusted context and output only if valid.

## Error policy
Fail before H3 generation for:
- mode/asset conflict
- missing physical media for a declared slot
- unexpected media type/slot reference
- invalid H3 limits
- shot duration mismatch or numbering gaps
- mutated/missing/extra dialogue
- LLM output containing structural keys or H3 syntax
- wrong prompt section order or keyframe instruction
- unresolved/undeclared reference labels
- non-English generated prose outside protected dialogue/visible text.

## Provider independence
No hard dependency on RunningHub LLM, local Qwen, GGUF, or any single provider. Workbench outputs `llm_role`, `llm_prompt`, and optional `vision_sheet`. A provider adapter can be swapped without changing the trusted IR or renderers.

## Versioning
Registry v1.0.0 is an obsolete prototype. v1.1.0 was never published and is superseded by this corrected v1.2.0 architecture. Publish v1.2.0 only after cold-package tests and repository verification pass.
