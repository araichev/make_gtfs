from __future__ import annotations

import pathlib as pl
from dataclasses import dataclass

import geopandas as gpd
import pandas as pd
import numpy as np
import shapely.geometry as sg

from . import validators as vd
from . import constants as cs


#: Default average speeds by route type in kilometers per hour
SPEED_BY_RTYPE = {
    0: 11,  # tram
    1: 30,  # subway
    2: 45,  # rail
    3: 22,  # bus
    4: 22,  # ferry
    5: 13,  # cable tram
    6: 20,  # aerial lift
    7: 18,  # funicular
    11: 22,  # trolleybus
    12: 65,  # monorail
}


@dataclass
class ProtoFeed:
    """
    A ProtoFeed instance holds the source data from which to build a GTFS feed.
    The most common way to build is from files via the function :func:`read_protofeed`.
    """

    meta: pd.DataFrame
    service_windows: pd.DataFrame
    shapes: gpd.GeoDataFrame
    frequencies: pd.DataFrame
    stops: pd.DataFrame | None = None
    speed_zones: gpd.GeoDataFrame | None = None

    @staticmethod
    def clean_speed_zones(
        speed_zones: gpd.GeoDataFrame,
        service_area: gpd.GeoDataFrame,
        default_speed_zone_id: str = "default",
        default_speed: float = np.inf,
    ) -> gpd.GeoDataFrame:
        """
        Clip the speed zones to the service area.
        The zone ID of the service area outside of the speed zones will be set to
        ``default_speed_zone_id`` and the speed there will be set to ``default_speed``.
        Return the resulting service area of (Multi)Polygons, now partitioned into speed
        zones.
        The result is a GeoDataFrame with the columns 'speed_zone_id', 'speed',
        'geometry'.
        """
        if service_area.geom_equals(speed_zones.union_all()).all():
            # Speed zones already partition the study area, so good
            result = speed_zones
        else:
            # Work to be done
            result = (
                speed_zones
                # Clip to service area
                .clip(service_area)
                # Union chunks
                .overlay(service_area, how="union")
                .assign(
                    route_type=lambda x: x["route_type"].ffill().astype(int),
                    speed_zone_id=lambda x: x["speed_zone_id"].fillna(
                        default_speed_zone_id
                    ),
                    speed=lambda x: x["speed"].fillna(default_speed),
                )
                .filter(["route_type", "speed_zone_id", "speed", "geometry"])
                .sort_values("speed_zone_id", ignore_index=True)
            )
        return result

    def __post_init__(self):
        # Fill missing route speeds with speeds in SPEED_BY_RTYPE
        f = self.frequencies.copy()
        if "speed" not in f.columns:
            f["speed"] = np.nan

        f["speed"] = f.speed.fillna(f.route_type.map(SPEED_BY_RTYPE))
        self.frequencies = f

        # Build ``shapes_extra``, a dictionary of the form
        # <shape ID> -> <trip directions using the shape (0, 1, or 2)>
        def my_agg(group):
            d = {}
            dirs = group["direction"].unique()
            if len(dirs) > 1 or 2 in dirs:
                d["direction"] = 2
            else:
                d["direction"] = dirs[0]
            return pd.Series(d)

        self.shapes_extra = dict(
            self.frequencies.groupby("shape_id")
            .apply(my_agg, include_groups=False)
            .reset_index()
            .values
        )

        # Build service area as the bounding box of the shapes buffered by about 1 km
        service_area = gpd.GeoDataFrame(
            geometry=[sg.box(*self.shapes.total_bounds).buffer(0.01)], crs=cs.WGS84
        )

        # Clean speed zones
        if self.speed_zones is None:
            # Create one speed zone per route type present in this ProtoFeed.
            # For each zone, use the geometry of the service area and assign
            # it infinite speed so it won't override route speeds present in
            # ``self.frequencies``.
            frames = []
            for route_type in self.frequencies["route_type"].unique():
                g = service_area.assign(
                    route_type=route_type,
                    speed_zone_id=f"default{cs.SEP}{route_type}",
                    speed=np.inf,
                )
                frames.append(g)
            self.speed_zones = pd.concat(frames, ignore_index=True)
        else:

            def my_apply(group):
                group["route_type"] = group.name
                return self.clean_speed_zones(
                    group,
                    service_area,
                    default_speed_zone_id=f"default{cs.SEP}{group.name}",
                )

            self.speed_zones = (
                self.speed_zones.groupby("route_type", group_keys=False)
                .apply(my_apply, include_groups=False)
                .filter(["route_type", "speed_zone_id", "speed", "geometry"])
            )

        self.utm_crs = self.shapes.estimate_utm_crs()

    def __eq__(self, other) -> bool:
        for k in self.__dataclass_fields__:
            v1 = getattr(self, k)
            v2 = getattr(other, k)
            if isinstance(v1, (pd.DataFrame, gpd.GeoDataFrame)):
                if not v1.equals(v2):
                    return False
            elif not isinstance(v2, type(v1)) or v1 != v2:
                return False
        return True

    def copy(self) -> ProtoFeed:
        """
        Return a copy of this ProtoFeed, that is, a feed with all the
        same attributes.
        """
        d = {}
        for k in self.__dataclass_fields__:
            v = getattr(self, k)
            if isinstance(v, (pd.DataFrame, gpd.GeoDataFrame)):
                v = v.copy()
            d[k] = v

        return ProtoFeed(**d)

    def route_types(self) -> list[int]:
        return self.frequencies.route_type.unique().tolist()


def read_protofeed(path: str | pl.Path) -> ProtoFeed:
    """
    Read the data files at the given directory path
    (string or Path object) and build a ProtoFeed from them.
    Validate the resulting ProtoFeed.
    If invalid, raise a ``ValueError`` specifying the errors.
    Otherwise, return the resulting ProtoFeed.

    The data files needed to build a ProtoFeed are

    - ``meta.csv`` (required). A CSV file containing network metadata.
      The CSV file contains the columns

      - ``agency_id`` (required): string; the ID of the transport
        agency
      - ``agency_name`` (required): string; the name of the transport
        agency
      - ``agency_url`` (required): string; a fully qualified URL for
        the transport agency
      - ``agency_timezone`` (required): string; timezone where the
        transit agency is located; timezone names never contain the
        space character but may contain an underscore; refer to
        http://en.wikipedia.org/wiki/List_of_tz_zones for a list of valid values
      - ``start_date``, ``end_date`` (required): strings; the start
        and end dates for which all this network information is valid,
        formated as YYYYMMDD strings

    - ``service_windows.csv`` (required). A CSV file containing service window
      information.
      A *service window* is a time interval and a set of days of the
      week during which all routes have constant service frequency,
      e.g. Saturday and Sunday 07:00 to 09:00.
      The CSV file contains the columns

      - ``service_window_id`` (required): string; a unique identifier
        for a service window
      - ``start_time``, ``end_time`` (required): strings; the start
        and end times of the service window in HH:MM:SS format where
        the hour is less than 24
      - ``monday``, ``tuesday``, ``wednesday``, ``thursday``,
        ``friday``, ``saturday``, ``sunday`` (required): integer 0
        or 1; indicates whether the service is active on the given day
        (1) or not (0)

    - ``shapes.geojson`` (required). A GeoJSON file representing shapes for all
      (route, direction 0 or 1, service window) combinations.
      The file comprises one feature collection of LineString
      features (in WGS84 coordinates), where each feature has the property

      - ``shape_id`` (required): a unique identifier of the shape

      Each LineString should represent the run of one representive trip of a route.
      In particular, the LineString should not traverse the same section of
      road many times, unless you want a trip to actually do that.


    - ``frequencies.csv`` (required). A CSV file containing route frequency
      information. The CSV file contains the columns

      - ``route_short_name`` (required): string; a unique short name
        for the route, e.g. '51X'
      - ``route_long_name`` (required): string; full name of the route
        that is more descriptive than ``route_short_name``
      - ``route_type`` (required): integer; the GTFS type of the route type;
         https://developers.google.com/transit/gtfs/reference/#routestxt
      - ``service_window_id`` (required): string; a service window ID
        for the route taken from the file ``service_windows.csv``
      - ``direction`` (required): integer 0, 1, or 2;
        indicates whether the route travels in the direction of its shape (1),
        or in the reverse direction of its shape (0), or in both directions (2);
        in the latter case, trips will be created that travel in both
        directions along the route's shape, each direction operating at
        the given frequency;
        otherwise, trips will be created that travel in only the given direction
      - ``frequency`` (required): integer; the frequency of the route
        during the service window in vehicles per hour.
      - ``shape_id`` (required): string; a shape ID that is listed in
        ``shapes.geojson`` and corresponds to the linestring of the
        (route, direction 0 or 1, service window) tuple.
      - ``speed`` (optional): float; the average speed of the route in kilometers
        per hour

      Missing speed values will be filled with values from the dictionary
      :const:`SPEED_BY_RTYPE`.

    - ``stops.csv`` (optional). A CSV file containing all the required
      and optional fields of ``stops.txt`` in
      `the GTFS <https://developers.google.com/transit/gtfs/reference/#stopstxt>`_

    - ``speed_zones.geojson`` (optional). A GeoJSON file of Polygons representing
      speed zones for routes.
      The file consists of one feature collection of Polygon features
      (in WGS84 coordinates), each with the properties

      - ``speed_zone_id`` (required): string; a unique identifier of the zone polygon;
        can be re-used if the polygon is re-used
      - ``route_type`` (required): integer; a GTFS route type to which the zone applies
      - ``speed`` (required): positive float; the average speed in kilometers per hour
        of routes of that route type that travel within the zone; overrides route
        speeds in ``frequencies.csv`` within the zone.

    """
    path = pl.Path(path)
    d = {}
    d["meta"] = pd.read_csv(
        path / "meta.csv", dtype={"start_date": str, "end_date": str}
    )
    d["service_windows"] = pd.read_csv(path / "service_windows.csv")
    d["shapes"] = gpd.read_file(path / "shapes.geojson")
    d["frequencies"] = pd.read_csv(
        path / "frequencies.csv",
        dtype={
            "route_short_name": str,
            "service_window_id": str,
            "shape_id": str,
            "direction": int,
            "frequency": int,
        },
    )
    d["stops"] = None
    if (path / "stops.csv").exists():
        d["stops"] = pd.read_csv(
            path / "stops.csv",
            dtype={
                "stop_id": str,
                "stop_code": str,
                "zone_id": str,
                "location_type": int,
                "parent_station": str,
                "stop_timezone": str,
                "wheelchair_boarding": int,
            },
        )
    d["speed_zones"] = None
    if (path / "speed_zones.geojson").exists():
        g = gpd.read_file(path / "speed_zones.geojson")
        if "route_type" in g.columns:
            g["route_type"] = g["route_type"].astype(int)
        if "speed_zone_id" in g.columns:
            g["speed_zone_id"] = g["speed_zone_id"].astype(str)
        d["speed_zones"] = g

    pfeed = ProtoFeed(**d)

    # Validate
    vd.validate(pfeed)
    # if "error" in v.type.values:
    #     raise ValueError("Invalid ProtoFeed files:\n\n" + v.to_string(justify="left"))

    return pfeed
