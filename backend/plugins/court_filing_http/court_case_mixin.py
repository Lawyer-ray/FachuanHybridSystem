from __future__ import annotations

import re
from typing import Any

class CourtCaseMixin:
    async def _lookup_court(self: Any, sfid: str, court_name: str) -> str:
        keyword = re.sub(r"(人民法院|法院)$", "", court_name).strip()
        for fymc_param in (keyword, ""):
            courts = await self._get("/yzw-zxfw-lafw/api/v3/pz/fy", sfid=sfid, city="", fymc=fymc_param)
            if isinstance(courts, list):
                for c in courts:
                    if court_name in c.get("fymc", "") or keyword in c.get("fymc", ""):
                        return str(c.get("value") or c.get("fyid") or c.get("id"))
        raise RuntimeError(f"找不到法院: {court_name}")

    async def _create_layy(self: Any, fyid: str, ajlx: str, sfid: str, *, is_exec: bool = False) -> str:
        payload: dict[str, Any] = {
            "ajcx": "zx" if is_exec else "sp",
            "ajlx": ajlx,
            "tjcgsqsfqr": "1",
            "fyid": fyid,
            "sqrsf": "11800010-2",
            "ajlb": "zx" if is_exec else "sp",
            "pcSqrLx": "",
            "sqrlx": "11800011-1",
            "sfid": sfid,
            "ftmc": "",
            "sfzscq": "1501_000010-2",
            "sfysla": "1501_000010-2",
        }
        if not is_exec:
            payload["lafs"] = "2"
        data = await self._post("/yzw-zxfw-lafw/api/v3/layy", payload)
        return str(data)

    async def _get_jbxx(self: Any, layyid: str) -> dict[str, Any]:
        data = await self._get(f"/yzw-zxfw-lafw/api/v3/layy/jbxx/{layyid}")
        return dict(data) if isinstance(data, dict) else {}

    async def _patch_layy(self: Any, layyid: str, payload: dict[str, Any]) -> None:
        payload["id"] = layyid
        await self._patch("/yzw-zxfw-lafw/api/v3/layy", payload)

    async def _lookup_cause_code(self: Any, cause: str) -> str:
        try:
            tree = await self._get("/yzw-zxfw-lafw/api/v1/ay/tree/batch", lbs="0300")
            if isinstance(tree, list):
                for node in tree:
                    if node.get("laay") == cause or node.get("laayMz") == cause:
                        return str(node.get("laayMz", ""))
                    for child in node.get("children") or []:
                        if child.get("laay") == cause:
                            return str(child.get("laayMz", ""))
        except Exception:
            pass
        return ""
