import base64
from ai_engine import media  # from backend, via conftest sys.path


def test_prepare_payload_minimal():
    p = media._prepare_payload("make a cat", "model-x")
    assert p["prompt"] == "make a cat"
    assert p["model"] == "model-x"
    assert "image" not in p and "file" not in p


def test_prepare_payload_attached_bytes():
    raw = b"\x89PNG\r\n\x1a\n"
    p = media._prepare_payload("cat", "m", attached_file=raw)
    expected = base64.b64encode(raw).decode("ascii")
    # image bytes -> "image" field
    assert p["image"] == expected or p["file"] == expected


def test_prepare_payload_attached_path(tmp_path):
    f = tmp_path / "x.png"
    f.write_bytes(b"imgdata")
    p = media._prepare_payload("cat", "m", attached_file=str(f))
    assert p["image"] == base64.b64encode(b"imgdata").decode("ascii") or \
           p["file"] == base64.b64encode(b"imgdata").decode("ascii")


def test_prepare_payload_attached_b64_string_used_as_is():
    b64val = base64.b64encode(b"rawimg").decode("ascii")
    p = media._prepare_payload("cat", "m", attached_file=b64val)
    # a plain base64 string that is NOT a file path -> used as-is
    assert p["image"] == b64val


def test_prepare_payload_attached_data_uri_stripped():
    b64val = base64.b64encode(b"rawimg").decode("ascii")
    p = media._prepare_payload("cat", "m", attached_file=f"data:image/png;base64,{b64val}")
    assert p["image"] == b64val


def test_get_path_branches():
    assert media._get_path(False, "p", False) == media.DEFAULT_PATH_TEXT_TO_MEDIA
    assert media._get_path(True, "p", False) == media.DEFAULT_PATH_TEXT_IMAGE_TO_MEDIA
    assert media._get_path(True, "", False) == media.DEFAULT_PATH_IMAGE_TO_MEDIA
    assert media._get_path(False, "", True) == media.DEFAULT_PATH_VOICE


def test_get_path_user_paths_override():
    up = {"text_to_media": "my/custom/path"}
    assert media._get_path(False, "p", False, up) == "my/custom/path"
    # empty user_paths entry falls back to default
    assert media._get_path(False, "p", False, {"text_to_media": ""}) == media.DEFAULT_PATH_TEXT_TO_MEDIA
