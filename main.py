import argparse
from pydantic import ValidationError
from pathlib import Path

from src.lib.config import load_config


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Harpia - Drone waypoint generator")
    parser.add_argument(
        "--config",
        type=str,
        default="config/template.yaml",
        help="Path to configuration YAML file (default: config/template.yaml)"
    )
    parser.add_argument(
        "--mission-type",
        type=str,
        choices=["normal", "crown_mapping"],
        help="Override mission type from config file"
    )
    args = parser.parse_args()
    
    # Load configuration from file
    config = load_config(args.config)
    
    # Override config with command-line argument if provided
    if args.mission_type:
        config.mission_type = args.mission_type
    
    print(f"Running harpia with mission type: {config.mission_type}")
    
    try:
        # Import the appropriate builders based on mission type
        if config.mission_type == "normal":
            from src.lib.build_csv import BuildCSV
            from src.lib.build_template_kml import BuildTemplateKML
            from src.lib.build_waylines_wpml import BuildWaylinesWPML
        elif config.mission_type == "crown_mapping":
            from src.lib.build_csv_crown_mapping import BuildCSV
            from src.lib.build_template_kml_crown_mapping import BuildTemplateKML
            from src.lib.build_waylines_wpml_crown_mapping import BuildWaylinesWPML
        else:
            raise ValueError(f"Unknown mission type: {config.mission_type}")
        
        from src.lib.create_kmz import CreateKMZ
        
        # Step 1: Optionally run BuildCSV to generate the waypoints file
        if config.features_path and config.dsm_path:
            print("Building CSV from features and DSM")
            
            # Determine output folder: use config value or default to features file directory
            output_folder = config.output_folder
            if output_folder is None:
                output_folder = Path(config.features_path).parent
                print(f"No output_folder specified, using features file directory: {output_folder}")
            
            # Determine output filename: use config value or default to features filename
            output_filename = config.output_filename
            if output_filename is None:
                output_filename = Path(config.features_path).stem
                print(f"No output_filename specified, using features filename: {output_filename}")
            
            build_csv = BuildCSV(
                features_path=config.features_path,
                dsm_path=config.dsm_path,
                aoi_path=config.aoi_path,
                aoi_index=config.aoi_index,
                aoi_qualifier=config.aoi_qualifier,
                buffer_feature=config.buffer_feature,
                takeoff_coords=config.takeoff_coords,
                takeoff_coords_projected=config.takeoff_coords_projected
            )
            
            _, _, generated_csv_path = build_csv.run(
                output_folder=str(output_folder),
                output_filename=output_filename
            )
            
            # Update the global config object with the generated CSV path
            from src.lib.config import config as global_config
            global_config.csv_path = generated_csv_path
            print(f"Waypoints CSV generated at: {generated_csv_path}")
        
        # Reload config to ensure csv_path is set
        from src.lib.config import config as global_config
        
        # Ensure we have a CSV file to proceed
        if not global_config.csv_path:
            print("Error: No CSV path provided. Set csv_path in config or provide features_path and dsm_path. Aborting.")
            return
            
        if not Path(global_config.csv_path).exists():
            print(f"Error: Waypoints CSV file not found at {global_config.csv_path}. Aborting.")
            return

        # Step 2 & 3: Build KML and WPML from the CSV
        print(f"Building KML and WPML from waypoints CSV: {global_config.csv_path}")
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
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
