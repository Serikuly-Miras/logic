"""Turn a LibreLane (sky130) run into a three.js-ready 3D model.

Usage: python export_3d.py <librelane run dir> <out dir> [--z-scale K]

Writes:
  layout.glb   one mesh node per layer and kind ("met1_logic", "met1_filler", ...)
               plus a "die" plate; units are um, Y is up, die centred at the origin.
               Load with three.js GLTFLoader.
  layout.json  what a mesh can't carry: layer table, pin labels, sign-off metrics.
"""

import argparse
import json
import re
from pathlib import Path

import gdstk
import mapbox_earcut as earcut
import numpy as np
import trimesh

# (gds layer, datatype) -> (name, z bottom um, thickness um, color)
# Heights roughly follow the sky130 metal stack; vias fill the gap below their metal.
LAYERS = {
    (65, 20): ("diff", 0.00, 0.12, "#7a9a5a"),
    (66, 20): ("poly", 0.33, 0.18, "#c0392b"),
    (66, 44): ("licon", 0.51, 0.43, "#888888"),
    (67, 20): ("li1", 0.94, 0.10, "#9b59b6"),
    (67, 44): ("mcon", 1.04, 0.34, "#888888"),
    (68, 20): ("met1", 1.38, 0.36, "#3498db"),
    (68, 44): ("via", 1.74, 0.27, "#888888"),
    (69, 20): ("met2", 2.01, 0.36, "#e67e22"),
    (69, 44): ("via2", 2.37, 0.42, "#888888"),
    (70, 20): ("met3", 2.79, 0.85, "#1abc9c"),
    (70, 44): ("via3", 3.63, 0.39, "#888888"),
    (71, 20): ("met4", 4.02, 0.85, "#f1c40f"),
    (71, 44): ("via4", 4.87, 0.51, "#888888"),
    (72, 20): ("met5", 5.37, 1.26, "#e84393"),
}

# Cells that only keep rows continuous / decouple power, not part of the logic.
FILLER_CELLS = ("decap", "fill_", "tapvpwrvgnd")

# Pin text is on <metal layer>/5; the metal itself is on <metal layer>/20.
LABEL_DT, METAL_DT = 5, 20

DIE_COLOR, DIE_THICKNESS = "#2b3038", 0.1


def to_world(x, y, h):
    """GDS (x, y) + height -> three.js (x, y up, z). A proper rotation, so winding is kept."""
    return np.column_stack([x, h, -np.asarray(y)])


def extrude(polys, z, t):
    """Extrude 2D polygons (um, relative to die centre) into one flat-shaded mesh."""
    verts, faces, n = [], [], 0
    for pts in polys:
        pts = np.asarray(pts, dtype=np.float64)
        if len(pts) > 1 and np.allclose(pts[0], pts[-1]):
            pts = pts[:-1]
        if len(pts) < 3:
            continue
        x, y = pts[:, 0], pts[:, 1]
        if np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y) < 0:
            pts = pts[::-1]  # make counter-clockwise
            x, y = pts[:, 0], pts[:, 1]
        k = len(pts)

        tris = earcut.triangulate_float64(pts, np.array([k], dtype=np.uint32)).reshape(
            -1, 3
        )
        if len(tris):
            a, b, c = pts[tris[:, 0]], pts[tris[:, 1]], pts[tris[:, 2]]
            cw = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (
                c[:, 0] - a[:, 0]
            ) < 0
            tris[cw] = tris[cw][:, ::-1]

        # Vertices 0..k-1 are the top ring, k..2k-1 the bottom ring.
        verts.append(to_world(x, y, np.full(k, z + t)))
        verts.append(to_world(x, y, np.full(k, z)))
        top, bot = np.arange(k), np.arange(k) + k
        nxt = np.roll(np.arange(k), -1)
        # Caps: top keeps CCW (normal +Y), bottom is flipped (normal -Y).
        faces.append(tris + n)
        faces.append(tris[:, ::-1] + n + k)
        # Walls: two triangles per edge, wound so the normal points outward.
        faces.append(np.column_stack([bot, bot[nxt], top[nxt]]) + n)
        faces.append(np.column_stack([bot, top[nxt], top]) + n)
        n += 2 * k

    if not verts:
        return None
    # Corner vertices are shared between caps and walls, so the GLB carries no normals;
    # three.js GLTFLoader turns on flatShading for normal-less meshes.
    return trimesh.Trimesh(np.concatenate(verts), np.concatenate(faces), process=False)


def material(name, color):
    rgba = [int(color[i : i + 2], 16) for i in (1, 3, 5)] + [255]
    return trimesh.visual.material.PBRMaterial(
        name=name, baseColorFactor=rgba, metallicFactor=0.3, roughnessFactor=0.55
    )


def build(run_dir, z_scale):
    gds_path = next((run_dir / "final" / "gds").glob("*.gds"))
    def_path = run_dir / "final" / "def" / f"{gds_path.stem}.def"
    lib = gdstk.read_gds(str(gds_path))
    top = lib.top_level()[0]

    # Routing, power grid and pins live in the top cell itself.
    parts = {"logic": list(top.get_polygons(include_paths=True, depth=0)), "filler": []}
    for ref in top.references:
        kind = "filler" if any(s in ref.cell.name for s in FILLER_CELLS) else "logic"
        parts[kind].extend(ref.get_polygons(include_paths=True, depth=None))

    grouped = {}
    for kind, polys in parts.items():
        for poly in polys:
            key = (poly.layer, poly.datatype)
            if key in LAYERS:
                grouped.setdefault((key, kind), []).append(poly)

    (x0, y0), (x1, y1) = top.bounding_box()
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w, h = x1 - x0, y1 - y0

    scene = trimesh.Scene()
    die = extrude(
        [[(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]],
        -DIE_THICKNESS,
        DIE_THICKNESS,
    )
    die.visual = trimesh.visual.TextureVisuals(material=material("die", DIE_COLOR))
    scene.add_geometry(die, node_name="die", geom_name="die")

    layers = []
    for key, (name, z, thickness, color) in LAYERS.items():
        z, thickness = z * z_scale, thickness * z_scale
        nodes = {}
        for kind in parts:
            polys = gdstk.boolean(
                grouped.get((key, kind), []), [], "or", precision=1e-3
            )
            mesh = extrude([p.points - (cx, cy) for p in polys], z, thickness)
            if mesh is None:
                continue
            mesh.visual = trimesh.visual.TextureVisuals(material=material(name, color))
            node = f"{name}_{kind}"
            scene.add_geometry(mesh, node_name=node, geom_name=node)
            nodes[kind] = {"node": node, "shapes": len(polys)}
            print(f"{name:6} {kind:6} {len(polys):6} shapes {len(mesh.faces):8} tris")
        if nodes:
            layers.append(
                {
                    "name": name,
                    "z": z,
                    "thickness": thickness,
                    "color": color,
                    "nodes": nodes,
                }
            )

    pin_info = {}
    if def_path.exists():
        for m in re.finditer(
            r"- (\S+) \+ NET \S+ (?:\+ SPECIAL )?\+ DIRECTION (\w+) \+ USE (\w+)",
            def_path.read_text(),
        ):
            pin_info[m[1]] = (m[2].lower(), m[3].lower())

    # Pin text labels sit on <metal layer>/5; place them on top of that metal.
    labels = []
    for lbl in top.labels:
        metal = LAYERS.get((lbl.layer, METAL_DT))
        if lbl.texttype != LABEL_DT or not metal:
            continue
        direction, use = pin_info.get(lbl.text, ("unknown", "signal"))
        x, y = lbl.origin
        lx, ly, lz = to_world([x - cx], [y - cy], [(metal[1] + metal[2]) * z_scale])[0]
        labels.append(
            {
                "text": lbl.text,
                "position": [round(lx, 3), round(ly, 3), round(lz, 3)],
                "layer": metal[0],
                "direction": direction,
                "use": use,
            }
        )
    print(f"labels {len(labels)}")

    meta = {
        "design": top.name,
        "pdk": "sky130A",
        "units": "um",
        "axes": "x = GDS x, y = up, z = -GDS y; origin at die centre",
        "z_scale": z_scale,
        "size": [round(w, 3), round(h, 3)],
        "die": {"node": "die", "color": DIE_COLOR, "thickness": DIE_THICKNESS},
        "layers": layers,
        "labels": labels,
        "stats": run_stats(run_dir),
    }
    return scene, meta


def run_stats(run_dir):
    """LibreLane sign-off metrics, grouped like the old info drawer."""
    metrics_path = run_dir / "final" / "metrics.json"
    if not metrics_path.exists():
        return {}
    m = json.loads(metrics_path.read_text())
    period = json.loads((run_dir / "resolved.json").read_text())["CLOCK_PERIOD"]
    cls = "design__instance__count__class:"
    typ = "__corner:nom_tt_025C_1v80"

    def get(key, default=None):
        return m.get(key, default)

    def fmax_mhz(slack):
        return None if slack is None else round(1000 / (period - slack), 1)

    return {
        "area": {
            "die_um2": get("design__die__area"),
            "stdcell_um2": get("design__instance__area__stdcell"),
            "utilization": get("design__instance__utilization"),
            "wirelength_um": get("route__wirelength"),
        },
        "cells": {
            "flip_flops": get(cls + "sequential_cell", 0),
            "logic_gates": get(cls + "multi_input_combinational_cell", 0),
            "buffers": get(cls + "timing_repair_buffer", 0)
            + get(cls + "clock_buffer", 0),
            "filler_tap": get(cls + "fill_cell", 0) + get(cls + "tap_cell", 0),
        },
        "timing": {
            "clock_period_ns": period,
            "setup_slack_worst_ns": get("timing__setup__ws"),
            "hold_slack_worst_ns": get("timing__hold__ws"),
            "fmax_typical_mhz": fmax_mhz(get("timing__setup__ws" + typ)),
            "fmax_worst_corner_mhz": fmax_mhz(get("timing__setup__ws")),
        },
        "power_typical_w": {
            "total": get("power__total"),
            "switching": get("power__switching__total"),
            "internal": get("power__internal__total"),
            "leakage": get("power__leakage__total"),
        },
        "checks": {
            "drc_errors": get("magic__drc_error__count"),
            "lvs_errors": get("design__lvs_error__count"),
            "antenna_violations": get("route__antenna_violation__count"),
            "max_slew_violations": get("design__max_slew_violation__count"),
        },
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument(
        "--z-scale", type=float, default=1.0, help="stretch layer heights (default 1)"
    )
    args = ap.parse_args()

    scene, meta = build(args.run_dir, args.z_scale)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    glb = args.out_dir / "layout.glb"
    glb.write_bytes(scene.export(file_type="glb", include_normals=False))
    (args.out_dir / "layout.json").write_text(json.dumps(meta, indent=2))
    print(
        f"wrote {glb} ({glb.stat().st_size / 1e6:.1f} MB) and {args.out_dir / 'layout.json'}"
    )


if __name__ == "__main__":
    main()
