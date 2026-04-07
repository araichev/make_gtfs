import marimo

__generated_with = "0.22.4"
app = marimo.App()


@app.cell
def _():
    import sys
    import pathlib as pl
    import warnings

    import pandas as pd
    import numpy as np
    import gtfs_kit as gk
    import folium as fl

    sys.path.append('../')

    import make_gtfs as mg


    DATA_DIR = pl.Path('../data')

    # magic command not supported in marimo; please file an issue to add support
    # %load_ext autoreload
    # '%autoreload 2' command supported automatically in marimo

    warnings.filterwarnings(action='ignore')
    return DATA_DIR, fl, mg


@app.cell
def _(DATA_DIR, mg):
    path = DATA_DIR / 'auckland'
    pfeed = mg.read_protofeed(path)
    pfeed
    return (pfeed,)


@app.cell
def _(display, fl, pfeed):
    sz = pfeed.speed_zones
    display(sz)

    m = fl.Map(tiles="CartoDB Positron")
    fl.GeoJson(
        sz[lambda x: x.route_type == 3],
        tooltip=fl.GeoJsonTooltip(["speed_zone_id", "speed"])
    ).add_to(m)

    bounds = sz.total_bounds
    bounds = [(bounds[1], bounds[0]), (bounds[3], bounds[2])]  # rearrange for Folium
    m.fit_bounds(bounds)
    m
    return


@app.cell
def _(mg, pfeed):
    feed = mg.build_feed(pfeed)
    return (feed,)


@app.cell
def _(feed, pfeed):
    f = (
        feed.routes[['route_id', 'route_short_name']]
        .merge(pfeed.frequencies)
        .merge(pfeed.service_windows)
        .sort_values('route_id')
    )
    f
    return


@app.cell
def _(feed):
    # Map some trips
    tids = [feed.trips.trip_id.iat[0], feed.trips.trip_id.iat[-1]]
    feed.map_trips(tids, show_direction=True, show_stops=True)
    return


if __name__ == "__main__":
    app.run()
