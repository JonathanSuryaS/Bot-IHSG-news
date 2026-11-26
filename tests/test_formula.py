from brief.formula import card, find, fmt_value, load, menu, run


def test_every_group_term_exists_and_has_fields():
    cfg = load()
    listed = {c for g in cfg["groups"] for c in g["terms"]}
    assert listed == set(cfg["terms"])
    for t in cfg["terms"].values():
        for f in ("name", "source", "meaning", "formula", "example", "read"):
            assert t.get(f), (t["name"], f)


def test_find_aliases():
    cfg = load()
    assert find(cfg, "roe") == "ROE"
    assert find(cfg, "PER") == "PE" and find(cfg, "p/e") == "PE"
    assert find(cfg, "pb") == "PBV"
    assert find(cfg, "payout ratio") == "DPR"
    assert find(cfg, "xyz") is None


def test_fmt_value():
    assert fmt_value(0.18742, "pct") == "18,74%"
    assert fmt_value(7.2748, "ratio") == "7,27x"
    assert fmt_value(56.278, "der") == "0,56x"
    assert fmt_value(462569588391936, "rp_t") == "Rp462,57 T"
    assert fmt_value(0.0, "pct_nonzero") is None
    assert fmt_value(None, "pct") is None


def test_run_without_network():
    assert "📚 Daftar rumus" in run([])
    out = run(["ROE"])
    assert "Laba bersih ÷ ekuitas" in out and "bukan rekomendasi" in out
    assert "belum ada" in run(["XYZ"])
    assert "BBRI sekarang: 18,74%" in card(load()["terms"]["ROE"], ("BBRI", "18,74%"))
    assert len(menu(load())) < 4000
