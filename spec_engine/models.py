"""
models.py

Data structures for the DepoPro transcript processing pipeline.
Spec reference: Section 1.2 (Block), Section 9.3 (JobConfig)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class BlockType(str, Enum):
    QUESTION = "Q"
    ANSWER = "A"
    SPEAKER = "SPEAKER"
    COLLOQUY = "COLLOQUY"
    PARENTHETICAL = "PAREN"
    UNKNOWN = "UNKNOWN"
    FLAG = "FLAG"


class LineType(Enum):
    Q      = "Q"
    A      = "A"
    SP     = "SP"
    PN     = "PN"
    FLAG   = "FLAG"
    HEADER = "HEADER"
    BY     = "BY"
    PLAIN  = "PLAIN"


@dataclass
class Word:
    text: str
    start: Optional[float] = None
    end: Optional[float] = None
    confidence: Optional[float] = None
    speaker: Optional[int] = None


@dataclass
class Block:
    text: str
    speaker_id: Optional[int] = None
    raw_text: str = ""
    speaker_name: Optional[str] = None
    speaker_role: str = ""
    block_type: BlockType = BlockType.UNKNOWN
    words: List[Word] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    meta: Dict = field(default_factory=dict)

    def get_display_speaker(self) -> str:
        return self.speaker_name or self.speaker_role or "UNKNOWN"


@dataclass
class CorrectionRecord:
    original: str
    corrected: str
    pattern: str
    block_index: int


@dataclass
class ScopistFlag:
    number: int
    description: str
    block_index: int
    category: str = "general"
    inline_text: str = ""


@dataclass
class PostRecordSpelling:
    """
    Spec Section 8: Post-record spellings are AUTHORITATIVE.
    They override all prior uses of the name in the transcript.
    """
    name: str
    correct_spelling: str
    letters_as_given: str
    block_index: int
    flag: Optional[str] = None


@dataclass
class CounselInfo:
    name: str = ""
    firm: str = ""
    sbot: str = ""
    address: str = ""
    city: str = ""
    state: str = "Texas"
    zip_code: str = ""
    phone: str = ""
    party: str = ""
    role: str = ""


@dataclass
class ExhibitEntry:
    """Single exhibit in the exhibit index (UFM Section 11)."""
    number: str = ""
    description: str = ""
    offered_page: str = ""
    admitted_page: str = ""
    excluded_page: str = ""


@dataclass
class WitnessIndexEntry:
    """Single witness row in the witness index (UFM Section 11)."""
    name: str = ""
    direct_page: str = ""
    cross_page: str = ""
    redirect_page: str = ""
    recross_page: str = ""
    voir_dire_page: str = ""


@dataclass
class ChangeEntry:
    """Single row in the changes and signature page (UFM Figure 7)."""
    page: str = ""
    line: str = ""
    original: str = ""
    change: str = ""
    reason: str = ""


@dataclass
class JobConfig:
    """
    Per-deposition configuration (Spec Section 9.3).
    TERMINOLOGY: "Cause Number" not "Case Number" (Texas court terminology).
    """
    # Group 1 — Case Information
    cause_number: str = ""
    appellate_cause_number: str = ""
    case_style: str = ""
    plaintiff_name: str = ""
    defendant_names: List[str] = field(default_factory=list)
    court: str = ""
    court_type: str = "District Court"
    county: str = ""
    state: str = "Texas"
    judicial_district: str = ""

    # Group 2 — Proceeding Metadata
    proceeding_type: str = "Deposition"
    depo_date: str = ""
    depo_start_time: str = ""
    depo_end_time: str = ""
    location: str = ""
    location_address: str = ""
    location_city: str = ""
    method: str = "In Person"
    volume_number: int = 1
    total_volumes: int = 1
    is_videotaped: bool = False
    subpoena_duces_tecum: bool = False
    audio_quality: str = "clean"

    # Group 3 — Participants
    witness_name: str = ""
    witness_title: str = ""
    judge_name: str = ""
    plaintiff_counsel: List[CounselInfo] = field(default_factory=list)
    defense_counsel: List[CounselInfo] = field(default_factory=list)
    also_present: List[str] = field(default_factory=list)

    # Group 4 — Reporter Information
    reporter_name: str = "Miah Bardot"
    reporter_csr: str = "CSR No. 12129"
    reporter_expiration: str = ""
    reporter_firm: str = "SA Legal Solutions"
    reporter_address: str = "San Antonio, Texas"
    reporter_phone: str = ""
    reporter_city: str = ""
    firm_registration: str = ""
    is_official_reporter: bool = False

    # Group 5 — Financial / Certification
    cost_total: str = ""
    cost_paid_by: str = ""
    time_used: Dict[str, str] = field(default_factory=dict)
    certified_date: str = ""
    notary_name: str = ""
    notary_county: str = ""
    identification_method: str = ""
    spec_flags: List["ScopistFlag"] = field(default_factory=list)

    # Group 6 — Index / Transcript Structure
    witnesses: List[WitnessIndexEntry] = field(default_factory=list)
    exhibits: List[ExhibitEntry] = field(default_factory=list)
    changes: List[ChangeEntry] = field(default_factory=list)

    # Processing Control
    speaker_map: Dict[int, str] = field(default_factory=dict)
    examining_attorney_id: int = 2
    witness_id: int = 1
    confirmed_spellings: Dict[str, str] = field(default_factory=dict)
    post_record_spellings: List[PostRecordSpelling] = field(default_factory=list)
    split_embedded_answers: bool = True
    speaker_map_verified: bool = False

    def to_json(self) -> str:
        data = {
            "cause_number": self.cause_number,
            "appellate_cause_number": self.appellate_cause_number,
            "case_style": self.case_style,
            "plaintiff_name": self.plaintiff_name,
            "defendant_names": self.defendant_names,
            "court": self.court,
            "court_type": self.court_type,
            "county": self.county,
            "state": self.state,
            "judicial_district": self.judicial_district,
            "proceeding_type": self.proceeding_type,
            "depo_date": self.depo_date,
            "depo_start_time": self.depo_start_time,
            "depo_end_time": self.depo_end_time,
            "location": self.location,
            "location_address": self.location_address,
            "location_city": self.location_city,
            "method": self.method,
            "volume_number": self.volume_number,
            "total_volumes": self.total_volumes,
            "is_videotaped": self.is_videotaped,
            "subpoena_duces_tecum": self.subpoena_duces_tecum,
            "audio_quality": self.audio_quality,
            "witness_name": self.witness_name,
            "witness_title": self.witness_title,
            "judge_name": self.judge_name,
            "plaintiff_counsel": [vars(c) for c in self.plaintiff_counsel],
            "defense_counsel": [vars(c) for c in self.defense_counsel],
            "also_present": self.also_present,
            "reporter_name": self.reporter_name,
            "reporter_csr": self.reporter_csr,
            "reporter_expiration": self.reporter_expiration,
            "reporter_firm": self.reporter_firm,
            "reporter_address": self.reporter_address,
            "reporter_phone": self.reporter_phone,
            "reporter_city": self.reporter_city,
            "firm_registration": self.firm_registration,
            "is_official_reporter": self.is_official_reporter,
            "cost_total": self.cost_total,
            "cost_paid_by": self.cost_paid_by,
            "time_used": self.time_used,
            "certified_date": self.certified_date,
            "notary_name": self.notary_name,
            "notary_county": self.notary_county,
            "identification_method": self.identification_method,
            "witnesses": [vars(w) for w in self.witnesses],
            "exhibits": [vars(e) for e in self.exhibits],
            "changes": [vars(c) for c in self.changes],
            "spec_flags": [
                {
                    "number": f.number,
                    "description": f.description,
                    "block_index": f.block_index,
                    "category": f.category,
                    "inline_text": f.inline_text,
                }
                for f in self.spec_flags
            ],
            "speaker_map": {str(k): v for k, v in self.speaker_map.items()},
            "examining_attorney_id": self.examining_attorney_id,
            "witness_id": self.witness_id,
            "confirmed_spellings": self.confirmed_spellings,
            "post_record_spellings": [vars(p) for p in self.post_record_spellings],
            "split_embedded_answers": self.split_embedded_answers,
            "speaker_map_verified": self.speaker_map_verified,
        }
        return json.dumps(data, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "JobConfig":
        data = json.loads(json_str)
        cfg = cls()
        for key, value in data.items():
            if key == "speaker_map":
                cfg.speaker_map = {int(k): v for k, v in value.items()}
            elif key == "plaintiff_counsel":
                cfg.plaintiff_counsel = [CounselInfo(**c) for c in value]
            elif key == "defense_counsel":
                cfg.defense_counsel = [CounselInfo(**c) for c in value]
            elif key == "witnesses":
                cfg.witnesses = [WitnessIndexEntry(**w) for w in value]
            elif key == "exhibits":
                cfg.exhibits = [ExhibitEntry(**e) for e in value]
            elif key == "changes":
                cfg.changes = [ChangeEntry(**c) for c in value]
            elif key == "spec_flags":
                cfg.spec_flags = [
                    ScopistFlag(
                        number=f.get("number", 0),
                        description=f.get("description", ""),
                        block_index=f.get("block_index", 0),
                        category=f.get("category", "general"),
                        inline_text=f.get("inline_text", ""),
                    )
                    for f in value
                ]
            elif key == "post_record_spellings":
                cfg.post_record_spellings = [PostRecordSpelling(**p) for p in value]
            elif hasattr(cfg, key):
                setattr(cfg, key, value)
        return cfg

    def save(self, jobs_dir: str = "jobs") -> str:
        Path(jobs_dir).mkdir(exist_ok=True)
        safe_name = self.cause_number.replace("/", "-").replace("\\", "-") or "unnamed"
        path = Path(jobs_dir) / f"{safe_name}_job.json"
        path.write_text(self.to_json(), encoding="utf-8")
        return str(path)

    @classmethod
    def load(cls, path: str) -> "JobConfig":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))

    @classmethod
    def default_perez_ugalde(cls) -> "JobConfig":
        return cls(
            cause_number    = "2025-CI-12281",
            court           = "285th Judicial District, Bexar County, Texas",
            plaintiff_name  = "Bianca Perez",
            defendant_names = ["Simon Ugalde", "Lewis Energy Group LP"],
            method          = "In Person",
            reporter_name   = "Miah Bardot",
            reporter_csr    = "CSR No. 12129",
            reporter_firm   = "SA Legal Solutions",
            reporter_address= "San Antonio, Texas",
            speaker_map     = {
                0: "THE VIDEOGRAPHER",
                1: "THE WITNESS",
                2: "MR. SALAZAR",
                3: "MS. DURBIN",
                4: "THE REPORTER",
            },
            examining_attorney_id = 2,
            witness_id            = 1,
            speaker_map_verified  = True,
            confirmed_spellings   = {
                "Yugaldi": "Ugalde", "Yugaldo": "Ugalde", "Yigali": "Ugalde",
                "Ugalda": "Ugalde", "Ugaldo": "Ugalde", "Ugaldi": "Ugalde",
                "Nugaldi": "Ugalde", "Uvalde": "Ugalde", "Uganda": "Ugalde",
                "Auguste": "Ugalde", "Marupo": "Marrufo", "Marufo": "Marrufo",
                "Durban": "Durbin", "Tobar": "Tovar", "Tavar": "Tovar",
                "Talbad": "Tovar", "Tilbar": "Tovar", "Kovad": "Tovar",
                "Valveras": "Balderas", "Harlington": "Harlingen",
                "Harlingtons": "Harlingen", "InSNL": "Encinal",
                "Intonale": "Encinal", "Insanel": "Encinal",
                "Intondale": "Encinal",
            },
        )

    @classmethod
    def default_garza_perez(cls) -> "JobConfig":
        return cls(
            cause_number    = "2025-CI-00766",
            court           = "Bexar County, Texas",
            plaintiff_name  = "Andrew Garza",
            method          = "In Person",
            reporter_name   = "Miah Bardot",
            reporter_csr    = "CSR No. 12129",
            reporter_firm   = "SA Legal Solutions",
            reporter_address= "San Antonio, Texas",
            confirmed_spellings = {
                "Nevarete": "Navarrete", "Nevaret": "Navarrete",
                "McAatherine": "McCathern", "McAthron": "McCathern",
                "Cleanscapes": "Clean Scapes Enterprises, Inc.",
                "Brudeman": "Bruggemann", "Brueggemann": "Bruggemann",
                "Oak": "Hoak",
            },
        )


class SpeakerMapUnverifiedError(Exception):
    """Raised when process_transcript() is called without a verified speaker map."""
    pass


class SpecEngineError(Exception):
    """Base exception for all spec_engine errors."""
    pass
