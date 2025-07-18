import os
import zipfile
from datetime import datetime
from pathlib import Path

from src.lib.config import config

# -----------------------------------------------------------------------------
class CreateKMZ:
    # -------------------------------------------------------------------------
    def __init__(self):
        # File path
        self.wpmz_dir = Path(config.output_folder) / config.output_filename / f"wpmz"
        
        dji_name = config.output_filename
        for char in ['/', '\\', '|', '?', '*', '.', '_']:
            dji_name = dji_name.replace(char, '-')

        # Add datetime to filename when in debug mode
        if config.debug_mode == False:
            self.kmz_file_path = Path(config.output_folder) / config.output_filename / f"{dji_name}.kmz"
        else:
            # Get current datetime
            current_datetime = datetime.now().strftime("%Y%m%dT%H%M%S")            
            self.kmz_file_path = Path(config.output_folder) / config.output_filename / f"{dji_name}_{current_datetime}.kmz"

    # -------------------------------------------------------------------------
    def create_kmz(self):
        # Create the KMZ file
        with zipfile.ZipFile(self.kmz_file_path, 'w', zipfile.ZIP_DEFLATED) as kmz:
            # Add template.kml under wpmz folder
            template_path = self.wpmz_dir / "template.kml"
            if template_path.exists():
                kmz.write(template_path, "wpmz/template.kml")
            
            # Add waylines.wpml under wpmz folder
            wpml_path = self.wpmz_dir / "waylines.wpml"
            if wpml_path.exists():
                kmz.write(wpml_path, "wpmz/waylines.wpml")
