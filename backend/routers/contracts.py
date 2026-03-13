"""
Contract Intelligence router.
Handles standard contract management, prospect contract analysis, and cross-contract insights.
"""
import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from database import get_db
from services.demo_data import (
    DEMO_STANDARD_CLAUSES,
    DEMO_DEVIATIONS,
    DEMO_DISCOUNT_INSIGHTS,
)

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads", "contracts")


def _decode_session(authorization: str) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")
    token = authorization.replace("Bearer ", "").strip()
    try:
        payload = json.loads(base64.b64decode(token).decode())
        return payload
    except Exception:
        pass
    if len(token) > 10:
        return {"user_id": "zoho_user", "access_token": token}
    raise HTTPException(status_code=401, detail="Invalid session token")


def _is_demo(session: dict) -> bool:
    return session.get("access_token") == "DEMO_MODE"


def _validate_file(filename: str, size: int) -> None:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type .{ext} not supported. Use PDF or DOCX.")
    if size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum 10MB.")


def _severity_order(s: str) -> int:
    return {"critical": 0, "major": 1, "minor": 2, "acceptable": 3}.get(s, 4)


# ── Demo endpoints ─────────────────────────────────────────────────────────────

@router.get("/demo/analysis")
async def demo_contract_analysis():
    """Pre-computed demo analysis — no auth, no uploads needed."""
    counts = {"critical": 0, "major": 0, "minor": 0, "acceptable": 0}
    for d in DEMO_DEVIATIONS:
        counts[d.get("severity", "acceptable")] = counts.get(d.get("severity", "acceptable"), 0) + 1

    total_risk = sum(d.get("risk_score", 0) for d in DEMO_DEVIATIONS)
    avg_risk = round(total_risk / len(DEMO_DEVIATIONS)) if DEMO_DEVIATIONS else 0

    return {
        "demo": True,
        "deal_name": "Acme Corp — Enterprise Plan",
        "prospect_name": "Acme Corporation",
        "region": "APAC",
        "standard_contract_name": "SaaS Master Agreement v3.2",
        "standard_clauses": DEMO_STANDARD_CLAUSES,
        "standard_clause_count": len(DEMO_STANDARD_CLAUSES),
        "deviations": sorted(DEMO_DEVIATIONS, key=lambda d: _severity_order(d.get("severity", "acceptable"))),
        "summary": {
            "total_deviations": len(DEMO_DEVIATIONS),
            "critical_count": counts["critical"],
            "major_count": counts["major"],
            "minor_count": counts["minor"],
            "acceptable_count": counts["acceptable"],
            "contract_risk_score": avg_risk,
            "has_discount_risk": any(d.get("is_discount_related") for d in DEMO_DEVIATIONS),
        },
        "discount_insights": DEMO_DISCOUNT_INSIGHTS,
    }


# ── Standard contract endpoints ────────────────────────────────────────────────

@router.post("/standard/upload")
async def upload_standard_contract(
    file: UploadFile = File(...),
    name: str = Form(...),
    version: str = Form("1.0"),
    authorization: str = Header(...),
    db=Depends(get_db),
):
    """Upload company standard contract. Extracts text and clauses via LLM."""
    session = _decode_session(authorization)
    if _is_demo(session):
        return {
            "id": "std_demo",
            "name": name,
            "version": version,
            "clause_count": len(DEMO_STANDARD_CLAUSES),
            "clauses_preview": DEMO_STANDARD_CLAUSES[:3],
            "demo": True,
        }

    file_bytes = await file.read()
    _validate_file(file.filename or "file.pdf", len(file_bytes))

    from services.contract_processor import extract_text_from_bytes, extract_clauses
    raw_text = await extract_text_from_bytes(file_bytes, file.filename or "contract.pdf")
    clauses = await extract_clauses(raw_text)

    if db:
        try:
            from database.models import StandardContract
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            file_path = os.path.join(UPLOAD_DIR, f"std_{datetime.now(timezone.utc).timestamp()}_{file.filename}")
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            contract = StandardContract(
                name=name,
                version=version,
                file_path=file_path,
                raw_text=raw_text[:50000],
                is_active=True,
                clauses_json=json.dumps(clauses),
            )
            db.add(contract)
            await db.flush()
            contract_id = contract.id
        except Exception as e:
            logger.warning("Failed to save standard contract: %s", e)
            contract_id = "temp_" + str(datetime.now(timezone.utc).timestamp())
    else:
        contract_id = "temp_" + str(datetime.now(timezone.utc).timestamp())

    return {
        "id": contract_id,
        "name": name,
        "version": version,
        "clause_count": len(clauses),
        "clauses_preview": clauses[:3],
    }


@router.get("/standard/list")
async def list_standard_contracts(
    authorization: str = Header(...),
    db=Depends(get_db),
):
    session = _decode_session(authorization)
    if _is_demo(session):
        return [{"id": "std_demo", "name": "SaaS Master Agreement v3.2", "version": "3.2", "is_active": True, "clause_count": len(DEMO_STANDARD_CLAUSES)}]

    if not db:
        return []
    try:
        from database.models import StandardContract
        from sqlalchemy import select
        result = await db.execute(select(StandardContract).order_by(StandardContract.uploaded_at.desc()))
        contracts = result.scalars().all()
        return [
            {
                "id": c.id, "name": c.name, "version": c.version,
                "is_active": c.is_active,
                "clause_count": len(json.loads(c.clauses_json)) if c.clauses_json else 0,
                "uploaded_at": c.uploaded_at.isoformat() if c.uploaded_at else None,
            }
            for c in contracts
        ]
    except Exception as e:
        logger.warning("list_standard_contracts failed: %s", e)
        return []


# ── Prospect contract endpoints ────────────────────────────────────────────────

@router.post("/prospect/upload")
async def upload_prospect_contract(
    file: UploadFile = File(...),
    deal_id: str = Form(...),
    deal_name: str = Form(""),
    prospect_name: str = Form(""),
    region: str = Form(""),
    deal_amount: float = Form(0),
    deal_stage: str = Form(""),
    standard_contract_id: str = Form("std_demo"),
    authorization: str = Header(...),
    db=Depends(get_db),
):
    """Upload prospect redlined contract; compare against standard; return deviations."""
    session = _decode_session(authorization)
    if _is_demo(session):
        return await _demo_prospect_analysis(deal_id, deal_name, prospect_name, region)

    file_bytes = await file.read()
    _validate_file(file.filename or "file.pdf", len(file_bytes))

    from services.contract_processor import extract_text_from_bytes, extract_clauses, compare_contracts

    raw_text = await extract_text_from_bytes(file_bytes, file.filename or "contract.pdf")
    prospect_clauses = await extract_clauses(raw_text)

    # Load standard contract clauses
    std_clauses = DEMO_STANDARD_CLAUSES  # default fallback
    if db and standard_contract_id and not standard_contract_id.startswith("std_demo"):
        try:
            from database.models import StandardContract
            from sqlalchemy import select
            result = await db.execute(select(StandardContract).where(StandardContract.id == standard_contract_id))
            std = result.scalar_one_or_none()
            if std and std.clauses_json:
                std_clauses = json.loads(std.clauses_json)
        except Exception as e:
            logger.warning("Failed to load standard contract %s: %s", standard_contract_id, e)

    deal_context = {"name": deal_name, "amount": deal_amount, "region": region, "stage": deal_stage}
    deviations = await compare_contracts(std_clauses, prospect_clauses, deal_context)

    # Persist
    prospect_contract_id = "temp_" + str(datetime.now(timezone.utc).timestamp())
    if db:
        try:
            from database.models import ProspectContract, ContractDeviation
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            file_path = os.path.join(UPLOAD_DIR, f"pro_{datetime.now(timezone.utc).timestamp()}_{file.filename}")
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            pc = ProspectContract(
                deal_id=deal_id,
                deal_name=deal_name,
                prospect_name=prospect_name,
                region=region,
                file_path=file_path,
                raw_text=raw_text[:50000],
                clauses_json=json.dumps(prospect_clauses),
                standard_contract_id=standard_contract_id if not standard_contract_id.startswith("std_demo") else None,
            )
            db.add(pc)
            await db.flush()
            prospect_contract_id = pc.id
            for dev in deviations:
                cd = ContractDeviation(
                    prospect_contract_id=prospect_contract_id,
                    clause_category=dev.get("clause_category"),
                    clause_name=dev.get("clause_name"),
                    standard_value=dev.get("standard_value"),
                    prospect_value=dev.get("prospect_value"),
                    deviation_type=dev.get("deviation_type"),
                    severity=dev.get("severity"),
                    risk_score=dev.get("risk_score"),
                    ai_explanation=dev.get("explanation"),
                    ai_counter_suggestion=dev.get("counter_suggestion"),
                    is_discount_related=bool(dev.get("is_discount_related")),
                    discount_standard_pct=dev.get("discount_standard_pct"),
                    discount_prospect_pct=dev.get("discount_prospect_pct"),
                )
                db.add(cd)
        except Exception as e:
            logger.warning("Failed to persist prospect contract: %s", e)

    sorted_devs = sorted(deviations, key=lambda d: _severity_order(d.get("severity", "acceptable")))
    counts = {}
    for d in deviations:
        sev = d.get("severity", "acceptable")
        counts[sev] = counts.get(sev, 0) + 1

    total_risk = sum(float(d.get("risk_score") or 0) for d in deviations)
    avg_risk = round(total_risk / len(deviations)) if deviations else 0

    return {
        "prospect_contract_id": prospect_contract_id,
        "deal_id": deal_id,
        "deal_name": deal_name,
        "prospect_name": prospect_name,
        "region": region,
        "deviations": sorted_devs,
        "summary": {
            "total_deviations": len(deviations),
            "critical_count": counts.get("critical", 0),
            "major_count": counts.get("major", 0),
            "minor_count": counts.get("minor", 0),
            "acceptable_count": counts.get("acceptable", 0),
            "contract_risk_score": avg_risk,
            "has_discount_risk": any(d.get("is_discount_related") for d in deviations),
        },
    }


async def _demo_prospect_analysis(deal_id, deal_name, prospect_name, region):
    counts = {}
    for d in DEMO_DEVIATIONS:
        sev = d.get("severity", "acceptable")
        counts[sev] = counts.get(sev, 0) + 1
    total_risk = sum(d.get("risk_score", 0) for d in DEMO_DEVIATIONS)
    avg_risk = round(total_risk / len(DEMO_DEVIATIONS)) if DEMO_DEVIATIONS else 0
    return {
        "prospect_contract_id": "demo_prospect",
        "deal_id": deal_id,
        "deal_name": deal_name or "Acme Corp — Enterprise Plan",
        "prospect_name": prospect_name or "Acme Corporation",
        "region": region or "APAC",
        "deviations": sorted(DEMO_DEVIATIONS, key=lambda d: _severity_order(d.get("severity", "acceptable"))),
        "summary": {
            "total_deviations": len(DEMO_DEVIATIONS),
            "critical_count": counts.get("critical", 0),
            "major_count": counts.get("major", 0),
            "minor_count": counts.get("minor", 0),
            "acceptable_count": counts.get("acceptable", 0),
            "contract_risk_score": avg_risk,
            "has_discount_risk": any(d.get("is_discount_related") for d in DEMO_DEVIATIONS),
        },
        "discount_insights": DEMO_DISCOUNT_INSIGHTS,
        "demo": True,
    }


@router.get("/prospect/{contract_id}/deviations")
async def get_deviations(
    contract_id: str,
    authorization: str = Header(...),
    db=Depends(get_db),
):
    session = _decode_session(authorization)
    if _is_demo(session) or contract_id == "demo_prospect":
        return sorted(DEMO_DEVIATIONS, key=lambda d: _severity_order(d.get("severity", "acceptable")))

    if not db:
        return []
    try:
        from database.models import ContractDeviation
        from sqlalchemy import select
        result = await db.execute(
            select(ContractDeviation)
            .where(ContractDeviation.prospect_contract_id == contract_id)
            .order_by(ContractDeviation.risk_score.desc())
        )
        devs = result.scalars().all()
        return [
            {
                "id": d.id,
                "clause_category": d.clause_category,
                "clause_name": d.clause_name,
                "standard_value": d.standard_value,
                "prospect_value": d.prospect_value,
                "deviation_type": d.deviation_type,
                "severity": d.severity,
                "risk_score": float(d.risk_score or 0),
                "explanation": d.ai_explanation,
                "counter_suggestion": d.ai_counter_suggestion,
                "is_discount_related": d.is_discount_related,
                "discount_standard_pct": float(d.discount_standard_pct) if d.discount_standard_pct else None,
                "discount_prospect_pct": float(d.discount_prospect_pct) if d.discount_prospect_pct else None,
                "accepted": d.accepted,
            }
            for d in devs
        ]
    except Exception as e:
        logger.warning("get_deviations failed: %s", e)
        return []


class DeviationStatusBody(BaseModel):
    accepted: bool


@router.patch("/prospect/{contract_id}/deviations/{deviation_id}")
async def update_deviation_status(
    contract_id: str,
    deviation_id: str,
    body: DeviationStatusBody,
    authorization: str = Header(...),
    db=Depends(get_db),
):
    session = _decode_session(authorization)
    if _is_demo(session):
        return {"deviation_id": deviation_id, "accepted": body.accepted, "updated": True}
    if not db:
        return {"deviation_id": deviation_id, "accepted": body.accepted, "updated": False}
    try:
        from database.models import ContractDeviation
        from sqlalchemy import select
        result = await db.execute(select(ContractDeviation).where(ContractDeviation.id == deviation_id))
        dev = result.scalar_one_or_none()
        if not dev:
            raise HTTPException(status_code=404, detail="Deviation not found")
        dev.accepted = body.accepted
        dev.accepted_at = datetime.now(timezone.utc)
        return {"deviation_id": deviation_id, "accepted": body.accepted, "updated": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Insights endpoints ─────────────────────────────────────────────────────────

@router.get("/insights/discounts")
async def get_discount_insights(
    region: Optional[str] = None,
    authorization: str = Header(...),
    db=Depends(get_db),
):
    session = _decode_session(authorization)
    if _is_demo(session):
        result = dict(DEMO_DISCOUNT_INSIGHTS)
        if region:
            result["filtered_region"] = region
        return result

    if not db:
        return DEMO_DISCOUNT_INSIGHTS

    try:
        from database.models import ContractDeviation, ProspectContract
        from sqlalchemy import select
        q = (
            select(ContractDeviation, ProspectContract)
            .join(ProspectContract, ContractDeviation.prospect_contract_id == ProspectContract.id)
            .where(ContractDeviation.is_discount_related == True)
        )
        if region:
            q = q.where(ProspectContract.region == region)
        result = await db.execute(q)
        rows = result.all()

        all_discounts = [
            {
                "deal_name": pc.deal_name,
                "discount_pct": float(cd.discount_prospect_pct or 0),
                "accepted": cd.accepted,
                "region": pc.region,
            }
            for cd, pc in rows
            if cd.discount_prospect_pct
        ]

        if not all_discounts:
            return DEMO_DISCOUNT_INSIGHTS

        avg = sum(d["discount_pct"] for d in all_discounts) / len(all_discounts)
        return {
            "company_avg_discount_pct": round(avg, 1),
            "all_deals_discounts": all_discounts,
        }
    except Exception as e:
        logger.warning("get_discount_insights failed: %s", e)
        return DEMO_DISCOUNT_INSIGHTS


@router.get("/insights/common-deviations")
async def get_common_deviations(
    authorization: str = Header(...),
    db=Depends(get_db),
):
    session = _decode_session(authorization)
    if _is_demo(session):
        from collections import Counter
        cats = [d["clause_category"] for d in DEMO_DEVIATIONS]
        return [{"clause_category": c, "deviation_count": n, "acceptance_rate": 0.5} for c, n in Counter(cats).most_common()]

    if not db:
        return []
    try:
        from database.models import ContractDeviation
        from sqlalchemy import select, func as sqlfunc
        result = await db.execute(
            select(
                ContractDeviation.clause_category,
                sqlfunc.count(ContractDeviation.id).label("deviation_count"),
            ).group_by(ContractDeviation.clause_category).order_by(sqlfunc.count(ContractDeviation.id).desc())
        )
        return [{"clause_category": r.clause_category, "deviation_count": r.deviation_count} for r in result.all()]
    except Exception as e:
        logger.warning("get_common_deviations failed: %s", e)
        return []


@router.get("/insights/deal/{deal_id}")
async def get_deal_contract_risk(
    deal_id: str,
    authorization: str = Header(...),
    db=Depends(get_db),
):
    session = _decode_session(authorization)
    if _is_demo(session):
        return {
            "deal_id": deal_id,
            "total_deviations": len(DEMO_DEVIATIONS),
            "critical_count": sum(1 for d in DEMO_DEVIATIONS if d["severity"] == "critical"),
            "major_count": sum(1 for d in DEMO_DEVIATIONS if d["severity"] == "major"),
            "discount_risk": True,
            "contract_risk_score": 75,
            "recommendation": "2 critical deviations require negotiation before signing.",
        }
    if not db:
        return {"deal_id": deal_id, "total_deviations": 0, "contract_risk_score": 0}
    try:
        from database.models import ContractDeviation, ProspectContract
        from sqlalchemy import select
        result = await db.execute(
            select(ContractDeviation)
            .join(ProspectContract, ContractDeviation.prospect_contract_id == ProspectContract.id)
            .where(ProspectContract.deal_id == deal_id)
        )
        devs = result.scalars().all()
        if not devs:
            return {"deal_id": deal_id, "total_deviations": 0, "contract_risk_score": 0, "no_contract": True}
        critical = sum(1 for d in devs if d.severity == "critical")
        major = sum(1 for d in devs if d.severity == "major")
        avg_risk = sum(float(d.risk_score or 0) for d in devs) / len(devs)
        return {
            "deal_id": deal_id,
            "total_deviations": len(devs),
            "critical_count": critical,
            "major_count": major,
            "discount_risk": any(d.is_discount_related for d in devs),
            "contract_risk_score": round(avg_risk),
        }
    except Exception as e:
        logger.warning("get_deal_contract_risk failed: %s", e)
        return {"deal_id": deal_id, "total_deviations": 0, "contract_risk_score": 0}


@router.get("/library")
async def list_prospect_contracts(
    authorization: str = Header(...),
    db=Depends(get_db),
):
    session = _decode_session(authorization)
    if _is_demo(session):
        return [
            {
                "id": "demo_prospect",
                "deal_name": "Acme Corp — Enterprise Plan",
                "prospect_name": "Acme Corporation",
                "region": "APAC",
                "uploaded_at": "2026-03-10T10:00:00Z",
                "deviation_count": len(DEMO_DEVIATIONS),
                "critical_count": sum(1 for d in DEMO_DEVIATIONS if d["severity"] == "critical"),
                "has_discount_risk": True,
                "contract_risk_score": 75,
            }
        ]
    if not db:
        return []
    try:
        from database.models import ProspectContract, ContractDeviation
        from sqlalchemy import select, func as sqlfunc
        result = await db.execute(
            select(ProspectContract).order_by(ProspectContract.uploaded_at.desc()).limit(50)
        )
        contracts = result.scalars().all()
        output = []
        for c in contracts:
            dev_result = await db.execute(
                select(sqlfunc.count(ContractDeviation.id))
                .where(ContractDeviation.prospect_contract_id == c.id)
            )
            dev_count = dev_result.scalar() or 0
            critical_result = await db.execute(
                select(sqlfunc.count(ContractDeviation.id))
                .where(ContractDeviation.prospect_contract_id == c.id)
                .where(ContractDeviation.severity == "critical")
            )
            critical_count = critical_result.scalar() or 0
            output.append({
                "id": c.id,
                "deal_name": c.deal_name,
                "prospect_name": c.prospect_name,
                "region": c.region,
                "deal_id": c.deal_id,
                "uploaded_at": c.uploaded_at.isoformat() if c.uploaded_at else None,
                "deviation_count": dev_count,
                "critical_count": critical_count,
            })
        return output
    except Exception as e:
        logger.warning("list_prospect_contracts failed: %s", e)
        return []
