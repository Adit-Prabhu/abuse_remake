"""Classic mode must not change while Remastered grows. These state hashes were computed on
``main`` at 1773353 (before the Remastered campaign work) by this same script; every later change
has to reproduce them exactly."""

import pytest

from abuse_remake.engine.game import Game, WeaponCommand
from abuse_remake.engine.view import Inputs

GOLDEN = {  # (seed, difficulty): state hash after 300, 600 and 900 ticks
    (0, "hard"): ["be99eddb17e2d237b806bc2a40801a61fe437e59386b029ef2b2cf60e027a556",
                  "9d419a8426877afcb0ace965bf981e049e09264651506b2a1a84ec4c3ed9f12e",
                  "a5f9f0ccfacf76b672624129035261b1cd0ecc7fa2a94ef59a9c0e80ff2d1006"],
    (7, "easy"): ["e0dfa67e595a4965100e52cb19c910c9491b616a7e0981a9909dea3c482c55b0",
                  "c898056beb67d842c42fb5462c0da572fa6f21d0c946ddfaedce88790cce8c8e",
                  "463a1fa231547e8a298f0179d0841a925d85693c7e40c1a001e4908e8659bd55"],
    (123, "extreme"): ["720d84d852a64917a9285b7ec0dac453c7542dec863cfece78313671766ccd0a",
                       "2c5feeed469303061178e80fae9d14dfe8b4e393e8cf88fef5ae78c7d574216b",
                       "bab5f8b3b18e19b054c317966778d594185ab4bd3d3994b171e3c0679e38e36e"],
}


def play(seed: int, difficulty: str) -> list[str]:
    g = Game(seed=seed, difficulty=difficulty)
    out = []
    for i in range(900):
        p = g.player
        phase = (i // 60) % 4
        x = (1, 1, -1, 0)[phase] if i % 90 < 80 else 0
        inp = Inputs(x=x, y=-1 if i % 23 == 0 else (1 if i % 41 == 0 else 0), b1=int(i % 97 < 6),
                     b2=int(i % 3 == 0), pointer_x=p.x + (120 if phase != 2 else -120), pointer_y=p.y - 30 + i % 50)
        weapon = WeaponCommand(cycle=1) if i % 150 == 75 else None
        if i == 200:
            g.view.give_weapon(1)
            g.view.add_ammo(1, 5)
        g.step(inp, weapon)
        if (i + 1) % 300 == 0:
            out.append(g.state_hash())
    return out


@pytest.mark.parametrize("seed,difficulty", sorted(GOLDEN))
def test_classic_level_1_is_unchanged(seed, difficulty):
    assert play(seed, difficulty) == GOLDEN[(seed, difficulty)]
