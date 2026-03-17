import nibabel as nib
import numpy as np

def convert_gifti_to_obj(gii_file, output_obj):
    img = nib.load(gii_file)
    
    coords = img.darrays[0].data
    triangles = img.darrays[1].data
    
    with open(output_obj, 'w') as f:
        for c in coords:
            f.write(f"v {c[0]} {c[1]} {c[2]}\n")
        for t in triangles:
            f.write(f"f {t[0]+1} {t[1]+1} {t[2]+1}\n")

convert_gifti_to_obj('/Users/pilarbourg/nilearn_data/fsaverage/pial_left.gii.gz', 'brain_left_quality.obj')
print("Successfully converted to OBJ!")