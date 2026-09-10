from __future__ import annotations

import json
from typing import Dict, Any

from .draft import parse_director_draft
from .modes import MODE_CHOICES, CONTRACT_PROFILES, Mode, resolve_mode
from .llm_ir import build_enrichment_request, parse_enrichment_response
from .renderers import render_prompt
from .audit import audit_prompt
from .media import (
    connected_media_manifest,
    validate_physical_media,
    make_multimodal_vision_sheet,
    summarize_audio_inputs,
    summarize_video_inputs,
    validate_ref2va_temporal_limits,
    build_ref2va_presentation_map,
    presentation_token,
    validate_presentation_map,
    h3_length_frames,
    h3_effective_duration_seconds,
)


def _declared_asset_keys(draft: Dict[str, Any]) -> set[str]:
    a = draft["assets"]
    keys = set(a.get("pictures", {})) | set(a.get("videos", {})) | set(a.get("video_audios", {})) | set(a.get("audios", {}))
    if a.get("first_frame"):
        keys.add("FIRST_FRAME")
    if a.get("last_frame"):
        keys.add("LAST_FRAME")
    return keys


def _validate_shot_asset_usage(mode: Mode, draft: Dict[str, Any]) -> None:
    declared = _declared_asset_keys(draft)
    used = set()
    for shot in draft["shots"]:
        for token in shot.get("used_assets", []):
            if token not in declared:
                raise ValueError(f"镜头{shot['shot_no']}使用了未声明资产：{token}")
            used.add(token)
    unused = sorted(declared - used)
    if unused:
        raise ValueError(
            ", ".join(unused) + " 已在资产装填清单声明，但没有任何镜头使用。请删除多余资产或在对应镜头写入使用资产。"
        )
    if mode is Mode.T2VA and any(shot.get("used_assets") for shot in draft["shots"]):
        raise ValueError("T2VA 镜头不应引用资产。")
    if mode is Mode.I2VA:
        illegal = [t for s in draft["shots"] for t in s.get("used_assets", []) if t != "FIRST_FRAME"]
        if illegal:
            raise ValueError(f"I2VA 只能引用首帧，发现：{illegal}")
        if "FIRST_FRAME" not in draft["shots"][0].get("used_assets", []):
            raise ValueError("I2VA 首帧必须归属镜头1，与官方 0.00 秒 [Shot 1] 锚点一致。")
        if any("FIRST_FRAME" in s.get("used_assets", []) for s in draft["shots"][1:]):
            raise ValueError("I2VA 首帧只能作为镜头1的 0.00 秒锚点，不应重新归属后续镜头。")
    if mode is Mode.L2VA:
        illegal = [t for s in draft["shots"] for t in s.get("used_assets", []) if t != "LAST_FRAME"]
        if illegal:
            raise ValueError(f"L2VA 只能引用尾帧，发现：{illegal}")
        if "LAST_FRAME" not in draft["shots"][-1].get("used_assets", []):
            raise ValueError("L2VA 尾帧必须归属最后镜头，与官方视频结束锚点一致。")
        if any("LAST_FRAME" in s.get("used_assets", []) for s in draft["shots"][:-1]):
            raise ValueError("L2VA 尾帧只能作为最后镜头的视频结束锚点，不应归属更早镜头。")
    if mode is Mode.FL2VA:
        illegal = [t for s in draft["shots"] for t in s.get("used_assets", []) if t not in {"FIRST_FRAME", "LAST_FRAME"}]
        if illegal:
            raise ValueError(f"FL2VA 只能引用首帧/尾帧，发现：{illegal}")
        if "FIRST_FRAME" not in draft["shots"][0].get("used_assets", []):
            raise ValueError("FL2VA 首帧必须归属镜头1，与官方 0.00 秒锚点一致。")
        if "LAST_FRAME" not in draft["shots"][-1].get("used_assets", []):
            raise ValueError("FL2VA 尾帧必须归属最后镜头，与官方视频结束锚点一致。")
        if any("FIRST_FRAME" in s.get("used_assets", []) for s in draft["shots"][1:]):
            raise ValueError("FL2VA 首帧只能归属镜头1。")
        if any("LAST_FRAME" in s.get("used_assets", []) for s in draft["shots"][:-1]):
            raise ValueError("FL2VA 尾帧只能归属最后镜头。")
    if mode is Mode.REF2VA:
        illegal = [t for s in draft["shots"] for t in s.get("used_assets", []) if t in {"FIRST_FRAME", "LAST_FRAME"}]
        if illegal:
            raise ValueError("Ref2VA 不使用专用首帧/尾帧标识；需要把关键画面放进 Picture 槽位并标注角色。")


def build_upload_plan_cn(mode: Mode, draft: Dict[str, Any], presentation_map: Dict[str, str] | None = None) -> str:
    a = draft["assets"]
    target_length = h3_length_frames(draft["duration"])
    lines = [
        f"=== H3 资产装填计划｜{mode.value} ===",
        f"名义目标时长={draft['duration']:.2f}秒；当前 ComfyUI H3 length={target_length}帧，实际端点={h3_effective_duration_seconds(draft['duration']):.2f}秒（24fps，17k+5 网格）。",
    ]
    if mode is Mode.T2VA:
        lines.append("无需上传参考素材。")
    elif mode is Mode.I2VA:
        lines.append(f"1. 首帧：{a['first_frame']['label']} → H3 first_frame；Prompt 固定为 <Picture 1>。")
    elif mode is Mode.L2VA:
        lines.append(f"1. 尾帧：{a['last_frame']['label']} → H3 last_frame；Prompt 固定为 <Picture 1>。")
    elif mode is Mode.FL2VA:
        lines.append(f"1. 首帧：{a['first_frame']['label']} → H3 first_frame；Prompt 为 <Picture 1>。")
        lines.append(f"2. 尾帧：{a['last_frame']['label']} → H3 last_frame；Prompt 为 <Picture 2>。")
    else:
        idx = 1
        for slot, meta in sorted(a.get("pictures", {}).items(), key=lambda kv: int(kv[0][1:])):
            lines.append(f"{idx}. {slot} 图片：{meta['label']} → H3 ref_image_{int(slot[1:]) - 1}；最终 Prompt 标签 {presentation_token(slot, presentation_map)}。")
            idx += 1
        for slot, meta in sorted(a.get("videos", {}).items(), key=lambda kv: int(kv[0][1:])):
            lines.append(f"{idx}. {slot} 视频画面：{meta['label']} → H3 ref_video_{int(slot[1:]) - 1}（IMAGE 帧序列，24fps）；最终 Prompt 标签 {presentation_token(slot, presentation_map)}。")
            idx += 1
            va = "VA" + slot[1:]
            if va in a.get("video_audios", {}):
                va_meta = a["video_audios"][va]
                lines.append(f"{idx}. {va} 视频原声：{va_meta['label']} → H3 ref_video_audio_{int(slot[1:]) - 1}；最终 Prompt 标签 {presentation_token(va, presentation_map)}。")
                idx += 1
        for slot, meta in sorted(a.get("audios", {}).items(), key=lambda kv: int(kv[0][1:])):
            lines.append(f"{idx}. {slot} 独立音频：{meta['label']} → H3 ref_audio_{int(slot[1:]) - 1}；最终 Prompt 标签 {presentation_token(slot, presentation_map)}。")
            idx += 1
        lines.append("注意：视频原声 VAx 会先占用 <Audio N>，独立 Ax 的最终 Audio 编号会自动后移；不得手工猜编号。")
        lines.append("Ref2VA：图片≤9、视频≤3、独立音频≤3；视频同步原声由对应视频槽决定；用户独立输入文件总数（图片+视频+独立音频）≤12。")
    lines.append("Codex 必须严格按此计划连接/上传；不得自行重排。")
    return "\n".join(lines)



class H3_ContextWorkbench:
    @classmethod
    def INPUT_TYPES(cls):
        sample = """标题：示例\n总时长：8秒\n\n【资产装填清单】\n首帧：开场参考图\n\n【镜头1】\n时长：8秒\n出场人物：角色甲\n使用资产：首帧\n画面内容：角色甲从静止状态抬眼，看向镜头外的人。镜头缓慢推近。\n对白：\n角色甲：你来了。"""
        optional = {
            "first_frame": ("IMAGE",),
            "last_frame": ("IMAGE",),
            **{f"p{i}": ("IMAGE",) for i in range(1, 10)},
            **{f"v{i}": ("IMAGE",) for i in range(1, 4)},
            **{f"va{i}": ("AUDIO",) for i in range(1, 4)},
            **{f"a{i}": ("AUDIO",) for i in range(1, 4)},
        }
        return {
            "required": {
                "generation_mode": (MODE_CHOICES, {"default": "AUTO"}),
                "contract_profile": (CONTRACT_PROFILES, {"default": CONTRACT_PROFILES[0]}),
                "director_draft_cn": ("STRING", {"multiline": True, "default": sample}),
            },
            "optional": optional,
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "FLOAT", "INT", "IMAGE", "STRING")
    RETURN_NAMES = (
        "resolved_mode", "context_json", "llm_role", "llm_prompt",
        "upload_plan_cn", "validation_report", "target_duration_seconds", "h3_length_frames",
        "vision_sheet", "vision_sheet_labels"
    )
    FUNCTION = "prepare"
    CATEGORY = "H3 Context Compiler"

    def prepare(
        self, generation_mode, contract_profile, director_draft_cn,
        first_frame=None, last_frame=None,
        p1=None, p2=None, p3=None, p4=None, p5=None, p6=None, p7=None, p8=None, p9=None,
        v1=None, v2=None, v3=None, va1=None, va2=None, va3=None, a1=None, a2=None, a3=None,
    ):
        draft = parse_director_draft(director_draft_cn)
        mode = resolve_mode(generation_mode, draft["assets"])
        _validate_shot_asset_usage(mode, draft)

        media_kwargs = {
            "first_frame": first_frame, "last_frame": last_frame,
            "p1": p1, "p2": p2, "p3": p3, "p4": p4, "p5": p5,
            "p6": p6, "p7": p7, "p8": p8, "p9": p9,
            "v1": v1, "v2": v2, "v3": v3,
            "va1": va1, "va2": va2, "va3": va3,
            "a1": a1, "a2": a2, "a3": a3,
        }
        physical_manifest = connected_media_manifest(**media_kwargs)
        validate_physical_media(draft, mode, physical_manifest)

        image_slots = {
            "FIRST_FRAME": first_frame, "LAST_FRAME": last_frame,
            **{f"P{i}": media_kwargs[f"p{i}"] for i in range(1, 10)},
        }
        video_slots = {f"V{i}": media_kwargs[f"v{i}"] for i in range(1, 4)}
        video_audio_slots = {f"VA{i}": media_kwargs[f"va{i}"] for i in range(1, 4)}
        standalone_audio_slots = {f"A{i}": media_kwargs[f"a{i}"] for i in range(1, 4)}
        audio_slots = {**video_audio_slots, **standalone_audio_slots}
        target_length = h3_length_frames(draft["duration"])
        video_metadata = summarize_video_inputs(video_slots, target_length_frames=target_length)
        audio_metadata = summarize_audio_inputs(audio_slots)
        presentation_map = build_ref2va_presentation_map(draft) if mode is Mode.REF2VA else {}
        if mode is Mode.REF2VA:
            validate_ref2va_temporal_limits(video_metadata, audio_metadata)
        vision_sheet, vision_labels = make_multimodal_vision_sheet(
            image_slots, video_slots, target_length_frames=target_length
        )
        media_context = {
            "vision_sheet_labels": vision_labels,
            "video_metadata": video_metadata,
            "audio_metadata": audio_metadata,
            "presentation_map": presentation_map,
            "video_preview_policy": "Each connected V slot is an H3 IMAGE frame sequence; the enrichment LLM sees only labeled 10%, 50%, and 90% preview frames while the full IMAGE frame sequence remains connected to H3.",
            "audio_semantics_policy": "No acoustic semantics are inferred from waveform metadata; original audio stays connected to H3 and its role comes from the locked director draft.",
        }
        role, prompt = build_enrichment_request(mode, draft, media_context=media_context)
        context = {
            "schema_version": "h3-context-2",
            "contract_profile": contract_profile,
            "mode": mode.value,
            "draft": draft,
            "target_generation": {
                "nominal_duration_seconds": float(draft["duration"]),
                "effective_duration_seconds": h3_effective_duration_seconds(draft["duration"]),
                "h3_length_frames": target_length,
                "fps": 24.0,
                "frame_grid": "17k+5",
            },
            "physical_media": physical_manifest,
            "media_context": media_context,
            "presentation_map": presentation_map,
        }
        report = (
            f"导演稿解析通过；模式={mode.value}；时长={draft['duration']:.2f}s；"
            f"镜头={len(draft['shots'])}；物理素材槽位核对通过。"
        )
        return (
            mode.value, json.dumps(context, ensure_ascii=False, indent=2), role, prompt,
            build_upload_plan_cn(mode, draft, presentation_map), report, float(draft["duration"]), target_length,
            vision_sheet, ",".join(vision_labels)
        )


class H3_ContextCompiler:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "context_json": ("STRING", {"multiline": True, "default": "{}"}),
            "llm_response": ("STRING", {"multiline": True, "default": ""}),
        }}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("compiled_prompt", "compile_report")
    FUNCTION = "compile"
    CATEGORY = "H3 Context Compiler"

    def compile(self, context_json, llm_response):
        context = json.loads(context_json or "{}")
        if context.get("schema_version") != "h3-context-2":
            raise ValueError("context_json 不是 h3-context-2。")
        mode = Mode(context["mode"])
        draft = context["draft"]
        if mode is Mode.REF2VA:
            validate_presentation_map(draft, context.get("presentation_map"))
        enrichment = parse_enrichment_response(llm_response, draft)
        prompt = render_prompt(mode, draft, enrichment, context.get("presentation_map"))
        return prompt, f"编译完成：{mode.value}；已使用确定性 Renderer，LLM 未参与编号、时间轴或台词写入。"


class H3_PromptAudit:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "context_json": ("STRING", {"multiline": True, "default": "{}"}),
            "compiled_prompt": ("STRING", {"multiline": True, "default": ""}),
        }}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("audited_prompt", "audit_report")
    FUNCTION = "audit"
    CATEGORY = "H3 Context Compiler"

    def audit(self, context_json, compiled_prompt):
        context = json.loads(context_json or "{}")
        if context.get("schema_version") != "h3-context-2":
            raise ValueError("context_json 不是 h3-context-2。")
        mode = Mode(context["mode"])
        if mode is Mode.REF2VA:
            validate_presentation_map(context["draft"], context.get("presentation_map"))
        report = audit_prompt(mode, compiled_prompt, context["draft"], context.get("presentation_map"))
        return compiled_prompt, report


NODE_CLASS_MAPPINGS = {
    "H3_ContextWorkbench": H3_ContextWorkbench,
    "H3_ContextCompiler": H3_ContextCompiler,
    "H3_PromptAudit": H3_PromptAudit,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3_ContextWorkbench": "H3 通用导演工作台｜自动识别模式",
    "H3_ContextCompiler": "H3 Context-IR 编译器",
    "H3_PromptAudit": "H3 Prompt 硬审计",
}
