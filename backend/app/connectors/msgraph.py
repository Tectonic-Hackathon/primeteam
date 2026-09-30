"""Microsoft Graph helpers shared by SharePoint, Teams, Outlook and Meetings connectors.
Auth: OAuth2 client credentials (app registration with application permissions)."""
import os
import httpx

GRAPH = "https://graph.microsoft.com/v1.0"
_token = {"value": None}


def token() -> str:
    if _token["value"]:
        return _token["value"]
    tenant = os.environ["MS_TENANT_ID"]
    r = httpx.post(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data={
            "client_id": os.environ["MS_CLIENT_ID"],
            "client_secret": os.environ["MS_CLIENT_SECRET"],
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    r.raise_for_status()
    _token["value"] = r.json()["access_token"]
    return _token["value"]


def get(path: str, params: dict | None = None, raw: bool = False):
    url = path if path.startswith("http") else f"{GRAPH}{path}"
    r = httpx.get(url, params=params, headers={"Authorization": f"Bearer {token()}"}, timeout=60)
    r.raise_for_status()
    return r.text if raw else r.json()


def paged(path: str, params: dict | None = None):
    """Follow @odata.nextLink pages."""
    data = get(path, params)
    while True:
        yield from data.get("value", [])
        nxt = data.get("@odata.nextLink")
        if not nxt:
            break
        data = get(nxt)
