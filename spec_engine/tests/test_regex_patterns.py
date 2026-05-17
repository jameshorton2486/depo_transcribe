from spec_engine.regex_patterns import QA_PREFIX_RE, SPEAKER_LABEL_RE


def test_qa_prefix_matches_colon_or_dot_forms():
    assert QA_PREFIX_RE.match("Q: Hello")
    assert QA_PREFIX_RE.match("A. yes")


def test_speaker_label_matches_uppercase_labels():
    assert SPEAKER_LABEL_RE.match("THE WITNESS:")
    assert SPEAKER_LABEL_RE.match("MR. SMITH::")
