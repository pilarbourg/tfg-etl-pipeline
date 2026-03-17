import os
import json
from nilearn import datasets

def download_fsaverage_assets(output_dir="assets/fsaverage"):
    print("Downloading fsaverage surface files...")
    fsaverage = datasets.fetch_surf_fsaverage('fsaverage')
    
    os.makedirs(output_dir, exist_ok=True)

    print("Available keys in fsaverage object:", fsaverage.keys())
    
    atlas_data = {
        "left_pial": str(fsaverage['pial_left']),
        "right_pial": str(fsaverage['pial_right']),
        "left_inflated": str(fsaverage['infl_left']),
        "right_inflated": str(fsaverage['infl_right']),
        "description": "Full-resolution fsaverage surface mesh."
    }
    
    config_path = os.path.join(output_dir, "fsaverage_paths.json")
    with open(config_path, "w") as f:
        json.dump(atlas_data, f, indent=4)
        
    print(f"Download complete. Paths saved to {config_path}")
    return atlas_data

if __name__ == "__main__":
    download_fsaverage_assets()