"""The sequence of placemarks a mission flies, shared by template.kml and waylines.wpml.

Both files must hold the same placemarks in the same order, so the sequence is
decided once here and each builder only renders it.

Every placemark sits directly above a waypoint; only its height changes. Each
waypoint is flown as:

    first     climb to the checkpoint before it  cpt + buffer + approach
    approach  full stop above it                 wpt + buffer + approach
    photo     full stop for the burst            wpt + buffer
    last      climb to the checkpoint after it   cpt + buffer + approach

Every touch_sky_interval waypoints, when touch-sky is on, the drone then climbs
to the touch-sky altitude and comes back down to the checkpoint after it:

    touch_sky climb to the touch-sky altitude    cpt + touch_sky_altitude
    last      back down to the checkpoint        cpt + buffer + approach
"""

from dataclasses import dataclass

FIRST = "first"
APPROACH = "approach"
PHOTO = "photo"
LAST = "last"
TOUCH_SKY = "touch_sky"

# Gimbal pitch set on arrival at a placemark: straight down above a tree, raised
# to look ahead when leaving it for the next tree.
GIMBAL_DOWN = "-90"
GIMBAL_AHEAD = "-15"


@dataclass(frozen=True)
class Step:
    kind: str
    # Index of the waypoint, in CSV order, the placemark sits above.
    wpt: int
    # DSM elevation the height is measured from, as read from the CSV.
    elevation: str
    # Metres added to that elevation, one by one: summing them in this order
    # keeps heights bit-for-bit what harpia wrote before this module existed.
    offsets: tuple
    # Gimbal pitch set on arrival, for the placemarks that rotate it.
    gimbal: str | None = None


# -----------------------------------------------------------------------------
def step_height(elevation, offsets):
    """A placemark's height: its elevation plus each of its offsets, as a string."""
    height = float(elevation)
    for offset in offsets:
        height += float(offset)
    return str(height)


# -----------------------------------------------------------------------------
def placemark_plan(
    wpt_csv_properties,
    cpt_csv_properties,
    buffer,
    approach,
    touch_sky=False,
    touch_sky_interval=10,
    touch_sky_altitude=100,
):
    """Every placemark of the mission, in flight order.

    `cpt_csv_properties` holds one checkpoint per leg plus a copy at each end,
    as the builders' setup() lays it out: waypoint i is entered through
    checkpoint i and left through checkpoint i + 1.
    """
    transit = (buffer, approach)
    steps = []
    touch_sky_count = 0

    for idx, (_, _, wpt_elevation, _) in enumerate(wpt_csv_properties):
        cpt_in = cpt_csv_properties[idx][2]
        cpt_out = cpt_csv_properties[idx + 1][2]

        steps.append(Step(FIRST, idx, cpt_in, transit, GIMBAL_DOWN))
        steps.append(Step(APPROACH, idx, wpt_elevation, transit))
        steps.append(Step(PHOTO, idx, wpt_elevation, (buffer,)))
        steps.append(Step(LAST, idx, cpt_out, transit, GIMBAL_AHEAD))

        touch_sky_count += 1

        if touch_sky and touch_sky_count >= touch_sky_interval:
            steps.append(Step(TOUCH_SKY, idx, cpt_out, (touch_sky_altitude,), GIMBAL_DOWN))
            steps.append(Step(LAST, idx, cpt_out, transit, GIMBAL_AHEAD))
            touch_sky_count = 0

    return steps
