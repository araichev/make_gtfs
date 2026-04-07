"""
The command-line-interface module.
"""

import click

from . import protofeed as pf
from . import constants as cs
from . import main as m


@click.command(short_help="Create a GTFS feed from simpler files")
@click.argument("source_path", type=click.Path())
@click.argument("target_path", type=click.Path())
@click.option(
    "-bf",
    "--buffer",
    default=cs.BUFFER,
    type=float,
    show_default=True,
    help="Meters to buffer shapes to find stops",
)
@click.option(
    "-so",
    "--stop-offset",
    default=cs.STOP_OFFSET,
    type=float,
    show_default=True,
    help="Meters to offset stops from route shapes",
)
@click.option(
    "-ns",
    "--num-stops-per-shape",
    default=2,
    type=int,
    show_default=True,
    help="Number of stops to assign to each route shape",
)
@click.option(
    "-ss",
    "--stop-spacing",
    default=None,
    type=float,
    show_default=True,
    help="Spacing between stops; overrides num-stops-per-shape",
)
@click.option(
    "-nd",
    "--num-digits",
    default=6,
    type=int,
    show_default=True,
    help="Number of decimal places to round float values in the output " "GTFS feed",
)
def make_gtfs(
    source_path,
    target_path,
    buffer,
    stop_offset,
    num_stops_per_shape,
    stop_spacing,
    num_digits,
):
    """
    Create a GTFS feed from the files in the directory SOURCE_PATH.
    See the project README for a description of the required source
    files.
    Save the feed to the file or directory TARGET_PATH.
    If the target path ends in '.zip', then write the feed as a zip
    archive.
    Otherwise assume the path is a directory, and write the feed as a
    collection of CSV files to that directory, creating the directory
    if it does not exist.

    If a stops file is present, then search within ``buffer`` meters
    on the traffic side of trip paths for stops.
    Round all decimals to ndigits decimal places.
    All distances in the resulting GTFS feed will be in meters.
    """
    pfeed = pf.read_protofeed(source_path)
    feed = m.build_feed(
        pfeed,
        buffer=buffer,
        stop_offset=stop_offset,
        num_stops_per_shape=num_stops_per_shape,
        stop_spacing=stop_spacing,
    )
    feed.to_file(target_path, ndigits=num_digits)
