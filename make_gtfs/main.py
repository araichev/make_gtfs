"""
This module contains the main logic.
"""

from functools import lru_cache
import math

import geopandas as gpd
import pandas as pd
import numpy as np
import shapely.ops as so
import shapely.geometry as sg
import gtfs_kit as gk

from . import protofeed as pf
from . import constants as cs
from . import hashables as h


def get_duration(timestr1: str, timestr2: str, units="s") -> float:
    """
    Return the duration of the time period between the first and second
    time string in the given units.
    Allowable units are 's' (seconds), 'min' (minutes), 'h' (hours).
    Assume ``timestr1 < timestr2``.
    """
    valid_units = ["s", "min", "h"]
    assert units in valid_units, "Units must be one of {!s}".format(valid_units)

    duration = gk.timestr_to_seconds(timestr2) - gk.timestr_to_seconds(timestr1)

    if units == "s":
        result = duration
    elif units == "min":
        result = duration / 60
    else:
        result = duration / 3600

    return result


def build_agency(pfeed: pf.ProtoFeed) -> pd.DataFrame:
    """
    Given a ProtoFeed, return a DataFrame representing ``agency.txt``
    """
    return pd.DataFrame(
        {
            "agency_id": pfeed.meta["agency_id"].iat[0],
            "agency_name": pfeed.meta["agency_name"].iat[0],
            "agency_url": pfeed.meta["agency_url"].iat[0],
            "agency_timezone": pfeed.meta["agency_timezone"].iat[0],
        },
        index=[0],
    )


def build_calendar_etc(pfeed: pf.ProtoFeed) -> pd.DataFrame:
    """
    Given a ProtoFeed, return a DataFrame representing ``calendar.txt``
    and a dictionary of the form <service window ID> -> <service ID>,
    respectively.
    """
    windows = pfeed.service_windows.copy()

    # Create a service ID for each distinct days_active field and map the
    # service windows to those service IDs
    def get_sid(bitlist):
        return "srv" + "".join([str(b) for b in bitlist])

    weekdays = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]
    bitlists = set()

    # Create a dictionary <service window ID> -> <service ID>
    d = dict()
    for index, window in windows.iterrows():
        bitlist = window[weekdays].tolist()
        d[window["service_window_id"]] = get_sid(bitlist)
        bitlists.add(tuple(bitlist))
    service_by_window = d

    # Create calendar
    start_date = pfeed.meta["start_date"].iat[0]
    end_date = pfeed.meta["end_date"].iat[0]
    F = []
    for bitlist in bitlists:
        F.append([get_sid(bitlist)] + list(bitlist) + [start_date, end_date])
    calendar = pd.DataFrame(
        F, columns=(["service_id"] + weekdays + ["start_date", "end_date"])
    )

    return calendar, service_by_window


def build_routes(pfeed: pf.ProtoFeed) -> pd.DataFrame:
    """
    Given a ProtoFeed, return a DataFrame representing ``routes.txt``.
    """
    f = (
        pfeed.frequencies.filter(
            ["route_short_name", "route_long_name", "route_type", "shape_id"]
        )
        .drop_duplicates()
        .copy()
    )

    # Create route IDs
    f["route_id"] = "r" + f["route_short_name"].map(str)

    f["agency_id"] = pfeed.meta["agency_id"].iat[0]

    del f["shape_id"]

    return f


def build_shapes(pfeed: pf.ProtoFeed) -> pd.DataFrame:
    """
    Given a ProtoFeed, return DataFrame representing ``shapes.txt``.
    Only use shape IDs that occur in both ``pfeed.shapes`` and
    ``pfeed.frequencies``.
    Create reversed shapes where routes traverse shapes in both
    directions.
    """
    rows = []
    for pshid, geom in pfeed.shapes[["shape_id", "geometry"]].itertuples(index=False):
        if pshid not in pfeed.shapes_extra:
            continue
        if pfeed.shapes_extra[pshid] == 2:
            # Add shape and its reverse
            did = "1"
            shid = f"{pshid}{cs.SEP}{did}"
            new_rows = [[shid, i, lon, lat] for i, (lon, lat) in enumerate(geom.coords)]
            rows.extend(new_rows)
            did = "0"
            shid = f"{pshid}{cs.SEP}{did}"
            new_rows = [
                [shid, i, lon, lat]
                for i, (lon, lat) in enumerate(reversed(geom.coords))
            ]
            rows.extend(new_rows)
        else:
            # Add shape
            did = pfeed.shapes_extra[pshid]
            shid = f"{pshid}{cs.SEP}{did}"
            new_rows = [[shid, i, lon, lat] for i, (lon, lat) in enumerate(geom.coords)]
            rows.extend(new_rows)

    return pd.DataFrame(
        rows, columns=["shape_id", "shape_pt_sequence", "shape_pt_lon", "shape_pt_lat"]
    )


def make_stop_points(
    lines: gpd.GeoDataFrame,
    id_col: str,
    offset: float,
    side: str,
    n: int = 2,
    spacing: float | None = None,
) -> gpd.GeoDataFrame:
    """
    Given a GeoDataFrame of lines with at least the columns

    - ``id_col``: a unique identifier of the line
    - ``'geometry'``: a LineString in a meters-based CRS

    return a GeoDataFrame containing ``n`` equally spaced points for each line,
    offset by ``offset`` meters on the ``side`` side ('left' or 'right') of the line.
    Set ``offset = 0`` to make points on each line.
    The lines represent route shapes and the points represent stops.

    If ``spacing`` is not ``None``, then ignore ``n`` and for each line,
    sample points along the line spaced ``spacing`` meters apart from start to end,
    except allow the spacing of the last two points to be < 2 * spacing.
    Then offset these points according to ``offset`` and ``side``.

    Drop duplicate point geometries, which can occur in loops.

    The resulting GeoDataFrame has the columns

    - ``'point_id'``: a unique identifier of the point
    - ``id_col``: ID of the line the point corresponds to
    - ``'shape_dist_traveled'``: how far along the line the point lies; in meters
    - ``'geometry'``: a Point in the same CRS as the ``lines`` GeoDataFrame

    Helper function for generating stops along trip shapes.
    """
    n = int(n)
    if n < 2:
        n = 2

    def get_dists(L, δ):
        return [δ * i for i in range(math.floor(L / δ))] + [L]

    frames = []
    for s in lines.itertuples(index=False):
        geom_1 = s.geometry
        L = geom_1.length
        if spacing is None:
            δ = L / (n - 1)
        else:
            δ = spacing
        # Sample points spaced at ``spacing`` meters along the line
        dists = get_dists(L, δ)

        if offset > 0:
            # Offset the points in the correct direction using vector addition.
            # It's simpler to offset the line, then sample points on the offset.
            # But that method often fails on self-intersecting lines,
            # producting disconnected offsets.
            points_1 = [geom_1.interpolate(x) for x in dists]
            geom_2 = geom_1.parallel_offset(0.1, side)  # offset line by a smidge
            points_2 = [geom_2.interpolate(geom_2.project(p)) for p in points_1]
            # Make unit vectors in the correct directions
            vectors = [
                np.array(points_2[i].coords[0]) - np.array(points_1[i].coords[0])
                for i in range(len(points_1))
            ]
            unit_vectors = [v / np.linalg.norm(v) for v in vectors]
            # Make points as points_1 + offset * unit_vectors.
            points = [
                np.array(points_1[i].coords[0]) + offset * unit_vectors[i]
                for i in range(len(points_1))
            ]
        else:
            # Skip the complexities
            points = [geom_1.interpolate(x).coords[0] for x in dists]

        line_id = s._asdict()[id_col]
        suffixes = gk.make_ids(len(points), prefix="")
        point_ids = [f"{line_id}{cs.SEP}{suffix}" for suffix in suffixes]
        geometry = gpd.points_from_xy(
            x=[p[0] for p in points], y=[p[1] for p in points], crs=lines.crs
        )
        g = gpd.GeoDataFrame(
            {"point_id": point_ids, id_col: line_id, "shape_dist_traveled": dists},
            geometry=geometry,
        ).drop_duplicates("geometry")
        frames.append(g)

    if frames:
        result = pd.concat(frames)
    else:
        result = gpd.GeoDataFrame()
    return result


def build_stops(
    pfeed: pf.ProtoFeed,
    shapes: pd.DataFrame | None = None,
    offset: float = cs.STOP_OFFSET,
    n: int = 2,
    spacing: float | None = None,
) -> pd.DataFrame:
    """
    Given a ProtoFeed, return a DataFrame representing ``stops.txt``.
    If ``pfeed.stops`` is not ``None``, then return that.
    Otherwise, require built shapes output by :func:`build_shapes`.
    In that case, for each shape, build ``n`` equally spaced stops offset by ``offset``
    meters on the traffic side of the shape.
    If ``spacing`` is not ``None``, then ignore ``n`` and for each shape,
    create offset stops spaced ``spacing`` meters apart (when projected onto the shape),
    except allow the spacing of the last two stops to be < 2 * spacing.

    When building stops, drop stops with duplicate geometries within a shape to
    gracefully handle loop shapes.
    Also, if a shape has an antiparallel clone, then only build stops for the shape,
    not its clone.
    """
    if pfeed.stops is not None:
        stops = pfeed.stops.copy()
    else:
        if shapes is None:
            raise ValueError("Must input shapes built by build_shapes()")

        # Keep only one line per antiparallel pair of shapes.
        # These can be determined from the shape IDs.
        shapes_g = (
            gk.geometrize_shapes(shapes, use_utm=True)
            .assign(base_shape=lambda x: x.shape_id.str.split(cs.SEP, expand=True)[0])
            .drop_duplicates("base_shape")
        )
        side = cs.TRAFFIC_BY_TIMEZONE[pfeed.meta.agency_timezone.iat[0]]
        stops = (
            make_stop_points(
                shapes_g,
                id_col="shape_id",
                offset=offset,
                side=side,
                n=n,
                spacing=spacing,
            )
            .to_crs(cs.WGS84)
            .rename(columns={"point_id": "stop_id"})
            .assign(
                stop_name=lambda x: "stop " + x.stop_id,
                stop_lon=lambda p: p.geometry.x,
                stop_lat=lambda p: p.geometry.y,
            )
            .filter(["stop_id", "stop_name", "stop_lon", "stop_lat"], axis="columns")
        )

    return stops


def build_trips(
    pfeed: pf.ProtoFeed,
    routes: pd.DataFrame,
    service_by_window: dict,
) -> pd.DataFrame:
    """
    Given a ProtoFeed and its corresponding routes and service-by-window,
    return a DataFrame representing ``trips.txt``.
    Trip IDs encode route, direction, and service window information
    to make it easy to compute stop times later.
    """
    # Put together the route and service data
    routes = (
        routes[["route_id", "route_short_name"]]
        .merge(pfeed.frequencies)
        .merge(pfeed.service_windows)
    )
    # For each row in routes, add trips at the specified frequency in
    # the specified direction
    rows = []
    for index, row in routes.iterrows():
        shape = row["shape_id"]
        route = row["route_id"]
        window = row["service_window_id"]
        start, end = row[["start_time", "end_time"]].values
        duration = get_duration(start, end, "h")
        frequency = row["frequency"]
        if not frequency:
            # No trips during this service window
            continue
        # Rounding down occurs here if the duration isn't integral
        # (bad input)
        num_trips_per_direction = int(frequency * duration)
        service = service_by_window[window]
        direction = row["direction"]
        if direction == 2:
            directions = [0, 1]
        else:
            directions = [direction]
        for direction in directions:
            # Warning: this shape-ID-making logic needs to match that
            # in ``build_shapes``
            shid = "{}{}{}".format(shape, cs.SEP, direction)
            rows.extend(
                [
                    [
                        route,
                        cs.SEP.join(
                            ["t", route, window, start, str(direction), str(i)]
                        ),
                        direction,
                        shid,
                        service,
                    ]
                    for i in range(num_trips_per_direction)
                ]
            )

    return pd.DataFrame(
        rows, columns=["route_id", "trip_id", "direction_id", "shape_id", "service_id"]
    )


def buffer_side(linestring: sg.LineString, side: str, buffer: float) -> sg.Polygon:
    """
    Given a Shapely LineString, a side of the LineString
    (string; 'left' = left hand side of LineString,
    'right' = right hand side of LineString, or
    'both' = both sides), and a buffer size in the distance units of
    the LineString, buffer the LineString on the given side by
    the buffer size and return the resulting Shapely polygon.
    """
    b = linestring.buffer(buffer, cap_style=2)
    if side in ["left", "right"] and buffer > 0:
        # Make a tiny buffer to split the normal-size buffer
        # in half across the linestring
        eps = min(buffer / 2, 0.001)
        b0 = linestring.buffer(eps, cap_style=3)
        diff = b.difference(b0)
        polys = so.polygonize(diff)
        # Buffer sides slightly to include original linestring
        if side == "left":
            b = list(polys)[0].buffer(1.1 * eps)
        else:
            b = list(polys)[-1].buffer(1.1 * eps)

    return b


def get_stops_nearby(
    geo_stops: gpd.GeoDataFrame,
    linestring: sg.LineString,
    side: str,
    buffer: float = cs.BUFFER,
) -> gpd.GeoDataFrame:
    """
    Given a GeoDataFrame of stops, a Shapely LineString in the
    same coordinate system, a side of the LineString
    (string; 'left' = left hand side of LineString,
    'right' = right hand side of LineString, or
    'both' = both sides), and a buffer in the distance units of that
    coordinate system, do the following.
    Return a GeoDataFrame of all the stops that lie within
    ``buffer`` distance units to the ``side`` of the LineString.
    """
    b = buffer_side(linestring, side, buffer)

    # Collect stops
    return geo_stops.loc[geo_stops.intersects(b)].copy()


def compute_shape_point_speeds(
    shapes: pd.DataFrame,
    speed_zones: gpd.GeoDataFrame,
    route_type: int,
    *,
    use_utm: bool = False,
) -> gpd.GeoDataFrame:
    """
    Intersect the given GTFS shapes table with the given speed zones subset to the given
    route type to assign speeds to each shape point.
    Also add points and speeds where the speed zones intersect the linestrings
    corresponding to the shapes (the boundary points).
    Return a GeoDataFrame with the columns

    - shape_id
    - shape_dist_traveled: in meters
    - shape_pt_sequence: -1 if a boundary point
    - geometry: Point object representing shape point
    - route_type: ``route_type``
    - speed: in kilometers per hour
    - speed_zone_id: speed zone ID

    Use UTM coordinates if specified.
    Return an empty GeoDataFrame if there are no speed zones for the given route type.
    """
    speed_zones = speed_zones.loc[lambda x: x.route_type == route_type]
    if speed_zones.empty:
        return gpd.GeoDataFrame()

    # Get UTM CRS to compute distances in metres
    utm_crs = speed_zones.estimate_utm_crs()
    speed_zones = speed_zones.to_crs(utm_crs)

    # Build shape points
    def compute_dists(group):
        p2 = group.geometry.shift(1)
        group["dist"] = group.geometry.distance(p2, align=False)
        group["shape_dist_traveled"] = group.dist.fillna(0).cumsum()
        return group

    shape_points = (
        gpd.GeoDataFrame(
            shapes,
            geometry=gpd.points_from_xy(shapes.shape_pt_lon, shapes.shape_pt_lat),
            crs=cs.WGS84,
        )
        .to_crs(utm_crs)
        .sort_values(["shape_id", "shape_pt_sequence"])
        .groupby("shape_id")
        .apply(compute_dists, include_groups=False)
        .drop(["dist", "shape_pt_lat", "shape_pt_lon"], axis="columns")
    )

    # Get points where shapes intersect speed zone boundaries
    shapes_g = (
        gk.geometrize_shapes(shapes)
        .to_crs(utm_crs)
        .assign(
            boundary_points=lambda x: x.intersection(speed_zones.boundary, align=True)
        )
    )

    # Assign distances to those boundary points
    rows = []
    for shape_id, group in shapes_g.groupby("shape_id"):
        bd = group.boundary_points.iat[0]
        if bd and not bd.is_empty:
            if isinstance(bd, sg.Point):
                bpoints = [bd]
            else:
                bpoints = bd.geoms
            for point in bpoints:
                dist = group.geometry.iat[0].project(point)
                rows.append([shape_id, dist, point])

    boundary_points = gpd.GeoDataFrame(
        rows,
        columns=["shape_id", "shape_dist_traveled", "geometry"],
        crs=utm_crs,
    )

    # Concatenate shape points and boundary points and assign speeds
    g = (
        pd.concat(
            [
                shape_points,
                boundary_points.assign(shape_pt_sequence=-1),
            ]
        )
        .sjoin(speed_zones)
        .drop("index_right", axis="columns")
        .sort_values(
            ["shape_id", "shape_dist_traveled", "shape_pt_sequence"], ignore_index=True
        )
    )

    if not use_utm:
        # Convert back to WGS84
        g = g.to_crs(cs.WGS84)

    return g.filter(
        [
            "shape_id",
            "shape_pt_sequence",
            "shape_dist_traveled",
            "geometry",
            "route_type",
            "speed_zone_id",
            "speed",
        ]
    )


def build_stop_times_for_trip(
    trip_id: str,
    stops_g_nearby: gpd.GeoDataFrame,
    shape_id: str,
    linestring: sg.LineString,
    speed_zones: gpd.GeoDataFrame,
    route_type: int,
    shape_point_speeds: gpd.GeoDataFrame,
    default_speed: float,
    start_time: int,
) -> pd.DataFrame:
    """
    Build stop times for the given trip ID.

    Assume all coordinates are in meters, distances are in meters, and speeds are in
    kilometers per hour.
    """
    # Subset frames and convert speeds to meters per second
    k = 1000 / 3600
    sps = (
        shape_point_speeds.loc[lambda x: x.shape_id == shape_id]
        .assign(speed=lambda x: x.speed * k)
        .filter(["shape_id", "shape_dist_traveled", "speed_zone_id", "speed"])
    )
    speed_zones = speed_zones.loc[lambda x: x.route_type == route_type].assign(
        speed=lambda x: x.speed * k
    )
    default_speed *= k

    # Get stop distances along linestring, and intersect with speed zones to get speeds
    f = (
        stops_g_nearby.assign(
            shape_dist_traveled=lambda x: x.apply(
                lambda row: linestring.project(row.geometry), axis=1
            ),
        )
        .sjoin(speed_zones)
        .sort_values("shape_dist_traveled", ignore_index=True)
        .filter(["stop_id", "shape_dist_traveled", "speed_zone_id", "speed"])
    )

    # Insert stops into shape point speeds at appropriate distances,
    # fill default speed, and assign distance weighted speeds to each point.
    # Use the latter later to compute distance-weighted average speeds between stops.
    return (
        pd.concat([f, sps])
        .sort_values("shape_dist_traveled", ignore_index=True)
        .assign(
            speed=lambda x: x.speed.replace({np.inf: default_speed}),
            dist_to_next=lambda x: x.shape_dist_traveled.diff().shift(-1).fillna(0),
            weight_to_next=lambda x: x.dist_to_next * x.speed,
            shape_weight_traveled=lambda x: x.weight_to_next.cumsum()
            .shift(1)
            .fillna(0),
        )
        # Drop the shape points, keeping only the stops,
        # then compute distances, distance-weighted speeds,
        # and times between successive stops.
        .loc[lambda x: x.stop_id.notna()]
        .assign(
            trip_id=trip_id,
            dist_to_next=lambda x: x.shape_dist_traveled.diff().shift(-1).fillna(0),
            weight_to_next=lambda x: x.shape_weight_traveled.diff().shift(-1).fillna(0),
            speed_to_next=lambda x: (x.weight_to_next / x.dist_to_next).fillna(0),
            duration_to_next=lambda x: (x.dist_to_next / x.speed_to_next).fillna(0),
            arrival_time=lambda x: x.duration_to_next.shift(1).cumsum().fillna(0)
            + start_time,
            departure_time=lambda x: x.arrival_time,
            stop_sequence=lambda x: range(len(x.index)),
        )
        .filter(
            [
                "trip_id",
                "stop_id",
                "stop_sequence",
                "arrival_time",
                "departure_time",
                "shape_dist_traveled",
            ]
        )
    )


@lru_cache()
def _build_stop_times_for_trip(
    trip_id: str,
    stops_g_nearby: h.HashableGeoDataFrame,
    shape_id: str,
    linestring: h.HashableLineString,
    speed_zones: h.HashableGeoDataFrame,
    route_type: int,
    shape_point_speeds: h.HashableGeoDataFrame,
    default_speed: float,
    start_time: int,
) -> pd.DataFrame:
    """
    Caching version of :func:`build_stop_times_for_trip` for greater speed and internal
    use.
    Needs hashable GeoDataFrames and LineStrings to work.
    """
    return build_stop_times_for_trip(
        trip_id,
        stops_g_nearby,
        shape_id,
        linestring,
        speed_zones,
        route_type,
        shape_point_speeds,
        default_speed,
        start_time,
    )


def build_stop_times(
    pfeed: pf.ProtoFeed,
    routes: pd.DataFrame,
    shapes: pd.DataFrame,
    stops: pd.DataFrame,
    trips: pd.DataFrame,
    buffer: float = cs.BUFFER,
) -> pd.DataFrame:
    """
    Given a ProtoFeed and its corresponding routes,
    shapes, stops, and trips DataFrames,
    return a DataFrame representing ``stop_times.txt``.
    Includes the optional ``shape_dist_traveled`` column rounded to the nearest meter.
    Does not make stop times for trips with no stops within the buffer.
    """
    # Get the table of trips and add frequency and service window details
    routes = routes.filter(["route_id", "route_short_name"]).merge(
        pfeed.frequencies.drop(["shape_id"], axis=1)
    )
    trips = trips.assign(
        service_window_id=lambda x: x.trip_id.map(lambda y: y.split(cs.SEP)[2])
    ).merge(routes)

    # Get the geometries of GTFS ``shapes``, not ``pfeed.shapes``
    shapes_gi = gk.geometrize_shapes(shapes, use_utm=True).set_index("shape_id")
    stops_g = gk.geometrize_stops(stops, use_utm=True)

    # For each trip get its shape and stops nearby and set stop times based on its
    # service window frequency.
    # Remember that every trip has a valid shape ID.
    frames = []
    # Look on the correct side of the street for stops
    side = cs.TRAFFIC_BY_TIMEZONE[pfeed.meta.agency_timezone.iat[0]]
    speed_zones = h.HashableGeoDataFrame(pfeed.speed_zones.to_crs(pfeed.utm_crs))
    for (route_type, shape_id, speed), group in trips.groupby(
        ["route_type", "shape_id", "speed"]
    ):
        shape_point_speeds = h.HashableGeoDataFrame(
            compute_shape_point_speeds(
                shapes, pfeed.speed_zones, route_type, use_utm=True
            )
        )
        linestring = h.HashableLineString(shapes_gi.loc[shape_id].geometry)
        stops_g_nearby = h.HashableGeoDataFrame(
            get_stops_nearby(stops_g, linestring, side, buffer=buffer)
        )

        if stops_g_nearby.empty:
            # No stops to make times for
            continue

        for __, row in group.iterrows():
            frequency = row["frequency"]
            if not frequency:
                # The trip actually doesn't run
                continue

            trip_id = row["trip_id"]
            headway = 3600 / frequency  # seconds
            __, route, window, base_timestr, direction, i = trip_id.split(cs.SEP)
            direction = int(direction)
            base_time = gk.timestr_to_seconds(base_timestr)
            start_time = base_time + headway * int(i)  # seconds
            f = (
                _build_stop_times_for_trip(
                    "tmp_trip_id",
                    stops_g_nearby,
                    shape_id,
                    linestring,
                    speed_zones,
                    route_type,
                    shape_point_speeds,
                    speed,
                    0,
                )
                # Fill in trip ID and start times.
                # Doing it after the fact to take advantage of caching?
                .assign(
                    trip_id=trip_id,
                    arrival_time=lambda x: x.arrival_time + start_time,
                    departure_time=lambda x: x.arrival_time,
                )
            )
            frames.append(f)

    if not frames:
        f = pd.DataFrame(
            columns=[
                "trip_id",
                "stop_id",
                "stop_sequence",
                "arrival_time",
                "departure_time",
            ]
        )
    else:
        f = pd.concat(frames, ignore_index=True).assign(
            shape_dist_traveled=lambda x: x.shape_dist_traveled.round()
        )
        # Convert seconds back to time strings
        f[["arrival_time", "departure_time"]] = f[
            ["arrival_time", "departure_time"]
        ].map(lambda x: gk.seconds_to_timestr(x))

    # Free memory
    _build_stop_times_for_trip.cache_clear()

    return f


def build_feed(
    pfeed: pf.ProtoFeed,
    buffer: float = cs.BUFFER,
    stop_offset: float = cs.STOP_OFFSET,
    num_stops_per_shape: int = 2,
    stop_spacing: float | None = None,
) -> gk.Feed:
    """
    Convert the given ProtoFeed to a GTFS Feed with meter distance units.
    Look at a distance of ``buffer`` meters from route shapes to find stops.
    If no stops are given, then for each shape build stops offset by ``stop_offset``
    meters on the traffic side of each built shape.
    Make ``n`` equally spaced stops for each shape, then offset them.
    But if ``stop_spacing`` is given, then instead space the stops every
    ``stop_spacing`` meters along each shape, then offset them.
    If a shape has an antiparallel clone, then only build stops on the shape, not
    its clone, thereby avoiding unnecessary stops.
    Output distance units will be in meters
    """
    # Create Feed tables
    agency = build_agency(pfeed)
    calendar, service_by_window = build_calendar_etc(pfeed)
    routes = build_routes(pfeed)
    shapes = build_shapes(pfeed)
    stops = build_stops(
        pfeed, shapes, offset=stop_offset, n=num_stops_per_shape, spacing=stop_spacing
    )
    trips = build_trips(pfeed, routes, service_by_window)
    stop_times = build_stop_times(pfeed, routes, shapes, stops, trips, buffer=buffer)

    # Create Feed and remove unused stops etc.
    return gk.Feed(
        agency=agency,
        calendar=calendar,
        routes=routes,
        shapes=shapes,
        stops=stops,
        stop_times=stop_times,
        trips=trips,
        dist_units="m",
    ).drop_zombies()
