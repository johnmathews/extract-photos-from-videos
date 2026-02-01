import json
from unittest.mock import MagicMock, patch

from extract_photos.immich import (
    add_assets_to_album,
    find_or_create_album,
    find_user,
    immich_request,
    parse_album_name,
    poll_for_assets,
    share_album,
    trigger_scan,
)


def _mock_response(data=None, status=200):
    """Create a mock urllib response that works as a context manager."""
    body = json.dumps(data).encode() if data is not None else b""
    resp = MagicMock()
    resp.read.return_value = body
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestParseAlbumName:
    def test_standard_youtube_filename(self):
        result = parse_album_name("Willem_Verbeeck-Shooting_Los_Angeles_on_8x10_Film-[ct4a89JIIkI].mkv")
        assert result == "Willem Verbeeck - Shooting Los Angeles on 8x10 Film"

    def test_underscored_hyphens_in_title(self):
        result = parse_album_name(
            "Willem_Verbeeck-Shooting_Los_Angeles_on_8x10_Film_-_Paloma_Dooley-[ct4a89JIIkI].mkv"
        )
        assert result == "Willem Verbeeck - Shooting Los Angeles on 8x10 Film - Paloma Dooley"

    def test_no_youtube_id(self):
        assert parse_album_name("Author-Title.mp4") == "Author - Title"

    def test_no_youtube_id_with_underscores(self):
        assert parse_album_name("Some_Author-Some_Title.mkv") == "Some Author - Some Title"

    def test_no_hyphen_no_id(self):
        assert parse_album_name("SingleName.mp4") == "SingleName"

    def test_no_hyphen_with_id(self):
        assert parse_album_name("SingleName-[abc123].mp4") == "SingleName"

    def test_multiple_extensions(self):
        assert parse_album_name("Author-Title.final.mp4") == "Author - Title.final"

    def test_empty_title_after_split(self):
        result = parse_album_name("Channel_Name-.mp4")
        assert result == "Channel Name"

    def test_whitespace_stripping(self):
        result = parse_album_name("Channel__Name-The__Title-[id].mkv")
        assert result == "Channel  Name - The  Title"

    def test_youtube_id_with_dashes(self):
        result = parse_album_name("Author-Title-[-xYz_123].mp4")
        assert result == "Author - Title"


class TestImmichRequest:
    @patch("extract_photos.immich.urllib.request.urlopen")
    def test_get_returns_parsed_json(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response([{"id": "1"}])
        result = immich_request("http://immich/api/test", "key123")
        assert result == [{"id": "1"}]

    @patch("extract_photos.immich.urllib.request.urlopen")
    def test_get_sets_api_key_header(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response([])
        immich_request("http://immich/api/test", "my-key")
        req = mock_urlopen.call_args[0][0]
        assert req.get_header("X-api-key") == "my-key"

    @patch("extract_photos.immich.urllib.request.urlopen")
    def test_get_uses_get_method(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response([])
        immich_request("http://immich/api/test", "key")
        req = mock_urlopen.call_args[0][0]
        assert req.get_method() == "GET"

    @patch("extract_photos.immich.urllib.request.urlopen")
    def test_post_with_data(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({"ok": True})
        result = immich_request("http://immich/api/test", "key", method="POST", data={"foo": "bar"})
        req = mock_urlopen.call_args[0][0]
        assert req.get_method() == "POST"
        assert req.get_header("Content-type") == "application/json"
        assert json.loads(req.data) == {"foo": "bar"}
        assert result == {"ok": True}

    @patch("extract_photos.immich.urllib.request.urlopen")
    def test_empty_response_returns_none(self, mock_urlopen):
        resp = MagicMock()
        resp.read.return_value = b""
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = resp
        result = immich_request("http://immich/api/test", "key", method="POST")
        assert result is None

    @patch("extract_photos.immich.urllib.request.urlopen")
    def test_no_content_type_without_body(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response([])
        immich_request("http://immich/api/test", "key")
        req = mock_urlopen.call_args[0][0]
        assert req.get_header("Content-type") is None


class TestTriggerScan:
    @patch("extract_photos.immich.immich_request")
    def test_calls_correct_endpoint(self, mock_req):
        trigger_scan("http://immich", "key", "lib-42")
        mock_req.assert_called_once_with("http://immich/api/libraries/lib-42/scan", "key", method="POST")


class TestPollForAssets:
    @patch("extract_photos.immich.time.sleep")
    @patch("extract_photos.immich.time.monotonic")
    @patch("extract_photos.immich.immich_request")
    def test_returns_assets_on_first_poll(self, mock_req, mock_mono, mock_sleep):
        mock_mono.return_value = 0
        assets = [{"id": "a1"}, {"id": "a2"}]
        mock_req.return_value = {"assets": {"items": assets}}
        result = poll_for_assets("http://immich", "key", "/photos/subdir/")
        assert result == assets
        mock_sleep.assert_not_called()

    @patch("extract_photos.immich.time.sleep")
    @patch("extract_photos.immich.time.monotonic")
    @patch("extract_photos.immich.immich_request")
    def test_polls_until_assets_appear(self, mock_req, mock_mono, mock_sleep):
        # First two polls return empty, third returns assets
        mock_mono.side_effect = [0, 5, 10, 15]
        mock_req.side_effect = [
            {"assets": {"items": []}},
            {"assets": {"items": []}},
            {"assets": {"items": [{"id": "a1"}]}},
        ]
        result = poll_for_assets("http://immich", "key", "/photos/subdir/", timeout=300)
        assert result == [{"id": "a1"}]
        assert mock_sleep.call_count == 2

    @patch("extract_photos.immich.time.sleep")
    @patch("extract_photos.immich.time.monotonic")
    @patch("extract_photos.immich.immich_request")
    def test_returns_empty_on_timeout(self, mock_req, mock_mono, mock_sleep):
        mock_mono.side_effect = [0, 301]
        mock_req.return_value = {"assets": {"items": []}}
        result = poll_for_assets("http://immich", "key", "/photos/subdir/", timeout=300)
        assert result == []

    @patch("extract_photos.immich.time.sleep")
    @patch("extract_photos.immich.time.monotonic")
    @patch("extract_photos.immich.immich_request")
    def test_handles_non_dict_response(self, mock_req, mock_mono, mock_sleep):
        mock_mono.side_effect = [0, 301]
        mock_req.return_value = None
        result = poll_for_assets("http://immich", "key", "/photos/subdir/", timeout=300)
        assert result == []

    @patch("extract_photos.immich.time.sleep")
    @patch("extract_photos.immich.time.monotonic")
    @patch("extract_photos.immich.immich_request")
    def test_sends_correct_search_payload(self, mock_req, mock_mono, mock_sleep):
        mock_mono.return_value = 0
        mock_req.return_value = {"assets": {"items": [{"id": "x"}]}}
        poll_for_assets("http://immich", "key", "/photos/subdir/")
        mock_req.assert_called_with(
            "http://immich/api/search/metadata", "key", method="POST", data={"originalPath": "/photos/subdir/"}
        )


class TestFindOrCreateAlbum:
    @patch("extract_photos.immich.immich_request")
    def test_returns_existing_album(self, mock_req):
        mock_req.return_value = [
            {"id": "album-1", "albumName": "Other Album"},
            {"id": "album-2", "albumName": "My Album"},
        ]
        result = find_or_create_album("http://immich", "key", "My Album")
        assert result == "album-2"
        mock_req.assert_called_once_with("http://immich/api/albums", "key", method="GET")

    @patch("extract_photos.immich.immich_request")
    def test_creates_album_when_not_found(self, mock_req):
        mock_req.side_effect = [
            [{"id": "album-1", "albumName": "Other Album"}],
            {"id": "album-new"},
        ]
        result = find_or_create_album("http://immich", "key", "New Album")
        assert result == "album-new"
        assert mock_req.call_count == 2
        mock_req.assert_called_with(
            "http://immich/api/albums", "key", method="POST", data={"albumName": "New Album"}
        )

    @patch("extract_photos.immich.immich_request")
    def test_creates_album_when_list_empty(self, mock_req):
        mock_req.side_effect = [[], {"id": "album-new"}]
        result = find_or_create_album("http://immich", "key", "Album")
        assert result == "album-new"

    @patch("extract_photos.immich.immich_request")
    def test_creates_album_when_response_not_list(self, mock_req):
        mock_req.side_effect = [None, {"id": "album-new"}]
        result = find_or_create_album("http://immich", "key", "Album")
        assert result == "album-new"


class TestAddAssetsToAlbum:
    @patch("extract_photos.immich.immich_request")
    def test_sends_asset_ids(self, mock_req):
        add_assets_to_album("http://immich", "key", "album-1", ["a1", "a2", "a3"])
        mock_req.assert_called_once_with(
            "http://immich/api/albums/album-1/assets", "key", method="PUT", data={"ids": ["a1", "a2", "a3"]}
        )


class TestFindUser:
    @patch("extract_photos.immich.immich_request")
    def test_finds_user_by_name(self, mock_req):
        mock_req.return_value = [
            {"id": "u1", "name": "alice"},
            {"id": "u2", "name": "john"},
        ]
        assert find_user("http://immich", "key", "john") == "u2"

    @patch("extract_photos.immich.immich_request")
    def test_returns_none_when_not_found(self, mock_req):
        mock_req.return_value = [{"id": "u1", "name": "alice"}]
        assert find_user("http://immich", "key", "bob") is None

    @patch("extract_photos.immich.immich_request")
    def test_returns_none_on_empty_list(self, mock_req):
        mock_req.return_value = []
        assert find_user("http://immich", "key", "john") is None

    @patch("extract_photos.immich.immich_request")
    def test_returns_none_on_non_list_response(self, mock_req):
        mock_req.return_value = None
        assert find_user("http://immich", "key", "john") is None


class TestShareAlbum:
    @patch("extract_photos.immich.immich_request")
    def test_shares_with_correct_payload(self, mock_req):
        share_album("http://immich", "key", "album-1", "user-42")
        mock_req.assert_called_once_with(
            "http://immich/api/albums/album-1/users",
            "key",
            method="PUT",
            data={"albumUsers": [{"userId": "user-42", "role": "editor"}]},
        )


class TestMain:
    @patch("extract_photos.immich.share_album")
    @patch("extract_photos.immich.find_user", return_value="user-42")
    @patch("extract_photos.immich.add_assets_to_album")
    @patch("extract_photos.immich.find_or_create_album", return_value="album-1")
    @patch("extract_photos.immich.poll_for_assets", return_value=[{"id": "a1"}, {"id": "a2"}])
    @patch("extract_photos.immich.trigger_scan")
    def test_full_flow_with_share(self, mock_scan, mock_poll, mock_album, mock_add, mock_find, mock_share):
        from extract_photos.immich import main

        args = [
            "--api-url", "http://immich",
            "--api-key", "key",
            "--library-id", "lib-1",
            "--asset-path", "/photos/subdir",
            "--video-filename", "Author-Title-[id].mkv",
            "--share-user", "john",
        ]
        with patch("sys.argv", ["immich.py"] + args):
            main()

        mock_scan.assert_called_once_with("http://immich", "key", "lib-1")
        mock_poll.assert_called_once_with("http://immich", "key", "/photos/subdir/")
        mock_album.assert_called_once_with("http://immich", "key", "Author - Title")
        mock_add.assert_called_once_with("http://immich", "key", "album-1", ["a1", "a2"])
        mock_find.assert_called_once_with("http://immich", "key", "john")
        mock_share.assert_called_once_with("http://immich", "key", "album-1", "user-42")

    @patch("extract_photos.immich.share_album")
    @patch("extract_photos.immich.find_user")
    @patch("extract_photos.immich.add_assets_to_album")
    @patch("extract_photos.immich.find_or_create_album", return_value="album-1")
    @patch("extract_photos.immich.poll_for_assets", return_value=[{"id": "a1"}])
    @patch("extract_photos.immich.trigger_scan")
    def test_no_share_without_flag(self, mock_scan, mock_poll, mock_album, mock_add, mock_find, mock_share):
        from extract_photos.immich import main

        args = [
            "--api-url", "http://immich",
            "--api-key", "key",
            "--library-id", "lib-1",
            "--asset-path", "/photos/subdir",
            "--video-filename", "Author-Title.mkv",
        ]
        with patch("sys.argv", ["immich.py"] + args):
            main()

        mock_find.assert_not_called()
        mock_share.assert_not_called()

    @patch("extract_photos.immich.find_or_create_album")
    @patch("extract_photos.immich.poll_for_assets", return_value=[])
    @patch("extract_photos.immich.trigger_scan")
    def test_exits_when_no_assets_found(self, mock_scan, mock_poll, mock_album):
        from extract_photos.immich import main

        args = [
            "--api-url", "http://immich",
            "--api-key", "key",
            "--library-id", "lib-1",
            "--asset-path", "/photos/subdir",
            "--video-filename", "Author-Title.mkv",
        ]
        with patch("sys.argv", ["immich.py"] + args):
            try:
                main()
            except SystemExit as e:
                assert e.code == 0

        mock_album.assert_not_called()

    @patch("extract_photos.immich.add_assets_to_album")
    @patch("extract_photos.immich.find_or_create_album", return_value="album-1")
    @patch("extract_photos.immich.poll_for_assets", return_value=[{"id": "a1"}])
    @patch("extract_photos.immich.trigger_scan", side_effect=Exception("connection refused"))
    def test_exits_on_scan_failure(self, mock_scan, mock_poll, mock_album, mock_add):
        import urllib.error

        from extract_photos.immich import main

        mock_scan.side_effect = urllib.error.URLError("connection refused")
        args = [
            "--api-url", "http://immich",
            "--api-key", "key",
            "--library-id", "lib-1",
            "--asset-path", "/photos/subdir",
            "--video-filename", "Author-Title.mkv",
        ]
        with patch("sys.argv", ["immich.py"] + args):
            try:
                main()
            except SystemExit as e:
                assert e.code == 1
        mock_album.assert_not_called()

    @patch("extract_photos.immich.share_album")
    @patch("extract_photos.immich.find_user", return_value=None)
    @patch("extract_photos.immich.add_assets_to_album")
    @patch("extract_photos.immich.find_or_create_album", return_value="album-1")
    @patch("extract_photos.immich.poll_for_assets", return_value=[{"id": "a1"}])
    @patch("extract_photos.immich.trigger_scan")
    def test_skips_share_when_user_not_found(self, mock_scan, mock_poll, mock_album, mock_add, mock_find, mock_share):
        from extract_photos.immich import main

        args = [
            "--api-url", "http://immich",
            "--api-key", "key",
            "--library-id", "lib-1",
            "--asset-path", "/photos/subdir",
            "--video-filename", "Author-Title.mkv",
            "--share-user", "nobody",
        ]
        with patch("sys.argv", ["immich.py"] + args):
            main()

        mock_find.assert_called_once_with("http://immich", "key", "nobody")
        mock_share.assert_not_called()

    @patch("extract_photos.immich.add_assets_to_album")
    @patch("extract_photos.immich.find_or_create_album", return_value="album-1")
    @patch("extract_photos.immich.poll_for_assets", return_value=[{"id": "a1"}])
    @patch("extract_photos.immich.trigger_scan")
    def test_trailing_slash_stripped_from_api_url(self, mock_scan, mock_poll, mock_album, mock_add):
        from extract_photos.immich import main

        args = [
            "--api-url", "http://immich/",
            "--api-key", "key",
            "--library-id", "lib-1",
            "--asset-path", "/photos/subdir",
            "--video-filename", "Author-Title.mkv",
        ]
        with patch("sys.argv", ["immich.py"] + args):
            main()

        mock_scan.assert_called_once_with("http://immich", "key", "lib-1")
