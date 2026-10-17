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


def test_inner_zone_faces_outer_center_and_boundaries_on_outer_midlines():
    outer_centers = {round(Z.zone(2, j).center_deg, 6) for j in range(32)}
    for r in (0, 1):
        for j in range(16):
            z = Z.zone(r, j)
            assert z.span_deg == pytest.approx(22.5)
            # 中心正对一个外环区域的中心（第一版的第 2j+1 扇区）
            assert round(z.center_deg, 6) in outer_centers
            assert z.center_deg == pytest.approx((2 * j + 1) * 11.25)
            # 两条边界落在相邻外环区域的中线（即外环区域中心）上
            lo = (z.center_deg - z.span_deg / 2) % 360
            hi = (z.center_deg + z.span_deg / 2) % 360
            assert round(lo, 6) in outer_centers and round(hi, 6) in outer_centers
    # 第 0、1 环划分完全相同
    assert [Z.zone(0, j).center_deg for j in range(16)] == [Z.zone(1, j).center_deg for j in range(16)]


def test_lookup_and_radius():
    z = Z.zone_by_id("3:7")
    assert (z.ring, z.slot) == (3, 7)
    assert list(Z.ring_indices(1)) == list(range(16, 32))
    radii = [Z.zone(r, 0).radius for r in range(8)]
    assert radii == sorted(radii) and 0 < radii[0] < radii[-1] < 1
