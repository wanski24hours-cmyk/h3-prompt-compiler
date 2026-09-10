import json
from pathlib import Path

import pytest

from h3_prompt_compiler.draft import parse_director_draft
from h3_prompt_compiler.modes import Mode, resolve_mode
from h3_prompt_compiler.llm_ir import parse_enrichment_response
from h3_prompt_compiler.renderers import render_prompt
from h3_prompt_compiler.audit import audit_prompt

ROOT = Path(__file__).resolve().parents[1]


def _asset_keys(draft):
    a = draft['assets']
    keys = list(a.get('pictures', {})) + list(a.get('videos', {})) + list(a.get('video_audios', {})) + list(a.get('audios', {}))
    if a.get('first_frame'):
        keys.append('FIRST_FRAME')
    if a.get('last_frame'):
        keys.append('LAST_FRAME')
    return keys


def _mock_enrichment(draft):
    subjects = []
    for shot in draft['shots']:
        for name in shot.get('cast', []):
            if name not in subjects:
                subjects.append(name)
    for name in draft.get('free_subjects', []):
        if name not in subjects:
            subjects.append(name)

    payload = {
        'schema_version': 'h3-enrichment-1',
        'style_en': 'Live-action cinematic staging with natural lighting and physically plausible motion.',
        'shots': [],
        'overall_soundscape_en': 'Natural room or location ambience continues under synchronized physical action sounds.',
        'non_diegetic_music_en': 'N/A',
        'subject_descriptions_en': {
            name: f'a consistently identifiable on-screen subject corresponding to cast member {index + 1}'
            for index, name in enumerate(subjects)
        },
        'asset_notes_en': {
            slot: 'the declared reference role and its observable visual or audio characteristics'
            for slot in _asset_keys(draft)
        },
    }
    for shot in draft['shots']:
        payload['shots'].append({
            'shot_no': shot['shot_no'],
            'visual_en': 'The locked action and spatial relationships develop exactly as described by the director draft.',
            'camera_en': 'The camera movement follows the locked shot direction with controlled amplitude and speed.',
            'diegetic_sound_en': 'Synchronized physical sounds follow the locked actions in the shot.',
            'dialogue_cues_en': ['with a natural delivery matched to the locked dramatic beat'] * len(shot.get('dialogue', [])),
        })
    return json.dumps(payload, ensure_ascii=False)


@pytest.mark.parametrize(
    ('filename', 'expected_mode'),
    [
        ('t2va.txt', Mode.T2VA),
        ('i2va.txt', Mode.I2VA),
        ('fl2va.txt', Mode.FL2VA),
        ('l2va.txt', Mode.L2VA),
        ('ref2va.txt', Mode.REF2VA),
    ],
)
def test_example_director_drafts_compile_and_pass_mode_specific_hard_audit(filename, expected_mode):
    draft = parse_director_draft((ROOT / 'examples' / filename).read_text(encoding='utf-8'))
    mode = resolve_mode('AUTO', draft['assets'])
    assert mode is expected_mode

    enrichment = parse_enrichment_response(_mock_enrichment(draft), draft)
    prompt = render_prompt(mode, draft, enrichment)
    report = audit_prompt(mode, prompt, draft)
    assert f'审计通过：{mode.value}' in report

    if mode is Mode.T2VA:
        assert prompt.startswith('integrated_multimodal_description: [Shot 1]')
    elif mode is Mode.I2VA:
        assert prompt.startswith('For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n')
    elif mode is Mode.FL2VA:
        assert prompt.startswith('How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video;')
    elif mode is Mode.L2VA:
        assert prompt.startswith('How the reference pictures align with the target video — <Picture 1>')
    else:
        expected_sections = [
            'subject_definitions:', 'summary:', 'retention_analysis:',
            'detailed_description:', 'overall_soundscape:', 'non_diegetic_music:'
        ]
        assert [prompt.index(x) for x in expected_sections] == sorted(prompt.index(x) for x in expected_sections)
