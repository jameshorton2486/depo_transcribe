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


def test_map_intake_to_ufm_puts_ordering_attorney_in_defense_counsel_fallback():
    mapped = map_intake_to_ufm(
        {
            "deposition_details": {
                "case_style": "Bianca Perez v. Simon Ugalde",
            },
            "ordering_attorney": {
                "name": "David Boyce",
                "firm": "Defense Firm",
                "address": "100 Main St",
                "city_state_zip": "San Antonio, Texas 78205",
                "phone": "(210) 555-1000",
                "email": "dboyce@example.com",
            },
        }
    )

    assert mapped["plaintiff_counsel"] == []
    assert len(mapped["defense_counsel"]) == 1
    assert mapped["defense_counsel"][0]["name"] == "David Boyce"
    assert mapped["defense_counsel"][0]["firm"] == "Defense Firm"
    assert mapped["defense_counsel"][0]["party"] == "Simon Ugalde"
