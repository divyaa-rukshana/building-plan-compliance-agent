from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator

class LandUseCategory(str, Enum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    MIXED_USE = "mixed-use"
    INSTITUTIONAL = "institutional"

class PlanningArea(str, Enum):
    AREA_A = "A"
    AREA_B = "B"
    AREA_C = "C"

class SetbacksInput(BaseModel):
    front_m: float = Field(..., ge=0.0, le=50.0)
    rear_m: float = Field(..., ge=0.0, le=50.0)
    left_m: float = Field(..., ge=0.0, le=50.0)
    right_m: float = Field(..., ge=0.0, le=50.0)

class BuildingProposalRequest(BaseModel):
    proposal_id: Optional[str] = None
    land_use: LandUseCategory
    planning_area: PlanningArea = PlanningArea.AREA_A
    plot_width_m: float = Field(..., gt=0.0, le=500.0)
    plot_depth_m: float = Field(..., gt=0.0, le=500.0)
    plot_area_sqm: float = Field(..., gt=0.0, le=250000.0)
    abutting_road_width_m: float = Field(..., gt=0.0, le=100.0)
    proposed_height_m: float = Field(..., gt=0.0, le=150.0)
    proposed_floors: int = Field(..., ge=1, le=50)
    proposed_plinth_area_sqm: float = Field(..., gt=0.0)
    proposed_total_floor_area_sqm: float = Field(..., gt=0.0)
    proposed_setbacks: SetbacksInput
    notes: Optional[str] = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def validate_cross_fields(self) -> "BuildingProposalRequest":
        expected_area = self.plot_width_m * self.plot_depth_m
        if abs(self.plot_area_sqm - expected_area) / expected_area > 0.15:
            raise ValueError("plot_area_sqm diverges >15% from width * depth.")
        return self

class ComplianceResultResponse(BaseModel):
    run_id: str
    correlation_id: str
    status: str
    metrics: dict = {}