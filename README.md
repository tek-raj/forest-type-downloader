# Forest Type Downloader (Mac)

Downloads the Copernicus **Forest Type** map (10 m resolution, whole of Europe)
for 2018, 2021 and/or 2024. Each year is about 3.5 GB (902 map tiles).

## ⬇️ [Download the app](https://github.com/tek-raj/forest-type-downloader/archive/refs/heads/main.zip)

## How to use

1. Click **Download the app** above and open the downloaded zip.
2. In the folder, **right-click** `Start Forest Type Downloader.command` and choose **Open**.
   The first time, macOS asks if you are sure: click **Open**.
   *(If there is no Open button: System Settings → Privacy & Security → scroll down → **Open Anyway**.)*
3. First time only:
   - If a message says Python is needed, your browser opens python.org. Click the yellow
     **Download Python** button, install it like any app, then repeat step 2.
   - A Terminal window shows *First-time setup, please wait…* for about a minute. Leave it open.
4. In the window that appears:
   - Enter the email and password of your free [Copernicus Data Space](https://dataspace.copernicus.eu) account.
   - Tick the year(s) you want and press **Download**.
5. When it finishes, click **Yes** to open the folder: `Downloads › Forest_Type › <year>`,
   one `.tif` per 100 × 100 km tile. Drag them into QGIS; they open already coloured
   (0 = non-forest, 1 = broadleaved, 2 = coniferous).

**Whole of Europe as one layer in QGIS:** Raster › Miscellaneous › Build Virtual Raster… →
Input layers: “…” › Add Directory… › choose the year folder → Run.
The five overseas tiles (GF, GP, MQ, RE, YT) use a different projection; leave them out.

## Good to know

- Keep the Terminal window open while the downloader runs.
- If it stops (internet dropped, laptop closed, you pressed Stop), press **Download** again:
  tiles you already have are skipped.
- The password is never saved; only the email is remembered.

---

Data: [CLMS High Resolution Layer Forest Type](https://land.copernicus.eu/en/products/high-resolution-layer-forests-and-tree-cover/forest-type-2018-present-raster-10-m-europe-3-yearly),
served by the Copernicus Data Space Ecosystem.
Also runs on Windows/Linux: `pip install requests` then `python forest_downloader_gui.py`.
