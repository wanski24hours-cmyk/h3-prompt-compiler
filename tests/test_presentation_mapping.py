import json

import pytest

from h3_prompt_compiler.draft import parse_director_draft
from h3_prompt_compiler.media import build_ref2va_presentation_map, connected_media_manifest
from h3_prompt_compiler.modes import Mode
from h3_prompt_compiler.renderers import render_prompt
from h3_prompt_compiler.audit import audit_prompt


def _draft_text():
    return '''标题：混合参考
总时长：6秒

【资产装填清单】
图片1：角色甲|人物|完全保留
图片3：场景|场景|完全保留
视频1：动作参考|动作|弱参考
视频1原声：原视频环境声|音频复用|完整复用
视频3：运镜参考|镜头运动|弱参考
音频2：角色甲声音|声音参考|参考

【镜头1】
时长：6秒
出场人物：角色甲
使用资产：图片1，图片3，视频1，视频1原声，视频3，音频2
画面内容：角色甲在场景中向前走。
对白：
角色甲：走。'''


def _enrichment(draft):
    return {
        'schema_version': 'h3-enrichment-1',
        'style_en': 'Live-action cinematic staging with natural light.',
        'shots': [{
            'shot_no': 1,
            'visual_en': 'The subject walks forward through the referenced environment.',
            'camera_en': 'The camera tracks forward at a controlled speed.',
            'diegetic_sound_en': 'Footsteps and room tone remain synchronized.',
            'dialogue_cues_en': ['with a concise natural delivery'],
        }],
        'overall_soundscape_en': 'Natural ambience and synchronized footsteps remain audible.',
        'non_diegetic_music_en': 'N/A',
        'subject_descriptions_en': {'角色甲': 'an adult man with stable appearance'},
        'asset_notes_en': {
            'P1': 'identity and appearance reference',
            'P3': 'environment layout reference',
            'V1': 'walking motion reference',
            'VA1': 'the synchronized source ambience reused from the first reference video',
            'V3': 'camera movement reference',
            'A2': 'voice timbre reference',
        },
    }


def test_parser_supports_video_soundtrack_as_coupled_asset_and_shot_reference():
    draft = parse_director_draft(_draft_text())
    assert draft['assets']['video_audios']['VA1']['label'] == '原视频环境声'
    assert 'VA1' in draft['shots'][0]['used_assets']


def test_presentation_map_compresses_sparse_picture_video_slots_and_numbers_video_soundtrack_before_standalone_audio():
    draft = parse_director_draft(_draft_text())
    mapping = build_ref2va_presentation_map(draft)
    assert mapping['P1'] == '<Picture 1>'
    assert mapping['P3'] == '<Picture 2>'
    assert mapping['V1'] == '<Video 1>'
    assert mapping['V3'] == '<Video 2>'
    assert mapping['VA1'] == '<Audio 1>'
    assert mapping['A2'] == '<Audio 2>'


def test_renderer_and_audit_use_resolved_h3_labels_not_logical_slot_numbers():
    draft = parse_director_draft(_draft_text())
    mapping = build_ref2va_presentation_map(draft)
    prompt = render_prompt(Mode.REF2VA, draft, _enrichment(draft), presentation_map=mapping)
    assert '<Picture 2>' in prompt
    assert '<Picture 3>' not in prompt
    assert '<Video 2>' in prompt
    assert '<Video 3>' not in prompt
    assert '<Audio 1>' in prompt  # V1 soundtrack
    assert '<Audio 2>' in prompt  # logical A2
    report = audit_prompt(Mode.REF2VA, prompt, draft, presentation_map=mapping)
    assert '审计通过：Ref2VA' in report


def test_ref2va_can_number_three_video_soundtracks_plus_three_standalone_audios_in_native_presentation_order():
    text = '''标题：六个Audio标签
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
    assert mapping['VA1'] == '<Audio 1>'
    assert mapping['VA2'] == '<Audio 2>'
    assert mapping['VA3'] == '<Audio 3>'
    assert mapping['A1'] == '<Audio 4>'
    assert mapping['A2'] == '<Audio 5>'
    assert mapping['A3'] == '<Audio 6>'


def test_physical_manifest_has_coupled_video_audio_slots():
    marker = object()
    manifest = connected_media_manifest(v1=marker, va1=marker, a1=marker)
    assert manifest['V1'] is True
    assert manifest['VA1'] is True
    assert manifest['A1'] is True

def test_context_compiler_rejects_missing_or_tampered_ref2va_presentation_map():
    from h3_prompt_compiler.nodes import H3_ContextCompiler
    draft = parse_director_draft(_draft_text())
    context = {
        'schema_version': 'h3-context-2',
        'mode': 'Ref2VA',
        'draft': draft,
        'presentation_map': {},
    }
    with pytest.raises(ValueError, match='presentation_map'):
        H3_ContextCompiler().compile(json.dumps(context, ensure_ascii=False), json.dumps(_enrichment(draft), ensure_ascii=False))

    context['presentation_map'] = build_ref2va_presentation_map(draft)
    context['presentation_map']['A2'] = '<Audio 1>'
    with pytest.raises(ValueError, match='presentation_map'):
        H3_ContextCompiler().compile(json.dumps(context, ensure_ascii=False), json.dumps(_enrichment(draft), ensure_ascii=False))
