import json
import os
import numpy as np
import nibabel as nib
from skimage.measure import marching_cubes

ASEG_PATH   = os.path.expanduser(
    "~/mne_data/MNE-fsaverage-data/fsaverage/mri/aseg.mgz"
)

OUTPUT_DIR  = "data/brain_regions"
MAPPING_PATH = os.path.join(OUTPUT_DIR, "mapping.json")

SUBCORTICAL_LABELS = {
    10: ("lh", "thalamus"),
    11: ("lh", "caudate"),
    12: ("lh", "putamen"),
    13: ("lh", "pallidum"),
    17: ("lh", "hippocampus"),
    18: ("lh", "amygdala"),
    26: ("lh", "accumbens"),
    28: ("lh", "ventraldc"),
    49: ("rh", "thalamus"),
    50: ("rh", "caudate"),
    51: ("rh", "putamen"),
    52: ("rh", "pallidum"),
    53: ("rh", "hippocampus"),
    54: ("rh", "amygdala"),
    58: ("rh", "accumbens"),
    60: ("rh", "ventraldc"),
    16: ("mid", "brainstem"),
    7:  ("lh", "cerebellum_cortex"),
    8:  ("lh", "cerebellum_white"),
    46: ("rh", "cerebellum_cortex"),
    47: ("rh", "cerebellum_white"),
    15: ("mid", "fourth_ventricle"),
}

PARKINSONS_RELEVANT = {
    "caudate", "putamen", "pallidum", "accumbens",
    "ventraldc", "brainstem", "thalamus", "hippocampus", "amygdala",
}

def write_obj(filepath: str, vertices: np.ndarray, faces: np.ndarray):
    """
    Write 3D mesh vertices and faces to a standard Wavefront OBJ file.
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        f.write(f"# Subcortical mesh — {os.path.basename(filepath)}\n")
        f.write(f"# Vertices: {len(vertices)}  Faces: {len(faces)}\n\n")
        for v in vertices:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        f.write("\n")
        for face in faces:
            f.write(f"f {face[0]+1} {face[1]+1} {face[2]+1}\n")

def extract_structure(vol_data: np.ndarray, label_id: int, affine: np.ndarray):
    """
    Generate a 3D surface mesh from a specific voxel label using marching cubes.
    """
    mask = (vol_data == label_id).astype(np.float32)

    if mask.sum() < 100:
        return None, None

    try:
        verts_vox, faces, _, _ = marching_cubes(mask, level=0.5)
    except (ValueError, RuntimeError):
        return None, None

    ones = np.ones((len(verts_vox), 1))
    verts_hom = np.hstack([verts_vox, ones])
    verts_mm  = (affine @ verts_hom.T).T[:, :3]

    return verts_mm.astype(np.float32), faces.astype(np.int32)

def extract_all_subcortical():
    """
    Process the segmentation volume to extract all designated subcortical structures.
    """
    if not os.path.exists(ASEG_PATH):
        raise FileNotFoundError(f"aseg.mgz not found at {ASEG_PATH}")

    img     = nib.load(ASEG_PATH)
    vol     = np.asarray(img.dataobj, dtype=np.int32)
    affine  = img.affine

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    new_regions = []

    for label_id, (hemi, name) in SUBCORTICAL_LABELS.items():
        region_id = f"{hemi}_{name}"
        filename  = f"{region_id}.obj"
        filepath  = os.path.join(OUTPUT_DIR, filename)

        verts, faces = extract_structure(vol, label_id, affine)

        if verts is None:
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

    return new_regions

def update_mapping(new_regions: list):
    """
    Append or update subcortical region properties in JSON mapping.
    """
    if os.path.exists(MAPPING_PATH):
        with open(MAPPING_PATH, "r", encoding="utf-8") as f:
            mapping = json.load(f)
    else:
        mapping = {}

    for r in new_regions:
        mapping[r["id"]] = {
            "hemisphere":          r["hemisphere"],
            "region_name":         r["region_name"],
            "file":                r["file"],
            "vertex_count":        r["vertex_count"],
            "face_count":          r["face_count"],
            "parkinsons_relevant": r["parkinsons_relevant"],
            "source":              r["source"],
            "metabolites":         mapping.get(r["id"], {}).get("metabolites", []),
        }

    with open(MAPPING_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)

    return mapping


if __name__ == "__main__":
    new_regions = extract_all_subcortical()
    mapping     = update_mapping(new_regions)