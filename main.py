from pydantic import ValidationError
from pathlib import Path

from src.lib.build_csv import BuildCSV
from src.lib.build_template_kml import BuildTemplateKML
from src.lib.build_waylines_wpml import BuildWaylinesWPML
from src.lib.config import config
from src.lib.create_kmz import CreateKMZ


def main():
    print("Running harpia")
    try:
        # Step 1: Optionally run BuildCSV to generate the waypoints file
        if config.features_path and config.dsm_path:
            print("Building CSV from features and DSM")
            build_csv = BuildCSV(
                features_path=config.features_path,
                dsm_path=config.dsm_path,
                aoi_path=config.aoi_path,
                aoi_index=config.aoi_index,
                aoi_qualifier=config.aoi_qualifier,
                buffer_path=config.buffer_path,
                buffer_feature=config.buffer_feature,
                takeoff_coords=config.takeoff_coords,
                takeoff_coords_projected=config.takeoff_coords_projected
            )
            
            _, _, generated_csv_path = build_csv.run(
                output_folder=config.output_folder,
                output_filename=config.output_filename
            )
            
            # Update config with the path of the generated CSV
            config.csv_path = generated_csv_path
            print(f"Waypoints CSV generated at: {config.csv_path}")

        # Ensure we have a CSV file to proceed
        if not config.csv_path or not Path(config.csv_path).exists():
             print("Error: Waypoints CSV file not found or not generated. Aborting.")
             return

        # Step 2 & 3: Build KML and WPML from the CSV
        print("Building KML and WPML from waypoints CSV")
        build_template_kml = BuildTemplateKML()
        build_template_kml.setup()
        build_template_kml.generate()
        build_template_kml.saveNewKML()

        build_waylines_wpml = BuildWaylinesWPML()
        build_waylines_wpml.setup()
        build_waylines_wpml.generate()
        build_waylines_wpml.saveNewWPML()

        # Step 4: Create the KMZ package
        print("Creating KMZ file")
        create_kmz = CreateKMZ()
        create_kmz.create_kmz()

    except ValidationError as e:
        print(f"Configuration error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
