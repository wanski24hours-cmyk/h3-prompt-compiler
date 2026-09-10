import torch

from h3_prompt_compiler.media import make_multimodal_vision_sheet, summarize_video_inputs
from h3_prompt_compiler.nodes import H3_ContextWorkbench


def test_context_workbench_video_inputs_are_image_frame_batches_and_exposes_paired_soundtracks():
    optional = H3_ContextWorkbench.INPUT_TYPES()['optional']
    assert optional['v1'][0] == 'IMAGE'
    assert optional['v2'][0] == 'IMAGE'
    assert optional['v3'][0] == 'IMAGE'
    assert optional['va1'][0] == 'AUDIO'
    assert optional['va2'][0] == 'AUDIO'
    assert optional['va3'][0] == 'AUDIO'


def test_video_duration_is_derived_from_image_frame_count_at_h3_24fps():
    frames = torch.zeros((72, 8, 8, 3), dtype=torch.float32)
    metadata = summarize_video_inputs({'V1': frames})
    assert metadata['V1']['frame_count'] == 72
    assert metadata['V1']['fps'] == 24.0
    assert metadata['V1']['duration_seconds'] == 3.0


def test_video_preview_sheet_samples_image_batch_directly_without_file_path():
    frames = torch.zeros((48, 8, 8, 3), dtype=torch.float32)
    frames[4] = 0.1
    frames[24] = 0.5
    frames[43] = 0.9
    sheet, labels = make_multimodal_vision_sheet({}, {'V1': frames}, tile_width=64, tile_height=64, columns=3)
    assert sheet is not None
    assert labels == ['V1@10%', 'V1@50%', 'V1@90%']


def test_reference_video_preview_and_metadata_are_limited_to_frames_h3_will_present_for_target_length():
    import pytest
    torch = pytest.importorskip('torch')
    from h3_prompt_compiler.media import summarize_video_inputs, _video_preview_tiles

    # 240 source frames (10s) but the target clip length is 107 frames (~4.46s on H3's grid).
    frames = torch.arange(240, dtype=torch.float32).view(240, 1, 1, 1).repeat(1, 1, 1, 3)
    meta = summarize_video_inputs({'V1': frames}, target_length_frames=107)['V1']
    assert meta['source_frame_count'] == 240
    assert meta['effective_frame_count'] == 107
    assert meta['source_duration_seconds'] == 10.0
    assert meta['effective_duration_seconds'] == round(107 / 24.0, 6)

    tiles = _video_preview_tiles(frames, 'V1', target_length_frames=107)
    # 90% preview must come from the effective H3 prefix, never from source frames >106.
    assert float(tiles[-1][1][0, 0, 0]) <= 106.0
