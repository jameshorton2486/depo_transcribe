from spec_engine.ufm_rules import enforce_qa_tabs, is_qa_formatted, normalize_qa_line


def test_normalize_qa_line_canonicalizes_prefix():
    assert normalize_qa_line("Q: What is your name?") == "\tQ.\tWhat is your name?"
    assert normalize_qa_line("a . yes") == "\tA.\tyes"


def test_is_qa_formatted():
    assert is_qa_formatted("\tQ.\tQuestion")
    assert not is_qa_formatted("Q: Question")


def test_enforce_qa_tabs_returns_canonical():
    assert enforce_qa_tabs("A: Yes") == "\tA.\tYes"
