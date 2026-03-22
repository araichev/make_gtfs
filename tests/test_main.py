import pandas as pd
import gtfs_kit as gk
import shapely.geometry as sg
import geopandas as gpd
import numpy as np
import pytest

from .context import make_gtfs, DATA_DIR
import make_gtfs as mg


# Load test ProtoFeed
pfeed = mg.read_protofeed(DATA_DIR / "auckland")
pfeed_l = mg.read_protofeed(DATA_DIR / "auckland_light")
pfeed_w = mg.read_protofeed(DATA_DIR / "auckland_wonky")


def test_get_duration():
    ts1 = "01:01:01"
    ts2 = "01:05:01"
    get = mg.get_duration(ts1, ts2, units="min")
    expect = 4
    assert get == expect


def test_make_stop_points():
    lines = gpd.read_file(DATA_DIR / "auckland" / "shapes.geojson").to_crs("epsg:2193")
    lines_looping = lines.iloc[:1]
    lines_nonlooping = lines.iloc[1:]

    offset = 5
    side = "left"
    points = mg.make_stop_points(lines_nonlooping, "shape_id", offset=0, side=side)
    assert set(points.columns) == {
        "shape_id",
        "point_id",
        "shape_dist_traveled",
        "geometry",
    }
    for __, group in points.groupby("shape_id"):
        assert group.shape[0] == 2

    n = 5
    points = mg.make_stop_points(lines_nonlooping, "shape_id", offset, side, n=n)
    for __, group in points.groupby("shape_id"):
        assert group.shape[0] == n

    # Points should be the correct distance away.
    assert np.allclose(points.distance(lines_nonlooping.geometry.iat[0]), offset)

    points = mg.make_stop_points(lines_looping, "shape_id", offset, side, n=n)
    for __, group in points.groupby("shape_id"):
        assert group.shape[0] == n - 1

    points = mg.make_stop_points(lines, "shape_id", offset, side, spacing=200)
    for __, group in points.groupby("shape_id"):
        assert group.shape[0] >= 2


def test_build_routes():
    for p in [pfeed, pfeed_w]:
        routes = mg.build_routes(pfeed)

        # Should have correct shape
        assert (
            routes.shape[0]
            == pfeed.frequencies.drop_duplicates("route_short_name").shape[0]
        )
        assert set(routes.columns) == {
            "route_id",
            "agency_id",
            "route_type",
            "route_short_name",
            "route_long_name",
        }


def test_build_shapes():
    shapes = mg.build_shapes(pfeed)

    # Should be a data frame
    assert isinstance(shapes, pd.DataFrame)

    # Should have correct shape
    count = 0
    for direction in pfeed.shapes_extra.values():
        if direction == 0:
            count += 1
        else:
            count += direction
    expect_nshapes = count
    expect_ncols = 4
    assert shapes.groupby("shape_id").ngroups == expect_nshapes
    assert shapes.shape[1] == expect_ncols


def test_build_stops():
    # Test with null ``pfeed.stops``
    pfeed_stopless = pfeed.copy()
    pfeed_stopless.stops = None

    # Test with non-null ``pfeed.stops``
    stops = mg.build_stops(pfeed)
    assert stops.shape == pfeed.stops.shape
    assert set(stops.columns) == set(pfeed.stops.columns)

    shapes = mg.build_shapes(pfeed_stopless)
    stops = mg.build_stops(pfeed_stopless, shapes, spacing=400)
    assert set(stops.columns) == {"stop_id", "stop_name", "stop_lon", "stop_lat"}
    nshapes = shapes.shape_id.nunique()
    assert stops.shape[0] >= nshapes

    n = 4
    stops = mg.build_stops(pfeed_stopless, shapes, n=4)
    # Should have correct shape
    nshapes = shapes.shape_id.nunique()
    assert stops.shape[0] <= n * nshapes


def test_build_trips():
    routes = mg.build_routes(pfeed)
    __, service_by_window = mg.build_calendar_etc(pfeed)
    shapes = mg.build_shapes(pfeed)
    trips = mg.build_trips(pfeed, routes, service_by_window)

    # Should be a data frame
    assert isinstance(trips, pd.DataFrame)

    # Should have correct shape
    f = pd.merge(routes[["route_id", "route_short_name"]], pfeed.frequencies)
    f = pd.merge(f, pfeed.service_windows)
    shapes = set(shapes["shape_id"].unique())
    expect_ntrips = 0
    for index, row in f.iterrows():
        # Get number of trips corresponding to this row
        # and add it to the total
        frequency = row["frequency"]
        if not frequency:
            continue
        start, end = row[["start_time", "end_time"]].values
        duration = mg.get_duration(start, end, "h")
        direction = row["direction"]
        if direction == 0:
            trip_mult = 1
        else:
            trip_mult = direction
        expect_ntrips += int(duration * frequency) * trip_mult
    expect_ncols = 5
    assert trips.shape == (expect_ntrips, expect_ncols)


def test_buffer_side():
    s = sg.LineString([[0, 0], [1, 0]])
    buff = 5
    # Buffers should have correct area and orientation
    for side in ["left", "right", "both"]:
        b = mg.buffer_side(s, side, buff)
        p = b.representative_point()
        if side == "left":
            assert b.area >= buff
            assert p.coords[0][1] > 0
        elif side == "right":
            assert b.area >= buff
            assert p.coords[0][1] < 0
        else:
            assert b.area >= 2 * buff


def test_get_stops_nearby():
    geom = sg.LineString([[0, 0], [2, 0]])
    stops = gpd.GeoDataFrame(
        [["a", sg.Point([1, 1])], ["b", sg.Point([1, -1])]],
        columns=["stop_code", "geometry"],
    )
    for side in ["left", "right", "both"]:
        n = mg.get_stops_nearby(stops, geom, side, 1)
        if side == "left":
            assert n.shape[0] == 1
            assert n.stop_code.iat[0] == "a"
        elif side == "right":
            assert n.shape[0] == 1
            assert n.stop_code.iat[0] == "b"
        else:
            assert n.shape[0] == 2
            assert set(n.stop_code.values) == {"a", "b"}


def test_compute_shape_point_speeds():
    shapes = mg.build_shapes(pfeed)
    route_type = pfeed.route_types()[0]
    g = mg.compute_shape_point_speeds(shapes, pfeed.speed_zones, route_type)
    assert isinstance(g, gpd.GeoDataFrame)
    assert set(g.columns) == {
        "shape_id",
        "shape_pt_sequence",
        "shape_dist_traveled",
        "geometry",
        "route_type",
        "speed_zone_id",
        "speed",
    }
    assert g.crs == mg.WGS84

    # Should have correct length
    assert g.shape[0] >= shapes.shape[0]

    # Speed zones present should make sense
    sz = pfeed.speed_zones.loc[lambda x: x.route_type == route_type]
    assert set(g.speed_zone_id) <= set(sz.speed_zone_id)


@pytest.mark.slow
def test_build_stop_times_for_trip():
    stops = mg.build_stops(pfeed)
    stops_g = gk.geometrize_stops(stops, use_utm=True)
    shapes = mg.build_shapes(pfeed)
    shapes_gi = gk.geometrize_shapes(shapes, use_utm=True).set_index("shape_id")
    trip_id = "bingo"
    shape_id = shapes_gi.index[0]

    # Generic case
    linestring = shapes_gi.loc[shape_id].geometry
    stops_g_nearby = mg.get_stops_nearby(stops_g, linestring, "left")
    route_type = 3
    sz = pfeed.speed_zones.to_crs(pfeed.utm_crs)
    shape_point_speeds = mg.compute_shape_point_speeds(shapes, sz, route_type)
    default_speed = 2
    start_time = 0
    f = mg.build_stop_times_for_trip(
        trip_id,
        stops_g_nearby,
        shape_id,
        linestring,
        sz,
        route_type,
        shape_point_speeds,
        default_speed,
        start_time,
    )
    assert set(f.columns) == {
        "trip_id",
        "stop_id",
        "stop_sequence",
        "arrival_time",
        "departure_time",
        "shape_dist_traveled",
    }

    # Should have correct length
    assert f.shape[0] == stops_g_nearby.shape[0]

    # Average speed of trip should be reasonable
    def compute_avg_speed(f):
        return (
            3.6
            * (f.shape_dist_traveled.iat[-1] - f.shape_dist_traveled.iat[0])
            / (f.arrival_time.iat[-1] - f.arrival_time.iat[0])
        )

    sz = pfeed.speed_zones.loc[lambda x: x.route_type == route_type]
    avg_speed = compute_avg_speed(f)
    assert (
        min(sz.speed.min(), default_speed)
        <= avg_speed
        <= max(sz.speed.max(), default_speed)
    )

    # Edge case with one speed zone encompassing the trip and infinite speed
    sz = gpd.GeoDataFrame(
        [{"speed": np.inf, "route_type": route_type}],
        geometry=[sg.box(*linestring.bounds).buffer(10)],
        crs=stops_g.crs,
    )
    shape_point_speeds = mg.compute_shape_point_speeds(shapes, sz, route_type)
    default_speed = 2

    f = mg.build_stop_times_for_trip(
        trip_id,
        stops_g_nearby,
        shape_id,
        linestring,
        sz,
        route_type,
        shape_point_speeds,
        default_speed,
        start_time,
    )

    # Average speed should be correct
    avg_speed = compute_avg_speed(f)
    assert np.allclose(avg_speed, default_speed)

    # Edge case with one speed zone encompassing the trip
    sz = gpd.GeoDataFrame(
        [{"speed": 100, "route_type": route_type}],
        geometry=[sg.box(*linestring.bounds).buffer(10)],
        crs=stops_g.crs,
    )
    shape_point_speeds = mg.compute_shape_point_speeds(shapes, sz, route_type)

    f = mg.build_stop_times_for_trip(
        trip_id,
        stops_g_nearby,
        shape_id,
        linestring,
        sz,
        route_type,
        shape_point_speeds,
        default_speed,
        start_time,
    )

    # Average speed should be correct
    avg_speed = compute_avg_speed(f)
    assert np.allclose(avg_speed, 100)


@pytest.mark.slow
def test_build_stop_times():
    # Test stopless version first
    pfeed_stopless = pfeed.copy()
    pfeed_stopless.stops = None
    routes = mg.build_routes(pfeed_stopless)
    shapes = mg.build_shapes(pfeed_stopless)
    __, service_by_window = mg.build_calendar_etc(pfeed_stopless)
    stops = mg.build_stops(pfeed_stopless, shapes)
    trips = mg.build_trips(pfeed_stopless, routes, service_by_window)
    stop_times = mg.build_stop_times(pfeed_stopless, routes, shapes, stops, trips)

    assert isinstance(stop_times, pd.DataFrame)

    # Should have correct shape.
    # Number of stop times is at most twice the number of trips,
    # because each trip has at most two stops
    assert stop_times.shape[0] <= 2 * trips.shape[0]
    assert stop_times.shape[1] == 6

    # Test with stops
    routes = mg.build_routes(pfeed)
    shapes = mg.build_shapes(pfeed)
    stops = mg.build_stops(pfeed)
    __, service_by_window = mg.build_calendar_etc(pfeed)
    trips = mg.build_trips(pfeed, routes, service_by_window)
    stop_times = mg.build_stop_times(pfeed, routes, shapes, stops, trips)

    # Should be a data frame
    assert isinstance(stop_times, pd.DataFrame)

    # Should have correct shape.
    # Number of stop times is at least twice the number of trips,
    # because each trip has two stops
    assert stop_times.shape[0] >= 2 * trips.shape[0]
    assert stop_times.shape[1] == 6

    # Test with stops and tiny buffer so that no stop times are built
    stop_times = mg.build_stop_times(pfeed, routes, shapes, stops, trips, buffer=0)

    # Should be a data frame
    assert isinstance(stop_times, pd.DataFrame)

    # Should be empty
    assert stop_times.empty


@pytest.mark.slow
def test_build_feed():
    feed = mg.build_feed(pfeed)

    # Should be a GTFSTK Feed
    assert isinstance(feed, gk.Feed)

    # Should have correct tables
    names = ["agency", "calendar", "routes", "shapes", "stops", "stop_times", "trips"]
    for name in names:
        assert hasattr(feed, name)
