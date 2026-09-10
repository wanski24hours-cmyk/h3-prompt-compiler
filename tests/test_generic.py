import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))


def sample_draft():
    return '''标题：通用H3测试
总时长：15秒

【本条需要上传的图片参考资产】
图片槽位1：角色甲角色卡|人物
图片槽位2：角色乙角色卡|人物
图片槽位3：空
图片槽位4：室内场景|场景
图片槽位5：关键道具|道具
图片槽位6：空
图片槽位7：空
图片槽位8：空
图片槽位9：空

【本条需要上传的视频参考资产】
视频槽位1：动作参考|动作
视频槽位2：空
视频槽位3：空

【本条需要上传的音频参考资产】
音频槽位1：情绪参考|声音
音频槽位2：空
音频槽位3：空

【本条不需要上传、让H3自行生成的主体】
路人

【镜头1】
时长：7秒
出场人物：角色甲，角色乙
使用资产：图片槽位1，图片槽位2，图片槽位4，视频槽位1
画面内容：角色甲走向角色乙，镜头缓慢跟随。
对白：
角色甲：你来了。

【镜头2】
时长：8秒
出场人物：角色乙，角色甲，路人
使用资产：图片槽位1，图片槽位2，图片槽位5，音频槽位1
画面内容：角色乙转身回应，路人从背景经过。
对白：
角色乙：刚到。'''


def test_generic_package_imports_and_names_are_not_project_specific():
    from h3_prompt_compiler_plugin import nodes
    assert 'H3_AssetBinder_9P3V3A' in nodes.NODE_CLASS_MAPPINGS
    assert 'H3_DirectorCompiler' in nodes.NODE_CLASS_MAPPINGS
    assert 'H3_PromptAudit' in nodes.NODE_CLASS_MAPPINGS
    joined = ' '.join(nodes.NODE_DISPLAY_NAME_MAPPINGS.values())
    assert '小破观' not in joined
    assert 'XPG' not in joined


def test_compiler_supports_9_images_3_videos_3_audios_and_preserves_dialogue():
    from h3_prompt_compiler_plugin import nodes
    binder = nodes.H3_AssetBinder_9P3V3A()
    manifest_json, _ = binder.bind(
        '角色甲角色卡|人物','角色乙角色卡|人物','空','室内场景|场景','关键道具|道具','空','空','空','空',
        '动作参考|动作','空','空',
        '情绪参考|声音','空','空'
    )
    compiler = nodes.H3_DirectorCompiler()
    prompt, ir, report = compiler.compile(sample_draft(), manifest_json)
    assert '编译成功' in report
    assert '<Picture 1>' in prompt
    assert '<Picture 2>' in prompt
    assert '<Video 1>' in prompt
    assert '<Audio 1>' in prompt
    assert '<d>你来了。</d>' in prompt
    assert '<d>刚到。</d>' in prompt
    assert '小破观' not in prompt
    assert '黑色幽默' not in prompt


def test_audit_blocks_empty_or_unknown_slot_reference():
    from h3_prompt_compiler_plugin import nodes
    binder = nodes.H3_AssetBinder_9P3V3A()
    manifest_json, _ = binder.bind(
        '角色甲角色卡|人物','角色乙角色卡|人物','空','室内场景|场景','关键道具|道具','空','空','空','空',
        '空','空','空','空','空','空'
    )
    compiler = nodes.H3_DirectorCompiler()
    broken = sample_draft().replace('视频槽位1：动作参考|动作', '视频槽位1：空')
    prompt, ir, report = compiler.compile(broken, manifest_json)
    assert prompt == ''
    assert '空槽位' in report or '为空' in report


def test_duration_mismatch_is_blocked_before_h3():
    from h3_prompt_compiler_plugin import nodes
    binder = nodes.H3_AssetBinder_9P3V3A()
    manifest_json, _ = binder.bind(
        '角色甲角色卡|人物','角色乙角色卡|人物','空','室内场景|场景','关键道具|道具','空','空','空','空',
        '动作参考|动作','空','空',
        '情绪参考|声音','空','空'
    )
    bad = sample_draft().replace('时长：8秒', '时长：7秒')
    compiler = nodes.H3_DirectorCompiler()
    prompt, _, report = compiler.compile(bad, manifest_json)
    assert prompt == ''
    assert '总时长' in report


def test_node_input_count_matches_9p3v3a_contract():
    from h3_prompt_compiler_plugin import nodes
    required = nodes.H3_AssetBinder_9P3V3A.INPUT_TYPES()['required']
    assert list(required) == [
        'p1','p2','p3','p4','p5','p6','p7','p8','p9',
        'v1','v2','v3','a1','a2','a3'
    ]
