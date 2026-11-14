"""Preserve every actual rig rest matrix, including roll and helper bones."""


def capture_rest_frames(rig) -> dict:
    return {b.name:{"parent":b.parent.name if b.parent else None,
                    "matrix":[float(v) for row in b.matrix_local for v in row]}
            for b in rig.data.bones}


def same_rest_frames(original: dict, reopened: dict) -> bool:
    if type(original) is not dict or type(reopened) is not dict or set(original)!=set(reopened):return False
    for name,expected in original.items():
        actual=reopened[name]
        if (type(expected) is not dict or type(actual) is not dict or set(expected)!=set(actual) or
                set(actual)!={"parent","matrix"} or actual["parent"]!=expected["parent"]):return False
        a,b=actual["matrix"],expected["matrix"]
        if type(a) is not list or type(b) is not list or len(a)!=16 or len(b)!=16:return False
        if any(type(v) not in (int,float) or not -1e6<=v<=1e6 for v in a+b):return False
        if any(abs(x-y)>1e-6 for x,y in zip(a,b)):return False
    return True
