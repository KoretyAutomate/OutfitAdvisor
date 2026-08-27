"""schemas.py — the request bodies, and the sanitizer they all share.

Split out of app.py on 2026-08-24, when it crossed the 600-line ceiling. These are
the shapes the phone sends; app.py is the routing and the orchestration. Keeping
them apart also keeps the validators next to each other, which matters because
they encode one rule between them: free text that is destined for an LLM prompt is
length-capped and character-stripped HERE, once, so no endpoint has to remember.

Injection posture lives here too — see the note on _TEXT_OK.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

import vocab

# Free text destined for the LLM prompt: keep word chars (incl. CJK), spaces,
# and a few naming chars. Kills backticks, braces, newlines — the fence-escape
# and JSON-confusion vectors.
_TEXT_OK = re.compile(r"[^\w \-'&/()+.,]", flags=re.UNICODE)


def _clean(s: str, max_len: int) -> str:
    return _TEXT_OK.sub("", s)[:max_len].strip()


class ClosetItem(BaseModel):
    id: str = Field(..., min_length=8, max_length=64, pattern=r"^[A-Za-z0-9\-]+$")
    label: str = Field(..., min_length=1, max_length=60)
    # `category` is the item's PRIMARY layer — still the tie-breaker when the model
    # duplicates a pick — but it no longer decides what the item may be worn as.
    category: Literal["inner", "base", "mid", "outer", "bottoms", "footwear", "accessories"]
    # What the garment IS, for grouping the wardrobe into folders (2026-08-10).
    # Optional: closets saved before this field exist, and are mapped from category.
    #
    # `knitwear` is STILL ACCEPTED here although it stopped being a group on
    # 2026-08-20. A phone running an older build sends it, and a Literal rejection
    # is a 422 on the whole /advice request — every other item in the closet lost
    # because one of them used last week's spelling. vocab.canonical_group() maps
    # it to `tops` inside _derive.
    group: Literal["underwear", "tops", "knitwear", "outerwear", "bottoms",
                   "onepiece", "footwear", "accessories"] | None = None
    # Second level of the taxonomy (2026-08-14, extended 2026-08-20): WHICH KIND of
    # garment inside that group — "Tops > Polo". Deliberately a plain string
    # validated against the group's own list rather than a Literal: a type that does
    # not belong to the group is DROPPED (see vocab.normalize_type), never a 422, so
    # a closet saved before this field and a /classify guess that misses both stay
    # usable.
    #
    # No `max_length` here, deliberately. A Field constraint runs BEFORE the model
    # validator that normalizes this, so an over-long unknown type would 422 the
    # whole request — exactly the rejection the paragraph above promises never
    # happens. The bound is applied in `_cap_type` below instead, which is a
    # `before` validator and so cannot invert the order. The longest real type is
    # `dress_shoes` (11), so capping at 24 can never truncate a valid value into an
    # invalid one.
    type: str | None = None
    # Every layer this ONE garment can play across the year — a shirt is the outer
    # layer at 30C and a base under a coat at 8C. Empty/absent => [category], i.e.
    # exactly the old fixed behaviour, so an old closet is unchanged.
    roles: list[Literal["inner", "base", "mid", "outer", "bottoms",
                        "footwear", "accessories"]] = Field(default_factory=list, max_length=7)
    colors: list[str] = Field(default_factory=list, max_length=3)
    warmth: int = Field(3, ge=1, le=5)
    formality: list[Literal["casual", "smart", "active"]] = Field(default_factory=list)
    waterproof: bool = False
    availableCount: int = Field(1, ge=1, le=99)

    @model_validator(mode="after")
    def _derive(self):
        # Normalize here, once, so every consumer (advice, packing, prompts) reads
        # the same already-safe values and none of them has to remember the rules.
        #
        # reconcile() replaced a normalize_roles() + group-default pair that treated
        # the fields as independent, which is how a `tops` item could arrive carrying
        # the `inner` role and reach closet.py as a legal undershirt (user,
        # 2026-08-18). A contradictory item cannot be constructed now.
        cat, grp, kind, roles = vocab.reconcile(
            self.category, self.group, self.roles, self.type
        )
        object.__setattr__(self, "category", cat)
        object.__setattr__(self, "group", grp)
        object.__setattr__(self, "type", kind)
        object.__setattr__(self, "roles", roles)
        return self

    @field_validator("type", mode="before")
    @classmethod
    def _cap_type(cls, v):
        """Bound the field without ever rejecting it.

        `before` is load-bearing: it runs ahead of the `after` model validator that
        calls reconcile(), so an over-long value is cut down rather than raised on.
        Anything still unrecognised is dropped there, as the field's own docstring
        promises.
        """
        return v[:24] if isinstance(v, str) else v

    @field_validator("label")
    @classmethod
    def _san_label(cls, v: str) -> str:
        v = _clean(v, 60)
        if not v:
            raise ValueError("label empty after sanitization")
        return v

    @field_validator("colors")
    @classmethod
    def _san_colors(cls, v: list[str]) -> list[str]:
        return [c for c in (_clean(x, 20) for x in v) if c]


class AdviceRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    # Closed vocabularies — free strings would flow into the LLM prompt (injection)
    # and the engine; anything else is a 422 before it touches either.
    gender: Literal["man", "woman", "neutral"] = "neutral"
    style: Literal["casual", "smart", "active"] = "casual"
    day: int = Field(0, ge=0, le=1)  # 0 = today (morning push), 1 = tomorrow
    # Personal thermal calibration from the phone's 5-point feedback (2026-07-27).
    # ADDED to the temps the recommender sees: positive = user ran warm = dress
    # lighter. A bounded float, so it adds no prompt-injection surface. The phone
    # owns the rating history; the server stays stateless and just applies it.
    tempOffset: float = Field(0.0, ge=-6, le=6)
    # Phone-side closet: AVAILABLE items only (rotation already applied on the
    # phone — items in the laundry are never sent). Absent/empty = generic advice.
    closet: list[ClosetItem] | None = Field(None, max_length=100)
    # The wearer's own prohibitions, parsed once by /rule and held on the phone
    # (2026-08-24). Passed through to rules.clean_rules(), which drops anything it
    # cannot enforce rather than 422-ing the whole request — a stale rule from an
    # older build must never cost the user their morning advice.
    rules: list[dict] | None = Field(None, max_length=24)
    # "My closet is complete" (2026-08-27). The default stays False and keeps the
    # 2026-07-15 behaviour — a slot the wardrobe cannot fill gets a generic
    # suggestion, which answered a real complaint that a bare "None" told a user
    # with three registered shirts nothing about their legs. Once the user says the
    # wardrobe IS everything they own, that suggestion becomes an item they cannot
    # wear, so the slot is reported empty instead.
    closetOnly: bool = False


class KnownPlace(BaseModel):
    """One abbreviation the user has told their phone the meaning of."""

    abbr: str = Field("", max_length=40)
    city: str = Field("", max_length=80)

    @field_validator("abbr", "city")
    @classmethod
    def _san(cls, v: str) -> str:
        return _clean(v, 80)


class Gap(BaseModel):
    """One slot the wardrobe could not fill, and the weather it happened in.

    Counted on the PHONE across the period, so this server still stores nothing.
    """

    slot: Literal["inner", "base", "mid", "outer", "bottoms", "footwear", "accessories"]
    n: int = Field(1, ge=1, le=400)
    loC: int = Field(0, ge=-60, le=60)
    hiC: int = Field(0, ge=-60, le=60)


class ShoppingRequest(BaseModel):
    """Ask what the wardrobe is missing, with the evidence for it.

    The closet is sent because a suggestion must not name something already owned;
    the gaps because they are what makes a suggestion an argument rather than a
    catalogue; the rules because a suggestion that breaks one of the user's own bans
    is worse than none.
    """

    closet: list[ClosetItem] | None = Field(None, max_length=100)
    gaps: list[Gap] = Field(default_factory=list, max_length=20)
    rules: list[dict] | None = Field(None, max_length=24)
    tempOffset: float = Field(0.0, ge=-6, le=6)


class RuleRequest(BaseModel):
    """One line of feedback to be turned into a rule the server can check."""

    text: str = Field(..., min_length=2, max_length=200)

    @field_validator("text")
    @classmethod
    def _san_text(cls, v: str) -> str:
        return _clean(v, 200)


class TriageRequest(BaseModel):
    """A calendar entry to judge. Free text, so it is sanitized exactly like closet
    labels before it reaches the prompt (plan amendment 1)."""
    title: str = Field("", max_length=120)
    location: str = Field("", max_length=120)
    nights: int = Field(1, ge=0, le=60)
    start: str = Field("", max_length=10)
    end: str = Field("", max_length=10)
    # The phone's own table of what its owner's abbreviations mean (2026-08-24).
    # A work calendar writes "PPK", and nothing in that string says it is an office
    # on Princeton Pike — so the model was inferring a fact the user already knew,
    # and Open-Meteo's IATA table was happy to make PPK mean Petropavl, Kazakhstan.
    # The phone answers an exact match itself and never calls here; this list is for
    # the cases it could not match on whole tokens ("PPK-3", "at PPK").
    # Abbreviation and town only. No coordinates: this server has no use for them.
    known: list[KnownPlace] = Field(default_factory=list, max_length=40)

    @field_validator("title", "location")
    @classmethod
    def _san(cls, v: str) -> str:
        return _clean(v, 120)

    @field_validator("start", "end")
    @classmethod
    def _san_date(cls, v: str) -> str:
        return v if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v or "") else ""
