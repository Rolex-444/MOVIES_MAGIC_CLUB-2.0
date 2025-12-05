"""
PPD/PPV Remote Upload Handler (Dual-host)
- LuluStream => returns watch_url (stream)
- DropGalaxy => returns download_url (PPD)
- Fallback to generic PPD if either host vars are missing
"""

import os
import httpx
from typing import Optional, Dict

from .config import (
    LULU_API_KEY, LULU_API_BASE,
    DG_API_URL, DG_API_KEY,
    PPD_API_URL, PPD_API_KEY,
)

# Optional endpoint overrides via env (because each host names endpoints differently)
LULU_REMOTE_PATH = os.getenv("LULU_REMOTE_PATH", "/api/remote_upload")
LULU_STATUS_PATH = os.getenv("LULU_STATUS_PATH", "/api/upload_status")
DG_REMOTE_PATH   = os.getenv("DG_REMOTE_PATH", "/api/remote_upload")
DG_STATUS_PATH   = os.getenv("DG_STATUS_PATH", "/api/upload_status")

TIMEOUT_SECS = 300  # generous for remote uploads


class PPDUploader:
    def __init__(self):
        self.lulu_base = (LULU_API_BASE or "").rstrip("/")
        self.lulu_key  = LULU_API_KEY or ""
        self.dg_base   = (DG_API_URL or "").rstrip("/")    # some sites give full API base
        self.dg_key    = DG_API_KEY or ""
        self.generic_base = (PPD_API_URL or "").rstrip("/")
        self.generic_key  = PPD_API_KEY or ""

    # ---------- Public API ----------

    async def remote_upload(self, direct_link: str, filename: str) -> Optional[Dict]:
        """
        Returns: {"watch_url": <lulu stream>, "download_url": <ppd>, "lulu_id": ..., "dg_id": ...}
        If either host config is missing, will try the other and/or generic fallback.
        """
        watch_url = None
        download_url = None
        lulu_id = None
        dg_id = None

        # 1) LuluStream (Watch)
        if self.lulu_base and self.lulu_key:
            watch = await self._upload_to_lulu(direct_link, filename)
            if watch:
                watch_url, lulu_id = watch.get("watch_url"), watch.get("file_id")

        # 2) DropGalaxy (Download)
        if self.dg_base:
            down = await self._upload_to_dg(direct_link, filename)
            if down:
                download_url, dg_id = down.get("download_url"), down.get("file_id")

        # 3) Generic fallback (if download_url still empty and generic PPD configured)
        if not download_url and self.generic_base and self.generic_key:
            gen = await self._upload_generic_ppd(direct_link, filename)
            if gen:
                download_url = gen.get("download_url")

        if watch_url or download_url:
            return {
                "watch_url": watch_url,
                "download_url": download_url,
                "lulu_id": lulu_id,
                "dg_id": dg_id,
            }

        print("❌ Remote upload failed on all configured hosts")
        return None

    async def check_upload_status(self, host: str, file_id: str) -> Dict:
        """
        host: "lulu" or "dg" or "generic"
        Standardized response: {"status": "pending|complete|error", "progress": int}
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                if host == "lulu" and self.lulu_base:
                    url = f"{self.lulu_base}{LULU_STATUS_PATH}"
                    r = await client.get(url, params={"api_key": self.lulu_key, "id": file_id})
                elif host == "dg" and self.dg_base:
                    url = f"{self.dg_base}{DG_STATUS_PATH}"
                    params = {"id": file_id}
                    if self.dg_key:
                        params["api_key"] = self.dg_key
                    r = await client.get(url, params=params)
                else:
                    # generic
                    url = f"{self.generic_base}/file/{file_id}/status"
                    r = await client.get(url, params={"api_key": self.generic_key})

                if r.status_code == 200:
                    data = r.json()
                    status = (data.get("status") or "").lower()
                    prog = int(data.get("progress", 0))
                    return {"status": status or "pending", "progress": prog}

        except Exception as e:
            print(f"❌ Status check error: {e}")
        return {"status": "error", "progress": 0}

    # ---------- Host adapters ----------

    async def _upload_to_lulu(self, direct_link: str, filename: str) -> Optional[Dict]:
        """
        LuluStream adapter.
        Notes:
        - Many hosts accept 'api_key' + 'url' + optional 'name/filename'.
        - We keep parsing flexible: file_id may be 'id' | 'file_id' | 'code', and URL may be 'watch_url' | 'url' | 'stream_url'.
        """
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECS) as client:
                endpoint = f"{self.lulu_base}{LULU_REMOTE_PATH}"
                payload = {"api_key": self.lulu_key, "url": direct_link, "name": filename}
                r = await client.post(endpoint, data=payload)
                if r.status_code != 200:
                    print(f"❌ Lulu upload HTTP {r.status_code}: {r.text[:200]}")
                    return None
                data = r.json()
                if not data or data.get("error"):
                    print(f"❌ Lulu upload error: {data}")
                    return None

                # Flexible parsing
                file_id = data.get("file_id") or data.get("id") or data.get("code")
                watch_url = (
                    data.get("watch_url")
                    or data.get("stream_url")
                    or data.get("url")
                    or (f"{self.lulu_base}/watch/{file_id}" if file_id else None)
                )
                if watch_url:
                    return {"watch_url": watch_url, "file_id": file_id}

                print(f"⚠️ Lulu response missing watch URL: {data}")
        except Exception as e:
            print(f"❌ Lulu upload exception: {e}")
        return None

    async def _upload_to_dg(self, direct_link: str, filename: str) -> Optional[Dict]:
        """
        DropGalaxy adapter.
        - Some accounts provide a full API base with token; we add filename and url.
        - If DG_API_KEY is set, include it as 'api_key'.
        """
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECS) as client:
                endpoint = f"{self.dg_base}{DG_REMOTE_PATH}"
                payload = {"url": direct_link, "filename": filename}
                if self.dg_key:
                    payload["api_key"] = self.dg_key
                r = await client.post(endpoint, data=payload)
                if r.status_code != 200:
                    print(f"❌ DG upload HTTP {r.status_code}: {r.text[:200]}")
                    return None
                data = r.json()
                if not data or data.get("error"):
                    print(f"❌ DG upload error: {data}")
                    return None

                file_id = data.get("file_id") or data.get("id") or data.get("code")
                download_url = (
                    data.get("download_url")
                    or data.get("url")
                    or (f"{self.dg_base}/download/{file_id}" if file_id else None)
                )
                if download_url:
                    return {"download_url": download_url, "file_id": file_id}

                print(f"⚠️ DG response missing download URL: {data}")
        except Exception as e:
            print(f"❌ DG upload exception: {e}")
        return None

    async def _upload_generic_ppd(self, direct_link: str, filename: str) -> Optional[Dict]:
        """
        Generic PPD fallback using the common 'remote_upload' pattern.
        Different hosts expose different paths and fields; this mirrors your old implementation.
        """
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECS) as client:
                endpoint = f"{self.generic_base}/remote_upload"
                payload = {"api_key": self.generic_key, "url": direct_link, "filename": filename}
                r = await client.post(endpoint, data=payload)
                if r.status_code != 200:
                    print(f"❌ Generic PPD HTTP {r.status_code}: {r.text[:200]}")
                    return None
                data = r.json()
                if data.get("success"):
                    file_id = data.get("file_id")
                    return {
                        "download_url": f"{self.generic_base}/download/{file_id}",
                        "file_id": file_id,
                    }
                print(f"❌ Generic PPD upload failed: {data}")
        except Exception as e:
            print(f"❌ Generic PPD exception: {e}")
        return None
        
