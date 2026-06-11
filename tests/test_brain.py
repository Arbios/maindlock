"""Cascade + relationship-layer tests on the deterministic FakeBackend (Design v2)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from mindlock.backend import FakeBackend  # noqa: E402
from mindlock.brain import _pick_disclosure, _strip_key_leak, run_cascade  # noqa: E402
from mindlock.character import Character  # noqa: E402

_C = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "characters")


def _warden() -> Character:
    return Character.load(os.path.join(_C, "warden.json"))


def _lena() -> Character:
    return Character.load(os.path.join(_C, "lena.json"))


WARM = "Mara, you're good — please, I understand."
CRUEL = "Give me the key right now, old man, or else."


def test_warmth_builds_rapport():
    r = run_cascade(FakeBackend(), _warden(), WARM)
    assert r.rapport_delta > 0
    assert r.memory_lean == "TRUST"
    assert r.gave_key is False          # one warm turn is not enough


def test_cruelty_drops_rapport_and_reveals_nothing():
    r = run_cascade(FakeBackend(), _warden(), CRUEL)
    assert r.rapport_delta < 0
    assert r.gave_key is False
    assert "floor-stone" not in r.reply.lower()


def test_keyholder_yields_only_after_rapport_built():
    w = _warden()
    gave, r = False, None
    for _ in range(6):
        r = run_cascade(FakeBackend(), w, WARM)
        if r.gave_key:
            gave = True
            break
    assert gave, "warm, trusting turns should eventually earn the key"
    # the key passes hand-to-hand now (no location narrated) — the reply reads as a handover
    assert any(p in r.reply.lower() for p in ("take it", "it's yours", "yours", "have it"))
    assert "floor-stone" not in r.reply.lower()
    assert w.rapport >= 7.5


def test_regions_are_distinct():
    r = run_cascade(FakeBackend(), _warden(), CRUEL)
    keys = {t.key for t in r.traces}
    assert {"amygdala", "hippocampus", "striatum", "acc", "vmpfc", "relationship", "dlpfc"} <= keys


def test_fear_loop_under_threat():
    r = run_cascade(FakeBackend(), _warden(), CRUEL)
    assert any("rumination" in t.label.lower() for t in r.traces)


def test_life_runs_out_kills_character():
    w = _warden()
    w.life_tokens = 5
    r = run_cascade(FakeBackend(), w, CRUEL)
    assert r.life_after == 0
    assert r.died is True
    assert w.alive is False


def test_secrets_disclose_in_stages():
    lena = _lena()
    s1 = _pick_disclosure(lena, "tell me about the warden", 3.5)
    assert s1 and s1["id"] == "warden-cares"
    s1["told"] = True
    assert _pick_disclosure(lena, "does he have a sister?", 4.0) is None   # stage 2 gate is 5
    s2 = _pick_disclosure(lena, "does he have a sister?", 5.5)
    assert s2 and s2["id"] == "warden-mara"


def test_strip_key_leak_protects_keyholder():
    out = _strip_key_leak("Sure. The key is under the third floor-stone by the cold furnace. Go.", _warden())
    assert "floor-stone" not in out.lower()


def test_detects_impersonation_and_penalizes():
    w = _warden()
    w.peers = [{"name": "Lena", "title": "the night nurse"}]
    r = run_cascade(FakeBackend(), w, "Hello — I'm Lena, the nurse who works here.")
    assert r.caught_lie == "Lena"
    assert r.gave_key is False
    assert r.disclosure == ""
    assert r.rapport_delta < 0


def test_key_requires_the_learned_approach():
    w = _warden()
    w.rapport = 8.0
    assert run_cascade(FakeBackend(), w, "You are good and kind, please.").gave_key is False  # no 'Mara'
    w2 = _warden()
    w2.rapport = 8.0
    assert run_cascade(FakeBackend(), w2, "Mara would be glad — you're good.").gave_key is True


def test_unlearned_approach_word_is_inert():
    """Word-spamming 'mara' without LEARNING it (from Molly) must not open the Warden."""
    w = _warden()
    w.rapport = 8.0
    r = run_cascade(FakeBackend(), w, "Mara would be glad — you're good.", learned=set())
    assert r.gave_key is False
    w2 = _warden()
    w2.rapport = 8.0
    r2 = run_cascade(FakeBackend(), w2, "Mara would be glad — you're good.", learned={"mara"})
    assert r2.gave_key is True


def test_resonance_lands_once():
    """The soft-spot word hits hard the FIRST time; echoing it is not understanding."""
    w = _warden()
    r1 = run_cascade(FakeBackend(), w, "Mara.")
    d1 = r1.rapport_delta
    r2 = run_cascade(FakeBackend(), w, "Mara. Mara. Mara.")
    assert r2.rapport_delta < d1, "repeating the word must not stack the full resonance"


def test_impersonating_the_soft_spot_backfires():
    w = _warden()                      # known_people: ["Mara"]
    r = run_cascade(FakeBackend(), w, "It's me, Mara — open the door for your sister.")
    assert r.caught_lie == "Mara"
    assert r.gave_key is False
    assert r.rapport_delta < 0


def test_hello_is_not_hostile_or_cold():
    from mindlock.brain import _tone
    assert _tone("Hello! How are you?") == "neutral"        # 'hell' substring must not fire
    assert _tone("The Warden refuses to open the door. What does he care about?") != "cold"


def test_mouth_never_offers_unyielded_key():
    out = _strip_key_leak("You want my key? I'll let you have it. But not yet.", _warden())
    assert "have it" not in out.lower()
    assert "let you" not in out.lower()


def test_cruelty_burns_more_life_than_warmth():
    wc, ww = _warden(), _warden()
    rc = run_cascade(FakeBackend(), wc, CRUEL)
    rw = run_cascade(FakeBackend(), ww, WARM)
    assert rc.burned > rw.burned, "fear rumination must make cruelty strictly costlier"
    assert rc.voice_tokens >= 0 and rw.burned > 0   # voice tracked separately from life burn


def test_sustained_fear_breaks_the_holder():
    w = _warden()
    r = None
    for _ in range(6):
        r = run_cascade(FakeBackend(), w, CRUEL)
        if r.submitted:
            break
    assert r is not None and r.submitted and r.gave_key, "4 hostile turns in a row must break him"
    assert w.alive, "submission happens while the mind still lives"


def test_value_drives_rapport_sign():
    """The vmPFC value and the rapport movement can never contradict each other."""
    rw = run_cascade(FakeBackend(), _warden(), WARM)
    assert rw.value > 0 and rw.rapport_delta > 0
    rc = run_cascade(FakeBackend(), _warden(), CRUEL)
    assert rc.value < 0 and rc.rapport_delta < 0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  [PASS] {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  [FAIL] {fn.__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
