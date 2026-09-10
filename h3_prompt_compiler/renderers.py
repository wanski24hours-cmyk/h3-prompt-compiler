from __future__ import annotations

import re
from typing import Dict, Any, List, Tuple

from .modes import Mode
from .media import presentation_token, h3_effective_duration_seconds

VISUAL_SUBJECT_ROLES = {"人物", "角色", "主体", "场景", "环境", "道具", "物件", "服装", "风格", "动作", "表情", "姿势", "特效"}
STRUCTURAL_PICTURE_ROLES = {"首帧", "尾帧", "关键帧", "分镜", "构图", "构图锚点", "画面锚点"}
VIDEO_EDIT_ROLES = {"视频编辑", "编辑源", "原视频"}
VIDEO_CONTINUE_ROLES = {"视频续写", "续写源", "延续源"}
VIDEO_STRUCTURE_ROLES = VIDEO_EDIT_ROLES | VIDEO_CONTINUE_ROLES | {"镜头运动", "运镜", "剪辑", "剪辑节奏", "节奏", "时间结构", "视频结构", "镜头结构"}
AUDIO_REUSE_ROLES = {"音频复用", "完整复用", "复用"}
AUDIO_PARTIAL_REUSE_ROLES = {"部分复用"}


def _fmt_time(seconds: float) -> str:
    minutes = int(seconds // 60)
    sec = seconds - minutes * 60
    return f"{minutes:02d}:{sec:06.3f}"


def _language_tag(text: str) -> str:
    if re.search(r"[\u3040-\u30ff]", text):
        return "Japanese"
    if re.search(r"[\uac00-\ud7af]", text):
        return "Korean"
    if re.search(r"[\u0600-\u06ff]", text):
        return "Arabic"
    if re.search(r"[\u0400-\u04ff]", text):
        return "Russian"
    if re.search(r"[\u3400-\u9fff]", text):
        return "Chinese"
    return "English"


def _speaker_ids(draft: Dict[str, Any]) -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    for shot in draft["shots"]:
        for line in shot.get("dialogue", []):
            speaker = line["speaker"]
            if speaker not in mapping:
                mapping[speaker] = len(mapping) + 1
    return mapping


def _best_subject_description(name: str, enrichment: Dict[str, Any]) -> str:
    desc = enrichment.get("subject_descriptions_en", {}).get(name)
    return desc or "a consistently identifiable on-screen subject"


def _dialogue_subject_phrase(description: str) -> str:
    """Turn an English noun phrase into a natural sentence subject."""
    desc = (description or "a consistently identifiable on-screen subject").strip()
    if re.match(r"^(?:a|an|the)\s+", desc, flags=re.I):
        return desc[0].upper() + desc[1:]
    return "The " + desc


def _role_tokens(meta: Dict[str, Any]) -> set[str]:
    raw = str(meta.get("role", "参考") or "参考")
    return {x.strip() for x in re.split(r"[+＋,，/]", raw) if x.strip()}


def _find_cast_name_for_asset(meta: Dict[str, Any], draft: Dict[str, Any]) -> str | None:
    label = meta.get("label", "")
    candidates: List[str] = []
    for shot in draft["shots"]:
        candidates.extend(shot.get("cast", []))
        candidates.extend(d["speaker"] for d in shot.get("dialogue", []))
    for name in candidates:
        if name and (name == label or name in label or label in name):
            return name
    return None


def _visual_subjects(draft: Dict[str, Any], enrichment: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    source_order: List[str] = []
    for group in ("pictures", "videos"):
        for slot, meta in draft["assets"].get(group, {}).items():
            roles = _role_tokens(meta)
            if not (roles & VISUAL_SUBJECT_ROLES):
                continue
            matched_cast = _find_cast_name_for_asset(meta, draft)
            name = matched_cast or meta.get("label", "")
            if name not in grouped:
                if matched_cast:
                    desc = _best_subject_description(name, enrichment)
                else:
                    desc = enrichment.get("asset_notes_en", {}).get(slot, "reusable visible content with stable appearance and state")
                grouped[name] = {
                    "name": name,
                    "slots": [],
                    "roles": [],
                    "description_en": desc,
                }
                source_order.append(name)
            grouped[name]["slots"].append(slot)
            grouped[name]["roles"].extend(sorted(roles))
            if not matched_cast:
                note = enrichment.get("asset_notes_en", {}).get(slot)
                if note and grouped[name]["description_en"].startswith("reusable visible content"):
                    grouped[name]["description_en"] = note

    subjects: List[Dict[str, Any]] = []
    source_to_subject: Dict[str, int] = {}
    for name in source_order:
        item = grouped[name]
        subject = {
            "id": len(subjects) + 1,
            "name": item["name"],
            "slots": item["slots"],
            "roles": list(dict.fromkeys(item["roles"])),
            "description_en": item["description_en"],
        }
        subjects.append(subject)
        for slot in subject["slots"]:
            source_to_subject[slot] = subject["id"]
    return subjects, source_to_subject


def _asset_token(slot: str, presentation_map: Dict[str, str] | None = None) -> str:
    return presentation_token(slot, presentation_map)


def _is_audio_slot(slot: str) -> bool:
    return slot.startswith("A") or slot.startswith("VA")


def _needs_standalone_reference(slot: str, meta: Dict[str, Any]) -> bool:
    """Whether the source asset itself must remain addressable in Ref2VA.

    A source that only defines reusable visible content can live solely inside
    <Subject N>. A keyframe/shot-planning picture or whole-video structural
    source has an independent role and therefore needs its own Picture/Video
    definition even when it also contributes to a Subject.
    """
    roles = _role_tokens(meta)
    if _is_audio_slot(slot):
        return True
    if slot.startswith("P"):
        return bool(roles & STRUCTURAL_PICTURE_ROLES)
    if slot.startswith("V"):
        return bool(roles & VIDEO_STRUCTURE_ROLES)
    return False


def _relationship_from_meta(slot: str, meta: Dict[str, Any]) -> str:
    hint = (meta.get("relationship") or "").strip()
    roles = _role_tokens(meta)

    if _is_audio_slot(slot):
        audio_aliases = {
            "最终音轨完整复制": "fully_copy", "最终音轨1:1复制": "fully_copy", "完整最终音轨复制": "fully_copy",
            "部分保留": "partially_copy", "部分复用": "partially_copy", "部分复制": "partially_copy",
            "参考": "reference", "声音参考": "reference", "音频参考": "reference",
            "弱参考": "weak_reference",
        }
        if hint in audio_aliases:
            return audio_aliases[hint]
        # Generic wording such as “完全保留/完整复用” is not strong enough for
        # H3's fully_copy marker: fully_copy means this source is the complete
        # final soundtrack, with no added/replaced audio layers. Stay conservative.
        if hint in {"完全保留", "完整保留", "完整复用"}:
            return "partially_copy" if roles & (AUDIO_REUSE_ROLES | AUDIO_PARTIAL_REUSE_ROLES) else "reference"
        if roles & AUDIO_PARTIAL_REUSE_ROLES:
            return "partially_copy"
        if roles & AUDIO_REUSE_ROLES:
            # "audio reuse" is a task type covering full or partial reuse.
            # Without an explicit full-copy relationship, stay conservative:
            # fully_copy means the source audio is the complete final track.
            return "partially_copy"
        if "弱参考" in roles:
            return "weak_reference"
        return "reference"

    visual_aliases = {
        "完全保留": "fully_preserved", "完整保留": "fully_preserved",
        "部分保留": "partially_preserved", "属性迁移": "attribute_transfer",
        "弱参考": "weak_reference",
    }
    return visual_aliases.get(hint, "fully_preserved")


def _task_types(draft: Dict[str, Any]) -> List[str]:
    result: List[str] = []
    pictures = draft["assets"].get("pictures", {})
    videos = draft["assets"].get("videos", {})
    video_audios = draft["assets"].get("video_audios", {})
    audios = {**video_audios, **draft["assets"].get("audios", {})}
    if any(_role_tokens(meta) & VIDEO_EDIT_ROLES for meta in videos.values()):
        result.append("video editing")
    if any(_role_tokens(meta) & VIDEO_CONTINUE_ROLES for meta in videos.values()):
        result.append("video continuation")
    if any(_role_tokens(meta) & STRUCTURAL_PICTURE_ROLES for meta in pictures.values()):
        result.append("keyframe completion")
    has_nonstructural_picture = any(not (_role_tokens(meta) & STRUCTURAL_PICTURE_ROLES) or bool(_role_tokens(meta) & VISUAL_SUBJECT_ROLES) for meta in pictures.values())
    has_reference_video = any(not (_role_tokens(meta) & (VIDEO_EDIT_ROLES | VIDEO_CONTINUE_ROLES)) or bool(_role_tokens(meta) & VISUAL_SUBJECT_ROLES) for meta in videos.values())
    if has_nonstructural_picture or has_reference_video:
        result.append("reference generation")
    if audios:
        has_audio_reuse = any(
            _role_tokens(meta) & (AUDIO_REUSE_ROLES | AUDIO_PARTIAL_REUSE_ROLES)
            for meta in audios.values()
        )
        has_audio_reference = any(
            not (_role_tokens(meta) & (AUDIO_REUSE_ROLES | AUDIO_PARTIAL_REUSE_ROLES))
            or bool(_role_tokens(meta) & {"声音参考", "音频参考", "参考", "弱参考"})
            for meta in audios.values()
        )
        if has_audio_reuse:
            result.append("audio reuse")
        if has_audio_reference:
            result.append("audio reference")
    # De-duplicate while preserving order.
    return list(dict.fromkeys(result or ["reference generation"]))


def _base_shot_text(mode: Mode, draft: Dict[str, Any], enrichment: Dict[str, Any]) -> str:
    speakers = _speaker_ids(draft)
    enriched = {item["shot_no"]: item for item in enrichment["shots"]}
    parts: List[str] = []
    last_shot_no = draft["shots"][-1]["shot_no"]

    for shot in draft["shots"]:
        e = enriched[shot["shot_no"]]
        if shot["shot_no"] == 1:
            head = "[Shot 1]"
        else:
            head = f"[Shot {shot['shot_no']}] At {_fmt_time(shot['start'])},"
        body: List[str] = []
        if shot["shot_no"] == 1:
            body.append(enrichment["style_en"].rstrip(". ") + ".")
        if mode is Mode.I2VA and shot["shot_no"] == 1:
            body.append("The opening composition, subject appearance, clothing, key objects, and spatial relationships follow <Picture 1> exactly at the start of the shot.")
        if mode is Mode.FL2VA and shot["shot_no"] == 1:
            body.append("The shot begins from the composition and visible state established by <Picture 1>.")
        body.append(e["visual_en"].strip())
        for locked_text in shot.get("visible_text", []):
            body.append(f'Visible on-screen text reads "{locked_text}" exactly.')
        body.append(e["camera_en"].strip())
        cues = e.get("dialogue_cues_en", [])
        for index, line in enumerate(shot.get("dialogue", [])):
            sid = speakers[line["speaker"]]
            desc = _best_subject_description(line["speaker"], enrichment)
            tag = _language_tag(line["text"])
            cue = cues[index].strip() if index < len(cues) else ""
            cue_part = f" {cue}" if cue else ""
            body.append(f"{_dialogue_subject_phrase(desc)} (S{sid}) says{cue_part}: <d>[{tag}] {line['text']}</d>")
        body.append(e["diegetic_sound_en"].strip())
        if mode is Mode.FL2VA and shot["shot_no"] == last_shot_no:
            body.append("By the end of the shot, the visible state, object positions, camera angle, lighting, and composition converge to <Picture 2>.")
        if mode is Mode.L2VA and shot["shot_no"] == last_shot_no:
            body.append("By the final moment, the visible state, object positions, camera angle, lighting, and composition converge exactly to <Picture 1>.")
        parts.append(head + " " + " ".join(x.rstrip() for x in body if x).strip())
    return " ".join(parts)


def _render_base(mode: Mode, draft: Dict[str, Any], enrichment: Dict[str, Any]) -> str:
    instruction = ""
    if mode is Mode.I2VA:
        instruction = "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n"
    elif mode is Mode.FL2VA:
        final_shot = draft["shots"][-1]["shot_no"]
        instruction = (
            "How the reference pictures align with the target video — "
            f"Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot {final_shot}) aligns with the {h3_effective_duration_seconds(draft['duration']):.2f}-second mark of the target video.\n\n"
        )
    elif mode is Mode.L2VA:
        final_shot = draft["shots"][-1]["shot_no"]
        instruction = (
            "How the reference pictures align with the target video — "
            f"<Picture 1> (from [Shot {final_shot}]) aligns with the {h3_effective_duration_seconds(draft['duration']):.2f}-second mark of the target video.\n\n"
        )

    body = _base_shot_text(mode, draft, enrichment)
    return (
        instruction
        + f"integrated_multimodal_description: {body}\n\n"
        + f"overall_soundscape: {enrichment['overall_soundscape_en'].strip()}\n\n"
        + f"non_diegetic_music: {enrichment['non_diegetic_music_en'].strip()}"
    )


def _ref_shot_reference_sentences(
    shot: Dict[str, Any],
    source_to_subject: Dict[str, int],
    draft: Dict[str, Any],
    enrichment: Dict[str, Any],
    presentation_map: Dict[str, str] | None = None,
) -> List[str]:
    sentences: List[str] = []
    seen_subjects: set[int] = set()
    for slot in shot.get("used_assets", []):
        meta = (
            draft["assets"].get("pictures", {}).get(slot)
            or draft["assets"].get("videos", {}).get(slot)
            or draft["assets"].get("video_audios", {}).get(slot)
            or draft["assets"].get("audios", {}).get(slot)
            or {}
        )
        subject_id = source_to_subject.get(slot)
        if subject_id is not None:
            if subject_id not in seen_subjects:
                sentences.append(
                    f"<Subject {subject_id}> follows its defined reference identity and attributes in this shot."
                )
                seen_subjects.add(subject_id)
            if not _needs_standalone_reference(slot, meta):
                continue

        note = enrichment.get("asset_notes_en", {}).get(slot, "the declared reference role")
        note = note.rstrip(". ")
        if slot.startswith("P"):
            sentences.append(f"This shot uses {_asset_token(slot, presentation_map)} as {note}.")
        elif slot.startswith("V") and not slot.startswith("VA"):
            sentences.append(f"This shot uses {_asset_token(slot, presentation_map)} as {note}.")
        elif _is_audio_slot(slot):
            roles = _role_tokens(meta)
            if roles & (AUDIO_REUSE_ROLES | AUDIO_PARTIAL_REUSE_ROLES):
                sentences.append(f"This shot reuses {_asset_token(slot, presentation_map)} as {note}.")
            else:
                sentences.append(f"The audible performance uses {_asset_token(slot, presentation_map)} as {note}.")
    return sentences


def _render_ref(mode: Mode, draft: Dict[str, Any], enrichment: Dict[str, Any], presentation_map: Dict[str, str] | None = None) -> str:
    subjects, source_to_subject = _visual_subjects(draft, enrichment)
    speakers = _speaker_ids(draft)
    subject_lines: List[str] = []

    for subject in subjects:
        sources = " and ".join(_asset_token(slot, presentation_map) for slot in subject["slots"])
        subject_lines.append(
            f"<Subject {subject['id']}> is reusable visible content defined by {sources}: {subject['description_en'].rstrip('. ')}."
        )

    for slot, meta in draft["assets"].get("pictures", {}).items():
        if slot in source_to_subject and not _needs_standalone_reference(slot, meta):
            continue
        note = enrichment.get("asset_notes_en", {}).get(slot, "a visual reference used according to the director draft")
        subject_lines.append(f"{_asset_token(slot, presentation_map)} is {note.rstrip('. ')}.")
    for slot, meta in draft["assets"].get("videos", {}).items():
        if slot in source_to_subject and not _needs_standalone_reference(slot, meta):
            continue
        note = enrichment.get("asset_notes_en", {}).get(slot, "a temporal or structural video reference used according to the director draft")
        subject_lines.append(f"{_asset_token(slot, presentation_map)} is {note.rstrip('. ')}.")
    for slot, meta in draft["assets"].get("video_audios", {}).items():
        note = enrichment.get("asset_notes_en", {}).get(slot, "the synchronized soundtrack from its reference video")
        video_slot = "V" + slot[2:]
        video_token = _asset_token(video_slot, presentation_map)
        speaker_suffix = ""
        for name, sid in speakers.items():
            if name and (name in meta.get("label", "") or meta.get("label", "") in name):
                matching_subject = next((s for s in subjects if s["name"] == name), None)
                speaker_suffix = f" for <Subject {matching_subject['id']}> (S{sid})" if matching_subject else f" for speaker (S{sid})"
                break
        subject_lines.append(f"{_asset_token(slot, presentation_map)} is the synchronized soundtrack of {video_token}, used as {note.rstrip('. ')}{speaker_suffix}.")
    for slot, meta in draft["assets"].get("audios", {}).items():
        note = enrichment.get("asset_notes_en", {}).get(slot, "an audio reference used according to the director draft")
        speaker_suffix = ""
        for name, sid in speakers.items():
            if name and (name in meta.get("label", "") or meta.get("label", "") in name):
                matching_subject = next((s for s in subjects if s["name"] == name), None)
                speaker_suffix = f" for <Subject {matching_subject['id']}> (S{sid})" if matching_subject else f" for speaker (S{sid})"
                break
        subject_lines.append(f"{_asset_token(slot, presentation_map)} is {note.rstrip('. ')}{speaker_suffix}.")

    task_type_list = _task_types(draft)
    task_types = " + ".join(task_type_list)
    used_tokens = [f"<Subject {s['id']}>" for s in subjects]
    used_tokens += [
        _asset_token(slot, presentation_map)
        for group in ("pictures", "videos", "video_audios", "audios")
        for slot in draft["assets"].get(group, {})
        if slot not in source_to_subject or _needs_standalone_reference(slot, draft["assets"][group][slot])
    ]
    if "video editing" in task_type_list:
        edit_slot = next(
            (slot for slot, meta in draft["assets"].get("videos", {}).items() if _role_tokens(meta) & VIDEO_EDIT_ROLES),
            "V1",
        )
        summary = f"[{task_types}] The target video is an edited version of {_asset_token(edit_slot, presentation_map)}."
        if used_tokens:
            summary += " It follows the locked director timeline while using " + ", ".join(used_tokens) + "."
    elif "video continuation" in task_type_list:
        continue_slot = next(
            (slot for slot, meta in draft["assets"].get("videos", {}).items() if _role_tokens(meta) & VIDEO_CONTINUE_ROLES),
            "V1",
        )
        summary = f"[{task_types}] The target video continues from {_asset_token(continue_slot, presentation_map)} and follows the locked director timeline."
        if used_tokens:
            summary += " Additional declared references are " + ", ".join(used_tokens) + "."
    else:
        summary = f"[{task_types}] The target video follows the locked director timeline and uses " + (", ".join(used_tokens) if used_tokens else "the declared references") + "."

    retention_lines: List[str] = []
    for subject in subjects:
        source_metas = []
        for slot in subject["slots"]:
            source_metas.append(
                draft["assets"]["pictures"].get(slot)
                or draft["assets"]["videos"].get(slot)
                or {}
            )
        relationships = [_relationship_from_meta(slot, meta) for slot, meta in zip(subject["slots"], source_metas)]
        rel = relationships[0] if relationships and len(set(relationships)) == 1 else "partially_preserved"
        appears = [
            f"[Shot {shot['shot_no']}]"
            for shot in draft["shots"]
            if any(slot in shot.get("used_assets", []) for slot in subject["slots"])
        ]
        where = ", ".join(appears) if appears else "the target video"
        notes = [enrichment.get("asset_notes_en", {}).get(slot) for slot in subject["slots"]]
        notes = [n.rstrip('. ') for n in notes if n]
        note = "; ".join(notes) if notes else "the defined identity and visible characteristics remain consistent"
        retention_lines.append(f"<Subject {subject['id']}> (appears in {where}): {rel} - {note}.")

    for group in ("pictures", "videos", "video_audios", "audios"):
        for slot, meta in draft["assets"].get(group, {}).items():
            if slot in source_to_subject and not _needs_standalone_reference(slot, meta):
                continue
            rel = _relationship_from_meta(slot, meta)
            note = enrichment.get("asset_notes_en", {}).get(slot, "the declared reference role is preserved")
            retention_lines.append(f"{_asset_token(slot, presentation_map)}: {rel} - {note.rstrip('. ')}.")

    enriched = {item["shot_no"]: item for item in enrichment["shots"]}
    detail_parts: List[str] = []
    for shot in draft["shots"]:
        e = enriched[shot["shot_no"]]
        head = "[Shot 1]" if shot["shot_no"] == 1 else f"[Shot {shot['shot_no']}] At {_fmt_time(shot['start'])},"
        body: List[str] = []
        body.extend(_ref_shot_reference_sentences(shot, source_to_subject, draft, enrichment, presentation_map))
        body.append(e["visual_en"].strip())
        for locked_text in shot.get("visible_text", []):
            body.append(f'Visible on-screen text reads "{locked_text}" exactly.')
        body.append(e["camera_en"].strip())
        cues = e.get("dialogue_cues_en", [])
        for index, line in enumerate(shot.get("dialogue", [])):
            sid = speakers[line["speaker"]]
            matching_subject = next((s for s in subjects if s["name"] == line["speaker"]), None)
            speaker_label = f"<Subject {matching_subject['id']}>" if matching_subject else _best_subject_description(line["speaker"], enrichment)
            tag = _language_tag(line["text"])
            cue = cues[index].strip() if index < len(cues) else ""
            cue_part = f" {cue}" if cue else ""
            body.append(f"{speaker_label} (S{sid}) says{cue_part}: <d>[{tag}] {line['text']}</d>")
        body.append(e["diegetic_sound_en"].strip())
        detail_parts.append(head + " " + " ".join(x.rstrip() for x in body if x).strip())

    return (
        "subject_definitions:\n" + "\n".join(subject_lines) + "\n\n"
        + "summary:\n" + summary + "\n\n"
        + "retention_analysis:\n" + "\n".join(retention_lines) + "\n\n"
        + "detailed_description:\n" + enrichment["style_en"].rstrip(". ") + ".\n" + " ".join(detail_parts) + "\n\n"
        + "overall_soundscape:\n" + enrichment["overall_soundscape_en"].strip() + "\n\n"
        + "non_diegetic_music:\n" + enrichment["non_diegetic_music_en"].strip()
    )

def render_prompt(mode: Mode, draft: Dict[str, Any], enrichment: Dict[str, Any], presentation_map: Dict[str, str] | None = None) -> str:
    if mode in {Mode.T2VA, Mode.I2VA, Mode.FL2VA, Mode.L2VA}:
        return _render_base(mode, draft, enrichment)
    if mode is Mode.REF2VA:
        return _render_ref(mode, draft, enrichment, presentation_map)
    raise ValueError(f"不支持的 H3 模式：{mode}")
