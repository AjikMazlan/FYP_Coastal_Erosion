# CoastSat site pilot

The first additional site is Pantai Bukit Keluang, Besut. The draft ROI surrounds
original JPS stations 3, 4 and 5. Those station numbers locate the study area;
they are not the IDs or geometry of the future prediction transects.

The initial pilot uses Sentinel-2 images acquired from **1 March through 30 April
2025** (the end date `2025-05-01` is exclusive). This is a limited imagery sample,
not a full-year shoreline reference or a newly trained model. Inspect the imagery
and identify suitable sandy-beach sections before choosing a reference shoreline
and drawing the site's transects. No Merang reference or transects are reused.

## Files and outputs

- `configs/coastsat/bukit_keluang_pilot.json`: site, date window and satellite settings.
- `configs/coastsat/bukit_keluang_roi.geojson`: draft WGS84 study-area rectangle.
- `scripts/coastsat/pilot_site.py`: preview, image-availability check and download commands.
- Imagery stays under `D:\CoastSat-master\data\BUKIT_KELUANG_2025_PILOT`, outside this repository.

The script locates the FYP repository from its own path. `--coastsat-root` points
to the existing CoastSat source checkout, not the Conda environment folder.
The request manifest prevents a changed ROI or date window from silently reusing
an existing pilot folder. Use a distinct sitename for a different sampling request.

## Windows: use the existing CoastSat environment

Open a **Command Prompt (cmd)** terminal in VS Code. The FYP `.venv` is used for
the backend/notebooks; this workflow uses the existing Miniforge `coastsat` environment.

```bat
call "%USERPROFILE%\miniforge3\Scripts\activate.bat"
conda activate coastsat
cd /d D:\FYP_Coastal_Erosion
```

Preview configuration locally (no CoastSat import, Earth Engine login or download):

```bat
python scripts\coastsat\pilot_site.py preview
```

Check available images using the existing `coastal-erosion-fyp` Earth Engine project:

```bat
python scripts\coastsat\pilot_site.py check --coastsat-root D:\CoastSat-master
```

`check` authenticates and queries availability but does not call the image
downloader. CoastSat may refresh local metadata for an existing pilot. Its "new"
count excludes images already downloaded; the script reports local matches separately.

To download the same pilot request:

```bat
python scripts\coastsat\pilot_site.py download --coastsat-root D:\CoastSat-master
```

The original Merang folders, FYP datasets and model files are not download targets.
After inspecting this pilot, prepare the site's reference and transects, choose a
consistent historical sampling policy, perform visual/statistical/tidal quality
checks, and evaluate temporal regression before enabling the site in the app.

## Offline checks

```bat
python -m unittest discover -s tests -p test_coastsat_pilot.py -v
```

These tests use a fake download backend and do not access Earth Engine or verify
actual satellite availability. Live check/download must run on the CoastSat computer.
