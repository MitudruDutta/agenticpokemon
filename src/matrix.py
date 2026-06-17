"""Round-robin matchup matrix over all agent/deck pairs in the repo.

Each agent is paired with its own deck (same basename in agents/ and decks/).
Runs every ordered pair head-to-head and prints a win-rate matrix plus a
ranking. This is the core evidence table for the writeup.

Run:  python src/matrix.py [games]
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.arena import load_agent_with_deck, run_matchup  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_DIR = os.path.join(REPO, "agents")
DECKS_DIR = os.path.join(REPO, "decks")


def discover():
    """Return [(name, agent_path, deck_path)] for agents that have a deck."""
    out = []
    for fn in sorted(os.listdir(AGENTS_DIR)):
        if not fn.endswith(".py") or fn.startswith("_"):
            continue
        name = fn[:-3]
        deck = os.path.join(DECKS_DIR, f"{name}.csv")
        # map known aliases (agent basename vs deck basename)
        if not os.path.exists(deck):
            alias = {"lucario_baseline": "lucario"}.get(name)
            if alias:
                deck = os.path.join(DECKS_DIR, f"{alias}.csv")
        if os.path.exists(deck):
            out.append((name, os.path.join(AGENTS_DIR, fn), deck))
        else:
            print(f"  (skip {name}: no deck)")
    return out


def main(games: int = 60):
    entries = discover()
    print(f"Loading {len(entries)} agents...")
    loaded = {}
    for name, ap, dp in entries:
        try:
            agent, deck = load_agent_with_deck(ap, dp)
            loaded[name] = (agent, deck)
            print(f"  ok: {name} (deck {len(deck)})")
        except Exception as e:
            print(f"  FAIL {name}: {type(e).__name__}: {e}")

    names = list(loaded)
    n = len(names)
    wr = {a: {} for a in names}  # wr[a][b] = a's win-rate vs b
    overall = {a: [0, 0] for a in names}  # wins, decisive

    t0 = time.time()
    for i, a in enumerate(names):
        for b in names:
            if a == b:
                wr[a][b] = None
                continue
            ag_a, dk_a = loaded[a]
            ag_b, dk_b = loaded[b]
            res = run_matchup(ag_a, dk_a, ag_b, dk_b, games=games, seed=i)
            wr[a][b] = res.a_win_rate
            overall[a][0] += res.a_wins
            overall[a][1] += res.a_wins + res.b_wins

    # Print matrix
    print("\n=== WIN-RATE MATRIX (row beats col) ===")
    col_w = max(len(x) for x in names) + 1
    header = " " * (col_w + 1) + "".join(f"{b[:7]:>8}" for b in names)
    print(header)
    for a in names:
        row = f"{a:<{col_w}} "
        for b in names:
            v = wr[a][b]
            row += "    -   " if v is None else f"{v:8.2f}"
        print(row)

    # Ranking by overall win-rate
    print("\n=== OVERALL (vs whole field) ===")
    rank = sorted(names, key=lambda a: overall[a][0] / overall[a][1] if overall[a][1] else 0, reverse=True)
    for a in rank:
        w, d = overall[a]
        print(f"  {a:<{col_w}} win-rate {w/d:.3f}  ({w}/{d})")
    print(f"\nelapsed: {time.time()-t0:.1f}s  ({games} games/pair)")


if __name__ == "__main__":
    g = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    main(g)
