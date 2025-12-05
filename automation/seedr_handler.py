"""
Seedr Handler
-------------
Uses Seedr REST API v1 with Basic Auth (email + password).

Flow for ONE movie:
1) add_magnet()          -> create transfer
2) wait_for_download()   -> poll until done
3) get_largest_file()    -> pick biggest file in folder
4) get_direct_link()     -> direct download URL
5) delete_transfer_data() -> delete folder/file to free space
"""

import asyncio
import httpx
from typing import Optional, Dict, Tuple

from os import getenv

SEEDR_EMAIL = getenv("SEEDR_EMAIL", "")
SEEDR_PASSWORD = getenv("SEEDR_PASSWORD", "")

BASE_URL = "https://www.seedr.cc"


class SeedrHandler:
    def __init__(self):
        if not SEEDR_EMAIL or not SEEDR_PASSWORD:
            print("❌ SEEDR_EMAIL / SEEDR_PASSWORD not set in env variables")

        self.auth = (SEEDR_EMAIL, SEEDR_PASSWORD)

    # ---------- CORE API CALL HELPERS ----------

    async def _post(self, path: str, data: Dict) -> Optional[Dict]:
        url = f"{BASE_URL}{path}"
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(url, data=data, auth=self.auth)
                if r.status_code == 200:
                    return r.json()
                print(f"❌ POST {path} failed: {r.status_code} {r.text[:200]}")
        except Exception as e:
            print(f"❌ POST {path} error: {e}")
        return None

    async def _get(self, path: str) -> Optional[Dict]:
        url = f"{BASE_URL}{path}"
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.get(url, auth=self.auth)
                if r.status_code == 200:
                    return r.json()
                print(f"❌ GET {path} failed: {r.status_code} {r.text[:200]}")
        except Exception as e:
            print(f"❌ GET {path} error: {e}")
        return None

    # ---------- HIGH LEVEL OPERATIONS ----------

    async def add_magnet(self, magnet_link: str) -> Optional[int]:
        """
        Add a magnet to Seedr.
        Returns transfer id (int) on success, None on failure.
        Seedr API: POST /rest/transfer/magnet  [web:37]
        """
        data = {"magnet": magnet_link}
        resp = await self._post("/rest/transfer/magnet", data)
        if not resp:
            return None

        # Response usually includes transfer list; pick newest
        transfers = resp.get("transfers") or resp.get("transfer") or []
        if isinstance(transfers, dict):
            # single transfer object
            t = transfers
        elif transfers:
            t = transfers[-1]
        else:
            print("⚠️ add_magnet: no transfer info in response", resp)
            return None

        transfer_id = t.get("id")
        print(f"✅ Seedr: magnet added, transfer_id={transfer_id}")
        return transfer_id

    async def get_transfer_info(self, transfer_id: int) -> Optional[Dict]:
        """
        Get status of a transfer.
        GET /rest/transfer/{id} or generic transfer list depending on API [web:37]
        """
        # Some Seedr docs show /rest/transfer/{id}, some /rest/transfer
        # Here we try per-id first, fallback to list.
        info = await self._get(f"/rest/transfer/{transfer_id}")
        if info:
            return info

        # Fallback: list all transfers, find ours
        transfers = await self._get("/rest/transfer")
        if not transfers:
            return None

        items = transfers.get("transfers") or []
        for t in items:
            if int(t.get("id", -1)) == int(transfer_id):
                return t
        return None

    async def wait_for_download(
        self,
        transfer_id: int,
        max_wait_minutes: int = 60,
        poll_seconds: int = 30,
    ) -> Tuple[bool, Optional[int]]:
        """
        Wait until transfer is finished or failed.
        Returns (True, folder_id) on success; (False, None) on failure.
        """
        attempts = int(max_wait_minutes * 60 / poll_seconds)

        for i in range(attempts):
            info = await self.get_transfer_info(transfer_id)
            if not info:
                print("⚠️ wait_for_download: no info, retrying...")
                await asyncio.sleep(poll_seconds)
                continue

            status = str(info.get("status") or info.get("state") or "").lower()
            progress = info.get("progress") or info.get("percent_done") or 0
            folder_id = info.get("folder_id") or info.get("folder") or None

            print(f"⏳ Seedr Transfer {transfer_id}: {status} {progress}%")

            if status in ("finished", "seeding", "done", "complete"):
                print(f"✅ Seedr: transfer completed, folder_id={folder_id}")
                return True, int(folder_id) if folder_id else None

            if status in ("error", "failed"):
                print(f"❌ Seedr: transfer failed: {info}")
                return False, None

            await asyncio.sleep(poll_seconds)

        print("⏰ Seedr: wait_for_download timeout")
        return False, None

    async def list_folder(self, folder_id: Optional[int] = None) -> Optional[Dict]:
        """
        List files/folders for root or given folder.
        GET /rest/folder or /rest/folder/{id} [web:37]
        """
        path = "/rest/folder" if folder_id is None else f"/rest/folder/{folder_id}"
        return await self._get(path)

    async def get_largest_file(
        self, folder_id: Optional[int]
    ) -> Optional[Dict]:
        """
        From a folder, choose largest file (movie file).
        """
        data = await self.list_folder(folder_id)
        if not data:
            return None

        files = data.get("files") or []
        if not files:
            print("⚠️ Seedr: no files in folder", folder_id)
            return None

        largest = max(files, key=lambda f: f.get("size", 0))
        print(
            f"🎬 Seedr: largest file = {largest.get('name')} "
            f"({largest.get('size',0)/(1024*1024):.2f} MB)"
        )
        return largest

    async def get_direct_link(self, file_id: int) -> Optional[str]:
        """
        Get direct download URL for file.
        GET /rest/file/{id} [web:37]
        """
        data = await self._get(f"/rest/file/{file_id}")
        if not data:
            return None

        # Docs show fields like 'download_url' or 'url'
        url = data.get("download_url") or data.get("url")
        if url:
            print(f"🔗 Seedr: direct link = {url[:80]}...")
            return url

        print("⚠️ Seedr: no direct link in response", data)
        return None

    async def delete_folder(self, folder_id: int) -> bool:
        """
        Delete folder and its contents to free space.
        POST /rest/folder/{id}/delete [web:37]
        """
        resp = await self._post(f"/rest/folder/{folder_id}/delete", {})
        if not resp:
            return False

        if resp.get("result") == "success" or resp.get("success") is True:
            print(f"🗑️ Seedr: folder {folder_id} deleted")
            return True

        print("⚠️ Seedr: delete_folder response:", resp)
        return False

    async def delete_transfer(self, transfer_id: int) -> bool:
        """
        Optionally remove transfer entry itself.
        POST /rest/transfer/delete or similar; not always necessary. [web:37]
        """
        resp = await self._post("/rest/transfer/delete", {"transfer_id": transfer_id})
        if not resp:
            return False
        print(f"🗑️ Seedr: transfer {transfer_id} delete resp={resp}")
        return True

    async def delete_transfer_data(
        self, transfer_id: int, folder_id: Optional[int]
    ) -> None:
        """
        Helper: delete both folder (data) and transfer entry.
        """
        if folder_id:
            await self.delete_folder(folder_id)
        await self.delete_transfer(transfer_id)

    # ---------- ONE-SHOT PIPELINE FOR ONE MOVIE ----------

    async def process_one_movie(self, magnet_link: str) -> Optional[str]:
        """
        Full Seedr side pipeline for ONE magnet:
        - add magnet
        - wait for download
        - get largest file
        - get direct link
        - delete data from Seedr

        Returns: direct_link (str) or None
        """
        # 1) Add magnet
        transfer_id = await self.add_magnet(magnet_link)
        if not transfer_id:
            return None

        # 2) Wait for completion
        ok, folder_id = await self.wait_for_download(transfer_id)
        if not ok:
            return None

        # 3) Pick largest file
        movie_file = await self.get_largest_file(folder_id)
        if not movie_file:
            await self.delete_transfer_data(transfer_id, folder_id)
            return None

        file_id = movie_file.get("id") or movie_file.get("file_id")
        if not file_id:
            print("⚠️ Seedr: no file_id in movie_file", movie_file)
            await self.delete_transfer_data(transfer_id, folder_id)
            return None

        # 4) Get direct link
        direct_link = await self.get_direct_link(int(file_id))

        # 5) Delete from Seedr to free 3GB space
        await self.delete_transfer_data(transfer_id, folder_id)

        return direct_link
