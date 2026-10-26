# Forest Type Downloader

Downloads the Copernicus **Forest Type** map (10 m resolution, whole of Europe)
for 2018, 2021 and/or 2024, ready to open in QGIS. Each year is about 3.5 GB (902 map tiles).

## 👉 [Open the downloader](https://tek-raj.github.io/forest-type-downloader/)

Runs in the browser — nothing to install. Use **Google Chrome** or **Microsoft Edge** (Mac or Windows).

1. Enter the email and password of your free [Copernicus Data Space](https://dataspace.copernicus.eu) account.
2. Tick the year(s).
3. Click **Choose folder & download**, pick a folder (e.g. Downloads) and allow the page to save there.
   Keep the tab open until it says *Finished*.
4. In QGIS, drag **`Forest_Type/<year>/Europe_ForestType_<year>.vrt`** onto the map:
   all of Europe as one layer, already coloured
   (0 = non-forest, 1 = broadleaved, 2 = coniferous).

If it stops (internet dropped, laptop closed, you pressed Stop), click download again and pick the
same folder — tiles already saved are skipped.

Your password is sent only to Copernicus's own login server (`identity.dataspace.copernicus.eu`)
and is never stored. The page is a single file, [`index.html`](index.html), if you want to check.

---

### Alternative: Mac app (Python)

If the browser version isn't an option, [download this folder](https://github.com/tek-raj/forest-type-downloader/archive/refs/heads/main.zip),
right-click `Start Forest Type Downloader.command` → **Open**, and follow `READ ME FIRST.txt`.
Command line on any system: `pip install requests` then `python cdse_download.py get --year 2024`.

Data: [CLMS High Resolution Layer Forest Type](https://land.copernicus.eu/en/products/high-resolution-layer-forests-and-tree-cover/forest-type-2018-present-raster-10-m-europe-3-yearly),
served by the Copernicus Data Space Ecosystem. Unofficial helper tool, not affiliated with Copernicus.
