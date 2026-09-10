from h3_prompt_compiler.renderers import render_prompt
from h3_prompt_compiler.modes import Mode


def draft(mode_assets=None):
    return {
        'title':'测试', 'duration':8.0,
        'assets': mode_assets or {'first_frame':None,'last_frame':None,'pictures':{},'videos':{},'audios':{}},
        'free_subjects':[],
        'shots':[
            {'shot_no':1,'start':0.0,'duration':3.0,'cast':['甲'],'used_assets':[], 'scene':'甲抬头。','dialogue':[{'speaker':'甲','text':'你好。'}]},
            {'shot_no':2,'start':3.0,'duration':5.0,'cast':['甲'],'used_assets':[], 'scene':'甲转身。','dialogue':[]},
        ]
    }


def enrichment():
    return {
        'style_en':'Live-action, cinematic.',
        'shots':[
            {'shot_no':1,'visual_en':'A young man raises his head in a narrow room.','camera_en':'The camera pushes in slowly.','diegetic_sound_en':'Soft fabric movement is audible.','dialogue_cues_en':['with a calm, direct delivery']},
            {'shot_no':2,'visual_en':'The same man turns toward the doorway.','camera_en':'The camera cuts to a medium shot.','diegetic_sound_en':'Light footsteps continue.','dialogue_cues_en':[]},
        ],
        'overall_soundscape_en':'Low room ambience with soft fabric movement and light footsteps.',
        'non_diegetic_music_en':'N/A',
        'subject_descriptions_en':{'甲':'a young man with short dark hair'},
        'asset_notes_en':{},
    }


def assert_three_core_fields_only(prompt):
    assert prompt.count('integrated_multimodal_description:') == 1
    assert prompt.count('overall_soundscape:') == 1
    assert prompt.count('non_diegetic_music:') == 1
    assert 'subject_definitions:' not in prompt
    assert 'retention_analysis:' not in prompt


def test_t2va_renders_base_three_field_contract():
    p = render_prompt(Mode.T2VA, draft(), enrichment())
    assert p.startswith('integrated_multimodal_description: [Shot 1]')
    assert '[Shot 2] At 00:03.000,' in p
    assert '<d>[Chinese] 你好。</d>' in p
    assert_three_core_fields_only(p)


def test_i2va_uses_exact_first_frame_instruction():
    d = draft({'first_frame':{'label':'开场'},'last_frame':None,'pictures':{},'videos':{},'audios':{}})
    p = render_prompt(Mode.I2VA, d, enrichment())
    assert p.startswith('For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n')
    assert_three_core_fields_only(p)


def test_fl2va_uses_exact_first_last_alignment_instruction():
    d = draft({'first_frame':{'label':'开场'},'last_frame':{'label':'结尾'},'pictures':{},'videos':{},'audios':{}})
    p = render_prompt(Mode.FL2VA, d, enrichment())
    assert p.startswith('How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot 2) aligns with the 8.00-second mark of the target video.\n\n')
    assert_three_core_fields_only(p)


def test_l2va_uses_exact_last_frame_alignment_instruction():
    d = draft({'first_frame':None,'last_frame':{'label':'结尾'},'pictures':{},'videos':{},'audios':{}})
    p = render_prompt(Mode.L2VA, d, enrichment())
    assert p.startswith('How the reference pictures align with the target video — <Picture 1> (from [Shot 2]) aligns with the 8.00-second mark of the target video.\n\n')
    assert_three_core_fields_only(p)


def test_ref2va_renders_exact_six_sections_and_no_dialogue_plan():
    a = {
        'first_frame':None,'last_frame':None,
        'pictures':{'P1':{'label':'角色甲','role':'人物'},'P2':{'label':'房间','role':'场景'}},
        'videos':{},'audios':{}
    }
    d = draft(a)
    d['shots'][0]['used_assets']=['P1','P2']
    d['shots'][1]['used_assets']=['P1','P2']
    e = enrichment()
    e['asset_notes_en']={'P1':'identity reference','P2':'room layout reference'}
    p = render_prompt(Mode.REF2VA, d, e)
    sections = ['subject_definitions:','summary:','retention_analysis:','detailed_description:','overall_soundscape:','non_diegetic_music:']
    assert all(s in p for s in sections)
    assert [p.index(s) for s in sections] == sorted(p.index(s) for s in sections)
    assert 'dialogue_plan:' not in p
    assert '<Subject 1>' in p
    assert '<Picture 1>' in p
    assert '<Picture 2>' in p
    assert '[Shot 2] At 00:03.000,' in p
    assert '<d>[Chinese] 你好。</d>' in p

def test_ref2va_video_editing_does_not_force_reference_generation_task_type():
    a = {
        'first_frame':None,'last_frame':None,
        'pictures':{},
        'videos':{'V1':{'label':'原视频','role':'视频编辑'}},
        'audios':{}
    }
    d = draft(a)
    d['shots'][0]['used_assets']=['V1']
    d['shots'][1]['used_assets']=['V1']
    e = enrichment()
    e['asset_notes_en']={'V1':'the source video being edited'}
    p = render_prompt(Mode.REF2VA, d, e)
    assert '[video editing]' in p
    assert '[video editing + reference generation]' not in p

def test_ref2va_groups_multiple_assets_for_same_subject_into_one_subject():
    a = {
        'first_frame':None,'last_frame':None,
        'pictures':{'P1':{'label':'角色甲','role':'人物','relationship':''}},
        'videos':{'V1':{'label':'角色甲','role':'动作','relationship':''}},
        'audios':{}
    }
    d = draft(a)
    d['shots'][0]['used_assets']=['P1','V1']
    d['shots'][1]['used_assets']=['P1','V1']
    e = enrichment()
    e['asset_notes_en']={'P1':'appearance and identity reference','V1':'walking motion reference'}
    p = render_prompt(Mode.REF2VA, d, e)
    subject_defs = p.split('summary:',1)[0]
    assert subject_defs.count('<Subject 1>') == 1
    assert '<Subject 2>' not in subject_defs
    assert '<Picture 1>' in subject_defs and '<Video 1>' in subject_defs


def test_ref2va_video_editing_summary_uses_official_opening_sentence():
    a = {
        'first_frame':None,'last_frame':None,'pictures':{},
        'videos':{'V1':{'label':'原视频','role':'视频编辑','relationship':''}},'audios':{}
    }
    d = draft(a)
    d['shots'][0]['used_assets']=['V1']
    d['shots'][1]['used_assets']=['V1']
    e = enrichment()
    e['asset_notes_en']={'V1':'the source video for the editing task'}
    p = render_prompt(Mode.REF2VA, d, e)
    assert 'summary:\n[video editing] The target video is an edited version of <Video 1>.' in p


def test_ref2va_integrates_reference_roles_in_shot_instead_of_vague_active_list():
    a = {
        'first_frame':None,'last_frame':None,
        'pictures':{'P1':{'label':'角色甲','role':'人物','relationship':''}},
        'videos':{'V1':{'label':'镜头运动参考','role':'镜头运动','relationship':'弱参考'}},
        'audios':{'A1':{'label':'角色甲声音参考','role':'声音参考','relationship':'参考'}},
    }
    d = draft(a)
    d['shots'][0]['used_assets']=['P1','V1','A1']
    d['shots'][1]['used_assets']=['P1']
    e = enrichment()
    e['asset_notes_en']={
        'P1':'appearance and identity reference',
        'V1':'camera movement and pacing reference',
        'A1':'voice timbre and delivery reference',
    }
    p = render_prompt(Mode.REF2VA, d, e)
    detail = p.split('detailed_description:\n',1)[1].split('\n\noverall_soundscape:',1)[0]
    assert 'Referenced content active in this shot' not in detail
    assert '<Subject 1> follows its defined reference identity and attributes in this shot.' in detail
    assert 'This shot uses <Video 1> as camera movement and pacing reference.' in detail
    assert 'The audible performance uses <Audio 1> as voice timbre and delivery reference.' in detail


def test_renderer_preserves_locked_visible_scene_text_in_original_language():
    d = draft()
    d['shots'][0]['visible_text'] = ['今日歇业']
    p = render_prompt(Mode.T2VA, d, enrichment())
    assert 'Visible on-screen text reads "今日歇业" exactly.' in p


def test_dialogue_subject_phrase_does_not_generate_double_article_grammar():
    d = draft()
    e = enrichment()
    e['subject_descriptions_en']['甲'] = 'an adult man with short dark hair'
    p = render_prompt(Mode.T2VA, d, e)
    assert 'The an adult man' not in p
    assert 'An adult man with short dark hair (S1) says' in p


def test_ref2va_dual_role_picture_gets_subject_definition_and_standalone_keyframe_definition():
    a = {
        'first_frame':None,'last_frame':None,
        'pictures':{'P1':{'label':'角色甲','role':'人物+关键帧','relationship':'完全保留'}},
        'videos':{},'audios':{}
    }
    d = draft(a)
    d['shots'][0]['used_assets']=['P1']
    d['shots'][1]['used_assets']=['P1']
    e = enrichment()
    e['asset_notes_en']={'P1':'the character appearance and shot-composition anchor'}
    p = render_prompt(Mode.REF2VA, d, e)
    definitions = p.split('\n\nsummary:',1)[0]
    assert '<Subject 1> is' in definitions
    assert '<Picture 1> is the character appearance and shot-composition anchor.' in definitions
    retention = p.split('retention_analysis:\n',1)[1].split('\n\ndetailed_description:',1)[0]
    assert '<Subject 1>' in retention
    assert '<Picture 1>:' in retention


def test_ref2va_dual_role_edit_video_gets_subject_definition_and_standalone_video_definition():
    a = {
        'first_frame':None,'last_frame':None,'pictures':{},
        'videos':{'V1':{'label':'角色甲','role':'人物+视频编辑','relationship':'完全保留'}},
        'audios':{}
    }
    d = draft(a)
    d['shots'][0]['used_assets']=['V1']
    d['shots'][1]['used_assets']=['V1']
    e = enrichment()
    e['asset_notes_en']={'V1':'the character appearance and source video for the editing task'}
    p = render_prompt(Mode.REF2VA, d, e)
    definitions = p.split('\n\nsummary:',1)[0]
    assert '<Subject 1> is' in definitions
    assert '<Video 1> is the character appearance and source video for the editing task.' in definitions
    assert 'summary:\n[video editing + reference generation] The target video is an edited version of <Video 1>.' in p
    retention = p.split('retention_analysis:\n',1)[1].split('\n\ndetailed_description:',1)[0]
    assert '<Subject 1>' in retention
    assert '<Video 1>:' in retention


def test_ref2va_mixed_audio_roles_emit_both_audio_reuse_and_audio_reference_task_types():
    a = {
        'first_frame':None,'last_frame':None,
        'pictures':{'P1':{'label':'角色甲','role':'人物','relationship':''}},
        'videos':{},
        'audios':{
            'A1':{'label':'原始配乐','role':'音频复用','relationship':'完整复用'},
            'A2':{'label':'角色甲声音','role':'声音参考','relationship':'参考'},
        },
    }
    d = draft(a)
    d['shots'][0]['used_assets']=['P1','A1','A2']
    d['shots'][1]['used_assets']=['P1']
    e = enrichment()
    e['asset_notes_en']={
        'P1':'appearance and identity reference',
        'A1':'the original music signal reused in the target',
        'A2':'voice timbre and delivery reference',
    }
    p = render_prompt(Mode.REF2VA, d, e)
    assert '[reference generation + audio reuse + audio reference]' in p


def test_ref2va_audio_retention_uses_audio_marker_vocabulary_not_visual_markers():
    a = {
        'first_frame':None,'last_frame':None,
        'pictures':{'P1':{'label':'角色甲','role':'人物','relationship':''}},
        'videos':{},
        'audios':{
            'A1':{'label':'完整音轨','role':'音频复用','relationship':'最终音轨完整复制'},
            'A2':{'label':'部分音轨','role':'部分复用','relationship':'部分保留'},
            'A3':{'label':'氛围参考','role':'声音参考','relationship':'弱参考'},
        },
    }
    d = draft(a)
    d['shots'][0]['used_assets']=['P1','A1','A2','A3']
    d['shots'][1]['used_assets']=['P1']
    e = enrichment()
    e['asset_notes_en']={
        'P1':'appearance reference', 'A1':'complete source audio',
        'A2':'selected source audio layers', 'A3':'broad ambience reference',
    }
    p = render_prompt(Mode.REF2VA, d, e)
    retention = p.split('retention_analysis:\n',1)[1].split('\n\ndetailed_description:',1)[0]
    assert '<Audio 1>: fully_copy -' in retention
    assert '<Audio 2>: partially_copy -' in retention
    assert '<Audio 3>: weak_reference -' in retention
    assert '<Audio 1>: fully_preserved' not in retention



def test_ref2va_places_style_opening_before_shot1_per_official_contract():
    a = {
        'first_frame':None,'last_frame':None,
        'pictures':{'P1':{'label':'角色甲','role':'人物','relationship':'完全保留'}},
        'videos':{},'audios':{}
    }
    d = draft(a)
    d['shots'][0]['used_assets']=['P1']
    d['shots'][1]['used_assets']=['P1']
    e = enrichment()
    e['asset_notes_en']={'P1':'identity reference'}
    prompt = render_prompt(Mode.REF2VA, d, e)
    detail = prompt.split('detailed_description:\n', 1)[1].split('\n\noverall_soundscape:', 1)[0]
    assert detail.startswith(e['style_en'].rstrip('. ') + '.\n[Shot 1]')


def test_ref2va_reused_video_soundtrack_is_described_as_reused_audio_not_audible_performance():
    a = {
        'first_frame': None, 'last_frame': None,
        'pictures': {'P1': {'label': '角色甲', 'role': '人物', 'relationship': '完全保留'}},
        'videos': {'V1': {'label': '动作参考', 'role': '动作', 'relationship': '弱参考'}},
        'video_audios': {'VA1': {'label': '原视频环境声', 'role': '音频复用', 'relationship': '完整复用'}},
        'audios': {},
    }
    d = draft(a)
    d['shots'][0]['used_assets'] = ['P1', 'V1', 'VA1']
    d['shots'][1]['used_assets'] = ['P1']
    e = enrichment()
    e['asset_notes_en'] = {
        'P1': 'identity reference',
        'V1': 'walking motion reference',
        'VA1': 'the synchronized source ambience',
    }
    mapping = {'P1': '<Picture 1>', 'V1': '<Video 1>', 'VA1': '<Audio 1>'}
    p = render_prompt(Mode.REF2VA, d, e, presentation_map=mapping)
    detail = p.split('detailed_description:\n', 1)[1].split('\n\noverall_soundscape:', 1)[0]
    assert 'This shot reuses <Audio 1> as the synchronized source ambience.' in detail
    assert 'The audible performance uses <Audio 1>' not in detail


def test_generic_audio_reuse_role_defaults_to_partial_copy_unless_full_copy_is_explicit():
    from h3_prompt_compiler.renderers import _relationship_from_meta
    assert _relationship_from_meta('A1', {'role': '音频复用', 'relationship': ''}) == 'partially_copy'
    assert _relationship_from_meta('A1', {'role': '音频复用', 'relationship': '最终音轨完整复制'}) == 'fully_copy'


def test_fl2va_alignment_uses_effective_h3_duration_not_unaligned_nominal_seconds():
    d = draft({'first_frame':{'label':'开场'},'last_frame':{'label':'结尾'},'pictures':{},'videos':{},'video_audios':{},'audios':{}})
    d['duration'] = 6.0
    d['shots'] = [
        {'shot_no':1,'start':0.0,'duration':2.0,'cast':['甲'],'used_assets':['FIRST_FRAME'], 'scene':'甲抬头。','dialogue':[{'speaker':'甲','text':'你好。'}]},
        {'shot_no':2,'start':2.0,'duration':4.0,'cast':['甲'],'used_assets':['LAST_FRAME'], 'scene':'甲转身。','dialogue':[]},
    ]
    p = render_prompt(Mode.FL2VA, d, enrichment())
    # Current ComfyUI H3 snaps 6.00s to 158 frames = 6.5833s, so the official
    # last-frame instruction must use the effective endpoint rounded to 2 decimals.
    assert 'aligns with the 6.58-second mark of the target video.' in p


def test_l2va_alignment_uses_effective_h3_duration_not_unaligned_nominal_seconds():
    d = draft({'first_frame':None,'last_frame':{'label':'结尾'},'pictures':{},'videos':{},'video_audios':{},'audios':{}})
    d['duration'] = 15.0
    d['shots'] = [
        {'shot_no':1,'start':0.0,'duration':15.0,'cast':['甲'],'used_assets':['LAST_FRAME'], 'scene':'甲逐渐停下。','dialogue':[{'speaker':'甲','text':'你好。'}]},
    ]
    e = enrichment()
    e['shots'] = [e['shots'][0]]
    p = render_prompt(Mode.L2VA, d, e)
    assert 'aligns with the 15.08-second mark of the target video.' in p


def test_audio_fully_copy_requires_explicit_final_track_semantics_not_generic_preserve_wording():
    from h3_prompt_compiler.renderers import _relationship_from_meta
    assert _relationship_from_meta('A1', {'role': '音频复用', 'relationship': '完全保留'}) == 'partially_copy'
    assert _relationship_from_meta('A1', {'role': '音频复用', 'relationship': '完整复用'}) == 'partially_copy'
    assert _relationship_from_meta('A1', {'role': '音频复用', 'relationship': '最终音轨完整复制'}) == 'fully_copy'
    assert _relationship_from_meta('A1', {'role': '声音参考', 'relationship': '完全保留'}) == 'reference'
