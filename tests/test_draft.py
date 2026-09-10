from h3_prompt_compiler.draft import parse_director_draft


def test_unified_chinese_draft_parses_keyframes_ref_assets_and_locked_dialogue():
    text = '''标题：测试条
总时长：8秒

【资产装填清单】
首帧：开场图
尾帧：空
图片1：角色甲角色卡|人物
视频1：动作参考|动作
音频1：空

【无参考主体】
路人

【镜头1】
时长：3秒
出场人物：角色甲
使用资产：首帧，图片1
画面内容：角色甲抬头。
对白：
角色甲：你来了。

【镜头2】
时长：5秒
出场人物：角色甲，路人
使用资产：图片1，视频1
画面内容：角色甲转身，路人经过。
对白：
角色甲：走吧。'''
    draft = parse_director_draft(text)
    assert draft['title'] == '测试条'
    assert draft['duration'] == 8.0
    assert draft['assets']['first_frame']['label'] == '开场图'
    assert draft['assets']['pictures']['P1']['label'] == '角色甲角色卡'
    assert draft['assets']['videos']['V1']['role'] == '动作'
    assert draft['shots'][0]['dialogue'][0]['text'] == '你来了。'
    assert draft['shots'][1]['start'] == 3.0


def test_duration_mismatch_is_rejected():
    text = '''标题：测试
总时长：8秒
【资产装填清单】
【镜头1】
时长：7秒
出场人物：甲
使用资产：无
画面内容：甲站着。
对白：'''
    try:
        parse_director_draft(text)
    except ValueError as exc:
        assert '时长总和' in str(exc)
    else:
        raise AssertionError('expected duration mismatch')


def test_dialogue_speaker_must_be_in_shot_cast():
    text = '''标题：说话人错误
总时长：4秒
【资产装填清单】
【镜头1】
时长：4秒
出场人物：甲
使用资产：无
画面内容：甲站着。
对白：
乙：你好。'''
    try:
        parse_director_draft(text)
    except ValueError as exc:
        assert '乙' in str(exc) and '出场人物' in str(exc)
    else:
        raise AssertionError('expected speaker/cast validation error')


def test_visible_scene_text_is_extracted_as_locked_original_language_text():
    text = '''标题：画面文字
总时长：4秒
【资产装填清单】
【镜头1】
时长：4秒
出场人物：甲
使用资产：无
画面内容：甲站在门口，门牌清晰写着“今日歇业”，旁边贴纸写着"NO ENTRY"。
对白：'''
    draft = parse_director_draft(text)
    assert draft['shots'][0]['visible_text'] == ['今日歇业', 'NO ENTRY']


def test_explicit_no_music_is_normalized_to_no_music_request():
    from h3_prompt_compiler.draft import parse_director_draft
    text = '''标题：无配乐测试
总时长：4秒
【镜头1】
时长：4秒
出场人物：甲
使用资产：无
画面内容：甲站着不动。
对白：
甲：好。
非画内音乐：无'''
    draft = parse_director_draft(text)
    assert draft['music_request_cn'] == ''
