# H3 Prompt Compiler

通用 MiniMax H3 Context-IR / Prompt Compiler，自定义 ComfyUI 节点。目标是把**中文导演稿**转换成模式正确、可硬审计的 H3 Prompt，并把 H3 最终语法、引用编号、Speaker、时间轴和锁定台词从上游 GPT / Codex / 豆包等导演模型手里拿走。

> Registry `1.0.0` 是废弃原型。`1.2.0` 是按当前 MiniMax H3 Prompt Guide、ComfyUI H3 原生节点与 Easy Media Reference Bridge 实际媒体 presentation 规则重构的版本。

## 支持模式

- `T2VA`：纯文本
- `I2VA`：首帧
- `FL2VA`：首帧 + 尾帧
- `L2VA`：尾帧
- `Ref2VA`：全参考
- `AUTO`：根据中文导演稿的资产装填清单自动判断

模式与 checkpoint 文件名解耦。只要后续 H3 模型继续遵循相同 Prompt Contract，就可复用同一编译器。

## 节点

### 1. H3 通用导演工作台｜自动识别模式

输入统一中文导演稿，并可连接真实媒体：

- `first_frame`, `last_frame`：IMAGE
- `p1 ... p9`：IMAGE
- `v1 ... v3`：**IMAGE 帧序列**，与当前 ComfyUI / Easy Media H3 `ref_video_N` 一致
- `va1 ... va3`：对应 `v1 ... v3` 的同步原声 AUDIO，映射到 `ref_video_audio_N`
- `a1 ... a3`：独立 AUDIO，映射到 `ref_audio_N`

`VAx` 不是额外的“第四类用户参考槽”，而是 `Vx` 的同步 soundtrack 属性。它之所以单独暴露，是因为当前 H3 ComfyUI 节点把视频画面和视频原声拆成两个输入。

工作台会解析导演稿、判断模式、核对物理连接、计算 H3 最终引用标签、生成 Codex 装填计划，并为外部多模态 LLM 生成 `llm_role` / `llm_prompt` 与一张带标签的视觉联系表。

### 2. H3 Context-IR 编译器

接收工作台 `context_json` 与外部 LLM 返回的英文语义 JSON。LLM 只补语义；程序负责模式 contract、引用标签、Subject、Speaker、镜头切点、台词和最终 H3 结构。

### 3. H3 Prompt 硬审计

按实际模式逐项检查：

- 官方字段结构与顺序
- I2VA / FL2VA / L2VA 对齐指令
- Ref2VA 六段结构
- H3 最终 Picture / Video / Audio 标签
- Shot 编号与切点
- Speaker 稳定编号
- `<d>` 台词原文和数量
- 正文英文约束
- 未声明引用 / 多余引用

任何硬错误直接阻断。

## 为什么 v1.2.0 不再把 P3 写成 `<Picture 3>`

H3 的媒体标签按**实际 presentation 顺序**编号，而不是按你工作流插口名字的尾号照抄。

例如只连接 `P1` 和 `P3`：

```text
P1 -> <Picture 1>
P3 -> <Picture 2>
```

视频同理，`V1 + V3` 会变成 `<Video 1> + <Video 2>`。

音频更特殊。当前 H3 presentation 中，**参考视频的同步 soundtrack 会在该 Video 之前占用一个 `<Audio N>`；所有独立 `A1-A3` 在全部视频之后继续编号。** 因此：

```text
V1 + VA1 + A2
```

实际是：

```text
V1  -> <Video 1>
VA1 -> <Audio 1>
A2  -> <Audio 2>
```

编译器会把这套映射写进 `presentation_map`，Renderer、Audit 和 `upload_plan_cn` 共用同一份映射。上游模型不得自己猜。

## 中文导演稿 v1.2

关键帧模式示例：

```text
标题：示例
总时长：8秒

【资产装填清单】
首帧：开场参考图

【镜头1】
时长：8秒
出场人物：角色甲
使用资产：首帧
画面内容：角色甲从静止状态抬眼，看向镜头外的人，镜头缓慢推近。
现场声音：衣料轻响和安静室内底噪。
对白：
角色甲：你来了。

非画内音乐：无
```

Ref2VA 示例：

```text
标题：混合参考
总时长：6秒

【资产装填清单】
图片1：角色甲角色卡|人物|完全保留
图片3：店铺内景|场景|完全保留
视频1：角色甲走路参考|动作|弱参考
视频1原声：原视频环境声|音频复用|完整复用
视频3：运镜参考|镜头运动|弱参考
音频2：角色甲声音参考|声音参考|参考

【镜头1】
时长：6秒
出场人物：角色甲
使用资产：图片1，图片3，视频1，视频1原声，视频3，音频2
画面内容：角色甲穿过店铺走向门口，镜头跟随。
对白：
角色甲：走。
```

资产格式：`素材名 | 角色 | 可选关系`。

## 视频与音频

- `V1-V3` 使用 H3 真实需要的 IMAGE 帧序列，而不是自定义 `VIDEO` 类型。
- 工作台从每个视频帧序列直接抽取约 10% / 50% / 90% 三张预览，仅给语义 LLM 理解可见状态；这些预览**不会**变成 `<Picture N>`。
- 视频时长按 H3 的 24 fps 合约由帧数计算，并在 Ref2VA 下检查单段 2–15 秒、视频总时长 ≤15 秒。
- `VA1-VA3` 是同编号视频的同步原声；没有对应 `Vx` 时会直接报错。
- `VAx` 与 `Ax` 会进入同一套 H3 `<Audio N>` 连续编号；当前原生节点分别允许最多 3 条视频同步原声和 3 条独立音频，因此最终可能出现 `<Audio 1>` 到 `<Audio 6>`。
- 音频只读取时长/采样率/声道等技术元数据，不靠波形统计臆造音色、台词或音乐内容；语义角色由锁定导演稿指定。

## Codex 装填规则

`upload_plan_cn` 是唯一装填真相。它同时显示：

1. 中文逻辑槽位，例如 `P3 / V1 / VA1 / A2`；
2. 当前 Easy Media / H3 物理输入，例如 `ref_image_2 / ref_video_0 / ref_video_audio_0 / ref_audio_1`；
3. H3 最终 Prompt 标签，例如 `<Picture 2> / <Video 1> / <Audio 1> / <Audio 2>`。

Codex 只能照计划连接/上传，不得重排，也不得根据槽位尾号自己生成 H3 标签。

## Ref2VA 输入限制

编译器按当前官方约束硬挡：

- 图片 ≤9
- 视频 ≤3
- 独立音频 `A1-A3` ≤3；视频同步原声 `VA1-VA3` 由对应 `V1-V3` 决定
- 用户独立输入文件（图片 + 视频 + 独立音频）总数 ≤12
- 独立音频不能作为唯一输入
- 视频原声必须有对应视频

## 语义 LLM 权限边界

LLM 只允许返回：`style_en`、每镜头 `visual_en/camera_en/diegetic_sound_en/dialogue_cues_en`、`overall_soundscape_en`、`non_diegetic_music_en`、`subject_descriptions_en`、`asset_notes_en`。

LLM 不允许生成 H3 section、Picture/Video/Audio/Subject 标签、Shot 标签、`<d>`、镜头时间、Subject/Speaker ID、task type 或 retention relationship。

## 推荐数据流

```text
中文导演稿 + 实际媒体
        │
        ▼
H3 通用导演工作台
  ├─ context_json
  ├─ llm_role / llm_prompt
  ├─ vision_sheet
  └─ upload_plan_cn
        │
        ├──────────────► 多模态 LLM ──► llm_response
        │                                  │
        ▼                                  ▼
        └────────────────────── H3 Context-IR 编译器
                                         │
                                         ▼
                                  H3 Prompt 硬审计
                                         │
                                         ▼
                                  对应 H3 生成节点
```

插件本身不绑定 RunningHub LLM。RunningHub 可接其 LLM Chat；本地也可接 Qwen/GGUF 或其他返回指定 JSON 的多模态 LLM。

## 安装

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/wanski24hours-cmyk/h3-prompt-compiler.git
```

重启后搜索 `H3 Context Compiler`。

## 开发验证

```bash
PYTHONPATH=. pytest -q
python -m compileall -q .
```
