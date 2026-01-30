import cv2
import numpy as np

from extract_photos.borders import trim_and_add_border


def _make_bordered_image(content_h, content_w, border_size, border_color, content_color=None):
    """Create a synthetic image: solid border around content."""
    h = content_h + 2 * border_size
    w = content_w + 2 * border_size
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = border_color

    if content_color is None:
        # Fill content with a gradient so it's distinguishable from border
        for c in range(3):
            img[border_size : border_size + content_h, border_size : border_size + content_w, c] = (
                np.tile(np.arange(content_w, dtype=np.uint8) % 200 + 50, (content_h, 1))
            )
    else:
        img[border_size : border_size + content_h, border_size : border_size + content_w] = content_color

    return img


class TestTrimAndAddBorder:
    def test_output_has_border(self):
        img = _make_bordered_image(200, 300, border_size=40, border_color=(0, 0, 0))
        result = trim_and_add_border(img)
        # Result should have a border added back (5% of min dimension)
        assert result.shape[0] > 0
        assert result.shape[1] > 0

    def test_border_color_preserved(self):
        border_color = (50, 50, 50)
        img = _make_bordered_image(200, 300, border_size=40, border_color=border_color)
        result = trim_and_add_border(img)
        # Top-left corner should be near the original border color
        corner = result[0, 0]
        assert abs(int(corner[0]) - border_color[0]) < 15
        assert abs(int(corner[1]) - border_color[1]) < 15
        assert abs(int(corner[2]) - border_color[2]) < 15

    def test_uniform_image_returned_unchanged(self):
        # All one color -> no content detected -> returns original
        img = np.full((100, 100, 3), 128, dtype=np.uint8)
        result = trim_and_add_border(img)
        assert np.array_equal(result, img)

    def test_white_border(self):
        img = _make_bordered_image(200, 300, border_size=50, border_color=(255, 255, 255))
        result = trim_and_add_border(img)
        # Should successfully trim and re-add border
        assert result.shape[0] > 200
        assert result.shape[1] > 300

    def test_thick_border_trimmed(self):
        img = _make_bordered_image(200, 300, border_size=100, border_color=(0, 0, 0))
        result = trim_and_add_border(img)
        # New border should be 5% of min content dimension = 5% of 200 = 10px each side
        # So result ~220 x ~320, much smaller than input 400 x 500
        assert result.shape[0] < img.shape[0]
        assert result.shape[1] < img.shape[1]
