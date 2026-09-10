from __future__ import annotations

from typing import Any, Dict, Mapping, Tuple, List
import re

from .modes import Mode




def h3_length_frames(duration_seconds: float) -> int:
    """Map requested seconds to the current ComfyUI H3 17k+5 frame grid at 24 fps."""
    base = max(5, round(float(duration_seconds) * 24.0))
    return int(base + (5 - (base % 17)) % 17)


def h3_effective_duration_seconds(duration_seconds: float) -> float:
    """Return the actual target duration after current ComfyUI H3 frame-grid alignment."""
    return h3_length_frames(duration_seconds) / 24.0

MEDIA_KEYS = (
    "FIRST_FRAME", "LAST_FRAME",
    "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9",
    "V1", "V2", "V3", "VA1", "VA2", "VA3", "A1", "A2", "A3",
)


def connected_media_manifest(**media: Any) -> Dict[str, bool]:
    """Return stable slot-presence flags without serializing media payloads."""
    return {
        "FIRST_FRAME": media.get("first_frame") is not None,
        "LAST_FRAME": media.get("last_frame") is not None,
        **{f"P{i}": media.get(f"p{i}") is not None for i in range(1, 10)},
        **{f"V{i}": media.get(f"v{i}") is not None for i in range(1, 4)},
        **{f"VA{i}": media.get(f"va{i}") is not None for i in range(1, 4)},
        **{f"A{i}": media.get(f"a{i}") is not None for i in range(1, 4)},
    }


def _declared_slots(draft: Mapping[str, Any], mode: Mode) -> set[str]:
    assets = draft["assets"]
    if mode is Mode.T2VA:
        return set()
    if mode is Mode.I2VA:
        return {"FIRST_FRAME"} if assets.get("first_frame") else set()
    if mode is Mode.L2VA:
        return {"LAST_FRAME"} if assets.get("last_frame") else set()
    if mode is Mode.FL2VA:
        declared = set()
        if assets.get("first_frame"):
            declared.add("FIRST_FRAME")
        if assets.get("last_frame"):
            declared.add("LAST_FRAME")
        return declared
    return (
        set(assets.get("pictures", {}))
        | set(assets.get("videos", {}))
        | set(assets.get("video_audios", {}))
        | set(assets.get("audios", {}))
    )


def validate_physical_media(draft: Mapping[str, Any], mode: Mode, manifest: Mapping[str, bool]) -> None:
    """Require exact agreement between the locked asset plan and real sockets."""
    declared = _declared_slots(draft, mode)
    connected = {key for key, present in manifest.items() if bool(present)}
    missing = sorted(declared - connected, key=_slot_sort_key)
    if missing:
        raise ValueError(", ".join(missing) + " 已声明但物理槽位未连接。")
    extra = sorted(connected - declared, key=_slot_sort_key)
    if extra:
        raise ValueError(", ".join(extra) + " 已连接但导演稿未声明。请清掉旧参考或补入资产装填清单。")


def _slot_sort_key(slot: str) -> Tuple[int, int]:
    if slot == "FIRST_FRAME":
        return (0, 0)
    if slot == "LAST_FRAME":
        return (0, 1)
    if slot.startswith("VA"):
        try:
            return (3, int(slot[2:]))
        except ValueError:
            return (9, 999)
    prefix_order = {"P": 1, "V": 2, "A": 4}
    if slot and slot[0] in prefix_order:
        try:
            return (prefix_order[slot[0]], int(slot[1:]))
        except ValueError:
            pass
    return (9, 999)


def _active_slots(mapping: Mapping[str, Any]) -> List[str]:
    return sorted([slot for slot, meta in mapping.items() if meta], key=_slot_sort_key)


def build_ref2va_presentation_map(draft: Mapping[str, Any]) -> Dict[str, str]:
    """Resolve logical workbench slots to labels H3 actually sees.

    H3 numbers each media type by presentation order, not by the physical socket suffix.
    Pictures and videos are therefore compacted independently. Audio numbering is more
    subtle: each enabled reference-video soundtrack is presented immediately before its
    corresponding video, and standalone audio is presented only after all videos.
    """
    a = draft["assets"]
    pictures = _active_slots(a.get("pictures", {}))
    videos = _active_slots(a.get("videos", {}))
    video_audios = _active_slots(a.get("video_audios", {}))
    audios = _active_slots(a.get("audios", {}))

    for va in video_audios:
        v = "V" + va[2:]
        if v not in a.get("videos", {}):
            raise ValueError(f"{va} 已声明，但对应 {v} 视频不存在。")

    result: Dict[str, str] = {}
    for index, slot in enumerate(pictures, 1):
        result[slot] = f"<Picture {index}>"
    for index, slot in enumerate(videos, 1):
        result[slot] = f"<Video {index}>"

    audio_index = 0
    for vslot in videos:
        vaslot = "VA" + vslot[1:]
        if vaslot in a.get("video_audios", {}):
            audio_index += 1
            result[vaslot] = f"<Audio {audio_index}>"
    for slot in audios:
        audio_index += 1
        result[slot] = f"<Audio {audio_index}>"
    return result


def validate_presentation_map(draft: Mapping[str, Any], presentation_map: Mapping[str, str] | None) -> None:
    expected = build_ref2va_presentation_map(draft)
    actual = dict(presentation_map or {})
    if actual != expected:
        raise ValueError(f"presentation_map 与当前 Ref2VA 资产顺序不一致；应为 {expected}，实际为 {actual}。")


def presentation_token(slot: str, presentation_map: Mapping[str, str] | None = None) -> str:
    if presentation_map and slot in presentation_map:
        return presentation_map[slot]
    if slot.startswith("P"):
        return f"<Picture {slot[1:]}>"
    if slot.startswith("V") and not slot.startswith("VA"):
        return f"<Video {slot[1:]}>"
    if slot.startswith("VA"):
        return f"<Audio {slot[2:]}>"
    if slot.startswith("A"):
        return f"<Audio {slot[1:]}>"
    raise ValueError(f"未知 Ref2VA 槽位：{slot}")


def _tensor_to_pil(image: Any):
    import numpy as np
    from PIL import Image
    if image is None:
        raise ValueError("不能把空 IMAGE 转成联系表。")
    tensor = image
    if hasattr(tensor, "detach"):
        tensor = tensor.detach().cpu()
    if getattr(tensor, "ndim", None) == 4:
        tensor = tensor[0]
    arr = tensor.numpy() if hasattr(tensor, "numpy") else np.asarray(tensor)
    if arr.ndim != 3:
        raise ValueError(f"IMAGE 需要 BHWC/HWC 张量，实际维度={arr.ndim}。")
    arr = (arr.clip(0.0, 1.0) * 255.0).round().astype("uint8")
    if arr.shape[-1] == 1:
        arr = arr.repeat(3, axis=-1)
    if arr.shape[-1] == 4:
        arr = arr[..., :3]
    return Image.fromarray(arr, mode="RGB")


def _pil_to_tensor(image: Any):
    import numpy as np
    import torch
    arr = np.asarray(image.convert("RGB"), dtype="float32") / 255.0
    return torch.from_numpy(arr).unsqueeze(0)


def _image_batch_length(frames: Any) -> int:
    shape = tuple(getattr(frames, "shape", ()))
    if len(shape) == 4:
        return int(shape[0])
    if len(shape) == 3:
        return 1
    raise ValueError(f"参考视频必须是 H3 可接受的 IMAGE 帧序列（BHWC）；实际 shape={shape}。")


def _select_frame(frames: Any, index: int):
    if hasattr(frames, "detach"):
        frames = frames.detach().cpu()
    if getattr(frames, "ndim", None) == 3:
        return frames
    return frames[index]


def _effective_h3_reference_frame_count(source_count: int, target_length_frames: int | None = None) -> int:
    """Mirror current ComfyUI H3 ref-video prefix truncation and 17k+5 crop."""
    n = int(source_count)
    if target_length_frames is not None:
        n = min(n, int(target_length_frames))
    if n < 5:
        return n
    while n % 17 != 5:
        n -= 1
    return n


def _video_preview_tiles(
    frames: Any, slot: str, target_length_frames: int | None = None
) -> List[Tuple[str, Any]]:
    source_count = _image_batch_length(frames)
    if source_count < 1:
        raise ValueError(f"{slot} 参考视频帧序列为空。")
    count = _effective_h3_reference_frame_count(source_count, target_length_frames)
    if count < 1:
        raise ValueError(f"{slot} 参考视频没有可供 H3 使用的有效帧。")
    # Sample only the prefix that current H3 will actually present.
    last = count - 1
    indices = [round(last * frac) for frac in (0.10, 0.50, 0.90)]
    return [
        (f"{slot}@{pct}%", _select_frame(frames, idx))
        for pct, idx in zip((10, 50, 90), indices)
    ]


def _image_tile(label: str, image: Any, tile_width: int, tile_height: int):
    from PIL import Image, ImageDraw, ImageOps
    src = image if isinstance(image, Image.Image) else _tensor_to_pil(image)
    src = src.convert("RGB")
    label_h = min(28, max(16, tile_height // 7))
    body_h = tile_height - label_h
    fitted = ImageOps.contain(src, (tile_width, body_h))
    tile = Image.new("RGB", (tile_width, tile_height), "black")
    x = (tile_width - fitted.width) // 2
    y = label_h + (body_h - fitted.height) // 2
    tile.paste(fitted, (x, y))
    draw = ImageDraw.Draw(tile)
    draw.rectangle((0, 0, tile_width, label_h), fill="white")
    draw.text((6, 3), label, fill="black")
    return tile



def make_labeled_contact_sheet(
    image_slots: Mapping[str, Any],
    *, tile_width: int = 224, tile_height: int = 224,
) -> Tuple[Any, List[str]]:
    """Backward-compatible picture-only contact sheet helper."""
    from PIL import Image
    active = [(slot, value) for slot, value in image_slots.items() if value is not None]
    active.sort(key=lambda item: _slot_sort_key(item[0]))
    if not active:
        return None, []
    if tile_width < 32 or tile_height < 32:
        raise ValueError("联系表 tile 尺寸至少为 32x32。")
    sheet = Image.new("RGB", (tile_width * len(active), tile_height), "black")
    labels: List[str] = []
    for index, (slot, value) in enumerate(active):
        tile = _image_tile(slot, value, tile_width, tile_height)
        sheet.paste(tile, (index * tile_width, 0))
        labels.append(slot)
    return _pil_to_tensor(sheet), labels

def make_multimodal_vision_sheet(
    image_slots: Mapping[str, Any],
    video_slots: Mapping[str, Any],
    *, tile_width: int = 320, tile_height: int = 240, columns: int = 4,
    target_length_frames: int | None = None,
) -> Tuple[Any, List[str]]:
    """Create an LLM-only labeled sheet; original H3 media remain untouched."""
    from math import ceil
    from PIL import Image
    if tile_width < 32 or tile_height < 32:
        raise ValueError("联系表 tile 尺寸至少为 32x32。")
    if columns < 1:
        raise ValueError("联系表 columns 至少为 1。")

    items: List[Tuple[str, Any]] = []
    for slot, value in sorted(((s, v) for s, v in image_slots.items() if v is not None), key=lambda x: _slot_sort_key(x[0])):
        items.append((slot, value))
    for slot, value in sorted(((s, v) for s, v in video_slots.items() if v is not None), key=lambda x: _slot_sort_key(x[0])):
        items.extend(_video_preview_tiles(value, slot, target_length_frames))
    if not items:
        return None, []

    cols = min(columns, len(items))
    rows = ceil(len(items) / cols)
    sheet = Image.new("RGB", (tile_width * cols, tile_height * rows), "black")
    labels: List[str] = []
    for index, (label, value) in enumerate(items):
        tile = _image_tile(label, value, tile_width, tile_height)
        sheet.paste(tile, ((index % cols) * tile_width, (index // cols) * tile_height))
        labels.append(label)
    return _pil_to_tensor(sheet), labels


def summarize_audio_inputs(audio_slots: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for slot, audio in audio_slots.items():
        if audio is None:
            continue
        if not isinstance(audio, dict):
            result[slot] = {"available": True}
            continue
        sample_rate = audio.get("sample_rate")
        waveform = audio.get("waveform")
        if sample_rate is None or waveform is None:
            result[slot] = {"available": True}
            continue
        shape = tuple(getattr(waveform, "shape", ()))
        channels = int(shape[-2]) if len(shape) >= 2 else 1
        samples = int(shape[-1]) if shape else 0
        duration = round(samples / float(sample_rate), 6) if sample_rate and samples else 0.0
        result[slot] = {"sample_rate": int(sample_rate), "channels": channels, "duration_seconds": duration}
    return result


def summarize_video_inputs(
    video_slots: Mapping[str, Any], fps: float = 24.0, target_length_frames: int | None = None
) -> Dict[str, Dict[str, Any]]:
    """Summarize source and effective H3 reference-video IMAGE frame batches."""
    if fps <= 0:
        raise ValueError("参考视频 fps 必须大于 0。")
    result: Dict[str, Dict[str, Any]] = {}
    for slot, frames in video_slots.items():
        if frames is None:
            continue
        source_count = _image_batch_length(frames)
        effective_count = _effective_h3_reference_frame_count(source_count, target_length_frames)
        source_duration = round(source_count / float(fps), 6)
        effective_duration = round(effective_count / float(fps), 6)
        result[slot] = {
            # Backward-compatible aliases describe the user-provided source sequence.
            "frame_count": source_count,
            "fps": float(fps),
            "duration_seconds": source_duration,
            "source_frame_count": source_count,
            "effective_frame_count": effective_count,
            "source_duration_seconds": source_duration,
            "effective_duration_seconds": effective_duration,
        }
    return result


def validate_ref2va_temporal_limits(
    video_metadata: Mapping[str, Mapping[str, Any]],
    audio_metadata: Mapping[str, Mapping[str, Any]],
) -> None:
    video_total = 0.0
    for slot, meta in video_metadata.items():
        duration = meta.get("duration_seconds")
        if duration is None:
            continue
        duration = float(duration)
        if not 2.0 <= duration <= 15.0:
            raise ValueError(f"{slot} 视频参考时长必须在 2–15 秒；当前 {duration:.2f} 秒。")
        video_total += duration
    if video_total > 15.0 + 1e-6:
        raise ValueError(f"Ref2VA 视频参考总时长必须 ≤ 15 秒；当前 {video_total:.2f} 秒。")

    standalone_audio_total = 0.0
    for slot, meta in audio_metadata.items():
        duration = meta.get("duration_seconds")
        if duration is None:
            continue
        duration = float(duration)
        if not 2.0 <= duration <= 15.0:
            raise ValueError(f"{slot} 音频参考时长必须在 2–15 秒；当前 {duration:.2f} 秒。")
        # Current H3 exposes video soundtracks (VAx/ref_video_audio_N) separately
        # from the <=3 standalone ref_audio_N inputs. Soundtracks consume Audio
        # labels in presentation order, but are not extra standalone input files.
        if slot.startswith("A") and not slot.startswith("VA"):
            standalone_audio_total += duration
    if standalone_audio_total > 15.0 + 1e-6:
        raise ValueError(
            f"Ref2VA 独立音频参考总时长必须 ≤ 15 秒；当前 {standalone_audio_total:.2f} 秒。"
        )
