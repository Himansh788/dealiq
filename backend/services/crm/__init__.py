from services.crm.base import CRMAdapter, CRMDeal, CRMActivity, CRMEmail, CRMContact, CRMUser, CRMAuthTokens
from services.crm.zoho_adapter import ZohoAdapter
from services.crm.salesforce_adapter import SalesforceAdapter
from services.crm.hubspot_adapter import HubSpotAdapter

CRM_ADAPTERS: dict[str, type[CRMAdapter]] = {
    "zoho": ZohoAdapter,
    "salesforce": SalesforceAdapter,
    "hubspot": HubSpotAdapter,
}

def get_crm_adapter(provider: str) -> CRMAdapter:
    adapter_class = CRM_ADAPTERS.get(provider)
    if not adapter_class:
        raise ValueError(f"Unknown CRM provider: {provider}. Supported: {list(CRM_ADAPTERS.keys())}")
    return adapter_class()
