"""Conservative prize-card deduction. Reusable by any agent.

Returns the inferred prized cards only when the visible zones make the deck
fully accounted for; otherwise returns None ("unknown"). A wrong prize guess
is worse than none — it makes forward search hallucinate winning lines that
the real game cannot reproduce. Based on the rank-3 Starmie agent's method.
"""

from collections import Counter

# AreaType.PRIZE == 6 in cg.api; matched defensively against name too.
_PRIZE_AREA = (6, "PRIZE", "Prize")


class PrizeTracker:
    def __init__(self, decklist):
        self._deck = Counter(int(c) for c in decklist)   # full 60
        self._prized = None          # Counter once inferred, else None
        self._last_prize_count = None

    def update(self, obs, obs_dict):
        state = obs.current
        if state is None:
            return
        yi = state.yourIndex
        player = state.players[yi]
        prize_count = len(player.prize)

        # Prizes were taken since last frame: drop the taken cards from the
        # known prized set (we now hold them). If we can't identify them, reset.
        if (self._prized is not None and self._last_prize_count is not None
                and prize_count < self._last_prize_count):
            taken_ids = self._prize_to_hand(obs_dict, yi)
            if taken_ids is None:
                self._prized = None
            else:
                removals = Counter(taken_ids)
                if any(self._prized.get(c, 0) < n for c, n in removals.items()):
                    self._prized = None
                else:
                    self._prized.subtract(removals)
                    self._prized += Counter()  # drop zero/negative
        self._last_prize_count = prize_count

        if self._prized is not None:
            return  # already known, keep it

        # Infer: full deck minus every visible card of ours == prized set,
        # but only when the deck is fully visible (deckCount known and the
        # remaining count matches the prize count exactly).
        seen = Counter()
        # hand
        for c in (player.hand or []):
            seen[c.id] += 1
        # active + bench (pokemon + their attached cards + pre-evolutions)
        for poke in player.active + player.bench:
            if poke is None:
                continue
            seen[poke.id] += 1
            for c in poke.energyCards:
                seen[c.id] += 1
            for c in poke.tools:
                seen[c.id] += 1
            for c in poke.preEvolution:
                seen[c.id] += 1
        # discard
        for c in player.discard:
            seen[c.id] += 1
        # stadium (ours if we played it — counted via deck delta; include all)
        for c in state.stadium:
            seen[c.id] += 1
        # in-flight effect card (e.g. a search card mid-resolution): subtract it
        eff = getattr(obs.select, "effect", None) if obs.select else None
        if eff is not None:
            seen[eff.id] += 1

        inferred = self._deck - seen
        inferred += Counter()  # drop negatives
        # Must exactly equal the prize count, and account for the hidden deck.
        if sum(inferred.values()) == prize_count and prize_count > 0:
            self._prized = inferred

    def _prize_to_hand(self, obs_dict, player_index):
        """Card IDs that moved out of PRIZE since last selection, from logs."""
        ids = []
        for log in obs_dict.get("logs", []):
            if log.get("fromArea") in _PRIZE_AREA and "cardId" in log:
                ids.append(log["cardId"])
        return ids or None

    def is_prized(self, card_id):
        if self._prized is None:
            return None
        return self._prized.get(card_id, 0) > 0

    def prized_cards(self):
        return self._prized.copy() if self._prized is not None else None

    def hidden_deck(self, deck_count):
        """Best guess of the cards still in our deck: full deck minus known
        prizes minus everything else visible isn't tracked here, so callers
        pass deck_count and we return prized-excluded ids padded as needed.
        Returns None if prizes unknown (caller should skip search then)."""
        if self._prized is None:
            return None
        # remaining deck = full deck - prized - visible-elsewhere. We only know
        # prized reliably; the engine wants exactly deck_count ids. Build from
        # full deck minus prized, then trust the engine to reconcile visible.
        remaining = self._deck - self._prized
        ids = list(remaining.elements())
        return ids if len(ids) >= deck_count else None


if __name__ == "__main__":
    # ponytail: self-check — deck of 4 known, 1 prized, rest visible -> infer it.
    from collections import Counter as _C
    pt = PrizeTracker([1, 1, 2, 3])
    assert pt.is_prized(2) is None  # nothing inferred yet
    # simulate: prized={3}, visible (hand+board+discard) = [1,1,2]
    class _P:  # minimal stubs
        prize = [None]            # 1 prize
        hand = []
        bench = []
        active = []
        discard = []
    class _St:
        yourIndex = 0
        stadium = []
        def __init__(s): s.players = [_P(), _P()]
    class _Sel:
        effect = None
    class _Obs:
        current = _St()
        select = _Sel()
    # put [1,1,2] in hand so deck(1,1,2,3) - seen(1,1,2) = {3} == 1 prize
    class _C2:
        def __init__(s, i): s.id = i; s.energyCards = []; s.tools = []; s.preEvolution = []
    o = _Obs(); o.current.players[0].hand = [_C2(1), _C2(1), _C2(2)]
    pt.update(o, {"logs": []})
    assert pt.is_prized(3) is True, pt.prized_cards()
    assert pt.is_prized(1) is False
    print("PrizeTracker self-check OK:", dict(pt.prized_cards()))
