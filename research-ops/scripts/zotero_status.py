from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path


def env_present(name: str) -> bool:
    return bool(os.environ.get(name))


def check_local_api() -> dict[str, object]:
    # Zotero Desktop exposes the local user library as userID 0. Use HEAD so
    # health checks never read item metadata or annotations from the library.
    url = "http://127.0.0.1:23119/api/users/0/items?limit=1"
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return {
                "available": True,
                "status": response.status,
                "library_id": 0,
                "method": "HEAD",
            }
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    appdata = os.environ.get("APPDATA")
    localappdata = os.environ.get("LOCALAPPDATA")
    status = {
        "zotero_desktop_paths": {
            "roaming": {
                "path": str(Path(appdata or "") / "Zotero") if appdata else None,
                "exists": bool(appdata and (Path(appdata) / "Zotero").exists()),
            },
            "local": {
                "path": str(Path(localappdata or "") / "Zotero") if localappdata else None,
                "exists": bool(localappdata and (Path(localappdata) / "Zotero").exists()),
            },
        },
        "web_api_env": {
            "ZOTERO_API_KEY": env_present("ZOTERO_API_KEY"),
            "ZOTERO_USER_ID": env_present("ZOTERO_USER_ID"),
            "ZOTERO_GROUP_ID": env_present("ZOTERO_GROUP_ID"),
            "ZOTERO_LIBRARY_TYPE": os.environ.get("ZOTERO_LIBRARY_TYPE") or None,
        },
        "local_api": check_local_api(),
        "ready_for_web_api_sync": env_present("ZOTERO_API_KEY")
        and (env_present("ZOTERO_USER_ID") or env_present("ZOTERO_GROUP_ID")),
    }
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
