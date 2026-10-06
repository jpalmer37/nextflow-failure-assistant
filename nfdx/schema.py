from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CauseCategory(StrEnum):
    MISSING_INPUT = "missing_input"
    CORRUPT_INPUT = "corrupt_input"
    CONDA_SOLVE_FAILED = "conda_solve_failed"
    CONTAINER_UNAVAILABLE = "container_unavailable"
    COMMAND_NOT_FOUND = "command_not_found"
    MISSING_OUTPUT = "missing_output"
    PERMISSION_DENIED = "permission_denied"
    TIMEOUT = "timeout"
    OUT_OF_MEMORY = "out_of_memory"
    BAD_INTERPOLATION = "bad_interpolation"
    MALFORMED_SAMPLESHEET = "malformed_samplesheet"
    TOOL_ERROR = "tool_error"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class Evidence(StrictModel):
    """One failed Nextflow task, as extracted from a run log."""

    process: str | None = None
    exit_status: str | None = None
    caused_by: str | None = None
    command_executed: str | None = None
    command_output: str | None = None
    command_error: str | None = None
    work_dir: str | None = None

    def as_text(self) -> str:
        """Flat rendering used both as model input and as the grounding reference."""
        fields = (
            ("Process", self.process),
            ("Exit status", self.exit_status),
            ("Caused by", self.caused_by),
            ("Command executed", self.command_executed),
            ("Command output", self.command_output),
            ("Command error", self.command_error),
        )
        return "\n".join(f"{label}:\n{value}" for label, value in fields if value)


class Diagnosis(StrictModel):
    cause_category: CauseCategory
    explanation: str = Field(min_length=1)
    supporting_lines: list[str] = Field(
        default_factory=list,
        description="Verbatim lines copied from the evidence; grounding is checked",
    )
    suggested_check_ids: list[str] = Field(
        default_factory=list,
        description="Check IDs from the notes catalogue, best first; the first is scored",
    )
    confidence: float = Field(ge=0.0, le=1.0)
