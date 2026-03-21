import pandera.pandas as pa
import pandas as pd

from .context import make_gtfs, DATA_DIR, pytest
import make_gtfs as mg


# Load test ProtoFeed
sample = mg.read_protofeed(DATA_DIR / "auckland")


def test_check_meta():
    assert mg.check_meta(sample).shape[0]

    pfeed = sample.copy()
    pfeed.meta = None
    with pytest.raises(ValueError):
        mg.check_meta(pfeed)

    pfeed = sample.copy()
    del pfeed.meta["agency_name"]
    with pytest.raises(pa.errors.SchemaError):
        mg.check_meta(pfeed)

    pfeed = sample.copy()
    pfeed.meta = pd.concat([pfeed.meta, pfeed.meta.iloc[:1]])
    with pytest.raises(pa.errors.SchemaError):
        mg.check_meta(pfeed)

    for col in [
        "agency_timezone",
        "agency_url",
        "start_date",
        "end_date",
    ]:
        pfeed = sample.copy()
        pfeed.meta[col] = "bingo"
        print(col)
        with pytest.raises(pa.errors.SchemaError):
            mg.check_meta(pfeed)


def test_check_shapes():
    assert mg.check_shapes(sample).shape[0]

    pfeed = sample.copy()
    del pfeed.shapes["shape_id"]
    with pytest.raises(pa.errors.SchemaError):
        mg.check_shapes(pfeed)

    pfeed = sample.copy()
    pfeed.shapes["yo"] = 3
    assert mg.check_shapes(pfeed).shape[0]

    pfeed = sample.copy()
    pfeed.shapes.loc[pfeed.shapes.index[0], "geometry"] = None
    with pytest.raises(pa.errors.SchemaError):
        mg.check_shapes(pfeed)


def test_check_service_windows():
    assert mg.check_service_windows(sample).shape[0]

    pfeed = sample.copy()
    pfeed.service_windows = pd.DataFrame()
    with pytest.raises(pa.errors.SchemaError):
        mg.check_service_windows(pfeed)

    pfeed = sample.copy()
    del pfeed.service_windows["service_window_id"]
    with pytest.raises(pa.errors.SchemaError):
        mg.check_service_windows(pfeed)

    pfeed = sample.copy()
    pfeed.service_windows = pd.concat(
        [pfeed.service_windows, pfeed.service_windows.iloc[:1]]
    )
    with pytest.raises(pa.errors.SchemaError):
        mg.check_service_windows(pfeed)

    for col in [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "start_time",
        "end_time",
    ]:
        pfeed = sample.copy()
        pfeed.service_windows.loc[pfeed.service_windows.index[0], col] = "-5" if col in ("start_time", "end_time") else -5
        with pytest.raises(pa.errors.SchemaError):
            mg.check_service_windows(pfeed)


def test_check_frequencies():
    assert mg.check_frequencies(sample).shape[0]

    pfeed = sample.copy()
    pfeed.frequencies = pd.DataFrame()
    with pytest.raises(pa.errors.SchemaError):
        mg.check_frequencies(pfeed)

    pfeed = sample.copy()
    del pfeed.frequencies["route_short_name"]
    with pytest.raises(pa.errors.SchemaError):
        mg.check_frequencies(pfeed)

    pfeed = sample.copy()
    pfeed.frequencies["route_long_name"] = ""
    with pytest.raises(pa.errors.SchemaError):
        mg.check_frequencies(pfeed)

    for col in ["direction", "frequency", "speed"]:
        pfeed = sample.copy()
        pfeed.frequencies[col] = "bingo"
        with pytest.raises(pa.errors.SchemaError):
            mg.check_frequencies(pfeed)


def test_check_stops():
    assert mg.check_stops(sample).shape[0]

    pfeed = sample.copy()
    pfeed.stops = None
    assert mg.check_stops(pfeed) is None

    pfeed = sample.copy()
    pfeed.stops = pd.DataFrame()
    with pytest.raises(pa.errors.SchemaError):
        mg.check_stops(pfeed)

    pfeed = sample.copy()
    pfeed.stops.loc[pfeed.stops.index[0], "stop_id"] = ""
    with pytest.raises(pa.errors.SchemaError):
        mg.check_stops(pfeed)


def test_check_speed_zones():
    assert mg.check_speed_zones(sample).shape[0]

    # Delete zone ID
    pfeed = sample.copy()
    del pfeed.speed_zones["speed_zone_id"]
    with pytest.raises(pa.errors.SchemaError):
        mg.check_speed_zones(pfeed)

    # Set bad route type
    pfeed = sample.copy()
    pfeed.speed_zones.loc[pfeed.speed_zones.index[0], "route_type"] = -2
    with pytest.raises(pa.errors.SchemaError):
        mg.check_speed_zones(pfeed)

    # Make speed zones IDs collide within a route type
    pfeed = sample.copy()
    pfeed.speed_zones["speed_zone_id"] = "a"
    with pytest.raises(ValueError):
        mg.check_speed_zones(pfeed)

    # Make speed zones overlap within a route type
    pfeed = sample.copy()
    pfeed.speed_zones["route_type"] = 3
    pfeed.speed_zones["speed_zone_id"] = [
        str(i) for i in range(pfeed.speed_zones.shape[0])
    ]
    with pytest.raises(ValueError):
        mg.check_speed_zones(pfeed)


def test_crosscheck_ids():
    pfeed = sample.copy()
    pfeed.frequencies["shape_id"] = "Hubba hubba"
    with pytest.raises(ValueError):
        mg.crosscheck_ids(
            "shape_id", pfeed.frequencies, "frequencies", pfeed.shapes, "shapes"
        )


def test_validate():
    assert isinstance(mg.validate(sample), mg.ProtoFeed)

    pfeed = sample.copy()
    pfeed.frequencies["service_window_id"] = "Hubba hubba"
    with pytest.raises(ValueError):
        mg.validate(pfeed)
