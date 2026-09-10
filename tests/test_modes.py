import pytest
from h3_prompt_compiler.modes import Mode, resolve_mode, validate_mode_assets


def assets(**kwargs):
    base = {
        'first_frame': None,
        'last_frame': None,
        'pictures': {},
        'videos': {},
        'video_audios': {},
        'audios': {},
    }
    base.update(kwargs)
    return base


def test_auto_detects_text_mode_without_assets():
    assert resolve_mode('AUTO', assets()) is Mode.T2VA


def test_auto_detects_first_frame_mode():
    assert resolve_mode('AUTO', assets(first_frame={'label':'开场'})) is Mode.I2VA


def test_auto_detects_last_frame_mode():
    assert resolve_mode('AUTO', assets(last_frame={'label':'结尾'})) is Mode.L2VA


def test_auto_detects_first_last_mode():
    assert resolve_mode('AUTO', assets(first_frame={'label':'开场'}, last_frame={'label':'结尾'})) is Mode.FL2VA


def test_auto_detects_full_reference_mode():
    assert resolve_mode('AUTO', assets(pictures={'P1':{'label':'角色'}})) is Mode.REF2VA


def test_mixing_keyframe_and_full_reference_assets_is_rejected():
    a = assets(first_frame={'label':'开场'}, pictures={'P1':{'label':'角色'}})
    with pytest.raises(ValueError, match='不能同时'):
        resolve_mode('AUTO', a)


def test_ref2va_limits_and_audio_only_rule():
    ok = assets(
        pictures={f'P{i}':{'label':str(i)} for i in range(1, 7)},
        videos={f'V{i}':{'label':str(i)} for i in range(1, 4)},
        audios={f'A{i}':{'label':str(i)} for i in range(1, 4)},
    )
    validate_mode_assets(Mode.REF2VA, ok)

    too_many = assets(pictures={f'P{i}':{'label':str(i)} for i in range(1, 10)}, videos={f'V{i}':{'label':str(i)} for i in range(1, 4)}, audios={'A1':{'label':'x'}})
    with pytest.raises(ValueError, match='12'):
        validate_mode_assets(Mode.REF2VA, too_many)

    with pytest.raises(ValueError, match='音频不能作为唯一输入'):
        validate_mode_assets(Mode.REF2VA, assets(audios={'A1':{'label':'voice'}}))


def test_ref2va_direct_video_edit_source_must_be_first_active_video_so_it_maps_to_video1():
    # Sparse physical slots compact: V2 alone is the first presented video and therefore becomes <Video 1>.
    validate_mode_assets(Mode.REF2VA, assets(videos={'V2': {'label': '原视频', 'role': '视频编辑'}}))

    bad = assets(videos={
        'V1': {'label': '运镜参考', 'role': '镜头运动'},
        'V2': {'label': '原视频', 'role': '视频编辑'},
    })
    with pytest.raises(ValueError, match='视频编辑.*第一个.*Video 1'):
        validate_mode_assets(Mode.REF2VA, bad)


def test_ref2va_native_contract_allows_three_video_soundtracks_plus_three_standalone_audio_inputs():
    a = assets(
        videos={f'V{i}': {'label': f'video{i}', 'role': '动作'} for i in range(1, 4)},
        video_audios={f'VA{i}': {'label': f'soundtrack{i}', 'role': '音频复用'} for i in range(1, 4)},
        audios={f'A{i}': {'label': f'audio{i}', 'role': '声音参考'} for i in range(1, 4)},
    )
    validate_mode_assets(Mode.REF2VA, a)


def test_ref2va_rejects_multiple_direct_video_edit_sources():
    bad = assets(videos={
        'V1': {'label': '原视频甲', 'role': '视频编辑'},
        'V2': {'label': '原视频乙', 'role': '视频编辑'},
    })
    with pytest.raises(ValueError, match='只能有一个.*视频编辑'):
        validate_mode_assets(Mode.REF2VA, bad)
