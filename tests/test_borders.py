import cv2
import numpy as np

from extract_photos.borders import trim_and_add_border, _find_text_gap_from_edge, _detect_text_padding


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
        # Result should have content + 5px border on each side
        assert result.shape[0] == 200 + 2 * 5
        assert result.shape[1] == 300 + 2 * 5

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
        # Should successfully trim and re-add 5px border
        assert result.shape[0] == 200 + 2 * 5
        assert result.shape[1] == 300 + 2 * 5

    def test_thick_border_trimmed(self):
        img = _make_bordered_image(200, 300, border_size=100, border_color=(0, 0, 0))
        result = trim_and_add_border(img)
        # Content 200x300 + 5px border each side = 210x310, much smaller than input 400x500
        assert result.shape[0] == 210
        assert result.shape[1] == 310
        assert result.shape[0] < img.shape[0]
        assert result.shape[1] < img.shape[1]

    def test_custom_border_px(self):
        img = _make_bordered_image(200, 300, border_size=40, border_color=(0, 0, 0))
        result = trim_and_add_border(img, border_px=20)
        assert result.shape[0] == 200 + 2 * 20
        assert result.shape[1] == 300 + 2 * 20

    def test_zero_border_px(self):
        img = _make_bordered_image(200, 300, border_size=40, border_color=(0, 0, 0))
        result = trim_and_add_border(img, border_px=0)
        assert result.shape[0] == 200
        assert result.shape[1] == 300


def _make_bordered_image_with_text(content_h, content_w, border_size, border_color, text_side, text_width, gap_width):
    """
    Create a synthetic image with a photo, a gap, and a text block in the border area.

    The layout from the text_side edge inward is:
    [outer border] [text block] [gap] [photo content]
    The text block and gap are placed between the outer border edge and the photo content.
    """
    h = content_h + 2 * border_size
    w = content_w + 2 * border_size
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = border_color

    # Fill content area with a gradient (distinguishable from border)
    cy1, cy2 = border_size, border_size + content_h
    cx1, cx2 = border_size, border_size + content_w
    for c in range(3):
        img[cy1:cy2, cx1:cx2, c] = np.tile(np.arange(content_w, dtype=np.uint8) % 200 + 50, (content_h, 1))

    # Place a "text" block: a small region of bright pixels in the border area
    text_color = (200, 200, 200) if border_color == (0, 0, 0) else (50, 50, 50)
    # text occupies a few rows/columns near the edge, separated from content by gap
    if text_side == "right":
        # Text goes in the right border area: after content + gap
        text_x1 = cx2 + gap_width
        text_x2 = min(text_x1 + text_width, w)
        text_y1 = cy1 + content_h // 4
        text_y2 = cy1 + content_h // 2
        img[text_y1:text_y2, text_x1:text_x2] = text_color
    elif text_side == "left":
        text_x2 = cx1 - gap_width
        text_x1 = max(text_x2 - text_width, 0)
        text_y1 = cy1 + content_h // 4
        text_y2 = cy1 + content_h // 2
        img[text_y1:text_y2, text_x1:text_x2] = text_color
    elif text_side == "bottom":
        text_y1 = cy2 + gap_width
        text_y2 = min(text_y1 + text_width, h)
        text_x1 = cx1 + content_w // 4
        text_x2 = cx1 + content_w // 2
        img[text_y1:text_y2, text_x1:text_x2] = text_color
    elif text_side == "top":
        text_y2 = cy1 - gap_width
        text_y1 = max(text_y2 - text_width, 0)
        text_x1 = cx1 + content_w // 4
        text_x2 = cx1 + content_w // 2
        img[text_y1:text_y2, text_x1:text_x2] = text_color

    return img


class TestTextPadding:
    def test_text_on_right_gets_extra_padding(self):
        img = _make_bordered_image_with_text(
            content_h=200, content_w=300, border_size=80, border_color=(0, 0, 0),
            text_side="right", text_width=30, gap_width=20,
        )
        result = trim_and_add_border(img, border_px=5)
        # Right side should have extra padding (gap_width=20 > border_px=5)
        # Content is 300px wide; result width should be > 300 + 2*5
        assert result.shape[1] > 300 + 2 * 5
        # Top and bottom should remain at border_px (5)
        # Left should remain at border_px (5)
        # Height shouldn't have extra padding
        assert result.shape[0] == 200 + 2 * 5

    def test_text_on_left_gets_extra_padding(self):
        img = _make_bordered_image_with_text(
            content_h=200, content_w=300, border_size=80, border_color=(0, 0, 0),
            text_side="left", text_width=30, gap_width=20,
        )
        result = trim_and_add_border(img, border_px=5)
        # Left side should have extra padding
        assert result.shape[1] > 300 + 2 * 5
        assert result.shape[0] == 200 + 2 * 5

    def test_no_text_unchanged(self):
        img = _make_bordered_image(200, 300, border_size=80, border_color=(0, 0, 0))
        result = trim_and_add_border(img, border_px=5)
        assert result.shape[0] == 200 + 2 * 5
        assert result.shape[1] == 300 + 2 * 5

    def test_small_gap_ignored(self):
        # Gap of 5px is below min_gap_px (10), so no extra padding
        img = _make_bordered_image_with_text(
            content_h=200, content_w=300, border_size=80, border_color=(0, 0, 0),
            text_side="right", text_width=30, gap_width=5,
        )
        result = trim_and_add_border(img, border_px=5)
        # The text is close enough to content that it'll be included in the content crop
        # by the std-dev scanner, or the gap is too small to trigger extra padding.
        # Either way, no huge extra padding should appear.
        assert result.shape[1] <= 300 + 30 + 2 * 5 + 10  # reasonable upper bound


class TestExcludeText:
    def test_exclude_text_crops_text_region(self):
        """With include_text=False, text region should be cropped out, resulting in a smaller image."""
        img = _make_bordered_image_with_text(
            content_h=200, content_w=300, border_size=80, border_color=(0, 0, 0),
            text_side="right", text_width=30, gap_width=20,
        )
        result_include = trim_and_add_border(img, border_px=5, include_text=True)
        result_exclude = trim_and_add_border(img, border_px=5, include_text=False)
        # Excluding text should produce a narrower image (text region cropped from right)
        assert result_exclude.shape[1] < result_include.shape[1]

    def test_exclude_text_uniform_border(self):
        """With include_text=False, all sides should get uniform border_px padding."""
        img = _make_bordered_image_with_text(
            content_h=200, content_w=300, border_size=80, border_color=(0, 0, 0),
            text_side="right", text_width=30, gap_width=20,
        )
        result = trim_and_add_border(img, border_px=10, include_text=False)
        # Height should be content (minus any top/bottom crop) + 2*10
        # The key check: height should have uniform 10px borders (no extra padding)
        assert result.shape[0] == 200 + 2 * 10

    def test_exclude_text_no_text_same_as_include(self):
        """Without text, include_text=False should produce the same result as True."""
        img = _make_bordered_image(200, 300, border_size=80, border_color=(0, 0, 0))
        result_include = trim_and_add_border(img, border_px=5, include_text=True)
        result_exclude = trim_and_add_border(img, border_px=5, include_text=False)
        assert result_include.shape == result_exclude.shape
        assert np.array_equal(result_include, result_exclude)

    def test_exclude_text_left_side(self):
        """Text on left should be cropped when include_text=False."""
        img = _make_bordered_image_with_text(
            content_h=200, content_w=300, border_size=80, border_color=(0, 0, 0),
            text_side="left", text_width=30, gap_width=20,
        )
        result_include = trim_and_add_border(img, border_px=5, include_text=True)
        result_exclude = trim_and_add_border(img, border_px=5, include_text=False)
        assert result_exclude.shape[1] < result_include.shape[1]


class TestFindTextGapFromEdge:
    def test_clear_text_gap_pattern(self):
        # text (sparse) -> gap (zeros) -> dense content
        density = np.array([0.02, 0.03, 0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.8, 0.9])
        gap_width, dense_start = _find_text_gap_from_edge(density, content_fraction=0.3, min_gap_px=10)
        assert gap_width == 10  # gap from index 3 to 13
        assert dense_start == 13  # photo content starts at index 13

    def test_no_text_returns_zero(self):
        # All dense — no text-gap pattern
        density = np.array([0.5, 0.6, 0.7, 0.8, 0.9])
        gap_width, dense_start = _find_text_gap_from_edge(density, content_fraction=0.3, min_gap_px=10)
        assert gap_width == 0
        assert dense_start == 0

    def test_gap_too_small(self):
        # text -> small gap -> dense content
        density = np.array([0.02, 0.03, 0.0, 0.0, 0.0, 0.5, 0.8])
        gap_width, dense_start = _find_text_gap_from_edge(density, content_fraction=0.3, min_gap_px=10)
        assert gap_width == 0
        assert dense_start == 0

    def test_empty_density(self):
        assert _find_text_gap_from_edge(np.array([]), content_fraction=0.3, min_gap_px=10) == (0, 0)
