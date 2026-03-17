"""
subcortical_split.py  —  Extract subcortical structures from aseg.mgz
======================================================================
Converts FreeSurfer's volumetric subcortical segmentation into OBJ meshes,
one per structure, compatible with the cortical OBJs from brain_split.py.

Both hemispheres are extracted where applicable (e.g. Left-Putamen,
Right-Putamen). Output goes into the same data/brain_regions/ folder
so everything can be imported into Blender together.

Dependencies:
    uv pip install nibabel numpy scikit-image

Usage:
    python subcortical_split.py
"""

import json
import os
import numpy as np
import nibabel as nib
from skimage.measure import marching_cubes

# ── Config ────────────────────────────────────────────────────────────────────

ASEG_PATH   = os.path.expanduser(
    "~/mne_data/MNE-fsaverage-data/fsaverage/mri/aseg.mgz"
)
OUTPUT_DIR  = "data/brain_regions"
MAPPING_PATH = os.path.join(OUTPUT_DIR, "mapping.json")

# FreeSurfer aseg.mgz label IDs → anatomical names
# Full list: https://surfer.nmr.mgh.harvard.edu/fswiki/FsTutorial/AnatomicalROI/FreeSurferColorLUT
SUBCORTICAL_LABELS = {
    # Left hemisphere
    10: ("lh", "thalamus"),
    11: ("lh", "caudate"),
    12: ("lh", "putamen"),
    13: ("lh", "pallidum"),
    17: ("lh", "hippocampus"),
    18: ("lh", "amygdala"),
    26: ("lh", "accumbens"),
    28: ("lh", "ventraldc"),          # ventral diencephalon (incl. substantia nigra)

    # Right hemisphere
    49: ("rh", "thalamus"),
    50: ("rh", "caudate"),
    51: ("rh", "putamen"),
    52: ("rh", "pallidum"),
    53: ("rh", "hippocampus"),
    54: ("rh", "amygdala"),
    58: ("rh", "accumbens"),
    60: ("rh", "ventraldc"),

    # Midline / bilateral
    16: ("mid", "brainstem"),          # contains substantia nigra

    7:  ("lh", "cerebellum_cortex"),
    8:  ("lh", "cerebellum_white"),
    46: ("rh", "cerebellum_cortex"),
    47: ("rh", "cerebellum_white"),
    15: ("mid", "fourth_ventricle"),
}

# Which of these are most relevant to Parkinson's
PARKINSONS_RELEVANT = {
    "caudate", "putamen", "pallidum", "accumbens",  # basal ganglia
    "ventraldc",                                     # substantia nigra
    "brainstem",                                     # SN + other nuclei
    "thalamus",                                      # motor relay
    "hippocampus",                                   # PD dementia
    "amygdala",                                      # PD dementia
}

# ── OBJ export (same as brain_split.py) ──────────────────────────────────────

def write_obj(filepath: str, vertices: np.ndarray, faces: np.ndarray):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        f.write(f"# Subcortical mesh — {os.path.basename(filepath)}\n")
        f.write(f"# Vertices: {len(vertices)}  Faces: {len(faces)}\n\n")
        for v in vertices:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        f.write("\n")
        for face in faces:
            f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")


# ── Volumetric → surface mesh ─────────────────────────────────────────────────

def extract_structure(vol_data: np.ndarray, label_id: int, affine: np.ndarray):
    """
    Use marching cubes to extract an isosurface for a single label.
    Returns (vertices_in_mm, faces) or (None, None) if label not found.
    """
    # Binary mask for this label
    mask = (vol_data == label_id).astype(np.float32)

    if mask.sum() < 100:   # skip if fewer than 100 voxels
        return None, None

    # Marching cubes on the binary mask (level=0.5 = boundary)
    try:
        verts_vox, faces, _, _ = marching_cubes(mask, level=0.5)
    except (ValueError, RuntimeError):
        return None, None

    # Convert voxel coordinates to mm using the affine transform
    # verts are (N,3) in voxel space; affine is 4×4
    ones = np.ones((len(verts_vox), 1))
    verts_hom = np.hstack([verts_vox, ones])          # (N, 4)
    verts_mm  = (affine @ verts_hom.T).T[:, :3]       # (N, 3)

    return verts_mm.astype(np.float32), faces.astype(np.int32)


# ── Main ──────────────────────────────────────────────────────────────────────

def extract_all_subcortical():
    if not os.path.exists(ASEG_PATH):
        raise FileNotFoundError(
            f"aseg.mgz not found at {ASEG_PATH}\n"
            f"Run: python -c \"import mne; mne.datasets.fetch_fsaverage()\""
        )

    print(f"Loading {ASEG_PATH}...")
    img     = nib.load(ASEG_PATH)
    vol     = np.asarray(img.dataobj, dtype=np.int32)
    affine  = img.affine
    print(f"  Volume shape: {vol.shape}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    new_regions = []

    for label_id, (hemi, name) in SUBCORTICAL_LABELS.items():
        region_id = f"{hemi}_{name}"
        filename  = f"{region_id}.obj"
        filepath  = os.path.join(OUTPUT_DIR, filename)

        print(f"  Extracting {region_id} (label {label_id})...", end=" ")

        verts, faces = extract_structure(vol, label_id, affine)

        if verts is None:
            print("⚠ not found or too small, skipping")
            continue

        write_obj(filepath, verts, faces)
        is_pd = name in PARKINSONS_RELEVANT

        new_regions.append({
            "id":                  region_id,
            "hemisphere":          hemi,
            "region_name":         name,
            "file":                filename,
            "vertex_count":        int(len(verts)),
            "face_count":          int(len(faces)),
            "parkinsons_relevant": is_pd,
            "source":              "subcortical",
        })

        marker = "★" if is_pd else " "
        print(f"{marker}  {len(verts):>6} verts  {len(faces):>6} faces  → {filename}")

    return new_regions


def update_mapping(new_regions: list):
    """
    Merge subcortical regions into the existing mapping.json
    produced by brain_split.py. Creates it if it doesn't exist.
    """
    if os.path.exists(MAPPING_PATH):
        with open(MAPPING_PATH, "r") as f:
            mapping = json.load(f)
        print(f"\nLoaded existing mapping.json ({len(mapping)} cortical regions)")
    else:
        mapping = {}
        print("\nNo existing mapping.json found, creating new one")

    for r in new_regions:
        mapping[r["id"]] = {
            "hemisphere":          r["hemisphere"],
            "region_name":         r["region_name"],
            "file":                r["file"],
            "vertex_count":        r["vertex_count"],
            "face_count":          r["face_count"],
            "parkinsons_relevant": r["parkinsons_relevant"],
            "source":              r["source"],
            "metabolites":         [],
        }

    with open(MAPPING_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)

    print(f"mapping.json updated → {len(mapping)} total regions")
    return mapping


if __name__ == "__main__":
    new_regions = extract_all_subcortical()
    mapping     = update_mapping(new_regions)

    total      = len(new_regions)
    parkinsons = sum(1 for r in new_regions if r["parkinsons_relevant"])

    print(f"\n{'─'*55}")
    print(f"Done.  {total} subcortical OBJ files written to {OUTPUT_DIR}/")
    print(f"       {parkinsons} structures flagged as Parkinson's-relevant (★)")
    print(f"       mapping.json now has {len(mapping)} total regions")
    print(f"{'─'*55}")
    print(f"\nNext: import ALL OBJs from {OUTPUT_DIR}/ into Blender")
    print(f"      and export as a single .glb with named mesh objects")