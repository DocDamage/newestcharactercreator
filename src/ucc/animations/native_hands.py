"""Explicit hand anatomy for the measured Hips-object to MPFB rig family."""


def hand_pairs():
    """Return 38 roles: three thumb phalanges and four metacarpal/digit chains."""
    pairs = []
    for side, suffix in (("Left", ".L"), ("Right", ".R")):
        for joint in range(1, 4):
            pairs.append((f"{side}HandThumb{joint}", f"finger1-{joint}{suffix}",
                f"{side}HandThumb{joint+1}" if joint < 3 else f"{side}HandThumbEnd",
                f"finger1-{joint+1}{suffix}" if joint < 3 else None, "FORWARD"))
        for digit, name in enumerate(("Index", "Middle", "Ring", "Pinky"), 1):
            prefix = f"{side}Hand{name}"
            pairs.append((prefix+"1", f"metacarpal{digit}{suffix}", prefix+"2",
                          f"finger{digit+1}-1{suffix}", "FORWARD"))
            for joint in range(2, 5):
                pairs.append((prefix+str(joint), f"finger{digit+1}-{joint-1}{suffix}",
                    prefix+str(joint+1) if joint < 4 else prefix+"End",
                    f"finger{digit+1}-{joint}{suffix}" if joint < 4 else None, "FORWARD"))
    return pairs


HAND_TARGETS = frozenset(row[1] for row in hand_pairs())
