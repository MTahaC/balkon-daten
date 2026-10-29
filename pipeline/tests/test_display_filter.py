import pytest

from lod2pipe.__main__ import DISPLAY_FILTER


def evaluate(expr, zoom, props):
    """The subset of tippecanoe's feature-filter language DISPLAY_FILTER uses."""
    op, *args = expr
    if op == "any":
        return any(evaluate(a, zoom, props) for a in args)
    if op == "all":
        return all(evaluate(a, zoom, props) for a in args)
    key, value = args
    actual = zoom if key == "$zoom" else props[key]
    return {">=": actual >= value, "==": actual == value}[op]


@pytest.mark.parametrize(
    ("zoom", "area", "kept"),
    [
        (13, 49, False),
        (13, 50, True),
        (14, 24, False),
        (14, 25, True),
        (15, 1, True),
        (16, 1, True),
    ],
)
def test_smallest_parts_only_left_out_at_z13_and_z14(zoom, area, kept):
    assert evaluate(DISPLAY_FILTER, zoom, {"area": area}) is kept
