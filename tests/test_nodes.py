def test_comfy_nodes_register_generic_mode_aware_workflow():
    import importlib.util
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('h3_plugin_root', root / '__init__.py', submodule_search_locations=[str(root)])
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules['h3_plugin_root'] = module
    spec.loader.exec_module(module)
    assert 'H3_ContextWorkbench' in module.NODE_CLASS_MAPPINGS
    assert 'H3_ContextCompiler' in module.NODE_CLASS_MAPPINGS
    assert 'H3_PromptAudit' in module.NODE_CLASS_MAPPINGS
    names = ' '.join(module.NODE_DISPLAY_NAME_MAPPINGS.values())
    assert '小破观' not in names
    assert 'Ref2VA' not in names  # plugin identity is H3-wide, not one mode


def test_workbench_exposes_real_keyframe_and_9p3v3a_media_sockets():
    from h3_prompt_compiler.nodes import H3_ContextWorkbench

    inputs = H3_ContextWorkbench.INPUT_TYPES()
    optional = inputs["optional"]
    assert optional["first_frame"][0] == "IMAGE"
    assert optional["last_frame"][0] == "IMAGE"
    assert [optional[f"p{i}"][0] for i in range(1, 10)] == ["IMAGE"] * 9
    assert [optional[f"v{i}"][0] for i in range(1, 4)] == ["IMAGE"] * 3
    assert [optional[f"va{i}"][0] for i in range(1, 4)] == ["AUDIO"] * 3
    assert [optional[f"a{i}"][0] for i in range(1, 4)] == ["AUDIO"] * 3


def test_workbench_returns_vision_sheet_output_for_external_multimodal_llm():
    from h3_prompt_compiler.nodes import H3_ContextWorkbench

    assert H3_ContextWorkbench.RETURN_NAMES[-2:] == ("vision_sheet", "vision_sheet_labels")
    assert H3_ContextWorkbench.RETURN_TYPES[-2:] == ("IMAGE", "STRING")


def test_root_entrypoints_load_when_comfy_executes_them_without_package_context():
    import importlib.util
    import pathlib
    import sys

    root = pathlib.Path(__file__).resolve().parents[1]
    for filename in ('__init__.py', 'nodes.py'):
        module_name = 'standalone_' + filename.replace('.', '_')
        spec = importlib.util.spec_from_file_location(module_name, root / filename)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        assert 'H3_ContextWorkbench' in module.NODE_CLASS_MAPPINGS


def test_workbench_feeds_image_and_video_preview_labels_plus_audio_metadata_into_llm_context(tmp_path):
    import json
    import pytest
    torch = pytest.importorskip('torch')
    from h3_prompt_compiler.nodes import H3_ContextWorkbench

    video_frames = torch.zeros((60, 32, 48, 3), dtype=torch.float32)

    draft = '''标题：多参测试
总时长：4秒
【资产装填清单】
图片1：角色甲角色卡|人物
视频1：角色甲动作参考|动作
音频1：角色甲声音参考|声音参考
【镜头1】
时长：4秒
出场人物：角色甲
使用资产：图片1，视频1，音频1
画面内容：角色甲向前走两步并停下。
对白：
角色甲：到了。'''
    image = torch.zeros((1, 32, 48, 3), dtype=torch.float32)
    audio = {'waveform': torch.zeros((1, 2, 64000)), 'sample_rate': 32000}
    out = H3_ContextWorkbench().prepare(
        'AUTO', 'MiniMax H3 Official 2026-08', draft,
        p1=image, v1=video_frames, a1=audio,
    )
    context = json.loads(out[1])
    assert context['mode'] == 'Ref2VA'
    assert context['media_context']['vision_sheet_labels'] == ['P1','V1@10%','V1@50%','V1@90%']
    assert context['media_context']['audio_metadata']['A1']['duration_seconds'] == 2.0
    assert 'V1@50%' in out[3]
    assert 'audio_metadata' in out[3]
    values = dict(zip(H3_ContextWorkbench.RETURN_NAMES, out))
    assert values['vision_sheet_labels'] == 'P1,V1@10%,V1@50%,V1@90%'


def test_workbench_enforces_ref2va_video_audio_duration_limits_before_llm(tmp_path):
    import pytest
    torch = pytest.importorskip('torch')
    from h3_prompt_compiler.nodes import H3_ContextWorkbench

    short_frames = torch.zeros((24, 32, 48, 3), dtype=torch.float32)

    draft = '''标题：短视频参考
总时长：4秒
【资产装填清单】
图片1：角色甲|人物
视频1：动作参考|动作
【镜头1】
时长：4秒
出场人物：角色甲
使用资产：图片1，视频1
画面内容：角色甲向前走。
对白：'''
    image = torch.zeros((1, 32, 48, 3), dtype=torch.float32)
    with pytest.raises(ValueError, match='V1.*2–15'):
        H3_ContextWorkbench().prepare(
            'AUTO', 'MiniMax H3 Official 2026-08', draft,
            p1=image, v1=short_frames,
        )


def test_declared_assets_must_be_used_by_at_least_one_shot():
    import pytest
    from h3_prompt_compiler.nodes import _validate_shot_asset_usage
    from h3_prompt_compiler.modes import Mode

    draft = {
        'assets': {
            'first_frame': None, 'last_frame': None,
            'pictures': {
                'P1': {'label':'角色甲','role':'人物','relationship':''},
                'P2': {'label':'没用到的场景','role':'场景','relationship':''},
            },
            'videos': {}, 'video_audios': {}, 'audios': {},
        },
        'shots': [
            {'shot_no':1, 'used_assets':['P1']},
        ],
    }
    with pytest.raises(ValueError, match='P2.*声明.*没有任何镜头使用'):
        _validate_shot_asset_usage(Mode.REF2VA, draft)


def test_root_init_can_self_bootstrap_when_plugin_directory_is_not_on_sys_path(tmp_path):
    import pathlib
    import subprocess
    import sys

    root = pathlib.Path(__file__).resolve().parents[1]
    script = tmp_path / 'probe.py'
    script.write_text(f'''
import importlib.util, sys
root = r"{root}"
sys.path = [p for p in sys.path if p not in (root, '')]
spec = importlib.util.spec_from_file_location("standalone_h3_plugin", root + "/__init__.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert "H3_ContextWorkbench" in mod.NODE_CLASS_MAPPINGS
print("ok")
''', encoding='utf-8')
    proc = subprocess.run([sys.executable, str(script)], text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == 'ok'


def test_workbench_video_preview_policy_describes_actual_h3_image_frame_sequence_contract():
    import json
    import pytest
    torch = pytest.importorskip('torch')
    from h3_prompt_compiler.nodes import H3_ContextWorkbench

    draft = '''标题：视频帧接口
总时长：4秒
【资产装填清单】
图片1：角色|人物
视频1：动作参考|动作
【镜头1】
时长：4秒
出场人物：角色
使用资产：图片1，视频1
画面内容：角色向前走。
对白：'''
    image = torch.zeros((1, 32, 48, 3), dtype=torch.float32)
    frames = torch.zeros((48, 32, 48, 3), dtype=torch.float32)
    out = H3_ContextWorkbench().prepare(
        'AUTO', 'MiniMax H3 Official 2026-08', draft, p1=image, v1=frames,
    )
    context = json.loads(out[1])
    policy = context['media_context']['video_preview_policy']
    assert 'IMAGE frame sequence' in policy
    assert 'original video stays connected' not in policy


def test_ref2va_upload_plan_does_not_claim_video_soundtracks_and_standalone_audio_share_a_three_label_cap():
    from h3_prompt_compiler.draft import parse_director_draft
    from h3_prompt_compiler.media import build_ref2va_presentation_map
    from h3_prompt_compiler.modes import Mode
    from h3_prompt_compiler.nodes import build_upload_plan_cn

    text = '''标题：六音频标签计划
总时长：4秒
【资产装填清单】
视频1：视频甲|动作
视频1原声：甲原声|音频复用
视频2：视频乙|动作
视频2原声：乙原声|音频复用
视频3：视频丙|动作
视频3原声：丙原声|音频复用
音频1：声音甲|声音参考
音频2：声音乙|声音参考
音频3：声音丙|声音参考
【镜头1】
时长：4秒
出场人物：角色
使用资产：视频1，视频1原声，视频2，视频2原声，视频3，视频3原声，音频1，音频2，音频3
画面内容：角色走动。
对白：'''
    draft = parse_director_draft(text)
    mapping = build_ref2va_presentation_map(draft)
    plan = build_upload_plan_cn(Mode.REF2VA, draft, mapping)
    assert '<Audio 6>' in plan
    assert 'Audio 标签（视频原声+独立音频）≤3' not in plan
    assert '独立音频≤3' in plan


def test_workbench_outputs_duration_and_h3_length_binding_so_downstream_length_cannot_drift_silently():
    from h3_prompt_compiler.nodes import H3_ContextWorkbench

    draft = '''标题：时长绑定
总时长：12秒
【资产装填清单】
【镜头1】
时长：12秒
出场人物：甲
使用资产：无
画面内容：甲站在门口。
对白：'''
    out = H3_ContextWorkbench().prepare('AUTO', 'MiniMax H3 Official 2026-08', draft)
    names = H3_ContextWorkbench.RETURN_NAMES
    values = dict(zip(names, out))
    assert values['target_duration_seconds'] == 12.0
    assert values['h3_length_frames'] == 294
    assert 'H3 length=294帧' in values['upload_plan_cn']
    context = __import__('json').loads(values['context_json'])
    assert context['target_generation']['nominal_duration_seconds'] == 12.0
    assert context['target_generation']['effective_duration_seconds'] == 12.25
    assert '实际端点=12.25秒' in values['upload_plan_cn']


def test_i2va_first_frame_must_be_assigned_to_shot1_not_a_later_shot():
    import pytest
    from h3_prompt_compiler.nodes import _validate_shot_asset_usage
    from h3_prompt_compiler.modes import Mode
    draft = {
        'assets': {'first_frame': {'label':'开场','role':'参考','relationship':''}, 'last_frame':None, 'pictures':{},'videos':{},'video_audios':{},'audios':{}},
        'shots': [
            {'shot_no':1,'used_assets':[]},
            {'shot_no':2,'used_assets':['FIRST_FRAME']},
        ],
    }
    with pytest.raises(ValueError, match='I2VA.*首帧.*镜头1'):
        _validate_shot_asset_usage(Mode.I2VA, draft)


def test_l2va_last_frame_must_be_assigned_to_actual_final_shot():
    import pytest
    from h3_prompt_compiler.nodes import _validate_shot_asset_usage
    from h3_prompt_compiler.modes import Mode
    draft = {
        'assets': {'first_frame':None, 'last_frame': {'label':'结尾','role':'参考','relationship':''}, 'pictures':{},'videos':{},'video_audios':{},'audios':{}},
        'shots': [
            {'shot_no':1,'used_assets':['LAST_FRAME']},
            {'shot_no':2,'used_assets':[]},
        ],
    }
    with pytest.raises(ValueError, match='L2VA.*尾帧.*最后镜头'):
        _validate_shot_asset_usage(Mode.L2VA, draft)


def test_fl2va_keyframes_must_be_assigned_to_opening_and_final_shots():
    import pytest
    from h3_prompt_compiler.nodes import _validate_shot_asset_usage
    from h3_prompt_compiler.modes import Mode
    draft = {
        'assets': {'first_frame': {'label':'开场','role':'参考','relationship':''}, 'last_frame': {'label':'结尾','role':'参考','relationship':''}, 'pictures':{},'videos':{},'video_audios':{},'audios':{}},
        'shots': [
            {'shot_no':1,'used_assets':['LAST_FRAME']},
            {'shot_no':2,'used_assets':['FIRST_FRAME']},
        ],
    }
    with pytest.raises(ValueError, match='FL2VA.*首帧.*镜头1'):
        _validate_shot_asset_usage(Mode.FL2VA, draft)
