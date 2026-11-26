import math

# 0 = true north, per the DJI WPML orientedShoot spec.
NORTH = "0"


# -----------------------------------------------------------------------------
def photo_headings(wpt_csv_properties, mode):
    """Aircraft yaw for each waypoint's photo burst, in CSV order.

    ``north`` holds every burst at true north, so frames of the same tree can be
    compared across missions. ``arrival`` faces the burst the way the aircraft
    flew in, which costs no rotation on arrival: the leg into a waypoint is the
    only horizontal one, since a waypoint's four placemarks share its lat/lon and
    differ only in height.

    The first waypoint is reached from the take-off site, which the waypoints CSV
    does not record, so it faces the way *out* to the second waypoint instead --
    the one rotation it cannot avoid is spent leaving rather than arriving. A
    lone waypoint has no leg at all and faces north.
    """
    if mode != "arrival" or len(wpt_csv_properties) < 2:
        return [NORTH] * len(wpt_csv_properties)

    inbound = [
        bearing(wpt_csv_properties[idx - 1], wpt_csv_properties[idx])
        for idx in range(1, len(wpt_csv_properties))
    ]
    return [inbound[0], *inbound]


# -----------------------------------------------------------------------------
def bearing(start, end):
    """Whole-degree bearing from one CSV waypoint row to the next, in (-180, 180].

    Equirectangular offsets about the mid-latitude, the same projection
    ``BuildWaylinesWPML.legLength`` measures its turn radii with. Only the ratio
    of the offsets matters here, so the sphere's radius cancels out.
    """
    lat_start, lon_start = float(start[0]), float(start[1])
    lat_end, lon_end = float(end[0]), float(end[1])
    mid_lat = math.radians((lat_start + lat_end) / 2)
    d_east = math.radians(lon_end - lon_start) * math.cos(mid_lat)
    d_north = math.radians(lat_end - lat_start)
    # + 0.0 so a bearing rounding to zero is written "0", never "-0".
    return f"{round(math.degrees(math.atan2(d_east, d_north))) + 0.0:.0f}"
