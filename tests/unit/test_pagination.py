from core.paginate import Paginate


def test_paginate_unit_page_1():
    p = Paginate(page=1, per_page=10)
    assert p.start == 0
    assert p.end == 10


def test_paginate_unit_page_2():
    p = Paginate(page=2, per_page=10)
    assert p.start == 10
    assert p.end == 20
