"""The fabric field, for laundry split by material (user, 2026-10-09)."""
from schemas import ClosetItem


def _item(**kw):
    return ClosetItem(id="abcdefgh", label="x", category="base", **kw)


def test_known_fabric_is_kept_and_normalised():
    assert _item(fabric=" Silk ").fabric == "silk"


def test_unknown_fabric_is_dropped_not_rejected():
    assert _item(fabric="unobtainium").fabric is None
    assert _item(fabric=7).fabric is None
    assert _item().fabric is None
