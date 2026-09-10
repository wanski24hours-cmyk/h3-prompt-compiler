from __future__ import annotations

from enum import Enum
from typing import Dict, Mapping, Any
import re


class Mode(str, Enum):
    T2VA = "T2VA"
    I2VA = "I2VA"
    FL2VA = "FL2VA"
    L2VA = "L2VA"
    REF2VA = "Ref2VA"


MODE_CHOICES = ["AUTO", Mode.T2VA.value, Mode.I2VA.value, Mode.FL2VA.value, Mode.L2VA.value, Mode.REF2VA.value]
CONTRACT_PROFILES = ["MiniMax H3 Official 2026-08"]

VIDEO_EDIT_ROLES = {"视频编辑", "编辑源", "原视频"}

def _role_tokens(meta: Mapping[str, Any]) -> set[str]:
    raw = str(meta.get("role", "") or "")
    return {x.strip() for x in re.split(r"[+＋,，/]", raw) if x.strip()}



def _active(mapping: Mapping[str, Any] | None) -> Dict[str, Any]:
    return {k: v for k, v in (mapping or {}).items() if v}


def has_full_reference_assets(assets: Mapping[str, Any]) -> bool:
    return bool(_active(assets.get("pictures")) or _active(assets.get("videos")) or _active(assets.get("video_audios")) or _active(assets.get("audios")))


def resolve_mode(requested: str, assets: Mapping[str, Any]) -> Mode:
    requested = (requested or "AUTO").strip()
    has_first = bool(assets.get("first_frame"))
    has_last = bool(assets.get("last_frame"))
    has_ref = has_full_reference_assets(assets)

    if requested.upper() == "AUTO":
        if has_ref and (has_first or has_last):
            raise ValueError("关键帧模式资产与 Ref2VA 全参考资产不能同时声明；请拆成对应 H3 模式。")
        if has_ref:
            mode = Mode.REF2VA
        elif has_first and has_last:
            mode = Mode.FL2VA
        elif has_first:
            mode = Mode.I2VA
        elif has_last:
            mode = Mode.L2VA
        else:
            mode = Mode.T2VA
    else:
        try:
            mode = Mode(requested)
        except ValueError as exc:
            raise ValueError(f"未知 H3 模式：{requested}") from exc

    validate_mode_assets(mode, assets)
    return mode


def validate_mode_assets(mode: Mode, assets: Mapping[str, Any]) -> None:
    has_first = bool(assets.get("first_frame"))
    has_last = bool(assets.get("last_frame"))
    pictures = _active(assets.get("pictures"))
    videos = _active(assets.get("videos"))
    video_audios = _active(assets.get("video_audios"))
    audios = _active(assets.get("audios"))
    has_ref = bool(pictures or videos or video_audios or audios)

    if mode is Mode.T2VA:
        if has_first or has_last or has_ref:
            raise ValueError("T2VA 是纯文本模式，不应声明首帧、尾帧或全参考素材。")
        return

    if mode is Mode.I2VA:
        if not has_first or has_last or has_ref:
            raise ValueError("I2VA 必须且只能声明首帧；不能同时声明尾帧或 Ref2VA 参考素材。")
        return

    if mode is Mode.L2VA:
        if not has_last or has_first or has_ref:
            raise ValueError("L2VA 必须且只能声明尾帧；不能同时声明首帧或 Ref2VA 参考素材。")
        return

    if mode is Mode.FL2VA:
        if not (has_first and has_last) or has_ref:
            raise ValueError("FL2VA 必须同时声明首帧与尾帧，且不能混入 Ref2VA 参考素材。")
        return

    if mode is Mode.REF2VA:
        if has_first or has_last:
            raise ValueError("Ref2VA 使用全参考槽位，不使用专用首帧/尾帧字段。")
        if len(pictures) > 9:
            raise ValueError("Ref2VA 图片参考最多 9 张。")
        if len(videos) > 3:
            raise ValueError("Ref2VA 视频参考最多 3 段。")
        for slot in video_audios:
            video_slot = "V" + slot[2:]
            if video_slot not in videos:
                raise ValueError(f"{slot} 是视频原声，但对应 {video_slot} 未声明。")
        total = len(pictures) + len(videos) + len(audios)
        if total == 0:
            raise ValueError("Ref2VA 至少需要一个参考素材。")
        if total > 12:
            raise ValueError(f"Ref2VA 图像/视频/音频文件总数最多 12 个；当前为 {total} 个。")
        if audios and not (pictures or videos):
            raise ValueError("Ref2VA 音频不能作为唯一输入，必须同时有图片或视频参考。")
        active_video_slots = sorted(videos, key=lambda slot: int(slot[1:]))
        edit_slots = [slot for slot in active_video_slots if _role_tokens(videos[slot]) & VIDEO_EDIT_ROLES]
        if len(edit_slots) > 1:
            raise ValueError("Ref2VA 只能有一个直接视频编辑源；多个视频可以做参考，但只能一个标注为视频编辑。")
        if edit_slots and edit_slots[0] != active_video_slots[0]:
            raise ValueError(
                "Ref2VA 视频编辑源必须是实际 presentation 中的第一个视频，使其最终映射为 <Video 1>；"
                f"当前第一个视频是 {active_video_slots[0]}，编辑源是 {edit_slots[0]}。"
            )
        return

    raise ValueError(f"未处理的 H3 模式：{mode}")
