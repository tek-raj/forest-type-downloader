#!/usr/bin/env python3
"""
Bulk download of CLMS Forest Type 2018-present (10 m, Europe) from the
Copernicus Data Space Ecosystem (CDSE).

The CLMS portal points full downloads of this dataset to CDSE, where it is
stored as one Cloud-Optimised GeoTIFF per 100 x 100 km tile (EPSG:3035, plus
the overseas regions GF/GP/MQ/RE/YT in UTM). A public CSV catalogue lists every
tile; each tile is downloaded through the CDSE OData API.

Setup:
    pip install requests
    Free account: https://dataspace.copernicus.eu  (the CLMS key does NOT work here)

Usage:
    python cdse_download.py list                       # tiles + size per year
    python cdse_download.py list --year 2018 --bbox 5.9 45.8 10.5 47.8
    python cdse_download.py get --year 2018            # all 2018 tiles (~3.4 GB)
    python cdse_download.py get --year 2018 2021 --bbox W S E N --workers 4

Credentials: set CDSE_USER / CDSE_PASSWORD, or you are prompted (password is
not echoed). Nothing is written to disk except the tiles.

Files go to downloads/forest_type/<year>/<tile>.tif (unpacked from the zip
CDSE serves, with a matching .qml style). Tiles already present are skipped,
so re-running resumes an interrupted download.
"""

import argparse
import csv
import getpass
import hashlib
import io
import os
import re
import shutil
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

CATALOGUE_CSV = ("https://s3.waw3-1.cloudferro.com/swift/v1/CatalogueCSV/landcover_landuse/"
                 "forest_type/clms_vlcc_forest-type_europe_10m_3yearly_v1/"
                 "clms_vlcc_forest-type_europe_10m_3yearly_v1_cog.csv")
TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
DOWNLOAD_URL = "https://download.dataspace.copernicus.eu/odata/v1/Products({id})/$value"
TIMEOUT = 120


# --------------------------------------------------------------------------
# Catalogue
# --------------------------------------------------------------------------
def load_tiles() -> list:
    r = requests.get(CATALOGUE_CSV, timeout=TIMEOUT)
    r.raise_for_status()
    tiles = []
    for row in csv.DictReader(io.StringIO(r.text), delimiter=";"):
        xs, ys = [], []
        for x, y in re.findall(r"(-?[\d.]+) (-?[\d.]+)", row["bbox"]):
            xs.append(float(x)); ys.append(float(y))
        tiles.append({
            "id": row["id"], "name": row["name"], "size": int(row["content_length"]),
            "year": row["content_date_start"][:4], "md5": row["checksum_value"].lower(),
            "bbox": (min(xs), min(ys), max(xs), max(ys)) if xs else None,
        })
    return tiles


def select(tiles: list, years, bbox) -> list:
    out = [t for t in tiles if not years or t["year"] in years]
    if bbox:
        w, s, e, n = bbox
        out = [t for t in out if t["bbox"] and not
               (t["bbox"][2] < w or t["bbox"][0] > e or t["bbox"][3] < s or t["bbox"][1] > n)]
    return out


def summary(tiles: list) -> None:
    by_year = {}
    for t in tiles:
        c, s = by_year.get(t["year"], (0, 0))
        by_year[t["year"]] = (c + 1, s + t["size"])
    for y in sorted(by_year):
        c, s = by_year[y]
        print(f"  {y}: {c} tiles, {s/1e9:.2f} GB")
    print(f"  total: {len(tiles)} tiles, {sum(t['size'] for t in tiles)/1e9:.2f} GB")


# --------------------------------------------------------------------------
# Auth (access tokens last ~10 min; refreshed automatically)
# --------------------------------------------------------------------------
class CDSE:
    def __init__(self, user: str, password: str):
        self._lock = threading.Lock()
        self._get({"grant_type": "password", "username": user, "password": password,
                   "client_id": "cdse-public"})

    def _get(self, data: dict) -> None:
        r = requests.post(TOKEN_URL, data=data, timeout=TIMEOUT)
        if r.status_code == 401 or "invalid_grant" in r.text:
            raise RuntimeError("CDSE login refused: check the email and password of your "
                               "dataspace.copernicus.eu account.")
        if r.status_code != 200:
            raise RuntimeError(f"CDSE login failed ({r.status_code}): {r.text[:300]}")
        j = r.json()
        self._access = j["access_token"]
        self._refresh = j.get("refresh_token")
        self._expires = time.time() + j.get("expires_in", 600) - 60

    def token(self) -> str:
        with self._lock:
            if time.time() >= self._expires:
                self._get({"grant_type": "refresh_token", "refresh_token": self._refresh,
                           "client_id": "cdse-public"})
            return self._access


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------
def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_tiff(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(4) in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")
    except OSError:
        return False


def unpack(zpath: Path, dest: Path) -> None:
    """CDSE delivers each tile as a zip: keep the GeoTIFF, its .aux.xml and the
    QGIS style (renamed <tile>.qml so QGIS applies the legend colours)."""
    with zipfile.ZipFile(zpath) as z:
        members = {}
        for info in z.infolist():
            base = info.filename.rsplit("/", 1)[-1]
            if base.endswith(".tif.aux.xml"):
                members[dest.with_name(dest.name + ".aux.xml")] = info
            elif base.endswith(".qml"):
                members[dest.with_suffix(".qml")] = info
            elif base.endswith(".tif"):
                tif = info
        # the .tif is written last, so its presence means the tile is complete
        for target, info in list(members.items()) + [(dest, tif)]:
            tmp = target.with_name(target.name + ".part")
            with z.open(info) as src, open(tmp, "wb") as f:
                shutil.copyfileobj(src, f)
            tmp.replace(target)


def fetch(auth: CDSE, t: dict, out_dir: Path) -> str:
    dest = out_dir / t["year"] / f"{t['name']}.tif"
    zpath = dest.with_suffix(".zip")
    if is_tiff(dest):
        return "skip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and zipfile.is_zipfile(dest):
        dest.replace(zpath)  # zip saved as .tif by the first version of this script
    if zpath.exists() and zpath.stat().st_size == t["size"] and md5_of(zpath) == t["md5"]:
        unpack(zpath, dest)
        zpath.unlink()
        return "ok"
    part = zpath.with_suffix(".zip.part")
    url = DOWNLOAD_URL.format(id=t["id"])
    for attempt in range(1, 4):
        try:
            # Follow redirects by hand so the token is only sent to CDSE hosts
            s = requests.Session()
            while True:
                if urlparse(url).scheme != "https":
                    raise RuntimeError(f"refusing non-HTTPS URL {url}")
                host = urlparse(url).hostname or ""
                headers = ({"Authorization": f"Bearer {auth.token()}"}
                           if host.endswith(".dataspace.copernicus.eu") else {})
                r = s.get(url, headers=headers, stream=True, allow_redirects=False, timeout=TIMEOUT)
                if r.status_code in (301, 302, 303, 307, 308):
                    url = urljoin(url, r.headers["Location"])
                    continue
                r.raise_for_status()
                break
            with open(part, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
            if md5_of(part) != t["md5"]:
                raise RuntimeError("MD5 mismatch")
            part.replace(zpath)
            unpack(zpath, dest)
            zpath.unlink()
            return "ok"
        except Exception as e:  # network hiccup / 429 / bad checksum -> retry
            if attempt == 3:
                part.unlink(missing_ok=True)
                return f"FAILED: {e}"
            time.sleep(5 * attempt)
            url = DOWNLOAD_URL.format(id=t["id"])


def cmd_list(a):
    tiles = select(load_tiles(), a.year, a.bbox)
    summary(tiles)


def cmd_get(a):
    tiles = select(load_tiles(), a.year, a.bbox)
    if not tiles:
        sys.exit("No tiles match.")
    print("Selected:"); summary(tiles)
    user = os.environ.get("CDSE_USER", "").strip()
    while not user:
        user = input("CDSE username (email): ").strip()
    password = os.environ.get("CDSE_PASSWORD", "")
    while not password:
        password = getpass.getpass("CDSE password (typing is hidden): ")
    try:
        auth = CDSE(user, password)
    except RuntimeError as e:
        sys.exit(str(e))
    out = Path(a.out)
    done = failed = 0
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futs = {pool.submit(fetch, auth, t, out): t for t in tiles}
        for i, fut in enumerate(as_completed(futs), 1):
            res = fut.result()
            if res.startswith("FAILED"):
                failed += 1
                print(f"\n  {futs[fut]['name']}: {res}")
            else:
                done += 1
            print(f"\r  {i}/{len(tiles)} done, {failed} failed", end="", flush=True)
    print(f"\nFinished: {done} ok/skipped, {failed} failed. Files in {out.resolve()}")
    if failed:
        print("Re-run the same command to retry the failed tiles.")


def main():
    p = argparse.ArgumentParser(description="CDSE bulk download: CLMS Forest Type 10 m")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("list", cmd_list), ("get", cmd_get)):
        s = sub.add_parser(name)
        s.add_argument("--year", nargs="+", choices=["2018", "2021", "2024"])
        s.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"),
                       help="lon/lat (EPSG:4326) area filter")
        if name == "get":
            s.add_argument("--out", default="downloads/forest_type")
            s.add_argument("--workers", type=int, default=4)
        s.set_defaults(fn=fn)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
