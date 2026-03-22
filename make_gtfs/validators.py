"""
ProtoFeed validators.
"""

import re
import pytz

import pandas as pd
import pandera as pa
import geopandas as gpd

from . import protofeed as pf


URL_PATTERN = re.compile(
    r"^(?:http)s?://(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?::\d+)?(?:/?|[/?]\S+)$",
    re.IGNORECASE | re.UNICODE,
)
DATE_PATTERN = r"\d\d\d\d\d\d\d\d"
TIME_PATTERN = r"([01][0-9]|2[0-3]):([0-5][0-9]):([0-5][0-9])"
TIMEZONES = set(pytz.all_timezones)
NONBLANK_PATTERN = r"(?!\s*$).+"

# ProtoFeed table schemas
SCHEMA_META = pa.DataFrameSchema(
    {
        "agency_id": pa.Column(str, pa.Check.str_matches(NONBLANK_PATTERN), unique=True),
        "agency_name": pa.Column(str, pa.Check.str_matches(NONBLANK_PATTERN)),
        "agency_url": pa.Column(str, pa.Check.str_matches(URL_PATTERN)),
        "agency_timezone": pa.Column(str, pa.Check.isin(TIMEZONES)),
        "start_date": pa.Column(
            str,
            checks=[
                pa.Check.str_matches(DATE_PATTERN),
                pa.Check(
                    lambda x: pd.to_datetime(x)
                    > pd.to_datetime("1900-01-01", yearfirst=True)
                ),
            ],
        ),
        "end_date": pa.Column(
            str,
            checks=[
                pa.Check.str_matches(DATE_PATTERN),
                pa.Check(
                    lambda x: pd.to_datetime(x)
                    > pd.to_datetime("1900-01-01", yearfirst=True)
                ),
            ],
        ),
    },
    checks=pa.Check(lambda x: x.shape[0] == 1),  # Should have exactly 1 row
    index=pa.Index(int),
    strict="filter",  # Drop columns not specified above
)
SCHEMA_SHAPES = pa.DataFrameSchema(
    {
        "shape_id": pa.Column(
            str,
            pa.Check.str_matches(NONBLANK_PATTERN),
            unique=True,
        ),
        "geometry": pa.Column(
            checks=[
                pa.Check(lambda x: x.geom_type == "LineString"),
                pa.Check(lambda x: x.is_valid),
                pa.Check(lambda x: ~x.is_empty),
            ]
        ),
    },
    checks=pa.Check(lambda x: x.shape[0] >= 1),  # Should have at least 1 row
    index=pa.Index(int),
    strict="filter",  # Drop columns not specified above
)
SCHEMA_SERVICE_WINDOWS = pa.DataFrameSchema(
    {
        "service_window_id": pa.Column(
            str,
            pa.Check.str_matches(NONBLANK_PATTERN),
            unique=True,
        ),
        "start_time": pa.Column(str, pa.Check.str_matches(TIME_PATTERN)),
        "end_time": pa.Column(str, pa.Check.str_matches(TIME_PATTERN)),
        "monday": pa.Column(int, pa.Check.isin(range(2))),
        "tuesday": pa.Column(int, pa.Check.isin(range(2))),
        "wednesday": pa.Column(int, pa.Check.isin(range(2))),
        "thursday": pa.Column(int, pa.Check.isin(range(2))),
        "friday": pa.Column(int, pa.Check.isin(range(2))),
        "saturday": pa.Column(int, pa.Check.isin(range(2))),
        "sunday": pa.Column(int, pa.Check.isin(range(2))),
    },
    checks=pa.Check(lambda x: x.shape[0] >= 1),  # Should have at least 1 row
    index=pa.Index(int),
    strict="filter",  # Drop columns not specified above
)
SCHEMA_FREQUENCIES = pa.DataFrameSchema(
    {
        "route_short_name": pa.Column(str, pa.Check.str_matches(NONBLANK_PATTERN)),
        "route_long_name": pa.Column(str, pa.Check.str_matches(NONBLANK_PATTERN)),
        "route_type": pa.Column(int, pa.Check.isin(list(range(8)) + [11, 12])),
        "service_window_id": pa.Column(str, pa.Check.str_matches(NONBLANK_PATTERN)),
        "shape_id": pa.Column(str, pa.Check.str_matches(NONBLANK_PATTERN)),
        "direction": pa.Column(int, pa.Check.isin(range(3))),
        "frequency": pa.Column(int, pa.Check.gt(0)),
        "speed": pa.Column(float, pa.Check.gt(0), required=False),
    },
    checks=pa.Check(lambda x: x.shape[0] >= 1),  # Should have at least 1 row
    index=pa.Index(int),
    strict="filter",  # Drop columns not specified above
)
SCHEMA_STOPS = pa.DataFrameSchema(
    {
        "stop_id": pa.Column(str, pa.Check.str_matches(NONBLANK_PATTERN), unique=True),
        "stop_code": pa.Column(str, nullable=True, required=False, coerce=True),
        "stop_name": pa.Column(str, pa.Check.str_matches(NONBLANK_PATTERN)),
        "stop_desc": pa.Column(str, nullable=True, required=False, coerce=True),
        "stop_lat": pa.Column(float),
        "stop_lon": pa.Column(float),
        "zone_id": pa.Column(str, nullable=True, required=False, coerce=True),
        "stop_url": pa.Column(
            str,
            pa.Check.str_matches(URL_PATTERN),
            nullable=True,
            required=False,
            coerce=True,
        ),
        "location_type": pa.Column(
            int, pa.Check.isin(range(5)), nullable=True, required=False
        ),
        "parent_station": pa.Column(str, nullable=True, required=False),
        "stop_timezone": pa.Column(
            str, pa.Check.isin(TIMEZONES), nullable=True, required=False
        ),
        "wheelchair_boarding": pa.Column(
            int, pa.Check.isin(range(3)), nullable=True, required=False
        ),
    },
    checks=pa.Check(lambda x: x.shape[0] >= 1),  # Should have at least 1 row
    index=pa.Index(int),
    strict="filter",  # Drop columns not specified above
)
SCHEMA_SPEED_ZONES = pa.DataFrameSchema(
    {
        "speed_zone_id": pa.Column(
            str,
            pa.Check.str_matches(NONBLANK_PATTERN),
            unique=False,
        ),
        "route_type": pa.Column(int, pa.Check.isin(list(range(8)) + [11, 12])),
        "speed": pa.Column(float, pa.Check.gt(0)),
        "geometry": pa.Column(
            checks=[
                pa.Check(lambda x: x.geom_type == "Polygon"),
                pa.Check(lambda x: x.is_valid),
                pa.Check(lambda x: ~x.is_empty),
            ]
        ),
    },
    checks=pa.Check(lambda x: x.shape[0] >= 1),  # Should have at least 1 row
    index=pa.Index(int),
    strict="filter",  # Drop columns not specified above
)


def check_meta(pfeed: pf.ProtoFeed) -> pd.DataFrame:
    """
    Return `pfeed.meta` if it is valid.
    Otherwise, raise a ValueError or a Pandera SchemaError.
    """
    if not isinstance(pfeed.meta, pd.DataFrame):
        raise ValueError("Meta must be a DataFrame")

    return SCHEMA_META.validate(pfeed.meta)


def check_shapes(pfeed: pf.ProtoFeed) -> pd.DataFrame:
    """
    Return `pfeed.shapes` if it is valid.
    Otherwise, raise a ValueError or a Pandera SchemaError.
    """
    if not isinstance(pfeed.shapes, gpd.GeoDataFrame):
        raise ValueError("Shapes must be a GeoDataFrame")

    return SCHEMA_SHAPES.validate(pfeed.shapes)


def check_service_windows(pfeed: pf.ProtoFeed) -> pd.DataFrame:
    """
    Return `pfeed.service_windows` if it is valid.
    Otherwise, raise a Pandera SchemaError.
    """
    if not isinstance(pfeed.service_windows, pd.DataFrame):
        raise ValueError("Service windows must be a DataFrame")

    return SCHEMA_SERVICE_WINDOWS.validate(pfeed.service_windows)


def check_frequencies(pfeed: pf.ProtoFeed) -> pd.DataFrame:
    """
    Return `pfeed.frequencies` if it is valid.
    Otherwise, raise a Pandera SchemaError.
    """
    if not isinstance(pfeed.frequencies, pd.DataFrame):
        raise ValueError("Frequencies must be a DataFrame")

    return SCHEMA_FREQUENCIES.validate(pfeed.frequencies)


def check_stops(pfeed: pf.ProtoFeed) -> pd.DataFrame:
    """
    Return `pfeed.stops` if it is valid.
    Otherwise, raise a Pandera SchemaError.
    """
    if pfeed.stops is None:
        return pfeed.stops
    else:
        return SCHEMA_STOPS.validate(pfeed.stops)


def check_speed_zones(pfeed: pf.ProtoFeed) -> pd.DataFrame:
    """
    Return `pfeed.shapes` if it is valid.
    Otherwise, raise a ValueError or a Pandera SchemaError.
    """
    f = pfeed.speed_zones

    result = SCHEMA_SPEED_ZONES.validate(f)

    if not isinstance(f, gpd.GeoDataFrame):
        raise ValueError("Speed zones must be a GeoDataFrame")

    # Zone ID must be unique within route type
    for route_type, group in f.groupby("route_type"):
        if group.speed_zone_id.nunique() != group.shape[0]:
            raise ValueError(
                f"Zone IDs must be unique within each route type; "
                f"failure with route type {route_type}"
            )

    # Zones must be pairwise disjoint within route type
    for route_type, group in f.groupby("route_type"):
        if group.geometry.nunique() != group.shape[0]:
            raise ValueError(
                f"Zones must not overlap each other within each route type; "
                f"failure with route type {route_type}"
            )
        for speed_zone_id, g in group.groupby("speed_zone_id"):
            other = group.loc[lambda x: x.speed_zone_id != speed_zone_id]
            if other.overlaps(g.geometry.iat[0]).any():
                raise ValueError(
                    f"Zones must not overlap each other within each route type; "
                    f"failure with route type {route_type}"
                )

    return result


def crosscheck_ids(
    id_col: str,
    src_table: pd.DataFrame,
    src_table_name: str,
    tgt_table: pd.DataFrame,
    tgt_table_name: str,
) -> None:
    """
    Check that the set of `id_col` values in the given source table are a subset
    of those in the target table.
    Raise a ValueError if not; otherwise do nothing.
    """
    if not (D := set(src_table[id_col].unique())) <= set(tgt_table[id_col].unique()):
        raise ValueError(
            f"Found {id_col} values in {src_table_name} "
            f"that are not in {tgt_table_name}: {D}"
        )


def validate(pfeed):
    """
    Return the given ProtoFeed if it is valid.
    Otherwise, raise a ValueError after encountering the first error.
    """
    # Run individual table validators
    checkers = [
        "check_meta",
        "check_shapes",
        "check_service_windows",
        "check_frequencies",
        "check_stops",
    ]
    for checker in checkers:
        try:
            globals()[checker](pfeed)
        except pa.errors.SchemaError as e:
            raise ValueError(e)

    # Cross-check IDs
    crosscheck_ids("shape_id", pfeed.frequencies, "frequencies", pfeed.shapes, "shapes")
    crosscheck_ids(
        "service_window_id",
        pfeed.frequencies,
        "frequencies",
        pfeed.service_windows,
        "service_windows",
    )

    return pfeed
