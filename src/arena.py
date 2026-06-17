"""Local match harness for the Pokémon TCG AI Battle Challenge.

Runs agent-vs-agent games on the local `cg` simulator and reports win rates.
This is the evidence-generation tool: every matchup number in the writeup
should come from here.

An "agent" here is any callable `agent(obs_dict) -> list[int]`, exactly the
contract the competition's `main.py` must satisfy. The first call passes
`obs["select"] is None`; the agent must then return its 60-card deck list.

Usage (from repo root, with `source ~/python/bin/activate`):

    from src.arena import load_agent, run_matchup, random_agent

    a = load_agent("agents/lucario.py")        # loads main.py-style file
    b = random_agent
    res = run_matchup(a, A_DECK, b, B_DECK, games=100)
    print(res)
"""

from __future__ import annotations

import glob
import importlib.util
import os
import random
import sys
import time
from dataclasses import dataclass, field

# --- Make the bundled cg/ engine importable -------------------------------
# The simulator lib lives in the unzipped sample submission. Add its parent
# so `import cg.api` / `import cg.game` resolve to the real native engine.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CG_PARENT_CANDIDATES = [
    os.path.join(_REPO_ROOT, "data", "sim", "sample_submission"),
    # Kaggle fallbacks, harmless locally:
    "/kaggle/input/competitions/pokemon-tcg-ai-battle/sample_submission",
]


def _ensure_cg_importable() -> str:
    for parent in _CG_PARENT_CANDIDATES:
        if os.path.isdir(os.path.join(parent, "cg")):
            if parent not in sys.path:
                sys.path.insert(0, parent)
            return parent
    # last resort: glob search under /kaggle/input
    for pat in ["/kaggle/input/**/sample_submission", "/kaggle/input/**/cg-lib"]:
        for m in glob.glob(pat, recursive=True):
            if os.path.isdir(os.path.join(m, "cg")):
                sys.path.insert(0, m)
                return m
    raise FileNotFoundError(
        "Could not locate the cg/ engine folder. Expected it under "
        "data/sim/sample_submission/cg"
    )


_CG_PARENT = _ensure_cg_importable()

from cg.api import to_observation_class  # noqa: E402
from cg.game import battle_finish, battle_select, battle_start  # noqa: E402


# --- Agent loading --------------------------------------------------------

def load_agent(path: str):
    """Load a competition-style main.py file and return its `agent` callable.

    The file is executed with its own directory on sys.path so a sibling
    `deck.csv` (if the agent reads one) resolves correctly.
    """
    path = os.path.abspath(path)
    mod_dir = os.path.dirname(path)
    added = False
    if mod_dir not in sys.path:
        sys.path.insert(0, mod_dir)
        added = True
    try:
        spec = importlib.util.spec_from_file_location(
            f"_agent_{abs(hash(path))}", path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if added:
            sys.path.remove(mod_dir)
    if not hasattr(module, "agent"):
        raise AttributeError(f"{path} has no `agent` function")
    return module.agent


def load_agent_with_deck(agent_path: str, deck_path: str):
    """Load an agent whose main.py reads `deck.csv` from its own directory.

    Copies the agent file and the chosen deck.csv into a temp dir, then imports
    from there so the agent's `read_deck_csv()` / module-level deck read resolves.
    Returns (agent_callable, deck_list).
    """
    import shutil
    import tempfile

    deck = [int(x) for x in open(deck_path).read().split() if x.strip()]
    tmp = tempfile.mkdtemp(prefix="agent_")
    shutil.copy(agent_path, os.path.join(tmp, "main.py"))
    with open(os.path.join(tmp, "deck.csv"), "w") as f:
        f.write("\n".join(map(str, deck)) + "\n")

    cwd = os.getcwd()
    os.chdir(tmp)  # agents read "deck.csv" relative to cwd at import time
    try:
        sys.path.insert(0, tmp)
        spec = importlib.util.spec_from_file_location(
            f"_agent_{abs(hash(tmp))}", os.path.join(tmp, "main.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        os.chdir(cwd)
        if tmp in sys.path:
            sys.path.remove(tmp)
    if not hasattr(module, "agent"):
        raise AttributeError(f"{agent_path} has no `agent` function")
    return module.agent, deck


def make_random_agent(deck: list[int]):
    """A random-but-legal agent bound to a deck (returns deck on first call)."""

    def random_agent(obs_dict):
        obs = to_observation_class(obs_dict)
        if obs.select is None:
            return deck
        n = len(obs.select.option)
        k = obs.select.maxCount
        return random.sample(range(n), k) if k > 0 else []

    return random_agent


# --- Game + matchup runner ------------------------------------------------

@dataclass
class MatchupResult:
    games: int = 0
    completed: int = 0
    a_wins: int = 0
    b_wins: int = 0
    draws: int = 0
    errors: int = 0
    total_steps: int = 0
    error_examples: list[str] = field(default_factory=list)

    @property
    def a_win_rate(self) -> float:
        decisive = self.a_wins + self.b_wins
        return self.a_wins / decisive if decisive else 0.0

    @property
    def avg_steps(self) -> float:
        return self.total_steps / self.completed if self.completed else 0.0

    def __str__(self) -> str:
        return (
            f"games={self.games} A={self.a_wins} B={self.b_wins} "
            f"draws={self.draws} err={self.errors} "
            f"A_winrate={self.a_win_rate:.3f} avg_steps={self.avg_steps:.1f}"
        )


def play_game(agent0, deck0, agent1, deck1, max_steps: int = 2000):
    """Play one game. Returns (result, steps, error_str).

    result: 0 -> player0 wins, 1 -> player1 wins, 2 -> draw, None -> error.
    Wraps each agent call so a crash is recorded as a loss for that side
    rather than killing the whole run (matches competition reality: crash=lose).
    """
    try:
        obs, start_data = battle_start(deck0, deck1)
        if obs is None:
            return None, 0, f"battle_start_failed:{start_data.errorPlayer}:{start_data.errorType}"
        for step in range(max_steps + 1):
            obc = to_observation_class(obs)
            if obc.current.result >= 0:
                battle_finish()
                return obc.current.result, step, ""
            agent = agent0 if obc.current.yourIndex == 0 else agent1
            try:
                selection = agent(obs)
            except Exception as e:  # crashing player loses
                loser = obc.current.yourIndex
                battle_finish()
                return (1 - loser), step, f"agent{loser}_crash:{type(e).__name__}:{e}"
            obs = battle_select(selection)
        battle_finish()
        return 2, max_steps, "max_steps_reached"
    except Exception as e:
        try:
            battle_finish()
        except Exception:
            pass
        return None, 0, f"engine_error:{type(e).__name__}:{e}"


def run_matchup(agent_a, deck_a, agent_b, deck_b, games: int = 100,
                swap_sides: bool = True, seed: int | None = 0) -> MatchupResult:
    """Run `games` games of A vs B. If swap_sides, A plays player0 and
    player1 on alternating games to cancel first-player advantage."""
    if seed is not None:
        random.seed(seed)
    res = MatchupResult(games=games)
    for g in range(games):
        a_is_p0 = (g % 2 == 0) or not swap_sides
        if a_is_p0:
            result, steps, err = play_game(agent_a, deck_a, agent_b, deck_b)
        else:
            result, steps, err = play_game(agent_b, deck_b, agent_a, deck_a)

        if result is None:
            res.errors += 1
            if len(res.error_examples) < 5:
                res.error_examples.append(err)
            continue
        res.completed += 1
        res.total_steps += steps
        if err and len(res.error_examples) < 5:
            res.error_examples.append(err)  # e.g. a crash that still resolved
        if result == 2:
            res.draws += 1
        else:
            winner_is_a = (result == 0) == a_is_p0
            if winner_is_a:
                res.a_wins += 1
            else:
                res.b_wins += 1
    return res


if __name__ == "__main__":
    # Smoke test: random vs random with the sample deck.
    deck_path = os.path.join(_CG_PARENT, "deck.csv")
    deck = [int(x) for x in open(deck_path).read().split() if x.strip()]
    a = make_random_agent(deck)
    b = make_random_agent(deck)
    t0 = time.time()
    res = run_matchup(a, deck, b, deck, games=20)
    print(res)
    print(f"elapsed: {time.time()-t0:.1f}s")
