
from pydantic import ValidationError

from lib.build_template_kml import BuildTemplateKML
from lib.build_waylines_wpml import BuildWaylinesWPML
from lib.config import config
from lib.create_kmz import CreateKMZ


def main():

    try:
        build_template_kml = BuildTemplateKML()
        build_template_kml.setup()
        build_template_kml.generate()
        build_template_kml.saveNewKML()

        build_waylines_wpml = BuildWaylinesWPML()
        build_waylines_wpml.setup()
        build_waylines_wpml.generate()
        build_waylines_wpml.saveNewWPML()

        create_kmz = CreateKMZ()
        create_kmz.create_kmz()

    except ValidationError as e:
        print(f"Configuration error: {e}")

        # Your code here
        print("Running lefolab-drone")


if __name__ == "__main__":
    main()
