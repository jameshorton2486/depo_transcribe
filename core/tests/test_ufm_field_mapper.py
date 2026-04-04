from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.ufm_field_mapper import map_intake_to_ufm


def test_map_intake_to_ufm_uses_correct_ordinal_suffixes_for_judicial_district():
    def _mapped_district(court: str) -> str:
        return map_intake_to_ufm(
            {
                "deposition_details": {
                    "court": court,
                }
            }
        )["judicial_district"]

    assert _mapped_district("1st Judicial District, Example County, Texas") == "1ST"
    assert _mapped_district("2nd Judicial District, Example County, Texas") == "2ND"
    assert _mapped_district("3rd Judicial District, Example County, Texas") == "3RD"
    assert _mapped_district("408th Judicial District, Bexar County, Texas") == "408TH"
