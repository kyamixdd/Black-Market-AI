"""Controlled evolution API routes."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from core.controlled_evolution import approve_proposal, create_improvement_proposal, detect_weaknesses, list_proposals, list_versions, rollback_version
from ..request_validation import validate_json_payload_size

router = APIRouter(prefix="/evolution", tags=["controlled-evolution"])

class ProposalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patch: dict[str, object] = Field(min_length=1)
    candidate_report: dict[str, object]
    baseline_report: dict[str, object] | None = None
    rationale: str = Field(min_length=10, max_length=1000)

    @model_validator(mode="before")
    @classmethod
    def bounded_payload(cls, value):
        return validate_json_payload_size(value, label="Evolution proposal")


class WeaknessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report: dict[str, object]

    @model_validator(mode="before")
    @classmethod
    def bounded_payload(cls, value):
        return validate_json_payload_size(value, label="Evolution report")


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    explicit_approval: bool

def _auth(request: Request):
    scheme, sep, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not sep or not token:
        raise HTTPException(status_code=401, detail="Authentication required")

@router.post("/weaknesses")
async def weaknesses(request: Request, payload: WeaknessRequest):
    _auth(request)
    try: return {"weaknesses": detect_weaknesses(payload.report)}
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.post("/proposals", status_code=201)
async def create_proposal(request: Request, payload: ProposalRequest):
    _auth(request)
    try:
        return create_improvement_proposal(payload.patch, payload.candidate_report, payload.baseline_report, payload.rationale)
    except (ValueError, RuntimeError) as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.get("/proposals")
async def proposals(request: Request):
    _auth(request)
    return {"proposals": list_proposals()}

@router.post("/proposals/{proposal_id}/approve")
async def approve(request: Request, proposal_id: str, payload: ApprovalRequest):
    _auth(request)
    try: return approve_proposal(proposal_id, explicit_approval=payload.explicit_approval)
    except PermissionError as exc: raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc

@router.get("/versions")
async def versions(request: Request):
    _auth(request)
    return {"versions": list_versions()}

@router.post("/versions/{version_id}/rollback")
async def rollback(request: Request, version_id: str, payload: ApprovalRequest):
    _auth(request)
    try: return rollback_version(version_id, explicit_approval=payload.explicit_approval)
    except PermissionError as exc: raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc
