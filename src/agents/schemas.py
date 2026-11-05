"""Typed contracts between the two agents and with the outside world."""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator

Route = Literal["clear-for-submission", "revise-and-recheck", "specialist-review"]
Status = Literal["completed", "escalated", "blocked"]
FindingStatus = Literal["within_limit", "exceeds_limit", "info", "needs_input", "exemption_possible"]


class Setbacks(BaseModel):
    front: float = Field(ge=0)
    rear: float = Field(ge=0)
    left: float = Field(ge=0)
    right: float = Field(ge=0)


class ProposalIn(BaseModel):
    """Agent-side view of the proposal. Keep in sync with Member 1's published data contract."""
    area_class: Optional[Literal["A", "B", "C"]] = None   # BDA map area (bye-law 9.10.1)
    zone: Literal["R_MAIN", "R_MIXED"] = "R_MAIN"           # RMP 2015 zone
    ring: Optional[Literal[1, 2, 3]] = None
    use: str = Field(min_length=1, max_length=200)
    land_use: Optional[Literal["residential", "commercial", "mixed-use", "institutional"]] = None  # declared category
    plot_area_sqm: Optional[float] = Field(default=None, gt=0, le=250000)  # surveyed area; else width x depth
    dwelling_type: Literal["single", "multi"] = "single"
    plot_width_m: float = Field(gt=0, le=1000)
    plot_depth_m: float = Field(gt=0, le=1000)
    road_width_m: float = Field(gt=0, le=100)
    height_m: float = Field(gt=0, le=300)
    storeys: int = Field(ge=1, le=100)                     # habitable storeys incl. ground (G+2 = 3)
    proposed_setbacks_m: Optional[Setbacks] = None
    proposed_coverage_pct: Optional[float] = Field(default=None, ge=0, le=100)
    proposed_floor_area_sqm: Optional[float] = Field(default=None, ge=0)
    notes: str = Field(default="", max_length=2000)

    @field_validator("use", "notes")
    @classmethod
    def _strip(cls, v):
        return v.strip()


class Passage(BaseModel):
    clause_id: str
    page: int
    source_doc: str
    text: str
    score: float = 0.0


class Citation(BaseModel):
    clause_id: str
    page: int
    source_doc: str
    quote: str


class Finding(BaseModel):
    id: str
    title: str
    status: FindingStatus
    proposal_value: str = ""
    limit: str = ""
    detail: str = ""
    source: str = ""                       # bylaws | rmp | both
    citations: List[Citation] = []
    verified: bool = False


class Conflict(BaseModel):
    quantity: str
    bylaws: str
    rmp: str
    clause_ids: List[str]


class EvidenceBundle(BaseModel):
    """Hand-off object: Researcher -> Assessor."""
    entities: Dict[str, Any] = {}
    passages: Dict[str, Passage] = {}
    queries: List[str] = []
    lookups: List[Dict[str, Any]] = []
    unresolved: List[str] = []             # clause ids we looked for and could not find
    steps: int = 0
    tool_calls: int = 0
    complete: bool = False
    stop_reason: str = ""


class Result(BaseModel):
    run_id: str
    correlation_id: str = ""
    corpus_backend: str = ""
    status: Status
    route: Route
    reason: str
    verified: bool
    degraded: bool = False
    entities: Dict[str, Any] = {}
    findings: List[Finding] = []
    conflicts: List[Conflict] = []
    escalation_path: List[str] = []
    summary: str = ""
    prompt_version: str = ""
    conflict_policy: str = ""
    cost: Dict[str, Any] = {}
    trace: List[Dict[str, Any]] = []
    limits_used: Dict[str, Any] = {}
    disclaimer: str = ("This is a pre-check finding with cited evidence, not a certification. "
                       "A licensed architect or engineer decides.")
