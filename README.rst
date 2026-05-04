> [!IMPORTANT]
> **This repository has moved.**
> Because GitHub's performance has degraded significantly, this repository has moved to Forgejo. Active development continues at **https://git.disroot.org/mrcagney/make_gtfs**.
> This GitHub copy is archived and will not receive updates, issues, or pull requests.
> Please file issues and submit changes on Forgejo.

---

Make GTFS
***********
.. image:: https://github.com/mrcagney/gtfs_kit/actions/workflows/test.yml/badge.svg

A Python 3.10+ library to build GTFS feeds from basic route information.
Inspired by Conveyal's `geom2gtfs <https://github.com/conveyal/geom2gtfs>`_.
Makes naive timetables, but they are often good enough for preliminary work.

Contributors
============
- Alex Raichev (maintainer), 2014-09


Installation
=============
Here are instructions if you're using UV for Python dependency management.
To use as a library in your own project, install as a dependency via  ``uv add make_gtfs``.
To develop the ``make_gtfs`` repo, Git clone it, then run ``uv add make_gtfs``.


Usage
=====
Use as a library, or use from the command line by typing ``uv run make_gtfs --help`` and following the instructions.
If you're using Poetry or another dependency management program then change the UV command above accordingly.

Make GTFS uses the following files to build a GTFS feed.


- ``meta.csv`` (required). A CSV file containing network metadata.
  The CSV file contains the following columns.

  - ``agency_id`` (required): string; the ID of the transport
    agency
  - ``agency_name`` (required): string; the name of the transport
    agency
  - ``agency_url`` (required): string; a fully qualified URL for
    the transport agency
  - ``agency_timezone`` (required): string; timezone where the
    transit agency is located; timezone names never contain the
    space character but may contain an underscore; refer to
    `http://en.wikipedia.org/wiki/List_of_tz_zones <http://en.wikipedia.org/wiki/List_of_tz_zones>`_ for a list of valid values
  - ``start_date``, ``end_date`` (required): strings; the start
    and end dates for which all this network information is valid
    formated as YYYYMMDD strings

- ``shapes.geojson`` (required). A GeoJSON file containing route shapes.
  The file comprises one feature collection of LineString features, where each feature's properties contains at least the attribute ``shape_id``.
  Each LineString should represent the run of one representive trip of a route.
  In particular, the LineString should not traverse the same section of road many times, unless you want a trip to actually do that.

- ``service_windows.csv`` (required). A CSV file containing service window
  information.
  A *service window* is a time interval and a set of days of the
  week during which all routes have constant service frequency,
  e.g. Saturday and Sunday 07:00 to 09:00.
  The CSV file contains the following columns.

  - ``service_window_id`` (required): string; a unique identifier
    for a service window
  - ``start_time``, ``end_time`` (required): string; the start
    and end times of the service window in HH:MM:SS format where
    the hour is less than 24
  - ``monday``, ``tuesday``, ``wednesday``, ``thursday``,
    ``friday``, ``saturday``, ``sunday`` (required); 0
    or 1; indicates whether the service is active on the given day
    (1) or not (0)

- ``frequencies.csv`` (required). A CSV file containing route frequency information.
  The CSV file contains the following columns.

  - ``route_short_name`` (required): string; a unique short name
    for the route, e.g. '51X'
  - ``route_long_name`` (required): string; full name of the route
    that is more descriptive than ``route_short_name``
  - ``route_type`` (required): integer; the
    `GTFS type of the route <https://gtfs.org/documentation/schedule/reference/#routestxt>`_
  - ``service_window_id`` (required): string; a service window ID
    for the route taken from the file ``service_windows.csv``
  - ``direction`` (required): 0, 1, or 2; indicates
    whether the route travels in the direction of its shape (1), or in the reverse direction of its shape (0), or in both directions (2);
    in the latter case, trips will be created that travel in both
    directions along the route's shape, each direction operating at
    the given frequency;  otherwise, trips will be created that
    travel in only the given direction
  - ``frequency`` (required): integer; the frequency of the route
    during the service window in vehicles per hour.
  - ``shape_id`` (required): string; a shape ID that is listed in
    ``shapes.geojson`` and corresponds to the linestring of the
    (route, direction, service window) tuple
  - ``speed`` (optional): float; the average speed of the route in
    kilometers per hour

  Missing speed values will be filled with values from the library's dictionary
  `SPEED_BY_RTYPE`.

- ``speed_zones.geojson`` (optional). A GeoJSON file of Polygons representing
  speed zones for routes.
  The file consists of one feature collection of Polygon features
  (in WGS84 coordinates), each with the properties

  - ``speed_zone_id`` (required): string; a unique identifier of the zone polygon; can
    be re-used if the polygon is re-used
  - ``route_type`` (required): integer; a GTFS route type to which the zone applies
  - ``speed`` (required): positive float; the average speed in kilometers per hour
    of routes of that route type that travel within the zone; overrides route
    speeds in ``frequencies.csv`` within the zone.

- ``stops.csv`` (optional). A CSV file containing all the required
  and optional fields of ``stops.txt`` in
  `the GTFS <https://gtfs.org/documentation/schedule/reference/#stopstxt>`_.



Algorithm
=========
Basically,

- ``routes.txt`` is created from ``frequencies.csv``.
- ``agency.txt`` is created from ``meta.csv``.
- ``calendar.txt`` is created in a dumb way with exactly one all-week service that applies to all trips.
- ``shapes.txt`` is created from ``shapes.geojson``.
- ``stops.txt`` is created from ``stops.csv`` if given.
  Otherwise it is created by making a pair of stops for each shape, one stop at each endpoint of the shape and then deleting stops with duplicate coordinates. Note that this yields only one stop for each shape that is a loop.
- ``trips.txt`` and ``stop_times.txt`` are created by taking each route, service window, and direction, and running a set of trips starting on the hour and operating at the route's speed and frequency specified for that service window.
  If the route direction is 2, then two sets of trips in opposing directions will be created, each operating at the route's frequency.
  Assign stops to each trip as follows.
  Collect all stops in the built file ``stops.txt`` that are within a fixed distance of the traffic side (e.g. the right hand side for USA agency timezones and the left hand side for New Zealand agency timezones) of the trip shape.
  If the trip has no nearby stops, then do not make stop times for that trip.
- Once validated, write these files to disk by running command ``feed.to_file("gtfsfile.zip")``.


Examples
=========
See ``data/auckland`` for example files and play with the Marimo notebook at ``notebooks/examples.py``.


Documentation
===============
On Github pages `here <https://araichev.github.io/make_gtfs_docs>`_.


Notes
======
- This project's development status is Alpha.
  Alex uses this project for work and changes it breakingly when it suits his needs.
- This project uses semantic versioning.
- Thanks to `MRCagney <https://mrcagney.com>`_ for periodically funding this project.


Maintainer Notes
================
- After pushing to master, update the published docs via ``uv run make -C docs publish-docs-github``


Changes
========

4.2.0, 2026-04-07
-----------------
- Updated to reflect ``gtfs_kit`` API changes, thanks to user deton and `pull request 4 <https://github.com/araichev/make_gtfs/pull/4>`__:
  * Replaced ``timestr_to_seconds(x, inverse=True)`` with ``seconds_to_timestr(x)``.
  * Replace ``feed.write()`` to ``feed.to_file()``.
  * Removed ``feed.validate()``.
  * Added ``'agency_id'`` to fix ``KeyError`` in ``feed.drop_zombies()``.
  * Added Pycountry dependency that was removed from ``gtfs_kit``.
- Fixed ``ZeroDivisionError`` and ``ChainedAssignmentError`` with Pandas 3.
- Fixed ``FutureWarning with pandera>=0.24.0``.
- Fixed deprecated ``tool.uv.dev-dependencies`` warning.
- Fixed broken link in README.
- Updated Makefile for docs.

4.1.1, 2024-12-20
-----------------
- Added the missing Click dependency.
- Improved the usage installation and usage instructions.

4.1.0, 2024-12-19
-----------------
- Switched from Poetry to UV for project management.
- Bumped to Python 3.10+.
- Fixed some Pandas deprecation warnings.
- Fixed CLI access.

4.0.7, 2024-07-10
-----------------
- Updated dependencies.
- Upgraded Python to 3.9+.
- Tweaked some validators.
- Updated README.

4.0.6, 2023-03-29
-----------------
- Updated dependencies and pre-commit hooks.

4.0.5, 2022-11-08
-----------------
- Removed most type coercion in validation.
  Probably more instructive for the user that way.
- Fixed `Issue 11 <https://gitlab.com/mrcagney/make_gtfs/-/issues/11>`_.


4.0.4, 2022-10-19
-----------------
- Bugfix: Changed ``make_stop_points`` to correctly respect the ``offset`` parameter.


4.0.3, 2022-10-18
-----------------
- Bugfix: Created proper default speed zones when creating ProtoFeeds without given speed zones.
- Clarified README docs some.


4.0.2, 2022-10-17
-----------------
- Bugfix: Propogated ``stop_offset`` parameter in ``build_feed`` down the function chain.


4.0.1, 2022-10-11
-----------------
- Speeded up ``make_stop_points`` when ``offset`` is zero.


4.0.0, 2022-10-11
-----------------
- Offset built stops to the traffic side of each shape.
- Breaking change: renamed some function parameters.


3.1.0, 2022-10-06
-----------------
- Extended ``build_stops()`` and ``build_feed()`` to to build a specified number of equally spaced stops on each built shape or to build stops with a specified spacing on each built shape.
  More specifically, stops will be built on a shape and not also on its antiparallel clone, if that exists.
  That way we avoid building duplicate stops.


3.0.0, 2022-07-19
-----------------
- Removed the option to set default speeds by route type as overly complex.
- Added speed zones to override route speeds in user-specified geographic zones.


2.3.0, 2022-06-21
-----------------
- Refactored to use a dataclass and updated the docstrings, adding some type hints.
- Added the ability to specify default speeds by route type in ``meta.csv``.
- Simplified validation with Pandera schemas.
- Updated dependencies.


2.2.1, 2022-05-03
-----------------
- Updated dependencies and removed version caps.
- Replaced Travis CI with Github Actions.
- Re-added support for Python 3.8.


2.2.0, 2021-10-04
-----------------
- Upgraded to Python 3.9, dropped support for Python <3.9, and updated dependencies.


2.1.0, 2019-10-10
-----------------
- Switched to Python 3.6+ and Poetry.
- Bugfix: Change ``build_feed()`` to use GTFS Kit's ``drop_zombies()`` method to delete unnecessary stops etc.


2.0.0, 2018-05-28
------------------
- Extended to handle optional input stops
- Wrote ProtoFeed validation
- Modularized code more


1.0.0, 2018-05-22
------------------
- Restructured code and used GTFSTK, Click, Pytest, Pipenv


0.6.1, 2015-03-05
-------------------
- Fixed a bug in ``create_stop_times()`` that crashed when given a zero frequency.


0.6, 2015-01-29
-------------------
- Added direction field and renamed ``routes.csv`` to ``frequencies.csv``.
- Simplified the code some too.


0.5.1, 2015-01-28
-------------------
- Eliminated stops and trips for routes that have no linestrings


0.5, 2015-01-27
-----------------
- Changed from headways to frequencies and replaced ``config.json`` with CSV files


0.4, 2014-10-09
------------------
- Changed ``config.json`` spec to account for active days


0.3, 2014-09-29
-----------------
- Finished writing first set of tests and packaged



