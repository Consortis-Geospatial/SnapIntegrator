# SnapIntegrator (QGIS 3.x plugin)

SnapIntegrator is a QGIS plugin for finding **unmerged road endpoints** inside a boundary polygon, based on a chosen attribute field in a road (line) layer.

It helps you detect where two road segments meet geometrically but **do not share the same attribute value** (for example, different street names or different IDs), which often indicates topology or data-cleaning issues.

---

## Features

- Works in **QGIS 3.16+**
- Lets you interactively choose:
  - A **polygon layer** as a boundary (e.g. municipality, tile, project area)
  - A **line layer** as a road network
  - A **field** from the road layer (e.g. `road_id`, `name`, `code`)
- Finds line endpoints that:
  - Belong to **non-closed** line features (no rings)
  - Are shared by **exactly two** line features
  - Are **strictly inside** the selected polygon (not on its boundary)
  - Have **different values** in the selected attribute field between the two line features
- Outputs results to a new **in-memory point layer** with:
  - `id`   – running ID of the point
  - `field` – the name of the selected attribute field
  - `val1` – value of that field in the first line feature
  - `val2` – value of that field in the second line feature

This makes it easy to spot potential **unmerged or inconsistent** roads.

---

## How it works

1. The plugin scans the selected **road line layer** and collects all endpoints of non-closed lines.
2. For each endpoint, it checks which line features share that exact coordinate (rounded to 6 decimal places).
3. Only endpoints shared by **exactly two** line features are kept.
4. For each such pair:
   - The plugin compares the values of the **user-selected attribute field** (`field_name`) on the two features.
   - If the values are equal, the endpoint is ignored.
   - If the values are **different**, the endpoint is considered a **candidate “unmerged” point**.
5. Each candidate point is tested to ensure it lies **inside** the selected polygon:
   - A small negative buffer (`-tolerance`) is used to avoid points lying exactly on the boundary.
6. All valid candidate points are written to a memory **point layer**, which is added to the current QGIS project.

---

## Installation

1. Create a folder named `SnapIntegrator` in your local QGIS plugins directory, for example:

   - Windows:  
     `C:\Users\<username>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\SnapIntegrator`
   - Linux (typical):  
     `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/SnapIntegrator`
   - macOS (typical):  
     `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/SnapIntegrator`

2. Copy the following files into the `SnapIntegrator` folder:
   - `__init__.py`
   - `snap_integrator.py`
   - `metadata.txt`
   - `icon.png`

3. Restart QGIS.
4. Go to **Plugins → Manage and Install Plugins…**, find **SnapIntegrator**, and enable it.

You should now see a toolbar icon and a menu entry under **Plugins → Snap Integrator**.

---

## Usage

1. In QGIS, load:
   - A **polygon layer** (your boundary).
   - A **line layer** representing your road network.
2. Select **exactly one polygon feature** in the polygon layer (this will be used as the search boundary).
3. Click the **SnapIntegrator** toolbar button (or use the Plugins menu).
4. In the dialog:
   - Choose your **polygon layer**.
   - Choose your **line (roads) layer**.
   - Choose the **attribute field** from the road layer that you want to check (e.g. `road_id`, `name`).
5. Click **OK**.
6. The plugin will:
   - Analyze endpoints inside the selected polygon.
   - Create a new memory layer named **`SnapIntegrator_Points`** with the candidate points.

You can then inspect those points, label them with `val1` and `val2`, or use them for further topology checks.

---

## Configuration & Notes

- **Tolerance**  
  The plugin uses a tolerance of `0.0001` in layer units to shrink the polygon boundary slightly when checking if a point is inside.  
  Adjust this in the code if necessary (for projected vs geographic CRS).

- **Supported versions**  
  Developed and tested for **QGIS 3.16**; it should also work on newer 3.x versions.

- **Limitations**
  - Only considers endpoints shared by **exactly two** line features.
  - Does not attempt to merge or edit geometry: it only **detects** candidate problem locations.
  - Assumes the line layer and polygon layer are in the **same CRS** (or set up correctly via QGIS).

---

## License

This project is released under the **GNU General Public License v3**.

You are free to use, modify, and distribute it under the terms of that license.
