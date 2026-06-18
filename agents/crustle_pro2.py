"""crustle_pro: a deeply-tuned Crustle stall-wall agent.

Crustle (card 345) walls the ex-heavy meta for free via its ability
"Mysterious Rock Inn" (prevents all damage from the opponent's ex Pokemon),
and it has a real 120-damage attack (Superb Scissors, {G} + 2 colorless) whose
damage ignores the opponent's effects. The public sample Crustle bot only
heals and ranks attacking dead last, so it grinds games it could close and
loses the prize race vs decks it can't out-stall.

This policy keeps the wall but plays to WIN the prize race:
  - evolve Dwebble -> Crustle fast (Ascension searches it out),
  - load 3 energy including grass so Superb Scissors comes online,
  - ATTACK with Superb Scissors whenever ready (take prizes, not just stall),
  - heal (Jumbo Ice / Cook) only when it is efficient (real damage + energy),
  - keep a bench backup so a KO never ends the game on an empty board,
  - choose to go second (a wall wants the opponent to commit first),
  - take a lethal / game-winning KO above everything else.

Design informed by analysis of the meta; all scoring is original.
"""

import os

from cg.api import (
    AreaType, CardType, EnergyType, Observation, OptionType, SelectContext,
    Card, Pokemon, all_card_data, to_observation_class,
)

# --- card ids -------------------------------------------------------------
DWEBBLE = 344
CRUSTLE = 345
JUMBO_ICE = 1147
HERO_CAPE = 1159
BATTLE_CAGE = 1264
COOK = 1212
CHEREN = 1224
BUDDY_POFFIN = 1086
GROW_GRASS = 18
MIST_ENERGY = 11
SPIKY_ENERGY = 14
BASIC_GRASS = 1

CARD_TABLE = {c.cardId: c for c in all_card_data()}


def read_deck_csv() -> list[int]:
    path = "deck.csv"
    if not os.path.exists(path):
        path = "/kaggle_simulations/agent/deck.csv"
    with open(path, "r") as f:
        return [int(x) for x in f.read().split() if x.strip()][:60]


def get_card(obs: Observation, area: AreaType, index: int, player_index: int):
    state = obs.current
    p = state.players[player_index]
    if area == AreaType.DECK and obs.select.deck is not None:
        return obs.select.deck[index]
    if area == AreaType.HAND:
        return p.hand[index]
    if area == AreaType.DISCARD:
        return p.discard[index]
    if area == AreaType.ACTIVE:
        return p.active[index]
    if area == AreaType.BENCH:
        return p.bench[index]
    if area == AreaType.PRIZE:
        return p.prize[index]
    if area == AreaType.STADIUM:
        return state.stadium[index]
    if area == AreaType.LOOKING and state.looking is not None:
        return state.looking[index]
    return None


def my_pokemon(obs, my_index):
    p = obs.current.players[my_index]
    out = []
    for poke in p.active:
        if poke is not None:
            out.append(poke)
    for poke in p.bench:
        if poke is not None:
            out.append(poke)
    return out


def has_grass(poke: Pokemon) -> bool:
    if EnergyType.GRASS in poke.energies:
        return True
    return any(c.id in (BASIC_GRASS, GROW_GRASS) for c in poke.energyCards)


def crustle_can_attack(poke) -> bool:
    # Superb Scissors costs {G} + 2 colorless = 3 energy incl. one grass.
    return poke is not None and poke.id == CRUSTLE and len(poke.energies) >= 3 and has_grass(poke)


def prize_value(poke) -> int:
    d = CARD_TABLE[poke.id]
    return 3 if d.megaEx else 2 if d.ex else 1


def read_deck():
    return read_deck_csv()


def agent(obs_dict: dict) -> list[int]:
    obs: Observation = to_observation_class(obs_dict)
    if obs.select is None:
        return read_deck()

    state = obs.current
    select = obs.select
    context = select.context
    me = state.yourIndex
    player = state.players[me]
    opp = state.players[1 - me]
    active = player.active[0] if player.active else None
    opp_active = opp.active[0] if opp.active else None

    bench_n = len(player.bench)
    my_prize = len(player.prize)
    opp_prize = len(opp.prize)
    crustle_on_field = sum(1 for p in my_pokemon(obs, me) if p.id == CRUSTLE)

    # Is our active Crustle ready + would Superb Scissors take a lethal/prize?
    active_can_attack = crustle_can_attack(active)
    lethal = False
    if active_can_attack and opp_active is not None:
        dmg = 120
        d = CARD_TABLE[opp_active.id]
        if d.weakness == EnergyType.GRASS:
            dmg *= 2
        elif d.resistance == EnergyType.GRASS:
            dmg -= 30
        lethal = opp_active.hp <= dmg

    scores = []
    for o in select.option:
        score = 0.0

        if context == SelectContext.MAIN:
            if o.type == OptionType.ATTACK:
                # Two attacks matter. Dwebble's Ascension searches the deck for
                # Crustle -> a free, reliable evolution (big consistency win,
                # esp. when no Crustle is in play yet). Crustle's Superb
                # Scissors is the 120-damage prize-taker. Distinguish by the
                # attacker: only a Crustle can do real damage.
                attacker_is_crustle = active is not None and active.id == CRUSTLE
                if attacker_is_crustle:
                    # Superb Scissors: take prizes; lethal KO is top priority.
                    score = 3000
                    if lethal:
                        score = 90000
                    if opp_prize <= 1:
                        score += 5000
                else:
                    # Dwebble Ascension: evolve into Crustle. Very high when we
                    # have no Crustle yet; still useful to thin toward more.
                    score = 26000 if crustle_on_field == 0 else 12000
            elif o.type == OptionType.ATTACH:
                card = get_card(obs, o.area, o.index, me)
                tgt = get_card(obs, o.inPlayArea, o.inPlayIndex, me)
                score = 2000
                if card is not None and card.id == HERO_CAPE:
                    # HP boost only on the active Crustle.
                    score = 4200 if (o.inPlayArea == AreaType.ACTIVE) else 0
                elif tgt is not None and tgt.id in (CRUSTLE, DWEBBLE):
                    # Build the active Crustle toward 3 energy (attack online).
                    need = 3 - len(tgt.energies)
                    is_grass = card is not None and card.id in (BASIC_GRASS, GROW_GRASS)
                    if o.inPlayArea == AreaType.ACTIVE and need > 0:
                        score = 2600
                        if is_grass and not has_grass(tgt):
                            score += 1500  # grass is required for the attack
                    else:
                        score = 1200
            elif o.type == OptionType.EVOLVE:
                # Evolving Dwebble -> Crustle is the engine; do it eagerly.
                score = 5000
            elif o.type == OptionType.PLAY:
                card = get_card(obs, AreaType.HAND, o.index, me)
                score = 600
                if card is None:
                    pass
                elif card.id == DWEBBLE:
                    # Keep a bench backup so a KO never ends the game; first
                    # couple of bodies are high priority, then taper off.
                    score = 4500 if (bench_n < 2 and crustle_on_field < 3) else 700
                elif card.id == BUDDY_POFFIN:
                    score = 4300 if bench_n < player.benchMax else 0
                elif card.id == JUMBO_ICE:
                    # Heal only when it actually matters: real damage + energy.
                    if active is not None and active.id == CRUSTLE and \
                            len(active.energies) >= 3 and (active.maxHp - active.hp) >= 50:
                        score = 3800 + (active.maxHp - active.hp)
                    else:
                        score = 0
                elif card.id == COOK:
                    if not state.supporterPlayed and active is not None and \
                            (active.maxHp - active.hp) >= 50:
                        score = 3400 + (active.maxHp - active.hp)
                    else:
                        score = 0
                elif card.id == CHEREN:
                    score = 2200 if not state.supporterPlayed else -5000
                elif card.id == BATTLE_CAGE:
                    stadium_id = state.stadium[0].id if state.stadium else 0
                    score = 1800 if stadium_id != BATTLE_CAGE else -1
            elif o.type == OptionType.ABILITY:
                # Crustle's Rock Inn (ex-damage block) is the whole defense;
                # always activate it.
                score = 20000
            elif o.type == OptionType.RETREAT:
                # Retreat only to promote a ready Crustle when the active is a
                # stuck non-Crustle (e.g. a lone Dwebble). Otherwise a wall
                # never wants to retreat.
                bench_has_ready = any(crustle_can_attack(p) or p.id == CRUSTLE
                                      for p in player.bench if p is not None)
                if active is not None and active.id != CRUSTLE and bench_has_ready:
                    score = 6000
                else:
                    score = -1

        else:
            # Sub-selections. Sensible defaults + a few key choices.
            score = 2000
            if o.type == OptionType.YES:
                # Go SECOND: a wall wants the opponent to commit first.
                score = -10 if context == SelectContext.IS_FIRST else 100
            elif o.type == OptionType.NO:
                score = 100 if context == SelectContext.IS_FIRST else 0
            elif o.type == OptionType.NUMBER:
                score = o.number or 0
            elif o.type == OptionType.CARD:
                card = get_card(obs, o.area, o.index, o.playerIndex)
                if card is None:
                    score = -10000
                elif context == SelectContext.SETUP_ACTIVE_POKEMON:
                    score = 10000 if card.id == DWEBBLE else 0
                elif context in (SelectContext.SETUP_BENCH_POKEMON,
                                 SelectContext.TO_BENCH, SelectContext.TO_FIELD):
                    score = 9000 if card.id == DWEBBLE else 1000
                elif context in (SelectContext.SWITCH, SelectContext.TO_ACTIVE):
                    # Promote a ready Crustle; otherwise a Crustle; else anything.
                    if o.playerIndex == me and isinstance(card, Pokemon):
                        if crustle_can_attack(card):
                            score = 3000
                        elif card.id == CRUSTLE:
                            score = 2000
                        else:
                            score = 1000 + len(card.energies) * 50
                    elif isinstance(card, Pokemon):
                        # Picking opponent's pokemon (gust): the juiciest target.
                        score = prize_value(card) * 1000 + (card.maxHp - card.hp)
                elif context == SelectContext.TO_HAND:
                    # Prefer pulling pieces we want: Dwebble/Crustle, heals.
                    if card.id in (DWEBBLE, CRUSTLE):
                        score = 2500
                    elif card.id in (JUMBO_ICE, COOK, CHEREN, BUDDY_POFFIN):
                        score = 2200
                    elif card.id in (BASIC_GRASS, GROW_GRASS):
                        score = 2100
                    else:
                        score = 1500
                elif context == SelectContext.DISCARD:
                    # Discard surplus energy / dead duplicates first.
                    if card.id in (BASIC_GRASS,):
                        score = 200
                    elif card.id in (DWEBBLE,) and crustle_on_field >= 3:
                        score = 150
                    else:
                        score = 100

        scores.append(score)

    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    out = []
    # When the selection is optional (minCount == 0), only take options that
    # are positively good — never play a card just because we can.
    threshold = 0.0 if select.minCount == 0 else -1.0
    for i in order:
        if len(out) >= select.maxCount:
            break
        if scores[i] > threshold or len(out) < select.minCount:
            out.append(i)
    # guarantee legality
    if len(out) < select.minCount:
        for i in range(len(select.option)):
            if i not in out:
                out.append(i)
            if len(out) >= select.minCount:
                break
    return out
