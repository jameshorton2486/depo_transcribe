from spec_engine.validator import validate_transcript_lines


def test_validator_reports_expected_issues():
    lines = [
        "Q: malformed",
        "MR SMITH::",
        "wait--what",
        "well . . . maybe",
        "Hello!!",
        "(discussion off the record",
    ]
    issues = validate_transcript_lines(lines)
    codes = {i.code for i in issues}
    assert "MALFORMED_QA" in codes
    assert "MALFORMED_SPEAKER" in codes
    assert "INVALID_DASH" in codes
    assert "INVALID_ELLIPSIS" in codes
    assert "DUP_PUNCT" in codes
    assert "MALFORMED_PAREN" in codes
