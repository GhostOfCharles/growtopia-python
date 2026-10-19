"""Collision regression cases independent of Pygame and saved worlds."""

import unittest

from src.physics import overlaps_solid, sweep_axis


class TileWorld:
    def __init__(self, solid_cells):
        self.solid_cells = set(solid_cells)

    def is_solid(self, column, row):
        return (column, row) in self.solid_cells


class SweptTileCollisionTests(unittest.TestCase):
    def test_large_rightward_motion_stops_at_first_wall(self):
        world = TileWorld({(10, 3), (15, 3)})
        self.assertEqual(sweep_axis(world, 0.25, 100.5, 28, 56,
                                    1000, 0, 32), (292.0, True))

    def test_large_leftward_motion_stops_at_first_wall(self):
        world = TileWorld({(10, 3), (5, 3)})
        self.assertEqual(sweep_axis(world, 500.25, 100.5, 28, 56,
                                    -1000, 0, 32), (352.0, True))

    def test_large_fall_stops_at_top_of_first_floor(self):
        world = TileWorld({(3, 40), (3, 41)})
        self.assertEqual(sweep_axis(world, 100.5, 100, 28, 56,
                                    3000, 1, 32), (1224.0, True))

    def test_large_rise_stops_at_bottom_of_first_ceiling(self):
        world = TileWorld({(3, 5), (3, 2)})
        self.assertEqual(sweep_axis(world, 100.5, 500, 28, 56,
                                    -800, 1, 32), (192.0, True))

    def test_motion_ending_at_wall_reports_contact_in_both_directions(self):
        world = TileWorld({(10, 3)})
        self.assertEqual(sweep_axis(world, 264, 100.5, 28, 56,
                                    28, 0, 32), (292.0, True))
        self.assertEqual(sweep_axis(world, 380, 100.5, 28, 56,
                                    -28, 0, 32), (352.0, True))

    def test_shared_perpendicular_edge_does_not_block_sliding(self):
        world = TileWorld({(10, 3)})
        self.assertEqual(sweep_axis(world, 292, 40, 28, 56,
                                    1000, 0, 32), (1292, False))

    def test_fractional_overlap_is_detected_without_integer_rounding(self):
        world = TileWorld({(10, 3)})
        self.assertFalse(overlaps_solid(world, 292, 100.5, 28, 56, 32))
        self.assertTrue(overlaps_solid(world, 292.25, 100.5, 28, 56, 32))

    def test_negative_tile_coordinates_work_in_both_directions(self):
        world = TileWorld({(-2, -2)})
        self.assertEqual(sweep_axis(world, -100, -40.5, 20, 10,
                                    100, 0, 32), (-84.0, True))
        self.assertEqual(sweep_axis(world, 0, -40.5, 20, 10,
                                    -100, 0, 32), (-32.0, True))

    def test_negative_exact_boundary_remains_half_open(self):
        world = TileWorld({(-2, -2)})
        self.assertFalse(overlaps_solid(world, -32, -64, 20, 32, 32))
        self.assertTrue(overlaps_solid(world, -32.25, -64, 20, 32, 32))

    def test_unobstructed_and_stationary_motion_preserve_position(self):
        world = TileWorld(set())
        self.assertEqual(sweep_axis(world, 12.25, -1.5, 28, 56,
                                    100.5, 0, 32), (112.75, False))
        self.assertEqual(sweep_axis(world, 12.25, -1.5, 28, 56,
                                    0, 1, 32), (-1.5, False))


if __name__ == "__main__":
    unittest.main()
