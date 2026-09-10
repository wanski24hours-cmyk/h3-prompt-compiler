import json
import re
from typing import Dict, List

EMPTY_VALUES = {"", "空", "无", "none", "null", "未使用", "关闭"}

TITLE_RE = re.compile(r"^标题\s*[:：]\s*(.+)$")
TOTAL_RE = re.compile(r"^总时长\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)\s*秒?$")
SHOT_RE = re.compile(r"^【镜头\s*([0-9]+)】$")
DURATION_RE = re.compile(r"^时长\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)\s*秒?$")
CAST_RE = re.compile(r"^出场人物\s*[:：]\s*(.+)$")
USE_RE = re.compile(r"^使用资产\s*[:：]\s*(.*)$")
SCENE_RE = re.compile(r"^画面内容\s*[:：]\s*(.+)$")
DIALOGUE_RE = re.compile(r"^([^：:]+)\s*[：:]\s*(.*)$")
IMG_RE = re.compile(r"^图片槽位\s*([1-9])\s*[:：]\s*(.*)$")
VID_RE = re.compile(r"^视频槽位\s*([1-3])\s*[:：]\s*(.*)$")
AUD_RE = re.compile(r"^音频槽位\s*([1-3])\s*[:：]\s*(.*)$")

SEC_IMAGES = "【本条需要上传的图片参考资产】"
SEC_VIDEOS = "【本条需要上传的视频参考资产】"
SEC_AUDIOS = "【本条需要上传的音频参考资产】"
SEC_FREE = "【本条不需要上传、让H3自行生成的主体】"


def _lines(text: str) -> List[str]:
    return [x.strip() for x in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def _asset(raw: str) -> Dict:
    raw = (raw or "").strip()
    if raw.lower() in EMPTY_VALUES:
        return {"label": "空", "type": "empty", "enabled": False}
    parts = [p.strip() for p in raw.split("|") if p.strip()]
    return {
        "label": parts[0] if parts else raw,
        "type": parts[1] if len(parts) > 1 else "未标注",
        "enabled": True,
    }


def _slot_token(slot: str) -> str:
    if slot.startswith("P"):
        return f"<Picture {slot[1:]}>"
    if slot.startswith("V"):
        return f"<Video {slot[1:]}>"
    if slot.startswith("A"):
        return f"<Audio {slot[1:]}>"
    return slot


def _normalize_slot_name(value: str) -> str:
    v = value.strip().replace(" ", "")
    replacements = (("图片槽位", "P"), ("视频槽位", "V"), ("音频槽位", "A"))
    for prefix, short in replacements:
        if v.startswith(prefix):
            return short + v[len(prefix):]
    return v.upper()


class DirectorDraftParser:
    @staticmethod
    def parse(text: str) -> Dict:
        lines = _lines(text)
        if not any(lines):
            raise ValueError("导演稿为空。")

        out = {
            "title": None,
            "total_duration": None,
            "image_assets": {},
            "video_assets": {},
            "audio_assets": {},
            "free_subjects": [],
            "shots": [],
        }
        i = 0
        while i < len(lines):
            line = lines[i]
            if not line:
                i += 1
                continue
            m = TITLE_RE.match(line)
            if m:
                out["title"] = m.group(1).strip(); i += 1; continue
            m = TOTAL_RE.match(line)
            if m:
                out["total_duration"] = float(m.group(1)); i += 1; continue

            if line in (SEC_IMAGES, SEC_VIDEOS, SEC_AUDIOS):
                sec = line
                regex = IMG_RE if sec == SEC_IMAGES else VID_RE if sec == SEC_VIDEOS else AUD_RE
                key = "image_assets" if sec == SEC_IMAGES else "video_assets" if sec == SEC_VIDEOS else "audio_assets"
                prefix = "P" if sec == SEC_IMAGES else "V" if sec == SEC_VIDEOS else "A"
                i += 1
                while i < len(lines) and lines[i] and not lines[i].startswith("【"):
                    mm = regex.match(lines[i])
                    if not mm:
                        raise ValueError(f"资产区格式错误：{lines[i]}")
                    out[key][f"{prefix}{mm.group(1)}"] = _asset(mm.group(2))
                    i += 1
                continue

            if line == SEC_FREE:
                i += 1
                while i < len(lines) and lines[i] and not lines[i].startswith("【"):
                    out["free_subjects"].append(lines[i])
                    i += 1
                continue

            sm = SHOT_RE.match(line)
            if sm:
                shot = {"shot_no": int(sm.group(1)), "duration": None, "cast": [], "used_assets": [], "scene": "", "dialogues": []}
                i += 1
                dialogue_mode = False
                while i < len(lines):
                    cur = lines[i]
                    if not cur:
                        i += 1
                        continue
                    if cur.startswith("【镜头") or (cur.startswith("【") and cur.endswith("】")):
                        break
                    if cur.startswith("对白"):
                        dialogue_mode = True; i += 1; continue
                    if dialogue_mode:
                        dm = DIALOGUE_RE.match(cur)
                        if not dm:
                            raise ValueError(f"对白行格式错误：{cur}")
                        shot["dialogues"].append({"speaker": dm.group(1).strip(), "text": dm.group(2).strip()})
                        i += 1
                        continue
                    dm = DURATION_RE.match(cur)
                    if dm:
                        shot["duration"] = float(dm.group(1)); i += 1; continue
                    cm = CAST_RE.match(cur)
                    if cm:
                        shot["cast"] = [x.strip() for x in re.split(r"[，,]", cm.group(1)) if x.strip()]; i += 1; continue
                    um = USE_RE.match(cur)
                    if um:
                        shot["used_assets"] = [_normalize_slot_name(x) for x in re.split(r"[，,]", um.group(1)) if x.strip()]; i += 1; continue
                    scm = SCENE_RE.match(cur)
                    if scm:
                        shot["scene"] = scm.group(1).strip(); i += 1; continue
                    if shot["scene"]:
                        shot["scene"] += " " + cur; i += 1; continue
                    i += 1
                out["shots"].append(shot)
                continue
            i += 1

        if not out["title"]:
            raise ValueError("导演稿缺少“标题：”。")
        if out["total_duration"] is None:
            raise ValueError("导演稿缺少“总时长：”。")
        if not out["shots"]:
            raise ValueError("导演稿没有任何【镜头N】块。")

        for n in range(1, 10):
            out["image_assets"].setdefault(f"P{n}", _asset("空"))
        for n in range(1, 4):
            out["video_assets"].setdefault(f"V{n}", _asset("空"))
            out["audio_assets"].setdefault(f"A{n}", _asset("空"))
        return out


def _manifest(img: List[str], vid: List[str], aud: List[str]) -> Dict:
    return {
        "images": {f"P{i+1}": _asset(v) for i, v in enumerate(img)},
        "videos": {f"V{i+1}": _asset(v) for i, v in enumerate(vid)},
        "audios": {f"A{i+1}": _asset(v) for i, v in enumerate(aud)},
    }


def _all_manifest_slots(manifest: Dict) -> Dict[str, Dict]:
    merged = {}
    merged.update(manifest.get("images", {}))
    merged.update(manifest.get("videos", {}))
    merged.update(manifest.get("audios", {}))
    return merged


def _validate(draft: Dict, manifest: Dict) -> List[str]:
    errors = []
    total = 0.0
    slots = _all_manifest_slots(manifest)

    groups = (("image_assets", "images"), ("video_assets", "videos"), ("audio_assets", "audios"))
    for draft_key, manifest_key in groups:
        for slot, declared in draft[draft_key].items():
            actual = manifest.get(manifest_key, {}).get(slot, _asset("空"))
            if declared["enabled"]:
                if not actual["enabled"]:
                    errors.append(f"导演稿声明 {slot}={declared['label']}，但实际槽位为空。")
                elif actual["label"] != declared["label"]:
                    errors.append(f"{slot} 资产名不一致：导演稿“{declared['label']}”，实际“{actual['label']}”。")

    for shot in draft["shots"]:
        if shot["duration"] is None:
            errors.append(f"镜头{shot['shot_no']}缺少时长。")
        else:
            total += shot["duration"]
        if not shot["cast"]:
            errors.append(f"镜头{shot['shot_no']}缺少出场人物。")
        if not shot["scene"]:
            errors.append(f"镜头{shot['shot_no']}缺少画面内容。")
        cast = set(shot["cast"])
        for d in shot["dialogues"]:
            if d["speaker"] not in cast:
                errors.append(f"镜头{shot['shot_no']}：{d['speaker']}有对白但不在出场人物中。")
            if not d["text"]:
                errors.append(f"镜头{shot['shot_no']}：{d['speaker']}台词为空。")
        for slot in shot["used_assets"]:
            if slot not in slots:
                errors.append(f"镜头{shot['shot_no']}使用未知槽位：{slot}。")
            elif not slots[slot]["enabled"]:
                errors.append(f"镜头{shot['shot_no']}使用了空槽位：{slot}。")

    if abs(total - draft["total_duration"]) > 0.05:
        errors.append(f"镜头时长总和为 {total:.2f} 秒，但总时长为 {draft['total_duration']:.2f} 秒。")
    return errors


def _resolve_character_slot(name: str, draft: Dict):
    for slot, meta in draft["image_assets"].items():
        if not meta["enabled"] or meta["type"] != "人物":
            continue
        if name == meta["label"] or name in meta["label"] or meta["label"] in name:
            return slot
    return None


def _subjects(draft: Dict) -> List[Dict]:
    names = []
    def add(name):
        if name and name not in names:
            names.append(name)
    for shot in draft["shots"]:
        for d in shot["dialogues"]:
            add(d["speaker"])
        for c in shot["cast"]:
            add(c)
    for n in draft["free_subjects"]:
        add(n)
    return [{"id": i + 1, "name": n, "ref_slot": _resolve_character_slot(n, draft)} for i, n in enumerate(names)]


def _compile(draft: Dict) -> str:
    subjects = _subjects(draft)
    by_name = {x["name"]: x for x in subjects}

    subject_lines = []
    for s in subjects:
        if s["ref_slot"]:
            subject_lines.append(f"Subject {s['id']}: {s['name']}，人物身份与外观严格参考 {_slot_token(s['ref_slot'])}。")
        else:
            subject_lines.append(f"Subject {s['id']}: {s['name']}，无直接人物参考，由模型生成，并在整条视频中保持一致。")

    retention = []
    for kind in ("image_assets", "video_assets", "audio_assets"):
        for slot, meta in draft[kind].items():
            if not meta["enabled"]:
                continue
            if kind == "image_assets" and meta["type"] == "人物":
                continue
            retention.append(f"{_slot_token(slot)} 对应“{meta['label']}”，在相关镜头中严格保留其关键视觉/运动/声音信息。")

    summaries, details, dialogue = [], [], []
    t = 0.0
    for shot in draft["shots"]:
        start, end = t, t + shot["duration"]
        t = end
        used = "、".join(f"{slot}={_slot_token(slot)}" for slot in shot["used_assets"]) or "无"
        cast = "、".join(shot["cast"])
        summaries.append(f"镜头{shot['shot_no']}（{start:.1f}-{end:.1f}s）：{shot['scene']}")
        details.append(
            f"镜头{shot['shot_no']}，{start:.1f}-{end:.1f}s，出场人物：{cast}。使用参考：{used}。{shot['scene']}"
        )
        for d in shot["dialogues"]:
            s = by_name[d["speaker"]]
            dialogue.append(f"<Subject {s['id']}> (S{s['id']}):\n<d>{d['text']}</d>")

    return (
        f"subject_definitions:\n{' '.join(subject_lines)}\n\n"
        f"summary:\n{' '.join(summaries)}\n\n"
        f"retention_analysis:\n{' '.join(retention) if retention else '保持所有已声明人物、场景、道具、动作和声音参考的一致性。'}\n\n"
        f"detailed_description:\n{' '.join(details)}\n\n"
        f"dialogue_plan:\n{'\n\n'.join(dialogue) if dialogue else 'N/A'}\n\n"
        f"overall_soundscape:\n根据导演稿和已声明音频参考生成自然、连贯、与空间和动作一致的声音；对白清晰，台词文本不得改写。\n\n"
        f"non_diegetic_music:\n仅在导演稿明确要求时加入非画内音乐；未明确要求则 N/A。"
    )


class H3_AssetBinder_9P3V3A:
    @classmethod
    def INPUT_TYPES(cls):
        req = {}
        for p in [f"p{i}" for i in range(1, 10)] + [f"v{i}" for i in range(1, 4)] + [f"a{i}" for i in range(1, 4)]:
            req[p] = ("STRING", {"default": "空", "multiline": False})
        return {"required": req}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("asset_manifest_json", "asset_manifest_report")
    FUNCTION = "bind"
    CATEGORY = "H3 Prompt Compiler"

    def bind(self, p1, p2, p3, p4, p5, p6, p7, p8, p9, v1, v2, v3, a1, a2, a3):
        manifest = _manifest([p1,p2,p3,p4,p5,p6,p7,p8,p9], [v1,v2,v3], [a1,a2,a3])
        rows = ["=== H3 参考资产槽位 ==="]
        for group in ("images", "videos", "audios"):
            for slot, meta in manifest[group].items():
                rows.append(f"{slot}: {meta['label']} | {meta['type']} | {'启用' if meta['enabled'] else '空'}")
        return json.dumps(manifest, ensure_ascii=False, indent=2), "\n".join(rows)


class H3_DirectorCompiler:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "director_draft": ("STRING", {"multiline": True, "default": "标题：测试\n总时长：15秒\n"}),
            "asset_manifest_json": ("STRING", {"multiline": True, "default": "{}"}),
        }}

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("compiled_prompt", "draft_ir_json", "compile_report")
    FUNCTION = "compile"
    CATEGORY = "H3 Prompt Compiler"

    def compile(self, director_draft, asset_manifest_json):
        try:
            draft = DirectorDraftParser.parse(director_draft)
            manifest = json.loads(asset_manifest_json or "{}")
        except Exception as e:
            return "", "{}", f"编译失败：{e}"
        errors = _validate(draft, manifest)
        ir = json.dumps(draft, ensure_ascii=False, indent=2)
        if errors:
            return "", ir, "编译失败：\n- " + "\n- ".join(errors)
        prompt = _compile(draft)
        used_p = [k for k,v in draft["image_assets"].items() if v["enabled"]]
        used_v = [k for k,v in draft["video_assets"].items() if v["enabled"]]
        used_a = [k for k,v in draft["audio_assets"].items() if v["enabled"]]
        report = (
            f"编译成功：{draft['title']}\n"
            f"总时长：{draft['total_duration']:.1f}秒；镜头数：{len(draft['shots'])}\n"
            f"图片：{', '.join(used_p) or '无'}；视频：{', '.join(used_v) or '无'}；音频：{', '.join(used_a) or '无'}"
        )
        return prompt, ir, report


class H3_PromptAudit:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "compiled_prompt": ("STRING", {"multiline": True, "default": ""}),
            "draft_ir_json": ("STRING", {"multiline": True, "default": "{}"}),
            "asset_manifest_json": ("STRING", {"multiline": True, "default": "{}"}),
        }}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("audited_prompt", "audit_report")
    FUNCTION = "audit"
    CATEGORY = "H3 Prompt Compiler"

    def audit(self, compiled_prompt, draft_ir_json, asset_manifest_json):
        if not (compiled_prompt or "").strip():
            raise ValueError("审计失败：上游 compiled_prompt 为空。")
        draft = json.loads(draft_ir_json or "{}")
        manifest = json.loads(asset_manifest_json or "{}")
        slots = _all_manifest_slots(manifest)
        errors = []

        for prefix, pattern in (("P", r"<Picture\s+([0-9]+)>"), ("V", r"<Video\s+([0-9]+)>"), ("A", r"<Audio\s+([0-9]+)>")):
            for n in re.findall(pattern, compiled_prompt):
                slot = prefix + n
                if slot not in slots or not slots[slot]["enabled"]:
                    errors.append(f"Prompt 引用了空或不存在的槽位 {slot}。")

        for shot in draft.get("shots", []):
            for d in shot.get("dialogues", []):
                if f"<d>{d['text']}</d>" not in compiled_prompt:
                    errors.append(f"台词未原样保留：{d['speaker']}：{d['text']}")

        required_sections = (
            "subject_definitions:", "summary:", "retention_analysis:",
            "detailed_description:", "dialogue_plan:", "overall_soundscape:", "non_diegetic_music:"
        )
        for sec in required_sections:
            if sec not in compiled_prompt:
                errors.append(f"缺少 H3 段落：{sec}")

        if errors:
            raise ValueError("审计失败：\n- " + "\n- ".join(errors))
        return compiled_prompt, "审计通过：参考槽位、台词原文、H3核心段落均通过。"


NODE_CLASS_MAPPINGS = {
    "H3_AssetBinder_9P3V3A": H3_AssetBinder_9P3V3A,
    "H3_DirectorCompiler": H3_DirectorCompiler,
    "H3_PromptAudit": H3_PromptAudit,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3_AssetBinder_9P3V3A": "H3 资产绑定器｜9图3视频3音频",
    "H3_DirectorCompiler": "H3 中文导演稿编译器",
    "H3_PromptAudit": "H3 提示词硬审计",
}
