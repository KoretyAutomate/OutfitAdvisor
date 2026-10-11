"""
review.py — the model looks at its own outfit again when it did not hold up
(user, 2026-10-11).

"Style check needs to have a common sense as no human would wear such outfit ...
Rule based fixes are not easy to scale. Shouldn't we approach it with the prompt?"

Two outfits that morning showed why. A polo over a polo was put there by a CODE
repair: the model's answer had nothing warm enough on top, the warmth fixer added
the lightest legal mid layer — another polo — and nothing with judgement looked at
the result. And twice the stylist scored the outfit 2/5, and its verdict was
dropped because it may only suggest one swap and the swap was refused.

So the judging stays with the model. The checks report facts — a repair had to
put warmth on, a sleeve was fixed, no shoes though they own some, the stylist said
it looks wrong — and the model is asked ONCE more, told exactly that, to choose
the whole outfit again. The code repairs still run on the second answer: they are
the last resort now, not the stylist.

Time-boxed like the stylist: only when the first answer came back early enough for
a second to fit inside the phone's 90 s.
"""
import asyncio
import time
from dataclasses import dataclass, field

import picks as pk
from layers import _still_warm
from llm import _fenced, _plan_temp, log
from stylist import POOR, Verdict
from vocab import CATEGORIES

# The first answer must be back by this for a second to be worth asking: a closet
# generation is 15-30 s, the stylist 2-3 s, and the phone gives up at 90 s.
REVISE_BUDGET_S = 40.0
# And the revision must be BACK by this, or the first answer stands: the phone
# aborts at 90 s, and a revision that needs its own corrective retry can take two
# more generations. Raised by the pre-push reviewer, 2026-10-11.
DEADLINE_S = 80.0
# Unresolved omissions: an outfit missing one of these is worse than any outfit a
# repair completed, whatever the counts say.
_BARE = ("it had no trousers", "it had no shoes")


@dataclass(frozen=True)
class Seen:
    """What the checks saw in one answer — attached by closet._dress."""

    verdict: Verdict | None = None
    repairs: list = field(default_factory=list)    # put_on tuples: (slot, id) or (slot, id, why, ...)


def problems(result: dict, wd: "pk.Wardrobe", w: dict, prefs) -> list[str]:
    """Plain sentences for each way this outfit failed, for the model to read."""
    picks, seen = result["picks"], result.get("review") or Seen()

    def name(iid: str) -> str:
        return _fenced((wd.by_item.get(iid) or {}).get("label"), 60) or "a garment"
    out = []
    for a in seen.repairs:
        if len(a) < 3:
            out.append(f"nothing was left on top, so {name(a[1])} had to be added as the {a[0]}")
        elif a[2] == "warmth":
            out.append(f"nothing in it was warm enough for the coldest hour, so {name(a[1])} had to "
                       f"be added as the {a[0]} — choose the warmth yourself: knitwear or a jacket "
                       "over ONE top")
        elif a[2] == "sleeve":
            out.append(f"a long sleeve sat under a short one, so the {a[0]} had to change")
    v = seen.verdict
    if v and v.score <= POOR and not v.swap:
        out.append(f"a stylist scored it {v.score}/5" + (f': "{v.issue}"' if v.issue else ""))
    # Trousers and shoes are never optional when they own some — a dress covers the
    # legs, nothing else does. The live test days caught an outfit with no trousers:
    # the model had put the sneakers in both slots and the duplicate was cleared.
    for slot, what in (("bottoms", "trousers"), ("footwear", "shoes")):
        if picks.get(slot) or (slot == "bottoms" and wd.by_group.get(picks.get("base")) == "onepiece"):
            continue
        if pk._has_suitable_alternative(slot, picks, wd, _plan_temp(w), list(prefs.rules)):
            out.append(f"it had no {what}, though they own suitable ones")
    return out


def revision_note(result: dict, wd: "pk.Wardrobe", found: list[str]) -> str:
    worn = "; ".join(f"{c}: {_fenced((wd.by_item.get(i) or {}).get('label'), 60)}"
                     for c in CATEGORIES if (i := result["picks"].get(c)))
    return ("REVISION — your previous outfit for this same day was: " + (worn or "nothing")
            + ". It did not hold up: " + "; ".join(found) + ". Choose the whole outfit again "
            "from the wardrobe above, fixing exactly this and keeping what worked.\n")


def _rank(result: dict, other: dict, wd: "pk.Wardrobe", w: dict, prefs) -> tuple[int, int, int]:
    """How bad the FINISHED outfit is, lower better — judged on its final state, the
    same way for both answers, never by counting the sentences that triggered the
    revision (two pre-push reviews, 2026-10-11, found ways to win that count):

      1. unresolved: bare legs or feet though some are owned, nothing on top, or
         still nothing warm enough on top — a revision that loses warmth, a top or
         trousers never wins;
      2. how many layer repairs the model's own answer needed;
      3. the stylist's score, only when BOTH answers have one — an unreviewed
         revision is no evidence either way.
    """
    picks = result["picks"]
    found = problems(result, wd, w, prefs)
    # Nothing above the waist is unresolved too, and "cold" cannot see it: with no
    # torso garment there is nothing to be warm enough. Raised by the pre-push
    # reviewer, 2026-10-11.
    torso = [picks.get(c) for c in ("base", "mid", "outer") if picks.get(c)]
    cold = not torso or not _still_warm(picks, wd.by_item, _plan_temp(w))
    mine, theirs = _score(result), _score(other)
    return (sum(1 for f in found if f.startswith(_BARE)) + int(cold),
            len((result.get("review") or Seen()).repairs),
            -(mine if mine is not None and theirs is not None else 0))


def _score(result: dict) -> int | None:
    v = (result.get("review") or Seen()).verdict
    return v.score if v else None


async def second_look(first: dict, again, wd: "pk.Wardrobe", w: dict, prefs) -> dict:
    """The answer that stands: `first`, or the model's revision when it did better."""
    look = getattr(prefs, "look", None)
    start = look.t0 if look else time.monotonic()
    found = problems(first, wd, w, prefs)
    if not found:
        return _done(first)
    age = time.monotonic() - start
    if age > REVISE_BUDGET_S:
        log.info("review: %d problem(s), no time to revise (%.0fs)", len(found), age)
        return _done(first)
    log.info("review: revising — %d problem(s)", len(found))
    try:
        second = await asyncio.wait_for(again(revision_note(first, wd, found)),
                                        DEADLINE_S - age)
    except TimeoutError:
        log.info("review: the revision ran past %.0fs, the first answer stands", DEADLINE_S)
        return _done(first)
    if second is None:
        log.info("review: no usable revision, the first answer stands")
        return _done(first)
    # The revision stands unless it is worse (see _rank): it is the model's own
    # answer, made knowing what went wrong, and the repairs have judged it too.
    a, b = _rank(first, second, wd, w, prefs), _rank(second, first, wd, w, prefs)
    keep = second if b <= a else first
    log.info("review: %s → %s, %s answer stands", a, b, "revised" if keep is second else "first")
    return _done(keep)


def _done(result: dict) -> dict:
    return {k: v for k, v in result.items() if k != "review"}
