import unittest
import zipfile
from copy import deepcopy

import pandas as pd 
from pandas.util.testing import assert_frame_equal, assert_series_equal
from shapely.geometry import Point, LineString, mapping

from make_gtfs.make_gtfs import *

# Load test feeds
akl = Feed('data/auckland_snippet/')

class TestFeed(unittest.TestCase):
    def test_timestr_to_seconds(self):
        timestr1 = '01:01:01'
        seconds1 = 3600 + 60 + 1
        timestr2 = '25:01:01'
        seconds2 = 25*3600 + 60 + 1
        self.assertEqual(timestr_to_seconds(timestr1), seconds1)
        self.assertEqual(timestr_to_seconds(seconds1, inverse=True), timestr1)
        self.assertEqual(timestr_to_seconds(seconds2, inverse=True), timestr2)
        self.assertEqual(timestr_to_seconds(timestr2, mod24=True), seconds1)
        self.assertEqual(
          timestr_to_seconds(seconds2, mod24=True, inverse=True), timestr1)
        # Test error handling
        self.assertIsNone(timestr_to_seconds(seconds1))
        self.assertIsNone(timestr_to_seconds(timestr1, inverse=True))
        
    def test_get_duration(self):
        ts1 = '01:01:01'
        ts2 = '01:05:01'
        get = get_duration(ts1, ts2, units='min')
        expect = 4
        self.assertEqual(get, expect)

    def test_init(self):
        feed = deepcopy(akl)
        self.assertIsInstance(feed.raw_routes, pd.core.frame.DataFrame)
        self.assertIsInstance(feed.config, dict)
        self.assertIsInstance(feed.raw_shapes, dict)

    def test_create_routes(self):
        feed = deepcopy(akl)
        feed.create_routes()      
        routes = feed.routes 
        # Should be a data frame
        self.assertIsInstance(routes, pd.core.frame.DataFrame)
        # Should have correct shape
        expect_nrows = feed.raw_routes.shape[0]
        expect_ncols = 4
        self.assertEqual(routes.shape, (expect_nrows, expect_ncols))

    def test_create_linestring_by_route(self):
        feed = deepcopy(akl)
        linestring_by_route = feed.get_linestring_by_route(use_utm=False)
        # Should be a dictionary
        self.assertIsInstance(linestring_by_route, dict)
        # The first element should be a Shapely linestring
        self.assertIsInstance(list(linestring_by_route.values())[0], 
          LineString)
        # Should contain one shape for each route
        self.assertEqual(len(linestring_by_route), feed.raw_routes.shape[0])

    def test_create_shapes(self):
        feed = deepcopy(akl)
        feed.create_shapes()
        shapes = feed.shapes
        # Should be a data frame
        self.assertIsInstance(shapes, pd.core.frame.DataFrame)
        # Should have correct shape
        expect_nshapes = feed.raw_routes.shape[0]
        expect_ncols = 4
        self.assertEqual(shapes.groupby('shape_id').ngroups, expect_nshapes)
        self.assertEqual(shapes.shape[1], expect_ncols)

    def test_create_stops(self):
        feed = deepcopy(akl)
        feed.create_stops()
        stops = feed.stops
        # Should be a data frame
        self.assertIsInstance(stops, pd.core.frame.DataFrame)
        # Should have correct shape
        expect_nrows = 2*feed.raw_routes.shape[0]
        expect_ncols = 4
        self.assertEqual(stops.shape, (expect_nrows, expect_ncols))

    def test_create_trips(self):
        feed = deepcopy(akl)
        feed.create_trips()
        trips = feed.trips
        # Should be a data frame
        self.assertIsInstance(trips, pd.core.frame.DataFrame)
        # Should have correct shape
        expect_nrows = 0
        for index, row in feed.raw_routes.iterrows():
            # Number of trips for this route is the sum over each service
            # window of twice the window duration divided by the headway. 
            # Twice because have a trip running in both directions 
            # simulateously
            expect_nrows += 2*sum(
              sum(get_duration(*s, units='min') 
              for s in window['subwindows'])//\
              row[window['name'] + '_headway'] 
              for window in feed.service_windows)
        expect_ncols = 5
        self.assertEqual(trips.shape, (expect_nrows, expect_ncols))

    def test_create_stop_times(self):
        feed = deepcopy(akl)
        feed.create_stop_times()
        stop_times = feed.stop_times
        # Should be a data frame
        self.assertIsInstance(stop_times, pd.core.frame.DataFrame)
        # Should have correct shape
        expect_nrows = 0
        for index, row in feed.raw_routes.iterrows():
            # Number of trips for this route is the sum over each service
            # window of twice the window duration divided by the headway. 
            # Twice because have a trip running in both directions 
            # simulateously.
            # Number of stop times is twice the number of trips,
            # because each trip has two stops.
            expect_nrows += 4*sum(
              sum(get_duration(*s, units='min') 
              for s in window['subwindows'])//\
              row[window['name'] + '_headway'] 
              for window in feed.service_windows)
        expect_ncols = 5
        self.assertEqual(stop_times.shape, (expect_nrows, expect_ncols))

    def test_create_all(self):
        feed = deepcopy(akl)
        feed.create_all()
        names = ['agency', 'calendar', 'routes', 'stops', 'trips',
          'stop_times', 'shapes']
        for name in names:
            self.assertTrue(hasattr(feed, name))

    def test_export(self):
        feed = deepcopy(akl)
        
        # Should raise an error if try to export before create files
        with self.assertRaises(AssertionError):
            feed.export()
        
        # Should create the necessary files. 
        # Already know they're CSV because rely on Pandas for CSV export.
        feed.create_all()
        odir = 'tests/'
        feed.export(output_dir=odir)
        names = ['agency', 'calendar', 'routes', 'stops', 'trips',
          'stop_times', 'shapes']
        for name in names:
            path = os.path.join(odir, name + '.txt')
            self.assertTrue(os.path.exists(path))
            print('hello', path)
            os.remove(path) # Clean up

        # # Should create a zip archive this time
        feed.export(output_dir=odir, as_zip=True)
        zip_path = os.path.join(odir, 'gtfs.zip')
        self.assertTrue(zipfile.is_zipfile(zip_path))
    
        # Zip archive should contain all the necessary files
        expect_nameset = set(name + '.txt' for name in names)
        get_nameset = set(zipfile.ZipFile(zip_path, 'r').namelist())
        self.assertEqual(get_nameset, expect_nameset)

        os.remove(zip_path) # Remove zip file


if __name__ == '__main__':
    unittest.main()