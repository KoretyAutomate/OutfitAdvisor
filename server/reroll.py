"""reroll.py — "show me something else", and making the answer differ.

Since the 2026-10-11 refactor: the prompt block, which slots repeated with an
alternative available (a soft issue in check.py), and the same-again line. The
code swap is gone — the advisor is told, and chooses again.

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
from vocab import CATEGORIES


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


