"""handles.py — the short names the model answers with, and reading them back.

Split out of picks.py on 2026-09-01, at the 600-line ceiling. It is the cleanest
seam left in that module: everything else there judges an OUTFIT — which garment may
sit in which slot, whether it is warm enough, whether anybody is dressed at the end —
and this is about the NAMING the conversation uses to refer to garments at all.

The through-line is the same one picks.py carries: a model is asked, and then
checked. Here the asking is made easy enough to get right.
"""

def handles_for(closet: list[dict]) -> dict:
    """A SHORT name per wardrobe item, for the model to answer with.

    The ids the phone generates are UUIDs — `itm-e27af5ac-6454-44ed-9a7e-3ddb...`.
    Asking a model to copy one back exactly is asking it to transcribe 32 random hex
    digits, and it gets them nearly right: on 2026-08-29 and again on 2026-08-30 the
    same real garment came back as `...-9a7e-3ddb08307222` and `...-9a7a-5ed294a3f494`,
    matching for 25 characters and differing after. Both were rejected as unknown
    ids, both attempts, and the user was told their closet had nothing wearable —
    twice, on consecutive days, with fifteen items registered.

    So the prompt never shows a UUID. `i1`..`iN` in listing order, mapped back here.
    A short handle is one token, and a model that miscopies it produces something
    that is obviously not a handle rather than something that looks like an id.
    """
    return {f"i{n}": i["id"] for n, i in enumerate(closet, 1)}


def resolve_handles(picks: dict, handles: dict, ids: frozenset | set) -> dict:
    """Handles back to real ids, for everything downstream.

    A real id is passed through untouched: the model may answer with one from the
    prefers block or from its own memory of the conversation, and rejecting an id
    that names the right garment would be a validation error of our own making.
    Anything that is neither stays as it is, to be caught by _unknown_ids and
    reported to the model in the handle vocabulary it was given.
    """
    out = {}
    for slot, v in picks.items():
        key = str(v).strip() if v else v
        out[slot] = handles.get(key, v) if key and key not in ids else v
    return out


def _unknown_ids(picks: dict, valid_ids: frozenset | set) -> str:
    """A corrective note naming ids that are not in the wardrobe, or "" if all are.

    An id the model invented cannot be looked up, so every check after this one
    would be reading an empty dict and quietly passing.
    """
    bad = [v for v in picks.values() if v is not None and v not in valid_ids]
    if not bad:
        return ""
    return (f"Your last reply used ids not present in the wardrobe: {bad}. "
            "Use ONLY listed ids or null. ")
