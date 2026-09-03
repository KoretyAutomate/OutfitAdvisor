"""reroll.py — "show me something else", and making the answer differ.

Split out of picks.py and closet.py on 2026-09-03, when both crossed the 600-line
ceiling. It is one feature end to end, and shaped like `rules.py` for that reason:
a block that goes into the prompt, and a check in code that makes the promise true
when the prompt is not enough. Those two agreeing is the whole of it, which is why
they live together rather than one in the generator and one in the validator.

The complaint it exists for:

> "the recommendation doesn't change when I want to get a new advice"

And it did not. Four identical /advice calls to the live server, a wardrobe with
five bases and four bottoms: the top and the trousers came back the same every
time, while the prose changed on all four — so the app looked like it was working
and the clothes did not move. /advice is stateless by design, so a re-tap sent a
byte-identical request and the model answered a very peaked distribution the same
way. Nothing anywhere said the wearer had already seen this.

Three rungs, because measurement said two were not enough. The prompt names the
handles to move away from; a repeat that could have been avoided spends the
corrective retry; and what survives that is swapped here in code.
"""

import picks as pk
from llm import _plan_temp, log
from vocab import CATEGORIES

def peak_temp(w: dict, plan_temp: float) -> float:
    """The hottest hour the outfit has to survive, already carrying the wearer's
    thermal offset because it is read off the same adjusted day."""
    hi = w.get("hi")
    return max(plan_temp, float(hi)) if hi is not None else plan_temp


def swap_repeats(picks: dict, repeated: list[str], wd: "pk.Wardrobe",
                 plan_temp: float, user_rules: list[dict],
                 peak_temp: float | None = None) -> list[tuple]:
    """Move the slots the model was asked twice to move and would not.

    Validate in code, never hope in prose — the lesson this module keeps relearning,
    and the reason `_cool_down` and `_relocate_mismatches` exist rather than a
    sterner paragraph in the prompt. Measured 2026-09-03: with the instruction and a
    corrective retry, two re-rolls in four still handed back a core slot unchanged.
    A feature that works three times in four is a feature the wearer stops trusting.

    Shaped on `_cool_down` deliberately, including the one-piece mirror: the search
    judges a trial outfit with the trousers off, so writing back only the base is how
    a dress goes out over jeans.

    A slot with nothing to swap to keeps what it has. Better the same trousers than
    no trousers — and that case is not a failure, it is a wardrobe with one answer,
    which `same_again_line` then says out loud.
    """
    done: list[tuple] = []
    peak = plan_temp if peak_temp is None else peak_temp
    for slot in repeated:
        was = picks.get(slot)
        if not was:
            continue
        # The incumbent stays in `picks` while the search runs, which is what
        # excludes it: "already worn somewhere else" is the only exclusion
        # pk._suitable_for has, and emptying the slot first — as _cool_down does, where
        # the heat check rejects the incumbent anyway — hands the same garment
        # straight back and swaps nothing at all (found 2026-09-03). The one-piece
        # trial is unaffected: pk._suitable_for judges `{**picks, slot: candidate}`, so
        # this slot is replaced in the trial either way.
        alt = pk._suitable_for(slot, picks, wd, plan_temp, user_rules,
                            hot_temp=pk._heat_temp(slot, plan_temp, peak))
        if not alt:
            continue
        picks[slot] = alt
        if slot == "base" and wd.by_group.get(alt) == "onepiece" and picks.get("bottoms"):
            picks["bottoms"] = None
            done.append(("bottoms", None))
        done.append((slot, alt))
    return done


def swapped_line(swapped: list[tuple], by_item: dict) -> str:
    """Say which garments the app changed after the advisor would not.

    Same reasoning as `_added_top_line`: a garment in the picture and not in the
    text reads as a bug, and it is there precisely because the model did not put it
    there. The bullets naming what it replaced are struck by the caller, so without
    this line the slot would simply have no words at all.
    """
    names = [str((by_item.get(iid) or {}).get("label") or "").strip()
             for _, iid in swapped if iid]
    names = [n for n in names if n]
    if not names:
        return ""
    listed = names[0] if len(names) == 1 else (", ".join(names[:-1]) + " and " + names[-1])
    return f"{listed} instead — you asked for something different."


def repeated_slots(picks: dict, shown: dict, wd: "pk.Wardrobe", plan_temp: float,
                   user_rules: list[dict],
                   peak_temp: float | None = None) -> list[str]:
    """Slots the wearer was already shown, asked to change, and got back anyway —
    counting ONLY the ones that could have changed (2026-09-03).

    A re-roll cannot promise a different garment in every slot. Somebody who owns
    one pair of shoes is wearing those shoes, and saying "show me something else"
    does not conjure a second pair. So a repeat is only a failure where the wardrobe
    held an answer, and that question is `pk._suitable_for` — the same search the gap
    logic uses, so a slot this calls stuck is one the generator could legitimately
    have moved.

    The distinction is the whole point. Without it the honest message ("nothing else
    of yours suits today") and the broken one (the model ignored the instruction)
    are the same screen, which is exactly the state this change was reported from.
    """
    peak = plan_temp if peak_temp is None else peak_temp
    stuck = []
    # In CATEGORIES order, so the note the model is retried with and the swaps below
    # read the same way every time — a dict's order is the phone's, and a repair
    # sequence that varies with it is one that cannot be reproduced from a log.
    for slot in CATEGORIES:
        iid = shown.get(slot)
        if not iid or picks.get(slot) != iid:
            continue
        # The heat ceiling applies to the ALTERNATIVE too. Without it a 29C day
        # counts a fleece as the answer for `base`, calls the slot stuck, and the
        # repair below puts the fleece on — undoing the ceiling added on 2026-09-01
        # in the name of variety.
        if pk._suitable_for(slot, picks, wd, plan_temp, user_rules,
                         hot_temp=pk._heat_temp(slot, plan_temp, peak)):
            stuck.append(slot)
    return stuck


def same_again_line(picks: dict, shown: dict) -> str | None:
    """The top line when a re-roll came back with the outfit it was asked to
    replace — and None when it did not, which is most of the time.

    Said out loud because silence here is indistinguishable from the bug: tapping
    "show me something else" and getting the same card back is precisely what the
    wearer reported, and an unexplained repeat teaches them the button is broken.

    But only when EVERY slot came back the same. An outfit whose top and trousers
    changed has plainly re-rolled, and remarking on the shoes that could not is a
    line of apology for working correctly — the wearer owns one pair, and they know.
    A note on every re-roll is a note nobody reads by the third one.

    It blames the wardrobe, and it is safe to, because by the time this is reached
    every slot that COULD have moved has: `swap_repeats` searches with exactly the
    same rules that decided the slot was stuck, so a slot still holding what it held
    is one the wardrobe has a single answer for. If those two searches are ever
    allowed to disagree, this sentence starts telling people to buy trousers they
    already own — see test_the_repair_can_always_move_what_it_calls_stuck.
    """
    worn = [(slot, iid) for slot, iid in shown.items() if iid]
    if not worn or any(picks.get(slot) != iid for slot, iid in worn):
        return None
    return "Same outfit again — nothing else you own suits today."


def prompt_block(shown: tuple, handles: dict | None = None) -> str:
    """The outfit already on the wearer's screen, which they have just turned down.

    Handles only, never labels: the model is being told which LINES of the wardrobe
    listing not to choose again, and a handle is what a line is addressed by. It is
    also the one place a UUID would do real damage — the prefers block was the last
    to hold one, and the listing right below this is what the model copies from.

    A slot with no alternative is exempted out loud. Told flatly to change
    everything, the model starts inventing: a wardrobe with one pair of shoes gets
    null footwear, or the tee moves into `inner` to free up `base`, and the wearer
    is charged a corrective retry for asking a reasonable question.
    """
    # `handles` arrives keyed BY ID, the same map _prefers_block reads and the same
    # one the wardrobe listing is rendered from. Inverting it here would silently
    # produce empty output rather than an error, which is the quietest way for a
    # re-roll to stop working.
    #
    # `iid in hmap` is also the ONLY place a stale id is filtered, and deliberately
    # the only one: a garment shown this morning and put in the wash since is not in
    # today's wardrobe, and naming a line absent from the listing below would spend
    # the single corrective retry on a contradiction this end put there. Nothing
    # upstream repeats the check — the endpoint passes `shown` through as the phone
    # sent it — and nothing downstream needs to, because an id that cannot be picked
    # can never equal a pick.
    hmap = handles or {}
    lines = [f"- {slot}: {hmap[iid]}" for slot, iid in shown if iid and iid in hmap]
    if not lines:
        return ""
    body = "\n".join(lines)
    return (
        "ALREADY SUGGESTED TODAY — the wearer has seen this exact outfit and asked "
        "for a DIFFERENT one. Pick a different item for each slot below wherever "
        "their wardrobe holds another one that suits today. Where it does not, keep "
        "what is there — a wardrobe with one pair of shoes means one pair of shoes, "
        "and leaving a slot null or borrowing from another slot to look different is "
        "worse than repeating yourself. The weather and their rules still come "
        "first.\n"
        f"{body}\n"
    )


def hold_the_reroll(picks: dict, w: dict, prefs: "pk.Prefs", wd: "pk.Wardrobe",
                    banned: list[dict], attempt: int
                    ) -> tuple[str, list, list[dict], set]:
    """Did the re-roll actually re-roll?

    Asked AFTER every repair in _hold_to_the_rules, because the outfit that reaches
    the wearer is the repaired one — a check run earlier would pass on a pick the
    warmth rule then puts back.

    Two chances and then a repair, which is the ladder every check in this module
    ended up on. Told plainly, the model gets it right most of the time; told again
    with the slots named, it gets most of the rest; and the remainder is fixed in
    code, because "validate in code, never hope in prose" is what the last four
    rounds of this file were about. Measured 2026-09-03: with the instruction AND
    the retry, two re-rolls in four still handed back a core slot unchanged, and a
    re-roll that works three times in four is one the wearer stops pressing.

    Returns a corrective note to retry with (empty when the outfit stands), the
    swaps this had to make itself, the garments whose mention must now be struck
    from the prose, and any slot now covered by something else — which is the last
    of those because this runs AFTER _hold_to_the_rules has computed coverage, and
    a swap can still change it. Raised by the pre-push reviewer, 2026-09-03.
    """
    shown = prefs.shown_map
    if not shown:
        return "", [], banned, set()
    plan = _plan_temp(w)
    peak = peak_temp(w, plan)
    repeated = repeated_slots(picks, shown, wd, plan, list(prefs.rules), peak)
    if not repeated:
        return "", [], banned, set()
    if attempt == 0:
        # Spends the corrective retry, exactly as a role violation does. Same failure
        # in kind: the model was told something plainly and did not do it, and there
        # is an owned garment that would have.
        log.info("closet picks: re-roll repeated %s — retrying", ",".join(repeated))
        # ADDS to the ALREADY SUGGESTED block; never replaces it. Naming only the
        # stuck slots was read as narrowing the job to those, and the model paid for
        # them by putting a slot it HAD changed back the way it was — measured
        # 2026-09-03, re-roll 1: told to move bottoms and footwear, it moved both and
        # reverted the base.
        return ("Your last reply repeated the outfit the wearer had already seen and "
                f"asked you to change. Still unchanged: {', '.join(repeated)} — their "
                "wardrobe holds another suitable item for each of those, so choose a "
                "DIFFERENT one there. This is IN ADDITION to the rest: every slot in "
                "ALREADY SUGGESTED must still differ, including the ones you did "
                "change. Do not put any of them back. "), [], banned, set()
    # The picks BEFORE the swap, so what comes off can be struck from the prose — a
    # bullet praising the trousers we have just replaced is the advice being wrong
    # while the outfit is right. Same treatment the heat swap gets, for the same
    # reason.
    was = {c: picks.get(c) for c in CATEGORIES}
    swapped = swap_repeats(picks, repeated, wd, plan, list(prefs.rules), peak)
    for slot, alt in swapped:
        log.info("closet picks: %s repeated what was already shown, swapped for %s",
                 slot, alt)
        gone = wd.by_item.get(was.get(slot))
        if gone and picks.get(slot) != was.get(slot):
            banned = banned + [gone]
    # Nothing is recomputed after the swap on purpose: swap_repeats searches with
    # the same rules repeated_slots used to call the slot stuck, so every slot it
    # was handed has moved. A slot still holding what it held is one the wardrobe has
    # a single answer for, which is what same_again_line then says out loud.
    #
    # A slot the swap EMPTIED is a different matter, and there is exactly one: the
    # legs, when a dress goes into `base`. _hold_to_the_rules already computed
    # `covered` by then, so left unsaid the cleared bottoms reads as a slot the
    # wardrobe could not fill — and the shopping list would answer a dress by
    # recommending trousers. Raised by the pre-push reviewer, 2026-09-03.
    return "", swapped, banned, {c for c, alt in swapped if alt is None}
