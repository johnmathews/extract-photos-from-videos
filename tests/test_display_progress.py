from extract_photos.display_progress import build_progress_bar, format_time


class TestFormatTime:
    def test_zero(self):
        assert format_time(0) == "0:00"

    def test_seconds_only(self):
        assert format_time(45) == "0:45"

    def test_minutes_and_seconds(self):
        assert format_time(125) == "2:05"

    def test_exactly_one_hour(self):
        assert format_time(3600) == "1:00:00"

    def test_hours_minutes_seconds(self):
        assert format_time(3661) == "1:01:01"

    def test_negative_clamps_to_zero(self):
        assert format_time(-10) == "0:00"

    def test_fractional_truncated(self):
        assert format_time(61.9) == "1:01"

    def test_large_value(self):
        assert format_time(7384) == "2:03:04"


class TestBuildProgressBar:
    def test_zero_percent(self):
        bar = build_progress_bar(0)
        assert bar == "[" + "-" * 30 + "]"

    def test_hundred_percent(self):
        bar = build_progress_bar(100)
        assert bar == "[" + "=" * 30 + "]"

    def test_fifty_percent(self):
        bar = build_progress_bar(50)
        assert bar == "[" + "=" * 15 + "-" * 15 + "]"

    def test_custom_width(self):
        bar = build_progress_bar(50, width=10)
        assert bar == "[" + "=" * 5 + "-" * 5 + "]"

    def test_over_hundred_clamps(self):
        bar = build_progress_bar(150)
        assert bar == "[" + "=" * 30 + "]"
