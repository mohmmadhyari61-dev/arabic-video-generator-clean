from lecture_studio.speech import Speaker
from lecture_studio.pronunciation import chunks, pause_after, spoken_text


def test_legal_speech_expands_only_unambiguous_numbers():
    source = "المادة (١٢)؛ المادة ۲۷، والمادة ١٢/٢٠٢٥، والمادة ١٢٫٥، ومهلة ١٥ يومًا للطعن؛ التقادم."
    speech = spoken_text(source)
    assert "المادة رقم اثنا عشر" in speech
    assert "المادة رقم سبعة وعشرون" in speech
    assert "12/2025" in speech and "12٫5" in speech and "15 يومًا" in speech
    assert speech.endswith("التَّقادُم.")


def test_narration_chunks_preserve_words_and_legal_operators():
    source = "تسري المادة ١٢. لا يقبل الطعن، ما لم يزُل المانع؛ ويقع عبء الإثبات على المدعي."
    blocks = list(chunks(source, 34))
    assert " ".join(blocks) == source
    assert all(len(block) <= 34 for block in blocks)
    assert blocks[0].endswith("١٢.")
    assert pause_after(blocks[0], False) > pause_after("كلمة", False)


def test_silma_bounds_normalized_not_just_original_text():
    text = "تشترط المادة (١٢) لقبول الطعن أن يقدم المدعي طلباً مكتوباً قبل قيد الدعوى، وإلا سقط الحق في الطعن."
    pieces = list(Speaker("silma", "silma", "-10%").chunks(text))
    assert " ".join(pieces) == text
    assert all(len(spoken_text(piece)) <= 110 for piece in pieces)
