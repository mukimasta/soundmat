import pytest

from soundmat.perception import zones as Z


def test_counts():
    assert Z.NUM_ZONES == 224
    assert [Z.zones_in_ring(r) for r in range(8)] == [16, 16] + [32] * 6
    assert [z.index for z in Z.ZONES] == list(range(224))


def test_outer_zone_centers_follow_v1_sectors():
    for r in range(2, 8):
        for j in range(32):
            z = Z.zone(r, j)
            assert z.center_deg == pytest.approx(j * 11.25)
            assert z.span_deg == pytest.approx(11.25)


def test_inner_zone_boundaries_continue_outer_boundaries():
    """实物：内环的分界线是外环分界线每隔一条延伸进来，内环一区盖住外环第 2j+1、2j+2 区。"""
    outer_edges = {round((j + 0.5) * 11.25 % 360, 6) for j in range(32)}
    for r in (0, 1):
        for j in range(16):
            z = Z.zone(r, j)
            assert z.span_deg == pytest.approx(22.5)
            assert z.center_deg == pytest.approx((2 * j + 1.5) * 11.25)
            lo = (z.center_deg - z.span_deg / 2) % 360
            hi = (z.center_deg + z.span_deg / 2) % 360
            assert round(lo, 6) in outer_edges and round(hi, 6) in outer_edges
    # 第 0、1 环划分完全相同
    assert [Z.zone(0, j).center_deg for j in range(16)] == [Z.zone(1, j).center_deg for j in range(16)]


def test_lookup_and_radius():
    z = Z.zone_by_id("3:7")
    assert (z.ring, z.slot) == (3, 7)
    assert list(Z.ring_indices(1)) == list(range(16, 32))
    radii = [Z.zone(r, 0).radius for r in range(8)]
    assert radii == sorted(radii) and 0 < radii[0] < radii[-1] < 1
