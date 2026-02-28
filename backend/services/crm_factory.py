"""
CRM adapter factory.

Single entry point for obtaining the right CRMAdapter given a session type.
Adding a new CRM integration means adding one entry here and one adapter file —
no other files need to change.
"""

from services.crm_adapter import CRMAdapter
from services.crm_errors import CRMError


def get_crm_adapter(session_type: str) -> CRMAdapter:
    """
    Return the CRMAdapter implementation for the given session_type.

    Args:
        session_type: One of "demo" | "zoho".
                      Future values: "salesforce" | "hubspot" | "pipedrive"

    Raises:
        CRMError: if session_type is not recognised.
    """
    if session_type == "demo":
        from services.demo_adapter import DemoCRMAdapter
        return DemoCRMAdapter()

    if session_type == "zoho":
        from services.zoho_adapter import ZohoCRMAdapter
        return ZohoCRMAdapter()

    raise CRMError(
        f"Unknown CRM session type '{session_type}'. "
        f"Supported: demo, zoho",
        crm=session_type,
    )


def get_adapter_from_session(session: dict) -> CRMAdapter:
    """
    Convenience helper: derive session_type from a decoded session dict and
    return the matching adapter.  Mirrors the _is_demo() check used in routers.

    Usage in future v2 routers:
        adapter = get_adapter_from_session(session)
        deals = await adapter.get_deals(session["access_token"])
    """
    access_token = session.get("access_token", "")
    session_type = "demo" if access_token == "DEMO_MODE" else "zoho"
    return get_crm_adapter(session_type)
