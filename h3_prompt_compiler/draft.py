from __future__ import annotations

import re
from typing import Dict, List, Any

EMPTY = {"", "空", "无", "none", "null", "未使用", "关闭", "n/a"}

TITLE_RE = re.compile(r"^标题\s*[:：]\s*(.+)$")
TOTAL_RE = re.compile(r"^总时长\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)\s*秒?$")
SHOT_RE = re.compile(r"^【镜头\s*([0-9]+)】$")
DURATION_RE = re.compile(r"^时长\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)\s*秒?$")
CAST_RE = re.compile(r"^(?:出场人物|出场主体)\s*[:：]\s*(.*)$")
USE_RE = re.compile(r"^使用资产\s*[:：]\s*(.*)$")
SCENE_RE = re.compile(r"^(?:画面内容|画面)\s*[:：]\s*(.*)$")
SOUND_RE = re.compile(r"^(?:声音设计|现场声音)\s*[:：]\s*(.*)$")
MUSIC_RE = re.compile(r"^非画内音乐\s*[:：]\s*(.*)$")
DIALOGUE_RE = re.compile(r"^([^：:]+)\s*[：:]\s*(.*)$")
ASSET_RE = re.compile(r"^(首帧|起始帧|尾帧|末帧|图片(?:槽位)?\s*[1-9]|视频(?:槽位)?\s*[1-3]原声|视频(?:槽位)?\s*[1-3]|音频(?:槽位)?\s*[1-3])\s*[:：]\s*(.*)$")

SEC_ASSETS = "【资产装填清单】"
SEC_FREE = {"【无参考主体】", "【本条不需要上传、让H3自行生成的主体】"}
LEGACY_ASSET_SECTIONS = {
    "【本条需要上传的图片参考资产】",
    "【本条需要上传的视频参考资产】",
    "【本条需要上传的音频参考资产】",
}


def _lines(text: str) -> List[str]:
    return [line.strip() for line in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def _music_request(raw: str) -> str:
    value = (raw or "").strip()
    if value.lower() in EMPTY or value in {"不要", "不需要", "无配乐", "无背景音乐", "不要配乐", "不要背景音乐"}:
        return ""
    return value


def _asset(raw: str) -> Dict[str, Any] | None:
    raw = (raw or "").strip()
    if raw.lower() in EMPTY:
        return None
    parts = [p.strip() for p in raw.split("|")]
    label = parts[0] if parts else raw
    role = parts[1] if len(parts) > 1 and parts[1] else "参考"
    relationship = parts[2] if len(parts) > 2 and parts[2] else ""
    return {"label": label, "role": role, "relationship": relationship}


def _asset_key(raw_key: str) -> tuple[str, str | None]:
    key = raw_key.replace(" ", "")
    if key in {"首帧", "起始帧"}:
        return "first_frame", None
    if key in {"尾帧", "末帧"}:
        return "last_frame", None
    m = re.match(r"图片(?:槽位)?([1-9])$", key)
    if m:
        return "pictures", f"P{m.group(1)}"
    m = re.match(r"视频(?:槽位)?([1-3])原声$", key)
    if m:
        return "video_audios", f"VA{m.group(1)}"
    m = re.match(r"视频(?:槽位)?([1-3])$", key)
    if m:
        return "videos", f"V{m.group(1)}"
    m = re.match(r"音频(?:槽位)?([1-3])$", key)
    if m:
        return "audios", f"A{m.group(1)}"
    raise ValueError(f"未知资产槽位：{raw_key}")


def _normalize_used_asset(value: str) -> str:
    value = value.strip().replace(" ", "")
    if value.lower() in EMPTY:
        return ""
    group, slot = _asset_key(value)
    if group == "first_frame":
        return "FIRST_FRAME"
    if group == "last_frame":
        return "LAST_FRAME"
    return slot or ""


def _parse_asset_line(line: str, assets: Dict[str, Any]) -> None:
    m = ASSET_RE.match(line)
    if not m:
        raise ValueError(f"资产装填行格式错误：{line}")
    group, slot = _asset_key(m.group(1))
    meta = _asset(m.group(2))
    if group in {"first_frame", "last_frame"}:
        assets[group] = meta
    elif meta is not None:
        assets[group][slot] = meta


def parse_director_draft(text: str) -> Dict[str, Any]:
    lines = _lines(text)
    if not any(lines):
        raise ValueError("中文导演稿为空。")

    out: Dict[str, Any] = {
        "title": None,
        "duration": None,
        "assets": {
            "first_frame": None,
            "last_frame": None,
            "pictures": {},
            "videos": {},
            "video_audios": {},
            "audios": {},
        },
        "free_subjects": [],
        "shots": [],
        "music_request_cn": "",
    }

    i = 0
    in_asset_section = False
    while i < len(lines):
        line = lines[i]
        if not line:
            i += 1
            continue

        m = TITLE_RE.match(line)
        if m:
            out["title"] = m.group(1).strip()
            i += 1
            continue
        m = TOTAL_RE.match(line)
        if m:
            out["duration"] = float(m.group(1))
            i += 1
            continue

        if line == SEC_ASSETS or line in LEGACY_ASSET_SECTIONS:
            in_asset_section = True
            i += 1
            while i < len(lines):
                current = lines[i]
                if not current:
                    i += 1
                    continue
                if current.startswith("【"):
                    break
                _parse_asset_line(current, out["assets"])
                i += 1
            in_asset_section = False
            continue

        if line in SEC_FREE:
            i += 1
            while i < len(lines):
                current = lines[i]
                if not current:
                    i += 1
                    continue
                if current.startswith("【"):
                    break
                out["free_subjects"].append(current)
                i += 1
            continue

        sm = SHOT_RE.match(line)
        if sm:
            shot = {
                "shot_no": int(sm.group(1)),
                "start": 0.0,
                "duration": None,
                "cast": [],
                "used_assets": [],
                "scene": "",
                "visible_text": [],
                "sound_cn": "",
                "dialogue": [],
            }
            i += 1
            dialogue_mode = False
            while i < len(lines):
                current = lines[i]
                if not current:
                    i += 1
                    continue
                if current.startswith("【"):
                    break
                if current.startswith("对白"):
                    dialogue_mode = True
                    i += 1
                    continue
                if dialogue_mode:
                    # Optional shot-level fields after a dialogue block can still be written explicitly.
                    mm = MUSIC_RE.match(current)
                    if mm:
                        out["music_request_cn"] = _music_request(mm.group(1))
                        i += 1
                        continue
                    dm = DIALOGUE_RE.match(current)
                    if not dm:
                        raise ValueError(f"对白行格式错误：{current}")
                    shot["dialogue"].append({"speaker": dm.group(1).strip(), "text": dm.group(2)})
                    i += 1
                    continue

                dm = DURATION_RE.match(current)
                if dm:
                    shot["duration"] = float(dm.group(1))
                    i += 1
                    continue
                cm = CAST_RE.match(current)
                if cm:
                    shot["cast"] = [x.strip() for x in re.split(r"[，,]", cm.group(1)) if x.strip()]
                    i += 1
                    continue
                um = USE_RE.match(current)
                if um:
                    shot["used_assets"] = [
                        token for token in (_normalize_used_asset(x) for x in re.split(r"[，,]", um.group(1))) if token
                    ]
                    i += 1
                    continue
                scm = SCENE_RE.match(current)
                if scm:
                    shot["scene"] = scm.group(1).strip()
                    i += 1
                    continue
                snd = SOUND_RE.match(current)
                if snd:
                    shot["sound_cn"] = snd.group(1).strip()
                    i += 1
                    continue
                mus = MUSIC_RE.match(current)
                if mus:
                    out["music_request_cn"] = _music_request(mus.group(1))
                    i += 1
                    continue
                if shot["scene"]:
                    shot["scene"] += " " + current
                    i += 1
                    continue
                raise ValueError(f"镜头{shot['shot_no']}存在无法识别的行：{current}")
            out["shots"].append(shot)
            continue

        # Global music request may be placed outside shot blocks.
        mus = MUSIC_RE.match(line)
        if mus:
            out["music_request_cn"] = _music_request(mus.group(1))
            i += 1
            continue

        if in_asset_section:
            _parse_asset_line(line, out["assets"])
            i += 1
            continue

        raise ValueError(f"无法识别的导演稿行：{line}")

    if not out["title"]:
        raise ValueError("导演稿缺少“标题：”。")
    if out["duration"] is None:
        raise ValueError("导演稿缺少“总时长：”。")
    if not out["shots"]:
        raise ValueError("导演稿没有任何【镜头N】。")

    expected_numbers = list(range(1, len(out["shots"]) + 1))
    actual_numbers = [shot["shot_no"] for shot in out["shots"]]
    if actual_numbers != expected_numbers:
        raise ValueError(f"镜头编号必须从1连续递增；当前为 {actual_numbers}。")

    cursor = 0.0
    for shot in out["shots"]:
        if shot["duration"] is None or shot["duration"] <= 0:
            raise ValueError(f"镜头{shot['shot_no']}缺少有效时长。")
        if not shot["scene"]:
            raise ValueError(f"镜头{shot['shot_no']}缺少画面内容。")
        visible_text = []
        for match in re.finditer(r'“([^”\n]+)”|"([^"\n]+)"', shot["scene"]):
            visible_text.append(match.group(1) if match.group(1) is not None else match.group(2))
        shot["visible_text"] = visible_text
        cast = set(shot.get("cast", []))
        for line in shot.get("dialogue", []):
            if line["speaker"] not in cast:
                raise ValueError(
                    f"镜头{shot['shot_no']}：说话人“{line['speaker']}”不在出场人物中。"
                )
        shot["start"] = round(cursor, 6)
        cursor += shot["duration"]

    if abs(cursor - out["duration"]) > 0.05:
        raise ValueError(f"镜头时长总和为 {cursor:.2f} 秒，但总时长为 {out['duration']:.2f} 秒。")
    if not 4.0 <= out["duration"] <= 15.0:
        raise ValueError("H3 目标视频总时长必须在 4–15 秒之间。")

    return out
