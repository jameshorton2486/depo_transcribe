"""Build template-ready rendering context from raw job data."""

from __future__ import annotations

from datetime import date


class ContextBuilder:
    """Normalize raw job data into a rendering context."""

    REQUIRED_FIELDS = ("witness_name", "date", "reporter_name", "csr_number")
    REQUIRED_CONTEXT_FIELDS = ("mr_ms", "zip", "answer")
    REQUIRED_TEMPLATE_FIELDS = ("witness_name", "month", "day", "year", "reporter_name", "csr_number")
    DEFAULTS = {
        "answer": "",
        "case_name": "",
        "cause_number": "2024-XXXX",
        "city": "San Antonio",
        "footer_text": "",
        "header_text": "",
        "mr_ms": "MR.",
        "question": "",
        "state": "Texas",
        "title": "",
        "zip": "78205",
    }

    def build_context(self, job_data: dict) -> dict:
        """Build a clean, template-ready context from raw job data.

        Args:
            job_data: Source job data collected from the application.

        Raises:
            ValueError: If required fields are missing or the date is invalid.
        """
        if not isinstance(job_data, dict):
            raise ValueError("job_data must be a dictionary.")

        missing_fields = [field for field in self.REQUIRED_FIELDS if not job_data.get(field)]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(f"Missing required job data fields: {missing}")

        deposition_date = self._parse_date(job_data["date"])
        is_remote = bool(job_data.get("is_remote", False))

        context = {
            "witness_name": str(job_data["witness_name"]).strip(),
            "month": deposition_date.strftime("%B"),
            "day": str(deposition_date.day),
            "year": str(deposition_date.year),
            "deposition_label": "REMOTE DEPOSITION" if is_remote else "DEPOSITION",
            "reporter_name": str(job_data["reporter_name"]).strip(),
            "csr_number": str(job_data["csr_number"]).strip(),
            "is_remote": is_remote,
        }

        optional_fields = {
            key: value
            for key, value in job_data.items()
            if key not in {"date", *self.REQUIRED_FIELDS} and value is not None
        }
        context.update(optional_fields)

        for key, default_value in self.DEFAULTS.items():
            if not context.get(key):
                context[key] = default_value

        missing_context_fields = [
            field for field in self.REQUIRED_CONTEXT_FIELDS if not context.get(field)
        ]
        if missing_context_fields:
            missing = ", ".join(missing_context_fields)
            raise ValueError(f"Template context incomplete: {missing}")

        missing_template_fields = [
            field for field in self.REQUIRED_TEMPLATE_FIELDS if not context.get(field)
        ]
        if missing_template_fields:
            missing = ", ".join(missing_template_fields)
            raise ValueError(f"Template context incomplete: {missing}")

        return context

    @staticmethod
    def _parse_date(raw_date: object) -> date:
        """Parse an ISO-format date string into a date object."""
        if not isinstance(raw_date, str) or not raw_date.strip():
            raise ValueError("job_data['date'] must be a non-empty ISO date string.")

        try:
            return date.fromisoformat(raw_date)
        except ValueError as exc:
            raise ValueError(f"Invalid date '{raw_date}'. Expected YYYY-MM-DD format.") from exc
