import pytest


def _assets(**overrides):
    assets = {
        "first_frame": None,
        "last_frame": None,
        "pictures": {},
        "videos": {},
        "video_audios": {},
        "audios": {},
    }
    assets.update(overrides)
    return assets


def test_connected_media_manifest_uses_stable_slot_names():
    from h3_prompt_compiler.media import connected_media_manifest

    marker = object()
    manifest = connected_media_manifest(
        first_frame=marker,
        last_frame=None,
        p1=marker,
        p9=marker,
        v1=marker,
        v3=marker,
        a2=marker,
    )
    assert manifest == {
        "FIRST_FRAME": True,
        "LAST_FRAME": False,
        "P1": True,
        "P2": False,
        "P3": False,
        "P4": False,
        "P5": False,
        "P6": False,
        "P7": False,
        "P8": False,
        "P9": True,
        "V1": True,
        "V2": False,
        "V3": True,
        "VA1": False,
        "VA2": False,
        "VA3": False,
        "A1": False,
        "A2": True,
        "A3": False,
    }


def test_declared_media_must_be_physically_connected():
    from h3_prompt_compiler.media import validate_physical_media
    from h3_prompt_compiler.modes import Mode

    draft = {"assets": _assets(pictures={"P1": {"label": "角色甲", "role": "人物", "relationship": ""}})}
    manifest = {"P1": False}
    with pytest.raises(ValueError, match="P1.*未连接"):
        validate_physical_media(draft, Mode.REF2VA, manifest)


def test_connected_but_undeclared_reference_slot_is_blocked():
    from h3_prompt_compiler.media import validate_physical_media
    from h3_prompt_compiler.modes import Mode

    draft = {"assets": _assets(pictures={"P1": {"label": "角色甲", "role": "人物", "relationship": ""}})}
    manifest = {"P1": True, "P2": True}
    with pytest.raises(ValueError, match="P2.*已连接.*未声明"):
        validate_physical_media(draft, Mode.REF2VA, manifest)


def test_keyframe_mode_requires_dedicated_physical_socket():
    from h3_prompt_compiler.media import validate_physical_media
    from h3_prompt_compiler.modes import Mode

    draft = {"assets": _assets(first_frame={"label": "开场图", "role": "参考", "relationship": ""})}
    with pytest.raises(ValueError, match="FIRST_FRAME.*未连接"):
        validate_physical_media(draft, Mode.I2VA, {"FIRST_FRAME": False})


def test_contact_sheet_labels_preserve_picture_order_and_shape():
    torch = pytest.importorskip("torch")
    from h3_prompt_compiler.media import make_labeled_contact_sheet

    # Comfy IMAGE convention: BHWC float in [0, 1].
    p1 = torch.zeros((1, 24, 32, 3), dtype=torch.float32)
    p9 = torch.ones((1, 24, 32, 3), dtype=torch.float32)
    sheet, labels = make_labeled_contact_sheet({"P9": p9, "P1": p1}, tile_width=64, tile_height=48)

    assert labels == ["P1", "P9"]
    assert tuple(sheet.shape) == (1, 48, 128, 3)
    assert float(sheet.min()) >= 0.0
    assert float(sheet.max()) <= 1.0


def test_multimodal_sheet_uses_grid_and_includes_three_preview_frames_per_video():
    torch = pytest.importorskip("torch")
    from h3_prompt_compiler.media import make_multimodal_vision_sheet

    p1 = torch.zeros((1, 32, 48, 3), dtype=torch.float32)
    frames = torch.zeros((48, 32, 48, 3), dtype=torch.float32)
    sheet, labels = make_multimodal_vision_sheet(
        {"P1": p1}, {"V1": frames}, tile_width=80, tile_height=64, columns=2,
    )

    assert labels == ["P1", "V1@10%", "V1@50%", "V1@90%"]
    assert tuple(sheet.shape) == (1, 128, 160, 3)


def test_audio_metadata_reports_duration_channels_and_sample_rate():
    torch = pytest.importorskip("torch")
    from h3_prompt_compiler.media import summarize_audio_inputs

    waveform = torch.zeros((1, 2, 48000), dtype=torch.float32)
    summary = summarize_audio_inputs({"A2": {"waveform": waveform, "sample_rate": 24000}})
    assert summary == {
        "A2": {"sample_rate": 24000, "channels": 2, "duration_seconds": 2.0}
    }


def test_ref2va_temporal_media_limits_reject_short_video_or_audio_and_total_over_15_seconds():
    from h3_prompt_compiler.media import validate_ref2va_temporal_limits

    with pytest.raises(ValueError, match='V1.*2–15'):
        validate_ref2va_temporal_limits({'V1': {'duration_seconds': 1.9}}, {})
    with pytest.raises(ValueError, match='A1.*2–15'):
        validate_ref2va_temporal_limits({}, {'A1': {'duration_seconds': 1.0}})
    with pytest.raises(ValueError, match='视频参考总时长.*15'):
        validate_ref2va_temporal_limits(
            {'V1': {'duration_seconds': 8.0}, 'V2': {'duration_seconds': 8.0}}, {}
        )
    with pytest.raises(ValueError, match='音频参考总时长.*15'):
        validate_ref2va_temporal_limits(
            {}, {'A1': {'duration_seconds': 10.0}, 'A2': {'duration_seconds': 6.0}}
        )


def test_video_metadata_reports_duration_from_h3_image_frames():
    torch = pytest.importorskip("torch")
    from h3_prompt_compiler.media import summarize_video_inputs
    frames = torch.zeros((60, 16, 16, 3), dtype=torch.float32)
    info = summarize_video_inputs({'V2': frames})
    assert info['V2']['frame_count'] == 60
    assert info['V2']['fps'] == 24.0
    assert info['V2']['duration_seconds'] == 2.5


def test_multimodal_sheet_keyframe_labels_use_canonical_internal_names():
    torch = pytest.importorskip('torch')
    from h3_prompt_compiler.media import make_multimodal_vision_sheet
    first = torch.zeros((1, 24, 32, 3), dtype=torch.float32)
    last = torch.ones((1, 24, 32, 3), dtype=torch.float32)
    _, labels = make_multimodal_vision_sheet(
        {'FIRST_FRAME': first, 'LAST_FRAME': last}, {}, tile_width=64, tile_height=48,
    )
    assert labels == ['FIRST_FRAME', 'LAST_FRAME']


def test_ref2va_audio_duration_total_applies_to_standalone_audio_not_coupled_video_soundtracks():
    from h3_prompt_compiler.media import validate_ref2va_temporal_limits

    validate_ref2va_temporal_limits(
        {
            'V1': {'duration_seconds': 5.0},
            'V2': {'duration_seconds': 5.0},
            'V3': {'duration_seconds': 5.0},
        },
        {
            'VA1': {'duration_seconds': 5.0},
            'VA2': {'duration_seconds': 5.0},
            'VA3': {'duration_seconds': 5.0},
            'A1': {'duration_seconds': 5.0},
            'A2': {'duration_seconds': 5.0},
            'A3': {'duration_seconds': 5.0},
        },
    )


def test_h3_length_frame_binding_matches_current_comfy_h3_17k_plus_5_grid():
    from h3_prompt_compiler.media import h3_length_frames
    assert h3_length_frames(8.0) == 192
    assert h3_length_frames(12.0) == 294
    assert h3_length_frames(15.0) == 362


def test_effective_h3_duration_is_derived_from_aligned_frame_count():
    from h3_prompt_compiler.media import h3_effective_duration_seconds
    assert h3_effective_duration_seconds(6.0) == pytest.approx(158 / 24.0)
    assert h3_effective_duration_seconds(8.0) == pytest.approx(8.0)
    assert h3_effective_duration_seconds(15.0) == pytest.approx(362 / 24.0)
