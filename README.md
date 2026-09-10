# H3 Prompt Compiler

通用 MiniMax H3 / ComfyUI 中文导演稿编译与硬审计插件。

## 核心目标
让 GPT / Codex / 豆包只输出中文导演稿：参考资产、镜头、动作、台词。
插件负责把导演稿确定性编译成 H3 Prompt，并在进入 H3 生成节点前做硬审计。

## 节点

### 1. H3 资产绑定器｜9图3视频3音频
内部节点名：`H3_AssetBinder_9P3V3A`

支持：
- 图片 P1-P9
- 视频 V1-V3
- 音频 A1-A3

每个槽位填写：
- `角色甲角色卡|人物`
- `大厅场景|场景`
- `木箱|道具`
- `走路动作参考|动作`
- `声音情绪参考|声音`
- 不使用时填 `空`

### 2. H3 中文导演稿编译器
内部节点名：`H3_DirectorCompiler`

输入：
- 中文导演稿
- 资产绑定器输出的 `asset_manifest_json`

输出：
- `compiled_prompt`
- `draft_ir_json`
- `compile_report`

### 3. H3 提示词硬审计
内部节点名：`H3_PromptAudit`

检查：
- Prompt 是否引用空槽位/不存在槽位
- 中文导演稿中的台词是否原样进入 `<d>...</d>`
- H3 核心段落是否完整
- 上游编译失败时阻断

审计通过后的 `audited_prompt` 再连接 H3 的 `prompt` 输入。

## 中文导演稿格式
见 `examples/通用中文导演稿示例.txt`。

## 推荐连接

```text
H3 资产绑定器｜9图3视频3音频
        │ asset_manifest_json
        ▼
H3 中文导演稿编译器
        │ compiled_prompt + draft_ir_json
        ▼
H3 提示词硬审计
        │ audited_prompt
        ▼
MiniMax H3 ReferenceToVideo / 对应 H3 prompt 输入
```

## 安装
把整个仓库目录放入：

```text
ComfyUI/custom_nodes/h3_prompt_compiler_plugin/
```

然后重启 ComfyUI。

如果平台使用 Git 仓库安装：

```bash
cd ComfyUI/custom_nodes
git clone <你的仓库地址> h3_prompt_compiler_plugin
```

本插件当前没有额外 Python 第三方依赖。

## 当前版本边界
当前版本是确定性编译器，不调用外部 LLM，不需要 GGUF/mmproj。
因此它不会自行“润色”导演稿；它只把结构化中文导演稿转成 H3 结构并审计。

后续可在保持硬编译/硬审计不变的前提下，再增加：
- 自动扫描 H3 当前已连接的 P/V/A 参考槽
- `@` 选择参考素材
- 可选视觉 LLM 扩写层
- RunningHub API/Codex 无人值守资产 manifest 自动生成
