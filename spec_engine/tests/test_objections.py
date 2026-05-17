from spec_engine.objections import normalize_objection_line, normalize_parenthetical_line


def test_normalize_objection_line():
    assert normalize_objection_line("objection form") == "Objection, form."
    assert normalize_objection_line("Objection") == "Objection."


def test_normalize_parenthetical_line():
    assert normalize_parenthetical_line("(discussion off the record)") == "(Discussion off the record.)"
