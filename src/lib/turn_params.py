"""Turn radii for coordinateTurn waypoints, shared by template.kml and waylines.wpml.

Both files carry a radius for every waypoint, and they have to agree: the
remote controller regenerates waylines.wpml from template.kml when a mission is
edited, so a radius that lived only in waylines.wpml would be replaced by
whatever the controller computes for itself.
"""

import math

COORDINATE_TURN = "coordinateTurn"
STOP_TURN = "toPointAndStopWithDiscontinuityCurvature"
STOP_DAMPING = "0"

# The RC sizes a coordinateTurn radius as a third of the shorter adjacent leg,
# measured on a sphere of this radius.
EARTH_RADIUS_M = 6371000.0
LEG_RATIO = 3.0


# -----------------------------------------------------------------------------
def finalize_turn_params(placemarks, namespaces, height_tag, horizontal_cap_m):
    """Size the radius of every coordinateTurn waypoint, in place.

    The first and last waypoints become full stops: the RC compiles them that
    way whatever the global turn mode says. Every other stop is left alone.

    `height_tag` is the element holding each waypoint's altitude --
    `executeHeight` in waylines.wpml, `ellipsoidHeight` in template.kml. The two
    carry the same values, so both files get the same radii.

    `horizontal_cap_m` is `buffer_feature`: see `turn_radius`.
    """
    if horizontal_cap_m is None or horizontal_cap_m <= 0:
        raise ValueError(
            "buffer_feature must be a positive number of metres: it is also the "
            f"farthest a coordinated turn may stray from a tree (got {horizontal_cap_m!r})"
        )

    points = [placemark_point(placemark, namespaces, height_tag) for placemark in placemarks]
    last = len(placemarks) - 1
    for idx, placemark in enumerate(placemarks):
        if idx in (0, last):
            set_turn_param(placemark, namespaces, STOP_TURN, STOP_DAMPING)
            continue
        if turn_mode(placemark, namespaces) != COORDINATE_TURN:
            continue
        radius = turn_radius(points[idx - 1], points[idx], points[idx + 1], horizontal_cap_m)
        if radius == 0:
            # Coincident waypoints leave no room to arc through at all.
            set_turn_param(placemark, namespaces, STOP_TURN, STOP_DAMPING)
        else:
            set_turn_param(placemark, namespaces, COORDINATE_TURN, f"{radius:.15g}")


# -----------------------------------------------------------------------------
def turn_radius(previous, corner, following, horizontal_cap_m):
    """The radius to arc through `corner` on, in metres. 0 means it cannot arc.

    Two limits, and the smaller wins.

    The legs: the flight controller rejects a route whose radius exceeds half
    of an adjacent leg ("waypoint turning intercept error", 1550), and the RC
    itself sizes a radius as a third of the shorter one. Legs run from
    centimetres to tens of metres -- the hop from a transit waypoint down to its
    approach waypoint collapses whenever a checkpoint sits at the same elevation
    as its tree.

    The ground: an arc leaves its waypoint early and flies the corner off, so
    the aircraft is away from the tree before it has finished climbing, or
    descending before it is over it. Every waypoint of a tree sits at the tree's
    own position, so most corners turn between a vertical leg and a horizontal
    one. A radius sized from the legs comes off the climb or the descent and is
    then spent flying sideways: a 12 m climb gives a 4 m radius, so the
    aircraft leaves the climb 4 m below the altitude it was climbing to and is
    4 m from the tree before it gets there. The DSM was sampled within
    `buffer_feature` of each tree and nowhere else, so that is the farthest an
    arc may reach.

    An arc of radius r reaches at most r * h from its waypoint horizontally,
    where h is the horizontal share of the steeper adjacent leg. Capping r at
    `horizontal_cap_m / h` bounds the reach exactly: a vertical corner is not
    limited at all, and a level one is limited to the cap itself.
    """
    legs = [leg_length(previous, corner), leg_length(corner, following)]
    radius = min(legs) / LEG_RATIO
    reach = max(horizontal_fraction(previous, corner), horizontal_fraction(corner, following))
    if reach > 0:
        radius = min(radius, horizontal_cap_m / reach)
    return radius


# -----------------------------------------------------------------------------
def leg_length(start, end):
    # Equirectangular projection about the mid-latitude, on a sphere of
    # EARTH_RADIUS_M: the measure the RC sizes its turn radii from. At the
    # tens-of-metres scale of a leg it agrees with a geodesic to the millimetre.
    d_east, d_north = _horizontal_offset(start, end)
    return math.sqrt(d_east**2 + d_north**2 + (end[2] - start[2]) ** 2)


# -----------------------------------------------------------------------------
def horizontal_fraction(start, end):
    """The share of a leg's length that is horizontal: 0 straight up, 1 level."""
    length = leg_length(start, end)
    if length == 0:
        return 0.0
    return math.hypot(*_horizontal_offset(start, end)) / length


# -----------------------------------------------------------------------------
def _horizontal_offset(start, end):
    lon_start, lat_start, _ = start
    lon_end, lat_end, _ = end
    mid_lat = math.radians((lat_start + lat_end) / 2)
    d_east = math.radians(lon_end - lon_start) * EARTH_RADIUS_M * math.cos(mid_lat)
    d_north = math.radians(lat_end - lat_start) * EARTH_RADIUS_M
    return d_east, d_north


# -----------------------------------------------------------------------------
def placemark_point(placemark, namespaces, height_tag):
    coordinates = placemark.find("kml:Point/kml:coordinates", namespaces).text
    lon_x, lat_y = (float(value) for value in coordinates.strip().split(","))
    height = float(placemark.find(f"wpml:{height_tag}", namespaces).text)
    return (lon_x, lat_y, height)


# -----------------------------------------------------------------------------
def turn_mode(placemark, namespaces):
    return placemark.find("wpml:waypointTurnParam/wpml:waypointTurnMode", namespaces).text


# -----------------------------------------------------------------------------
def set_turn_param(placemark, namespaces, mode, damping_dist):
    turn_param = placemark.find("wpml:waypointTurnParam", namespaces)
    turn_param.find("wpml:waypointTurnMode", namespaces).text = mode
    turn_param.find("wpml:waypointTurnDampingDist", namespaces).text = damping_dist
