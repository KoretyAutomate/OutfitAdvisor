"""Garment cutouts (user, 2026-09-07: "the functionality Indyx had").

The matte is faked — rembg is a 170 MB model and the tests are about what happens
AFTER it: the crop, the padding, the square white canvas, the levels, and the two
ways the route says no (no rembg; nothing found).
"""
import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app as srv
import cutout

client = TestClient(srv.app)


def photo(w=400, h=300, bg=(120, 90, 60), garment=None):
    """A 'photo': a coloured background with a rectangle 'garment' on it."""
    img = Image.new("RGB", (w, h), bg)
    if garment:
        x0, y0, x1, y1, col = garment
        for x in range(x0, x1):
            for y in range(y0, y1):
                img.putpixel((x, y), col)
    return img


def b64_of(img):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()


def matte_keeping(x0, y0, x1, y1):
    """A fake remover: transparent everywhere except the given box."""
    def fake(img):
        rgba = img.convert("RGBA")
        alpha = Image.new("L", rgba.size, 0)
        for x in range(x0, x1):
            for y in range(y0, y1):
                alpha.putpixel((x, y), 255)
        rgba.putalpha(alpha)
        return rgba
    return fake


# ── compose ───────────────────────────────────────────────────────────────────

def test_the_garment_is_cropped_padded_and_centred_on_a_white_square():
    rgba = matte_keeping(100, 50, 300, 250)(photo(garment=(100, 50, 300, 250, (30, 60, 200))))
    out = cutout.compose(rgba)
    assert out is not None and out.size == (cutout.CANVAS, cutout.CANVAS)
    # corners are the canvas, i.e. white
    for corner in ((2, 2), (cutout.CANVAS - 3, 2), (2, cutout.CANVAS - 3), (cutout.CANVAS - 3, cutout.CANVAS - 3)):
        assert out.getpixel(corner) == (255, 255, 255), corner
    # the garment sits in the middle, still blue-ish
    r, g, b = out.getpixel((cutout.CANVAS // 2, cutout.CANVAS // 2))
    assert b > r and b > g


def test_the_original_background_is_gone():
    """The brown bed the shirt was photographed on must not survive anywhere."""
    rgba = matte_keeping(100, 50, 300, 250)(photo(garment=(100, 50, 300, 250, (30, 60, 200))))
    out = cutout.compose(rgba).convert("RGB")
    colours = [c for _, c in (out.getcolors(1 << 24) or [])]
    browns = [c for c in colours if abs(c[0] - 120) < 20 and abs(c[1] - 90) < 20 and abs(c[2] - 60) < 20]
    assert browns == []


def test_padding_keeps_the_garment_off_every_edge():
    """A garment that fills the photo still gets the white margin on all four
    sides — the margin belongs to the canvas, not to the photo (the reviewer)."""
    rgba = matte_keeping(0, 0, 400, 300)(photo(garment=(0, 0, 400, 300, (30, 60, 200))))
    out = cutout.compose(rgba)
    mid = cutout.CANVAS // 2
    for edge in ((mid, 1), (mid, cutout.CANVAS - 2), (1, mid), (cutout.CANVAS - 2, mid)):
        assert out.getpixel(edge) == (255, 255, 255), edge
    # and the garment really is there, just inside the margin
    margin = int(round(400 * cutout.PAD)) * cutout.CANVAS // (400 + 2 * int(round(400 * cutout.PAD)))
    r, g, b = out.getpixel((margin + 8, mid))
    assert b > r and b > g


def test_an_empty_matte_is_nothing_not_a_white_square():
    rgba = photo().convert("RGBA")
    rgba.putalpha(Image.new("L", rgba.size, 0))
    assert cutout.compose(rgba) is None


def test_a_speck_is_nothing_too():
    rgba = matte_keeping(10, 10, 12, 12)(photo())
    assert cutout.compose(rgba) is None


def test_specks_far_apart_are_still_nothing():
    """Two artifacts in opposite corners span a box the size of the photo but keep
    almost no pixels — that near-blank square must not replace the original (the
    reviewer's case)."""
    rgba = photo().convert("RGBA")
    alpha = Image.new("L", rgba.size, 0)
    for x in range(2, 6):
        for y in range(2, 6):
            alpha.putpixel((x, y), 255)
            alpha.putpixel((rgba.width - 1 - x, rgba.height - 1 - y), 255)
    rgba.putalpha(alpha)
    assert cutout.compose(rgba) is None


# ── the route ─────────────────────────────────────────────────────────────────

def test_the_route_returns_a_jpeg_cutout(monkeypatch):
    monkeypatch.setattr(cutout, "available", lambda: True)
    monkeypatch.setattr(cutout, "_matte", matte_keeping(100, 50, 300, 250))
    r = client.post("/cutout", json={"imageB64": b64_of(photo(garment=(100, 50, 300, 250, (30, 60, 200))))})
    assert r.status_code == 200
    img = Image.open(io.BytesIO(base64.b64decode(r.json()["imageB64"])))
    assert img.format == "JPEG" and img.size == (cutout.CANVAS, cutout.CANVAS)


def test_without_rembg_the_route_says_so(monkeypatch):
    monkeypatch.setattr(cutout, "available", lambda: False)
    r = client.post("/cutout", json={"imageB64": b64_of(photo())})
    assert r.status_code == 503


def test_nothing_found_is_a_502_so_the_phone_keeps_the_original(monkeypatch):
    monkeypatch.setattr(cutout, "available", lambda: True)

    def blank(img):
        rgba = img.convert("RGBA")
        rgba.putalpha(Image.new("L", rgba.size, 0))
        return rgba

    monkeypatch.setattr(cutout, "_matte", blank)
    r = client.post("/cutout", json={"imageB64": b64_of(photo())})
    assert r.status_code == 502


def test_garbage_is_a_422(monkeypatch):
    monkeypatch.setattr(cutout, "available", lambda: True)
    r = client.post("/cutout", json={"imageB64": base64.b64encode(b"not an image at all" * 20).decode()})
    assert r.status_code == 422


def test_a_data_uri_prefix_is_tolerated(monkeypatch):
    monkeypatch.setattr(cutout, "available", lambda: True)
    monkeypatch.setattr(cutout, "_matte", matte_keeping(100, 50, 300, 250))
    b = b64_of(photo(garment=(100, 50, 300, 250, (30, 60, 200))))
    r = client.post("/cutout", json={"imageB64": "data:image/jpeg;base64," + b})
    assert r.status_code == 200


def test_the_journal_never_sees_the_image(monkeypatch, caplog):
    monkeypatch.setattr(cutout, "available", lambda: True)
    monkeypatch.setattr(cutout, "_matte", matte_keeping(100, 50, 300, 250))
    b = b64_of(photo(garment=(100, 50, 300, 250, (30, 60, 200))))
    with caplog.at_level("INFO", logger="outfit"):
        client.post("/cutout", json={"imageB64": b})
    assert "cutout ok" in caplog.text
    assert b[:40] not in caplog.text


@pytest.mark.skipif(not cutout.available(), reason="rembg not installed here")
def test_the_real_model_finds_a_garment_on_a_plain_ground():
    """Smoke test of the real matte, only where rembg is installed (the DGX)."""
    img = photo(w=320, h=320, bg=(235, 235, 235), garment=(90, 60, 230, 270, (20, 40, 160)))
    out = cutout.compose(cutout._matte(img.convert("RGBA")))
    assert out is not None
