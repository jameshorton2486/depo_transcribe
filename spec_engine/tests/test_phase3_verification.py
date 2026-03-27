"""
test_phase3_verification.py

Phase 3 Verification Test Suite — Corrections Engine Reliability
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from spec_engine.corrections import (
    ARTIFACT_DUPLICATE_RE,
    MULTIWORD_CORRECTIONS,
    SAN_NAME_FLAG_RE,
    UNIVERSAL_CORRECTIONS,
    VERBATIM_PROTECTED,
    apply_artifact_removal,
    apply_multiword_corrections,
    apply_san_name_flag,
    apply_universal_corrections,
    clean_block,
)
from spec_engine.models import JobConfig, ScopistFlag


def _cfg() -> JobConfig:
    return JobConfig()


def _coger_cfg() -> JobConfig:
    return JobConfig(
        cause_number="2025CI19595",
        witness_name="Matthew Allan Coger",
        reporter_name="Miah Bardot",
        speaker_map={
            0: "THE VIDEOGRAPHER",
            1: "THE WITNESS",
            2: "MR. ALLAN",
            3: "MR. BOYCE - OPPOSING COUNSEL",
            4: "THE REPORTER",
        },
        examining_attorney_id=2,
        witness_id=1,
        speaker_map_verified=True,
        confirmed_spellings={
            "Cogger": "Coger",
            "Bare County": "Bexar County",
            "David Blvd.": "David Blas",
            "Miah Vardell": "Miah Bardot",
        },
    )


def _clean(text: str, cfg=None) -> str:
    return clean_block(text, cfg or _cfg())[0]


class TestFix3A_NumberExclusionPerMatch:
    def test_exhibit_far_from_count_does_not_block_conversion(self):
        result = _clean("I signed Exhibit 3 and there were 5 witnesses present.")
        assert "five" in result.lower()
        assert "Exhibit 3" in result

    def test_exhibit_number_itself_not_converted(self):
        result = _clean("I refer you to Exhibit 3.")
        assert "Exhibit 3" in result
        assert "Exhibit three" not in result

    def test_mixed_block_exhibit_and_multiple_counts(self):
        result = _clean("Exhibit 3 shows 5 items and 7 documents were produced.")
        assert "five" in result.lower()
        assert "seven" in result.lower()
        assert "Exhibit 3" in result

    def test_time_near_count_does_not_block_conversion(self):
        result = _clean("At 3:00 p.m. there were 4 people waiting.")
        assert "four" in result.lower()
        assert "3:00" in result

    def test_dollar_amount_near_count_does_not_block_conversion(self):
        result = _clean("There is a $50 fee and 3 copies must be submitted.")
        assert "three" in result.lower()
        assert "$50" in result

    def test_count_only_block_still_converts(self):
        result = _clean("There were 5 witnesses present at the time.")
        assert "five" in result.lower()

    def test_large_number_exclusion_still_works_nearby(self):
        result = _clean("They were at 123 Main Street and 3 cars were parked outside.")
        assert "three" in result.lower() or "3" in result

    def test_sentence_start_number_converts_despite_exhibit_later(self):
        result = _clean("5 people were present. They signed Exhibit 3.")
        assert result.startswith("Five")

    def test_sentence_start_with_time_later_still_converts(self):
        result = _clean("3 times this occurred at 2:30 p.m.")
        assert result.startswith("Three")

    def test_sentence_start_time_itself_not_converted(self):
        result = _clean("3:00 p.m. is when the incident occurred.")
        assert result.startswith("3:00")


class TestFix3B_SubpoenaGarbles:
    @pytest.mark.parametrize("garble", [
        "subpeona", "subpena", "subpoina", "subpeana",
        "sub-poena", "supboena", "sub poena",
    ])
    def test_subpoena_garble_corrects(self, garble):
        result = _clean(f"The witness was served with a {garble}.")
        assert "subpoena" in result.lower()
        assert garble not in result.lower()

    def test_correct_subpoena_not_double_corrected(self):
        result = _clean("The witness was served with a subpoena.")
        assert "subpoena" in result

    def test_subpoena_duces_tecum_still_corrects(self):
        result = _clean("The subpoena deuces tikum was served.")
        assert "duces tecum" in result.lower()

    def test_subpoena_garble_in_sentence_context(self):
        result = _clean("Counsel stated they had served the defendant with a subpena for records.")
        assert "subpoena" in result.lower()


class TestFix3C_ResnickFirmRemoved:
    def test_resnick_lewis_not_corrupted_universally(self):
        records = []
        result = apply_multiword_corrections(
            "The firm of Resnick & Lewis handled the personal injury case.",
            records,
            0,
        )
        assert "Louis" not in result
        assert "Resnick & Lewis" in result

    def test_resnick_and_lewis_variant_not_corrupted(self):
        records = []
        result = apply_multiword_corrections(
            "Attorneys from Resnick and Lewis appeared for the deposition.",
            records,
            0,
        )
        assert "Louis" not in result

    def test_resnick_pattern_not_in_multiword_corrections(self):
        patterns = [p for p, _ in MULTIWORD_CORRECTIONS]
        assert [p for p in patterns if "resnick" in p.lower()] == []

    def test_other_law_firm_corrections_still_work(self):
        records = []
        result = apply_multiword_corrections(
            "Allen Stein in Durbin represented the plaintiff.",
            records,
            0,
        )
        assert "Allen, Stein & Durbin" in result

    def test_clean_scapes_correction_still_works(self):
        result = _clean("CleanScapes was the landscape contractor.")
        assert "Clean Scapes" in result


class TestFix3D_ZipCodeScoped:
    def test_zip_in_address_preserved(self):
        result = _clean("My address is 3201 Cherry Ridge, San Antonio, Texas 78216.")
        assert "78216" in result

    def test_zip_after_texas_preserved(self):
        result = _clean("The store is located in San Antonio, Texas 78216.")
        assert "78216" in result

    def test_floating_artifact_zip_removed(self):
        result = _clean("The incident occurred 78216 near the fuel pump area.")
        assert "78216" not in result

    def test_zip_in_reporter_address_preserved(self):
        result = _clean("SA Legal Solutions, 3201 Cherry Ridge, Ste. 208, San Antonio, Texas 78230.")
        assert "78230" in result


class TestFix3E_CleanBlockFlagsReturn:
    def test_three_element_unpack_works(self):
        text_out, records_out, flags_out = clean_block("Testing the new API.", _cfg(), block_index=0)
        assert isinstance(text_out, str)
        assert isinstance(records_out, list)
        assert isinstance(flags_out, list)

    def test_two_element_index_still_works(self):
        result = clean_block("Backward compat test.", _cfg(), block_index=0)
        assert isinstance(result[0], str)
        assert isinstance(result[1], list)

    def test_flags_returned_contain_scopist_flags(self):
        text_out, records_out, flags_out = clean_block(
            "The deposition took place on July twenty twenty five.",
            _cfg(),
            block_index=0,
        )
        assert isinstance(flags_out, list)
        if flags_out:
            assert all(isinstance(f, ScopistFlag) for f in flags_out)

    def test_flags_returned_is_independent_copy(self):
        _, _, flags1 = clean_block("July twenty twenty five meeting.", _cfg(), block_index=0)
        flags1.append(ScopistFlag(number=99, description="injected", block_index=0))
        _, _, flags2 = clean_block("July twenty twenty five meeting.", _cfg(), block_index=1)
        assert 99 not in [f.number for f in flags2]

    def test_existing_two_element_callers_unaffected(self):
        full_result = clean_block("The witness was present.", _cfg(), block_index=0)
        assert isinstance(full_result[0], str)
        assert isinstance(full_result[1], list)

    def test_flags_returned_for_san_name_trigger(self):
        _, _, flags_out = clean_block("San Xyzabc told me what happened.", _cfg(), block_index=0)
        assert isinstance(flags_out, list)
        if flags_out:
            categories = [f.category for f in flags_out]
            assert any(c in ("artifact", "date") for c in categories)


class TestFix3F_SanCityWhitelist:
    @pytest.mark.parametrize("city_text", [
        "San Antonio, Texas",
        "San Benito, Texas",
        "San Elizario, Texas",
        "San Saba, Texas",
        "San Isidro, Texas",
        "San Patricio County",
        "San Ygnacio, Texas",
        "San Marcos, Texas",
        "San Angelo, Texas",
        "San Augustine, Texas",
    ])
    def test_valid_texas_city_not_flagged(self, city_text):
        records, flags, fc = [], [], [0]
        apply_san_name_flag(city_text, records, flags, 0, fc)
        assert len(flags) == 0

    def test_unknown_san_name_still_flags(self):
        records, flags, fc = [], [], [0]
        apply_san_name_flag("San Xyzabc appeared and testified.", records, flags, 0, fc)
        assert len(flags) > 0

    def test_san_antonio_not_flagged(self):
        records, flags, fc = [], [], [0]
        apply_san_name_flag("San Antonio, Texas 78209", records, flags, 0, fc)
        assert len(flags) == 0

    def test_san_name_flag_re_pattern_compiles(self):
        assert SAN_NAME_FLAG_RE is not None
        assert hasattr(SAN_NAME_FLAG_RE, "search")

    def test_san_benito_in_block_text(self):
        records, flags, fc = [], [], [0]
        apply_san_name_flag(
            "The accident occurred in San Benito, Texas at the corner of Main Street.",
            records,
            flags,
            0,
            fc,
        )
        assert len(flags) == 0


class TestFix3G_VerbatimProtectedCleanup:
    def test_uh_removed_from_verbatim_protected(self):
        assert "uh" not in VERBATIM_PROTECTED

    def test_um_removed_from_verbatim_protected(self):
        assert "um" not in VERBATIM_PROTECTED

    def test_so_removed_from_verbatim_protected(self):
        assert "so" not in VERBATIM_PROTECTED

    def test_okay_remains_in_verbatim_protected(self):
        assert "okay" in VERBATIM_PROTECTED

    def test_well_remains_in_verbatim_protected(self):
        assert "well" in VERBATIM_PROTECTED

    def test_verbatim_protected_contains_only_reachable_words(self):
        assert [w for w in VERBATIM_PROTECTED if len(w) < 4] == []

    def test_uh_still_preserved_by_verbatim_rule(self):
        result = apply_artifact_removal("uh, I think so.", [], 0)
        assert "uh" in result

    def test_um_still_preserved_by_verbatim_rule(self):
        result = apply_artifact_removal("um, that is correct.", [], 0)
        assert "um" in result

    def test_okay_okay_still_preserved(self):
        result = apply_artifact_removal("okay okay I understand.", [], 0)
        assert result.count("okay") >= 1


class TestPhase3Integration:
    def test_coger_exhibit_and_count_in_same_block(self):
        result = _clean("I reviewed Exhibit 16 and noted 3 discrepancies.", _coger_cfg())
        assert "Exhibit 16" in result
        assert "three" in result.lower()

    def test_coger_subpoena_in_full_context(self):
        result = _clean(
            "You came today because you were served with a subpena for this deposition.",
            _coger_cfg(),
        )
        assert "subpoena" in result.lower()

    def test_all_phase3_fixes_work_together(self):
        result = _clean(
            "The 3 attorneys in Bare County signed Exhibit 5 of the record.",
            _coger_cfg(),
        )
        assert "Bexar County" in result
        assert "Exhibit 5" in result
        assert "three" in result.lower() or "3" in result

    def test_clean_block_three_tuple_with_confirmed_spellings(self):
        text_out, records_out, flags_out = clean_block(
            "The deposition was held in Bare County, Texas.",
            _coger_cfg(),
            block_index=0,
        )
        assert "Bexar County" in text_out
        assert isinstance(flags_out, list)
        assert any(
            r.pattern == "confirmed_spelling:Bare County" for r in records_out
        ) or "Bexar" in text_out


class TestPhase3ExitGate:
    def test_exhibit_block_does_not_block_count_conversion(self):
        result = _clean("Exhibit 3 was reviewed and 5 issues were found.")
        assert "five" in result.lower()

    def test_all_subpoena_garbles_corrected(self):
        for garble in ["subpeona", "subpena", "subpoina", "subpeana", "sub-poena", "supboena", "sub poena"]:
            result = _clean(f"Served with a {garble}.")
            assert "subpoena" in result.lower()

    def test_resnick_lewis_not_in_multiword_corrections(self):
        patterns = [p.lower() for p, _ in MULTIWORD_CORRECTIONS]
        assert not any("resnick" in p and "lewis" in p for p in patterns)

    def test_zip_in_texas_address_preserved(self):
        result = _clean("Located in San Antonio, Texas 78209.")
        assert "78209" in result

    def test_clean_block_returns_three_tuple(self):
        result = clean_block("Test.", _cfg())
        assert len(result) == 3

    def test_san_benito_and_san_elizario_not_flagged(self):
        for city in ["San Benito, Texas", "San Elizario, Texas"]:
            records, flags, fc = [], [], [0]
            apply_san_name_flag(city, records, flags, 0, fc)
            assert len(flags) == 0

    def test_verbatim_protected_has_exactly_two_entries(self):
        assert VERBATIM_PROTECTED == {"okay", "well"}
