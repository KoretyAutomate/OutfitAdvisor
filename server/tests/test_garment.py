"""What the funnel reads about one garment (garment.py, user 2026-10-20)."""
import garment
from schemas import ClosetItem


def it(label, typ, group, **kw):
    return {"id": "itm-x", "label": label, "type": typ, "group": group, **kw}


def test_level_stated_wins():
    assert garment.level(it("beige drawstring pants", "trousers", "bottoms", level=4)) == 4


def test_level_from_the_name_lowers_and_raises():
    assert garment.level(it("beige drawstring pants", "trousers", "bottoms")) == 2
    assert garment.level(it("grey joggers", "trousers", "bottoms")) == 1
    assert garment.level(it("navy chinos", "trousers", "bottoms")) == 3
    assert garment.level(it("charcoal wool trousers", "trousers", "bottoms")) == 4
    assert garment.level(it("white mesh sneakers", "sneakers", "footwear")) == 2
    assert garment.level(it("white leather sneakers", "sneakers", "footwear")) == 3
    assert garment.level(it("カーゴパンツ", "trousers", "bottoms")) == 2


def test_level_from_the_kind():
    assert garment.level(it("navy polo", "polo", "tops")) == 3
    assert garment.level(it("white tee", "t_shirt", "tops")) == 2
    assert garment.level(it("brown loafers", "loafers", "footwear")) == 3
    assert garment.level(it("blue jeans", "jeans", "bottoms")) == 2
    assert garment.level(it("jeans", "jeans", "bottoms", colors=["dark indigo"])) == 3


def test_level_of_an_unknown_kind_has_an_answer():
    assert garment.level(it("thing", None, "tops", formality=["active"])) == 1
    assert garment.level(it("thing", None, "bottoms")) == 3


def test_material_and_wet_shoes():
    mesh = it("grey mesh sneakers", "sneakers", "footwear")
    plain = it("white sneakers", "sneakers", "footwear")
    leather = it("brown loafers", "loafers", "footwear")
    assert garment.material(mesh) == "mesh" and garment.wets_through(mesh)
    assert garment.material(plain) is None and not garment.wets_through(plain), "unknown never removes"
    assert garment.material(leather) == "leather" and not garment.wets_through(leather)
    assert garment.wets_through(it("navy sneakers", "sneakers", "footwear", material="canvas"))
    assert not garment.wets_through(it("mesh top", "t_shirt", "tops")), "shoes only"


def test_gauge():
    assert garment.gauge(it("navy reindeer sweater", "sweater", "tops")) == "chunky"
    assert garment.gauge(it("grey merino crew", "sweater", "tops")) == "fine"
    assert garment.gauge(it("dusty rose crew-neck sweater", "sweater", "tops")) == "mid"
    assert garment.gauge(it("striped sweater", "sweater", "tops", pattern="striped")) == "chunky"
    assert garment.gauge(it("cardigan", "cardigan", "tops", gauge="fine")) == "fine"
    assert garment.gauge(it("navy polo", "polo", "tops")) is None


def test_utility_trousers():
    assert garment.utility_trousers(it("beige drawstring pants", "trousers", "bottoms"))
    # A stated level of smart casual or above outranks the name (user, 2026-10-22).
    assert not garment.utility_trousers(it("beige cargo pants", "trousers", "bottoms", level=3))
    assert garment.utility_trousers(it("black cargo pants", "trousers", "bottoms", level=2))
    assert garment.utility_trousers(it("beige cargo pants", "trousers", "bottoms", formality=["smart"])), \
        "the old tags alone do not"
    assert not garment.utility_trousers(it("navy chinos", "trousers", "bottoms"))
    assert not garment.utility_trousers(it("grey sweater", "sweater", "tops"))


def _item(**kw):
    base = {"id": "itm-12345678", "label": "navy chinos", "category": "bottoms", "group": "bottoms",
            "type": "trousers"}
    return ClosetItem(**{**base, **kw})


def test_schema_keeps_known_values_and_drops_the_rest_without_a_422():
    ok = _item(level=3, material="leather", gauge="fine")
    assert (ok.level, ok.material, ok.gauge) == (3, "leather", "fine")
    bad = _item(level=9, material="velvet", gauge="huge")
    assert (bad.level, bad.material, bad.gauge) == (None, None, None)
    assert _item(level=True).level is None, "a bool is not a level"
    assert _item(level="3").level is None
    assert _item().level is None


def test_a_stated_level_decides_the_old_tags_on_the_way_in():
    assert _item(level=1, formality=["smart"]).formality == ["active"]
    assert _item(level=3, formality=["active"]).formality == ["casual", "smart"]
    assert _item(formality=["active"]).formality == ["active"], "no level: the tags as sent"


def test_the_primary_layer_is_always_one_it_is_worn_as():
    # A shirt whose Base role was taken away is not packed as a base (Codex plan review, 2026-10-22).
    shirt = ClosetItem(id="itm-12345678", label="navy shirt", category="base", group="tops", type="shirt",
                       roles=["mid", "outer"])
    assert shirt.category == "mid" and shirt.roles == ["mid", "outer"]
