from fastapi import APIRouter

router = APIRouter()


@router.get("/db")
async def db_health():
    """
    Returns the live PostgreSQL connection status.

    - {"status": "ok", "db": true}  — DATABASE_URL is set and reachable
    - {"status": "ok", "db": false} — DATABASE_URL not set, or connection failed

    Never raises a 5xx — intentionally always returns 200 so orchestrators and
    uptime monitors can distinguish "API up, no DB configured" from "API down".
    """
    from database.connection import check_db_health

    db_ok = await check_db_health()
    return {"status": "ok", "db": db_ok}
