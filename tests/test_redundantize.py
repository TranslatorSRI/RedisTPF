from src.descender import redundantize_decs
def test_redundant_simple():
    d = {"a": {"a", "b", "c"}, "b": {"b", "d"}, "c": {"c", "e"}, "d": {"d"}, "e": {"e"}}
    d = redundantize_decs(d, "a")
    assert d == {"a": {"a", "b", "c", "d", "e"}, "b": {"b", "d"}, "c": {"c","e"}, "d": {"d"}, "e": {"e"}}

def test_diamond_redundant():
    d = {"a": {"a", "b", "c"}, "b": {"b", "d"}, "c": {"c", "d"}, "d": {"d"}}
    d = redundantize_decs(d, "a")
    assert d == {"a": {"a", "b", "c", "d"}, "b": {"b", "d"}, "c": {"c", "d"}, "d": {"d"}}