"""
closet.py — turning the user's ACTUAL wardrobe into an outfit.

Split out of llm.py on 2026-08-14, when that file passed 600 lines and had become
"everything that talks to the model". This is the coherent half: the vocabularies
that describe a garment, the validators that decide whether a pick is legitimate,
and the prompt that constrains the model to items the user owns.

The rules here exist because each was violated in the field, not in theory:
  - inner is a CLOSED role            "wear your tee under your tee" (2026-08-02)
  - a pick must be a role the ITEM allows, not a fixed category
                                       a shirt is outer in summer (2026-08-10)
  - the outer layer must be warm enough for the day
                                       a warmth-2 shirt outermost at 4C (2026-08-10)
  - slots the wardrobe cannot fill are named up front
                                       retries doubled latency to 35s (2026-08-13)

Depends one way on llm.py (transport + shared weather flags); llm.py does not
import this, so there is no cycle.
"""

import layers
import picks as pk
import stylist
import reroll
import scale
import prose
from llm import _chat, _parse_json, _peak_temp, _plan_temp, log
from picks import Prefs
from closet_prompt import _closet_prompt as _closet_prompt  # re-exported: tests reach it here
from closet_prompt import _prefers_block as _prefers_block
from vocab import CATEGORIES, NON_SLOT_TYPES


def wearable(closet: list[dict]) -> list[dict]:
    """The items that can fill an OUTFIT slot — everything except underpants.

    NON_SLOT_TYPES are real wardrobe entries that no slot in `picks` represents:
    the `inner` slot means the undershirt worn under the visible top, and the
    `footwear` slot means shoes. Before 2026-08-20 socks and briefs sat in groups
    that mapped to those slots, so nothing stopped the advisor recommending wool
    socks as the undershirt. They stay in the closet, they stay in the PACKING
    prompt — a packing list that forgets socks is worse than useless — and they are
    withheld here.

    Withholding rather than special-casing downstream is what makes the empty-slot
    line honest too: a closet holding only briefs now reports `inner` as a slot the
    wardrobe cannot fill, which is true — the user owns no undershirt.
    """
    return [i for i in closet if i.get("type") not in NON_SLOT_TYPES]


# Minimum warmth the OUTER layer must have at a given planning temperature.
#
# Roles alone are not enough, proven live 2026-08-10: given a shirt legitimately
# allowed to be `outer` in summer, the model put that warmth-2 shirt outermost at
# 4C in Ushuaia and left an available warmth-5 wool coat unused. Every pick was
# legal and the advice was still wrong — freedom to change role has to be bounded
# by whether the garment can actually handle the cold.
#
# Only `outer` is guarded: it is the layer that faces the weather. A thin base
# under a proper coat is fine at any temperature.
def _hold_to_the_rules(picks: dict, w: dict, prefs: "Prefs", wd: "pk.Wardrobe",
                       unsuitable: set, attempt: int
                       ) -> tuple[str, list[dict], set, set, tuple | None]:
    """Every check that judges the ANSWER, in the order they have to run.

    Returns a corrective note to retry with (empty when the outfit stands), the
    garments whose mention must now be struck from the prose, the slots something
    else already covers, the slots the wardrobe is genuinely short of, and the top
    this had to put on when the repairs left the wearer without one.

    The ORDER is load-bearing, and is why these live together rather than spread
    through the loop: each repair can empty the slot the next one depends on. A base
    cleared for breaking a rule leaves the undershirt as the outermost thing worn,
    and the underwear check has to see that.
    """
    plan = _plan_temp(w)
    rules_list = list(prefs.rules)

    # THE WEARER'S OWN RULES. Checked, not merely asked for: the prompt carries them
    # as prose, and prose in a prompt is followed most of the time, which is not the
    # same as followed.
    before_rules = {c for c, v in picks.items() if v}
    note, banned, combination = pk._enforce_user_rules(picks, wd.by_item, rules_list,
                                                       attempt)
    # Banned by the wearer: short of something LEGAL — unless something legal is
    # sitting there unused, in which case the choice was wrong, not the wardrobe.
    #
    # `combination` is excluded because it is neither. A pair rule says these two
    # garments do not go together, not that either is missing: the undershirt is
    # worn tomorrow under a different shirt. Counting it recommended buying a second
    # undershirt to somebody whose rule was "no inner with white Crew-neck T-shirt"
    # — and the rule would forbid that one too (2026-09-05).
    unsuitable = unsuitable | {
        c for c in before_rules if not picks.get(c) and c not in combination
        and not pk._has_suitable_alternative(c, picks, wd, plan, rules_list)
    }
    if note:
        return note, banned, set(), unsuitable, None

    # Trousers under a dress. _onepiece_conflicts repairs as it tests, so the picks
    # are never a dress over trousers; the retry is what fixes the BULLETS.
    note, banned = pk._enforce_onepiece(picks, wd.by_group, wd.by_item, banned, attempt)
    # Read off the garment actually in `base`, not off whether anything was cleared:
    # the model getting it right first time clears nothing, and keying on that
    # recorded a false bottoms gap on exactly the outfits that were correct.
    covered = {"bottoms"} if wd.by_group.get(picks.get("base")) == "onepiece" else set()
    # Emptied because of what it was worn WITH, so not a hole in the wardrobe —
    # `covered` is the one filter _missing_slots applies to all three of its
    # sources, which is what this needs.
    covered = covered | combination
    if note:
        return note, banned, covered, unsuitable, None

    # Legal role, wrong garment for the cold — see _OUTER_MIN_WARMTH.
    thin = pk._warmth_violations(picks, wd.by_item, plan)
    if thin:
        if attempt == 0:
            # On the scale the FAILING garment was numbered on — telling somebody
            # their warmth-3 jacket needs to be a 4 makes sense only in the units
            # they wrote the 3 in.
            worn = wd.by_item.get(picks.get("outer")) or {}
            need = scale.min_outer_warmth(plan, scale.graded_on(worn))
            return (f"The outer layer you chose is too thin for today — at this "
                    f"temperature the outermost garment needs warmth {need}/5 or "
                    f"more. Pick a warmer one, or null if you own nothing warmer. ",
                    banned, covered, unsuitable, None)
        for c in thin:
            log.warning("closet picks: %s was too thin for the cold, cleared", c)
            picks[c] = None
            # A judgement about the GARMENT — but only a gap if the wardrobe has no
            # warm enough, legal alternative.
            if not pk._has_suitable_alternative(c, picks, wd, plan, rules_list):
                unsuitable = unsuitable | {c}

    # MORE clothing than the day calls for (user, 2026-09-01: "today's highest is
    # estimated to be 31 degrees and it's showing items marked as 3. This is
    # horrible."). Every warmth check above this one is a FLOOR; the heat was only
    # ever ASKED about, in a prompt flag, and a request is followed most of the time.
    #
    # Runs after the thin check — they cannot both fire on one garment — and BEFORE
    # the top check, so a mid layer shed here can still be replaced by something
    # that covers the wearer.
    # The hottest hour the outfit has to survive. Already carries the wearer's
    # thermal offset, like plan, because both are read off the same adjusted day.
    peak = _peak_temp(w, plan)
    hot = pk._too_warm_slots(picks, wd.by_item, plan, peak)
    if hot:
        # No corrective retry here, unlike the checks above. The listing already
        # marks every garment the heat rules out, per role, so the model was told
        # BEFORE it answered; asking a second time cost a whole generation and in
        # 30 days of journal never once changed the answer the swap then made
        # anyway (2026-09-06). Repaired in code on every attempt.
        # The garments as they stand BEFORE the repair, so what is taken off can be
        # struck from the prose: a bullet recommending the fleece we have just shed
        # is the advice being wrong while the outfit is right, which is the half the
        # wearer actually reads. EVERY slot, not only the offending ones — swapping
        # a base for a dress also takes the trousers off.
        before = {c: picks.get(c) for c in CATEGORIES}
        for slot, alt in pk._cool_down(picks, wd, plan, rules_list, peak):
            log.warning("closet picks: %s was too warm for the heat, %s", slot,
                        f"swapped for {alt}" if alt else "shed")
            gone = wd.by_item.get(before.get(slot))
            if gone and picks.get(slot) != before.get(slot):
                banned = banned + [gone]
        # NOT a wardrobe gap. An empty mid layer on a hot day is the correct answer,
        # and recording it as evidence would have the shopping list recommending a
        # fleece to somebody who was told, correctly, not to wear one.

    # BEFORE the underwear check, and after everything that can empty a slot: an
    # outfit of trousers alone is not an outfit, and every repair above can leave
    # one. Dressing the torso here also lets the undershirt stay where it belongs,
    # under something, instead of being cleared for want of a cover.
    added = pk._enforce_a_top(picks, wd, plan, rules_list, peak)
    if added:
        log.warning("closet picks: nothing was left on top — added %s to %s",
                    added[1], added[0])
        # The top that covers the torso may be a DRESS, which covers the legs too.
        # The one-piece check ran before this one and cannot have seen it, so the
        # answer went out as trousers under a dress. Raised by the pre-push
        # reviewer, 2026-08-29.
        #
        # Struck from the PROSE as well, the way _enforce_onepiece does out of
        # retries: this runs after the last chance to regenerate, so the bullet
        # recommending those trousers would otherwise stand over an outfit that no
        # longer contains them.
        dropped = wd.by_item.get(picks.get("bottoms")) if picks.get("bottoms") else None
        if pk._onepiece_conflicts(picks, wd.by_group):
            covered = covered | {"bottoms"}
            if dropped:
                banned = [*banned, dropped]

    # LAST, because every repair above can take away the layer that was covering the
    # undershirt — a base cleared for breaking a rule, or an outer cleared for being
    # too thin. Checked first, an outfit of inner + an under-warm outer passed, the
    # warmth repair then removed the outer, and the bare undershirt was returned as
    # valid. The one check whose subject other repairs can create.
    note, banned = pk._enforce_underwear(picks, wd.by_item, banned, attempt)
    return note, banned, covered, unsuitable, added


_NO_REPLY = "no reply from the model"


async def _ask_model(prompt: str, reroll_: bool, attempt: int) -> tuple[dict | None, str]:
    """One generation, parsed. Returns (reply, note).

    The reply is None when nothing usable came back, and the note says which kind
    of nothing: _NO_REPLY when the model never answered — the loop stops there —
    or a corrective sentence for the next prompt when it answered in the wrong
    shape. The two used to be one `None`, so a vLLM still loading after a reboot
    was logged as "reply was not the required JSON" and asked again 4 ms later
    with a note about JSON (2026-09-06).
    """
    # 280 (plan estimate) truncated mid-JSON on a 6-item closet; 560 fit
    # 6 slots. Now 7 slots + up to 8 bullets, some carrying the longer
    # "(not in your closet yet)" generic-suggestion wording → ~650 worst
    # case; 768 leaves headroom (2026-07-15).
    raw = await _chat(
        [{"role": "user", "content": prompt}],
        max_tokens=1100,
        # A re-roll samples away from the peak. Measured 2026-09-03: four
        # identical requests returned the same base and the same bottoms
        # every time at 0.4, so an instruction to differ is argued with by
        # the sampler unless this moves too. Only the re-roll pays for it —
        # the day's first answer, which is the morning push and the one most
        # mornings are dressed from, is still 0.4.
        temperature=0.9 if reroll_ else 0.4,
    )
    if raw is None:
        # _chat has logged which kind of nothing. Not worth a second ask the same
        # second, and after a 45 s timeout a retry would push the request past
        # the phone's own 90 s ceiling.
        log.warning("closet attempt %s: no reply from the model — not retrying",
                    attempt + 1)
        return None, _NO_REPLY
    out = _parse_json(raw)
    if out is None or not isinstance(out.get("picks"), dict) or not isinstance(out.get("bullets"), list):
        # Logged because closet_outfit returning None is the difference between
        # the user seeing their own clothes and seeing generic advice, and it
        # was previously silent — a closetUsed=no line with no explanation
        # anywhere (2026-08-19).
        log.warning("closet attempt %s: reply was not the required JSON", attempt + 1)
        return None, "Your last reply was not the required JSON. "
    return out, ""


COLD_GAP = "warmth"     # not a slot: nothing owned is warm enough


def _with_cold_gap(missing: list[str], picks: dict, wd, plan_temp: float,
                   user_rules: list[dict], peak_temp: float) -> list[str]:
    """`missing`, plus COLD_GAP when nothing owned is warm enough. Not `outer`: the
    phone excuses and clears it by ANY torso layer, wrong for a missing raincoat."""
    if layers.too_cold_for_outfit(picks, wd, plan_temp, user_rules, peak_temp):
        return [*missing, COLD_GAP]
    return missing


async def closet_outfit(w: dict, gender: str, style: str, closet: list[dict],
                        prefs: "Prefs | None" = None) -> dict | None:
    """Outfit constrained to the user's items. Returns
    {"picks": {slot: id|None}, "text": str} with every pick VALIDATED against
    the closet, or None (caller falls back to generic advice, closetUsed=false).
    One retry on invalid/malformed output, per plan amendment 3.
    """
    # Underpants, bras, pyjamas and socks are wardrobe items that fill no slot —
    # dropped here, ONCE, so the prompt, the valid-id set and the empty-slot line
    # all see the same wardrobe. Filtering later would let the model name an item
    # the validator then rejects.
    prefs = prefs or Prefs()
    closet = wearable(closet)
    if not closet:
        log.warning("closet_outfit: nothing in the wardrobe can fill a slot")
        return None
    wd = pk._index(closet)
    # The same map _closet_prompt renders the listing with, built from the same list
    # in the same order. Two derivations of one thing is how a handle comes to mean
    # different garments on the two sides of the request.
    handles = pk.handles_for(closet)
    error_note = ""
    for attempt in range(2):
        out, error_note = await _ask_model(
            _closet_prompt(w, gender, style, closet, prefs, error_note),
            bool(prefs.shown), attempt)
        if out is None:
            if error_note == _NO_REPLY:
                break
            continue
        picks = pk.resolve_handles({c: out["picks"].get(c) for c in CATEGORIES},
                                   handles, wd.ids)
        # Snapshot BEFORE any repair runs. Every clearing step below — the duplicate
        # resolver, the role check, the warmth check, the rule repair — empties a
        # slot the model believed it had filled, and each of those is a wardrobe gap
        # the model will not report. Taken after one of them, that step's own
        # casualties would be invisible.
        filled_before = {c for c, v in picks.items() if v}
        unsuitable: set = set()
        unknown = pk._unknown_ids(picks, wd.ids)
        if unknown:
            error_note = unknown
            continue
        dup_note, picks = pk._enforce_one_slot_each(picks, wd.by_cat, attempt)
        if dup_note:
            error_note = dup_note
            continue
        # An item must sit in a slot its own category allows. The model's favourite
        # way to dodge the duplicate rule is to demote a tee into `inner` — which is
        # the original complaint, just relabelled.
        wrong = pk._slot_mismatches(picks, wd.by_roles)
        if wrong:
            if attempt == 0:
                detail = ", ".join(
                    f"{c} got an item that can only be {'/'.join(wd.by_roles.get(picks[c]) or [])}"
                    for c in wrong
                )
                error_note = (
                    f"Your last reply used items in roles they cannot play: {detail}. "
                    "Each wardrobe line lists that item's allowed roles — use an item "
                    "ONLY in one of its own listed roles. If nothing you own can fill a "
                    "slot, use null. "
                )
                continue
            moved = pk._relocate_mismatches(picks, wrong, wd.by_roles)
            for c, to in moved:
                log.info("closet picks: %s moved to %s — the role it can play", c, to)
            relocated = {frm for frm, _ in moved}
            for c in wrong:
                if c not in relocated:
                    log.warning("closet picks: %s held an item with nowhere to go, cleared", c)
            # A slot a garment was MOVED OUT OF is a filing correction, not a slot
            # the wardrobe could not fill. Left in the snapshot it read as the
            # latter: moving a mid-only hoodie out of `base` produced a good outfit
            # and reported a base gap, which the shopping list would answer by
            # recommending another shirt. A slot the model genuinely could not fill
            # still reaches `missing` by its own claim. Raised by the pre-push
            # reviewer, 2026-08-29.
            #
            # The TARGET joins it, because a relocation is also the model believing
            # that slot filled. Subtracting only the source hid a real gap: a thin
            # jacket moved into `outer` and then cleared by the warmth check was a
            # casualty of validation like any other, but the slot was no longer in
            # the snapshot for _missing_slots to notice.
            filled_before = (filled_before - relocated) | {to for _, to in moved}

        note, banned_labels, covered, unsuitable, added = _hold_to_the_rules(
            picks, w, prefs, wd, unsuitable, attempt)
        if note:
            error_note = note
            continue

        note, swapped, banned_labels, now_covered = reroll.hold_the_reroll(
            picks, w, prefs, wd, banned_labels, attempt)
        if note:
            error_note = note
            continue
        # The outfit as a STACK, LAST of all the repairs (layers.py): the re-roll
        # above can swap a short tee over a long undershirt, and every check before
        # it judged garments one at a time. Raised by the pre-push reviewer.
        banned_labels, put_on, cleared = await stylist.finish(picks, w, wd, prefs, banned_labels, added)

        def can_fill(slot: str, _p=picks) -> bool:
            return pk._has_suitable_alternative(slot, _p, wd, _plan_temp(w),
                                                list(prefs.rules))

        text = prose._assemble_text(out, banned_labels, prefs.closet_only, picks,
                                    wd.by_item)
        # A garment in the picture and not in the text reads as a bug in the app,
        # and this one is there precisely because the model did not put it there.
        text = layers.with_added(text, put_on, wd.by_item) if text and put_on else text
        # The bullets naming what these replaced were struck just above, so without
        # this the changed slots would have no words at all.
        if text and swapped:
            # Only swaps that survived the layer pass above — it can undo one.
            line = reroll.swapped_line([s for s in swapped if picks.get(s[0]) == s[1]], wd.by_item)
            if line:
                text = f"• {line}\n{text}"
        # Asked for something else and given the same thing back. By here that is
        # either honest — one pair of shoes is one pair of shoes — or the model
        # ignoring the instruction twice; the wearer cannot tell those apart from
        # the card, and an unexplained repeat is the exact symptom this change was
        # reported from. So it is said out loud either way.
        same_line = (reroll.same_again_line(picks, prefs.shown_map)
                     if text and prefs.shown else None)
        if same_line:
            text = f"• {same_line}\n{text}"
        if not text:
            log.warning("closet attempt %s: empty bullets", attempt + 1)
            error_note = "Your last reply had empty bullets. "
            continue
        return {"picks": picks, "text": text, "cleared": sorted(cleared),
                # `now_covered` unioned HERE rather than assigned above: the
                # re-roll swap can put a dress in `base` after _hold_to_the_rules
                # worked coverage out, and the legs it clears are not a gap.
                "missing": _with_cold_gap(
                    pk._missing_slots(out.get("missing"), picks, filled_before,
                                      covered | now_covered | cleared, can_fill, unsuitable),
                    picks, wd, _plan_temp(w), list(prefs.rules),
                    reroll.peak_temp(w, _plan_temp(w)))}
    # WITH the reason. Giving up costs the user their own clothes — under
    # closetOnly it empties the screen — and the line said only that it happened.
    # On 2026-08-29 a 15-item closet fell through here and there was nothing in the
    # journal to say which check had refused it.
    log.warning("closet_outfit gave up after %s attempts — %s — falling back to "
                "generic advice", 2, (error_note or "no reason recorded").strip()[:200])
    return None

