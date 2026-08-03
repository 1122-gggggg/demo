import unittest

import numpy as np

from 中央展示介面 import camera_frustum_world_points, should_redraw_map
from 展示核心 import (
    build_display_indices,
    camera_center,
    colorize_semantic_classes,
    nearest_projected_point,
    pose_index_for_time,
    progressive_colors,
)


class DemoCoreTests(unittest.TestCase):
    def test_pose_time_mapping_clamps(self):
        self.assertEqual(pose_index_for_time(-1.0, sample_fps=3.0, pose_count=339), 0)
        self.assertEqual(pose_index_for_time(1.0, sample_fps=3.0, pose_count=339), 3)
        self.assertEqual(pose_index_for_time(999.0, sample_fps=3.0, pose_count=339), 338)

    def test_progressive_semantics_are_retained(self):
        original = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]], np.uint8)
        semantic = np.array([[10, 20, 30], [40, 50, 60], [70, 80, 90]], np.uint8)
        reveal = np.array([0, 2, -1], np.int16)
        np.testing.assert_array_equal(
            progressive_colors(original, semantic, reveal, 0),
            np.array([[10, 20, 30], [4, 5, 6], [7, 8, 9]], np.uint8),
        )
        np.testing.assert_array_equal(
            progressive_colors(original, semantic, reveal, 2),
            np.array([[10, 20, 30], [40, 50, 60], [7, 8, 9]], np.uint8),
        )

    def test_semantic_classes_use_display_palette(self):
        original = np.array([[10, 20, 30], [40, 50, 60], [70, 80, 90]], np.uint8)
        labels = np.array([-1, 1, 4], np.int16)
        np.testing.assert_array_equal(
            colorize_semantic_classes(original, labels),
            np.array([[10, 20, 30], [0, 255, 0], [0, 128, 255]], np.uint8),
        )

    def test_camera_center_and_frustum(self):
        R = np.eye(3)
        t = np.array([-1.0, -2.0, -3.0])
        center = camera_center(R, t)
        np.testing.assert_allclose(center, [1.0, 2.0, 3.0])
        frustum = camera_frustum_world_points(center, R, length=2.0)
        self.assertEqual(frustum.shape, (6, 3))
        np.testing.assert_allclose(frustum[0], center)
        np.testing.assert_allclose(frustum[1], center + [0.0, 0.0, 2.0])

    def test_display_indices_are_deterministic_and_bounded(self):
        first = build_display_indices(2_799_538, 250_000)
        second = build_display_indices(2_799_538, 250_000)
        np.testing.assert_array_equal(first, second)
        self.assertLessEqual(len(first), 250_000)
        self.assertEqual(first[0], 0)

    def test_double_click_selects_nearest_visible_map_point(self):
        projected = np.array([[10.0, 10.0], [30.0, 35.0], [100.0, 100.0]])
        self.assertEqual(nearest_projected_point(projected, (32.0, 34.0)), 1)
        self.assertIsNone(nearest_projected_point(projected, (200.0, 200.0)))

    def test_final_odd_frame_is_always_redrawn(self):
        self.assertTrue(should_redraw_map(2708, 2708, 2710))
        self.assertTrue(should_redraw_map(2709, 2709, 2710))
        self.assertFalse(should_redraw_map(2707, 2707, 2710))


if __name__ == "__main__":
    unittest.main()
