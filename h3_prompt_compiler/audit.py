from __future__ import annotations

from collections import Counter
import re
from typing import Dict, Any, List

from .modes import Mode
from .media import presentation_token, h3_effective_duration_seconds

CJK_RE = re.compile(r"[\u3400-\u9fff]")
REF_RE = {
    "P": re.compile(r"<Picture\s+([0-9]+)>", re.I),
    "V": re.compile(r"<Video\s+([0-9]+)>", re.I),
    "A": re.compile(r"<Audio\s+([0-9]+)>", re.I),
}
SECTION_RE = re.compile(r"(?m)^([a-z_]+):")


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


def _allowed_refs(mode: Mode, draft: Dict[str, Any], presentation_map: Dict[str, str] | None = None) -> Dict[str, set[str]]:
    if mode is Mode.T2VA:
        return {"P": set(), "V": set(), "A": set()}
    if mode in {Mode.I2VA, Mode.L2VA}:
        return {"P": {"1"}, "V": set(), "A": set()}
    if mode is Mode.FL2VA:
        return {"P": {"1", "2"}, "V": set(), "A": set()}
    allowed = {"P": set(), "V": set(), "A": set()}
    mapping = presentation_map or {}
    logical = []
    a = draft["assets"]
    for group in ("pictures", "videos", "video_audios", "audios"):
        logical.extend(a.get(group, {}).keys())
    for slot in logical:
        token = presentation_token(slot, mapping)
        m = re.match(r"<(Picture|Video|Audio)\s+(\d+)>", token, re.I)
        if not m:
            continue
        prefix = {"picture": "P", "video": "V", "audio": "A"}[m.group(1).lower()]
        allowed[prefix].add(m.group(2))
    return allowed


def _expected_sections(mode: Mode) -> List[str]:
    if mode is Mode.REF2VA:
        return ["subject_definitions", "summary", "retention_analysis", "detailed_description", "overall_soundscape", "non_diegetic_music"]
    return ["integrated_multimodal_description", "overall_soundscape", "non_diegetic_music"]


def _strip_allowed_non_english(prompt: str) -> str:
    # Dialogue/lyrics and quoted visible scene text may preserve original language.
    text = re.sub(r"<d>.*?</d>", "", prompt, flags=re.S | re.I)
    text = re.sub(r'"[^"\n]*"', "", text)
    return text


def _expected_instruction(mode: Mode, draft: Dict[str, Any]) -> str:
    if mode is Mode.I2VA:
        return "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced."
    if mode is Mode.FL2VA:
        n = draft["shots"][-1]["shot_no"]
        return f"How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot {n}) aligns with the {h3_effective_duration_seconds(draft['duration']):.2f}-second mark of the target video."
    if mode is Mode.L2VA:
        n = draft["shots"][-1]["shot_no"]
        return f"How the reference pictures align with the target video — <Picture 1> (from [Shot {n}]) aligns with the {h3_effective_duration_seconds(draft['duration']):.2f}-second mark of the target video."
    return ""




def _speaker_ids(draft: Dict[str, Any]) -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    for shot in draft["shots"]:
        for line in shot.get("dialogue", []):
            speaker = line["speaker"]
            if speaker not in mapping:
                mapping[speaker] = len(mapping) + 1
    return mapping


def _audit_subject_labels(mode: Mode, prompt: str, errors: List[str]) -> None:
    subject_ids = [int(x) for x in re.findall(r"<Subject\s+(\d+)>", prompt, flags=re.I)]
    if mode is not Mode.REF2VA:
        if subject_ids:
            errors.append("Base 模式 T2VA/I2VA/FL2VA/L2VA 不应出现 <Subject N> 标签。")
        return

    definitions_block = prompt.split("subject_definitions:", 1)[1].split("\n\nsummary:", 1)[0] if "subject_definitions:" in prompt and "\n\nsummary:" in prompt else ""
    defined = [int(x) for x in re.findall(r"(?m)^<Subject\s+(\d+)>", definitions_block, flags=re.I)]
    if defined:
        expected = list(range(1, max(defined) + 1))
        if defined != expected:
            errors.append(f"Ref2VA Subject 定义编号必须从1连续且每个只定义一次；当前为 {defined}。")
    undefined = sorted(set(subject_ids) - set(defined))
    if undefined:
        errors.append(f"Prompt 使用了未在 subject_definitions 定义的 Subject：{undefined}。")


def _audit_required_references(mode: Mode, prompt: str, draft: Dict[str, Any], errors: List[str], presentation_map: Dict[str, str] | None = None) -> None:
    if mode is not Mode.REF2VA:
        required = _allowed_refs(mode, draft, presentation_map)
        for prefix, numbers in required.items():
            label = {"P": "Picture", "V": "Video", "A": "Audio"}[prefix]
            for number in sorted(numbers, key=int):
                if not re.search(rf"<{label}\s+{re.escape(number)}>", prompt, re.I):
                    errors.append(f"缺少必须的 <{label} {number}> 引用。")
        return
    a = draft["assets"]
    for group in ("pictures", "videos", "video_audios", "audios"):
        for slot in a.get(group, {}):
            token = presentation_token(slot, presentation_map)
            if token.lower() not in prompt.lower():
                errors.append(f"{slot} 已声明，但对应 {token} 未出现在 Prompt。")


def _audit_shot_labels(mode: Mode, prompt: str, draft: Dict[str, Any], errors: List[str]) -> None:
    if mode is Mode.REF2VA:
        if "detailed_description:\n" not in prompt or "\n\noverall_soundscape:" not in prompt:
            return
        body = prompt.split("detailed_description:\n", 1)[1].split("\n\noverall_soundscape:", 1)[0]
    else:
        if "integrated_multimodal_description:" not in prompt or "\n\noverall_soundscape:" not in prompt:
            return
        body = prompt.split("integrated_multimodal_description:", 1)[1].split("\n\noverall_soundscape:", 1)[0]
    actual = [int(x) for x in re.findall(r"\[Shot\s+(\d+)\]", body, flags=re.I)]
    expected = [int(shot["shot_no"]) for shot in draft["shots"]]
    if actual != expected:
        errors.append(f"H3 镜头标签/Shot 编号必须与导演稿一一对应；应为 {expected}，实际为 {actual}。")


def _audit_known_speaker_ids(prompt: str, draft: Dict[str, Any], errors: List[str]) -> None:
    expected_ids = set(_speaker_ids(draft).values())
    actual_ids = {int(x) for x in re.findall(r"\(S(\d+)\)", prompt)}
    unknown = sorted(actual_ids - expected_ids)
    if unknown:
        errors.append("Prompt 出现未锁定的 Speaker ID：" + ", ".join(f"S{x}" for x in unknown) + "。")


def _audit_speaker_ids(prompt: str, draft: Dict[str, Any], errors: List[str]) -> None:
    mapping = _speaker_ids(draft)
    cursor = 0
    for shot in draft["shots"]:
        for line in shot.get("dialogue", []):
            tag = _language_tag(line["text"])
            token = f"<d>[{tag}] {line['text']}</d>"
            pos = prompt.find(token, cursor)
            if pos < 0:
                continue  # dialogue-preservation audit reports this separately
            before = prompt[max(0, pos - 320):pos]
            ids = re.findall(r"\(S(\d+)\)", before)
            expected = mapping[line["speaker"]]
            if not ids or int(ids[-1]) != expected:
                actual = f"S{ids[-1]}" if ids else "无 Speaker ID"
                errors.append(f"{line['speaker']} 的锁定 Speaker ID 应为 S{expected}，实际最近标记为 {actual}。")
            cursor = pos + len(token)



def _audit_ref2va_task_type_and_audio_retention(prompt: str, draft: Dict[str, Any], errors: List[str], presentation_map: Dict[str, str] | None = None) -> None:
    if "summary:\n" not in prompt or "\n\nretention_analysis:" not in prompt:
        return
    from .renderers import _relationship_from_meta, _task_types

    summary_block = prompt.split("summary:\n", 1)[1].split("\n\nretention_analysis:", 1)[0]
    expected_prefix = "[" + " + ".join(_task_types(draft)) + "]"
    if not summary_block.startswith(expected_prefix):
        actual = re.match(r"^\[[^\]]+\]", summary_block)
        errors.append(
            f"Ref2VA summary task type 应为 {expected_prefix}，实际为 {actual.group(0) if actual else '缺失'}。"
        )

    if "retention_analysis:\n" not in prompt or "\n\ndetailed_description:" not in prompt:
        return
    retention = prompt.split("retention_analysis:\n", 1)[1].split("\n\ndetailed_description:", 1)[0]
    allowed_audio = {"fully_copy", "partially_copy", "reference", "weak_reference"}
    for group in ("video_audios", "audios"):
        for slot, meta in draft["assets"].get(group, {}).items():
            token = presentation_token(slot, presentation_map)
            number_match = re.search(r"<Audio\s+(\d+)>", token, re.I)
            if not number_match:
                errors.append(f"{slot} 没有解析到 H3 Audio 标签。")
                continue
            number = number_match.group(1)
            m = re.search(rf"(?m)^<Audio\s+{re.escape(number)}>:\s*([a-z_]+)\s+-", retention, flags=re.I)
            if not m:
                errors.append(f"{slot} 对应 <Audio {number}> 缺少 retention_analysis 条目。")
                continue
            actual_rel = m.group(1)
            expected_rel = _relationship_from_meta(slot, meta)
            if actual_rel not in allowed_audio or actual_rel != expected_rel:
                errors.append(f"{slot} 对应 <Audio {number}> retention marker 应为 {expected_rel}，实际为 {actual_rel}。")

def audit_prompt(mode: Mode, prompt: str, draft: Dict[str, Any], presentation_map: Dict[str, str] | None = None) -> str:
    errors: List[str] = []
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("H3 Prompt 为空。")

    if mode is Mode.REF2VA and not prompt.startswith("subject_definitions:"):
        errors.append("Ref2VA Prompt 必须从 subject_definitions: 开始，前面不能有额外说明。")
    if mode is Mode.T2VA and not prompt.startswith("integrated_multimodal_description:"):
        errors.append("T2VA Prompt 必须从 integrated_multimodal_description: 开始，前面不能有额外说明。")

    actual_sections = SECTION_RE.findall(prompt)
    expected_sections = _expected_sections(mode)
    if actual_sections != expected_sections:
        errors.append(f"H3 段落结构错误：应为 {expected_sections}，实际为 {actual_sections}。")

    instruction = _expected_instruction(mode, draft)
    if instruction and not prompt.startswith(instruction + "\n\n"):
        errors.append(f"{mode.value} 的首/尾帧对齐指令不符合官方 contract。")
    if mode is Mode.T2VA and prompt.startswith("How the reference pictures align"):
        errors.append("T2VA 不应包含关键帧对齐指令。")

    allowed = _allowed_refs(mode, draft, presentation_map)
    for prefix, regex in REF_RE.items():
        for number in regex.findall(prompt):
            if number not in allowed[prefix]:
                errors.append(f"Prompt 引用了未声明的 {prefix}{number}。")
    _audit_required_references(mode, prompt, draft, errors, presentation_map)
    _audit_subject_labels(mode, prompt, errors)
    if mode is Mode.REF2VA:
        _audit_ref2va_task_type_and_audio_retention(prompt, draft, errors, presentation_map)

    # Stable shot numbering and cut timestamps.
    _audit_shot_labels(mode, prompt, draft, errors)
    if "[Shot 1]" not in prompt:
        errors.append("缺少 [Shot 1]。")
    for shot in draft["shots"][1:]:
        expected = f"[Shot {shot['shot_no']}] At {_fmt_time(shot['start'])},"
        if expected not in prompt:
            errors.append(f"缺少或写错镜头切点：{expected}")

    # Every locked dialogue must appear exactly as many times as in the director draft.
    expected_dialogues = Counter()
    for shot in draft["shots"]:
        for line in shot.get("dialogue", []):
            tag = _language_tag(line["text"])
            expected_dialogues[f"<d>[{tag}] {line['text']}</d>"] += 1
    for token, expected_count in expected_dialogues.items():
        actual_count = prompt.count(token)
        if actual_count != expected_count:
            errors.append(f"锁定台词数量或原文被改变：{token}，应出现 {expected_count} 次，实际 {actual_count} 次。")

    # No additional dialogue blocks may be invented.
    actual_dialogue_blocks = re.findall(r"<d>.*?</d>", prompt, flags=re.S | re.I)
    if len(actual_dialogue_blocks) != sum(expected_dialogues.values()):
        errors.append("Prompt 出现了额外或缺失的 <d> 对白块。")
    _audit_speaker_ids(prompt, draft, errors)
    _audit_known_speaker_ids(prompt, draft, errors)

    expected_visible_text = Counter(
        text
        for shot in draft["shots"]
        for text in shot.get("visible_text", [])
    )
    for text, expected_count in expected_visible_text.items():
        token = f'"{text}"'
        actual_count = prompt.count(token)
        if actual_count != expected_count:
            errors.append(
                f"锁定画面文字“{text}”应以双引号原样出现 {expected_count} 次，实际 {actual_count} 次。"
            )

    # Outside <d> blocks, double quotes are reserved for director-locked visible text.
    without_dialogue = re.sub(r"<d>.*?</d>", "", prompt, flags=re.S | re.I)
    actual_quoted_text = Counter(re.findall(r'"([^"\n]*)"', without_dialogue))
    extras = actual_quoted_text - expected_visible_text
    if extras:
        errors.append("Prompt 出现未锁定的双引号画面文字：" + ", ".join(repr(x) for x in extras.elements()) + "。")

    english_surface = _strip_allowed_non_english(prompt)
    if CJK_RE.search(english_surface):
        errors.append("H3 重写正文必须为英文；中文只允许出现在 <d> 台词/歌词或双引号内的画面文字。")

    if mode is Mode.REF2VA:
        if "dialogue_plan:" in prompt:
            errors.append("Ref2VA 官方六段结构中不存在 dialogue_plan。")
        if "detailed_description:\n" in prompt and "[Shot 1]" in prompt:
            pre_shot = prompt.split("detailed_description:\n", 1)[1].split("[Shot 1]", 1)[0].strip()
            if not pre_shot:
                errors.append("Ref2VA detailed_description 必须在 [Shot 1] 前有英文样式开场。")

    if errors:
        raise ValueError("审计失败：\n- " + "\n- ".join(errors))
    return f"审计通过：{mode.value} contract、镜头时间、参考编号、英文正文和锁定台词均通过。"
