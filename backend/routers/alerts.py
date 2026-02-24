from fastapi import APIRouter, Header, HTTPException
import base64
import json
from services.alerts_digest import generate_digest
from services.demo_data import SIMULATED_DEALS
from services.health_scorer import score_deal_from_zoho

router = APIRouter()


def _decode_session(authorization: str) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")
    token = authorization.replace("Bearer ", "").strip()
    try:
        return json.loads(base64.b64decode(token).decode())
    except Exception:
        pass
    if len(token) > 10:
        return {"user_id": "zoho_user", "access_token": token, "refresh_token": ""}
    raise HTTPException(status_code=401, detail="Invalid session token")


def _is_demo(session: dict) -> bool:
    return session.get("access_token") == "DEMO_MODE"


def _enrich(raw: dict) -> dict:
    result = score_deal_from_zoho(raw)
    raw["health_score"] = result.total_score
    raw["health_label"] = result.health_label
    return raw


@router.get("/digest")
async def get_alerts_digest(authorization: str = Header(...)):
    session = _decode_session(authorization)
    simulated = _is_demo(session)

    if simulated:
        deals = [_enrich(dict(d)) for d in SIMULATED_DEALS]
    else:
        try:
            from routers.deals import _fetch_all_zoho_deals, is_active_deal, get_current_quarter_range
            raw_deals = await _fetch_all_zoho_deals(session["access_token"])
            quarter_start, quarter_end = get_current_quarter_range()
            active_deals = [d for d in raw_deals if is_active_deal(d, quarter_start, quarter_end)]
            deals = [_enrich(d) for d in active_deals]
        except Exception:
            deals = [_enrich(dict(d)) for d in SIMULATED_DEALS]
            simulated = True

    digest = generate_digest(deals)
    digest["simulated"] = simulated
    return digest