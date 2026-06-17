from __future__ import annotations

from cg.api import (
    AreaType,
    Observation,
    OptionType,
    SelectContext,
    SelectType,
    to_observation_class,
)


STYLE = "tempo"
PREFER_GO_FIRST = True

FIRE_ENERGY = 2
PSYCHIC_ENERGY = 5

DREEPY = 119
DRAKLOAK = 120
DRAGAPULT_EX = 121
FEZANDIPITI_EX = 140
LATIAS_EX = 184
BUDEW = 235
MEOWTH_EX = 1071

RARE_CANDY = 1079
UNFAIR_STAMP = 1080
BUDDY_BUDDY_POFFIN = 1086
NIGHT_STRETCHER = 1097
CRUSHING_HAMMER = 1120
ULTRA_BALL = 1121
POKE_PAD = 1152
LUCKY_HELMET = 1156
BOSS_ORDERS = 1182
CRISPIN = 1198
BROCK_SCOUTING = 1210
LILLIE_DETERMINATION = 1227
WATCHTOWER = 1256

JET_HEADBUTT = 153
PHANTOM_DIVE = 154
ITCHY_POLLEN = 323

DECK = [
    DREEPY, DREEPY, DREEPY, DREEPY,
    DRAKLOAK, DRAKLOAK, DRAKLOAK, DRAKLOAK,
    DRAGAPULT_EX, DRAGAPULT_EX, DRAGAPULT_EX,
    FEZANDIPITI_EX,
    LATIAS_EX,
    BUDEW, BUDEW,
    MEOWTH_EX,
    RARE_CANDY, RARE_CANDY,
    UNFAIR_STAMP,
    BUDDY_BUDDY_POFFIN, BUDDY_BUDDY_POFFIN, BUDDY_BUDDY_POFFIN, BUDDY_BUDDY_POFFIN,
    NIGHT_STRETCHER, NIGHT_STRETCHER,
    CRUSHING_HAMMER, CRUSHING_HAMMER, CRUSHING_HAMMER, CRUSHING_HAMMER,
    ULTRA_BALL, ULTRA_BALL, ULTRA_BALL, ULTRA_BALL,
    POKE_PAD, POKE_PAD, POKE_PAD,
    LUCKY_HELMET,
    BOSS_ORDERS, BOSS_ORDERS, BOSS_ORDERS,
    CRISPIN, CRISPIN, CRISPIN, CRISPIN,
    BROCK_SCOUTING, BROCK_SCOUTING,
    LILLIE_DETERMINATION, LILLIE_DETERMINATION, LILLIE_DETERMINATION, LILLIE_DETERMINATION,
    WATCHTOWER, WATCHTOWER,
    FIRE_ENERGY, FIRE_ENERGY, FIRE_ENERGY, FIRE_ENERGY,
    PSYCHIC_ENERGY, PSYCHIC_ENERGY, PSYCHIC_ENERGY, PSYCHIC_ENERGY,
]


class _DragapultPolicy:
    def __init__(self, obs: Observation):
        self.obs = obs
        self.select = obs.select
        self.state = obs.current
        self.yi = self.state.yourIndex if self.state is not None else 0
        self.oi = 1 - self.yi

    def choose(self) -> list[int]:
        option_count = len(self.select.option)
        if option_count == 0:
            return []

        special = self.choose_special()
        if special is not None:
            return special

        scored = [(self.score_option(i, opt), i) for i, opt in enumerate(self.select.option)]
        scored.sort(key=lambda x: (x[0], -x[1]), reverse=True)

        min_count = self.select.minCount
        max_count = self.select.maxCount
        if max_count <= 1:
            best_score, best_idx = scored[0]
            if min_count == 0 and best_score <= 0:
                return []
            return [best_idx]

        chosen = [idx for score, idx in scored if score > 0][:max_count]
        if len(chosen) < min_count:
            for _, idx in scored:
                if idx not in chosen:
                    chosen.append(idx)
                    if len(chosen) >= min_count:
                        break
        return chosen[:max_count]

    def choose_special(self):
        ctx = self.select.context
        if self.select.type == SelectType.YES_NO:
            yes_idx = self.first_option_of_type(OptionType.YES)
            no_idx = self.first_option_of_type(OptionType.NO)
            if ctx == SelectContext.IS_FIRST:
                return [yes_idx if PREFER_GO_FIRST else no_idx] if (yes_idx is not None and no_idx is not None) else [0]
            if ctx in (SelectContext.MULLIGAN, SelectContext.ACTIVATE, SelectContext.FIRST_EFFECT,
                       SelectContext.MORE_DEVOLVE, SelectContext.COIN_HEAD):
                return [yes_idx if yes_idx is not None else 0]
            return [yes_idx if yes_idx is not None else 0]

        if self.select.type == SelectType.COUNT:
            best_idx = 0
            best_number = -1
            for i, opt in enumerate(self.select.option):
                number = self.opt_value(opt, "number", i)
                if number > best_number:
                    best_idx = i
                    best_number = number
            return [best_idx]

        return None

    def first_option_of_type(self, option_type):
        for i, opt in enumerate(self.select.option):
            if self.opt_value(opt, "type") == option_type:
                return i
        return None

    def score_option(self, idx: int, opt) -> float:
        ctx = self.select.context
        typ = self.opt_value(opt, "type")

        if ctx == SelectContext.MAIN:
            return self.score_main_option(opt)
        if ctx in (SelectContext.SETUP_ACTIVE_POKEMON, SelectContext.TO_ACTIVE, SelectContext.SWITCH):
            return self.score_active_choice(opt)
        if ctx in (SelectContext.SETUP_BENCH_POKEMON, SelectContext.TO_BENCH, SelectContext.TO_FIELD):
            return self.score_bench_choice(opt)
        if ctx in (SelectContext.TO_HAND, SelectContext.LOOK):
            return self.score_card_to_hand(opt)
        if ctx in (SelectContext.DISCARD, SelectContext.DISCARD_CARD_OR_ATTACHED_CARD):
            return self.score_discard_choice(opt)
        if ctx in (SelectContext.EVOLVE, SelectContext.EVOLVES_TO):
            return self.score_evolve_choice(opt)
        if ctx in (SelectContext.ATTACH_TO, SelectContext.ATTACH_FROM, SelectContext.EFFECT_TARGET):
            return self.score_attach_or_target(opt)
        if ctx in (SelectContext.DAMAGE, SelectContext.DAMAGE_COUNTER, SelectContext.DAMAGE_COUNTER_ANY):
            return self.score_damage_target(opt)
        if ctx in (SelectContext.TO_DECK, SelectContext.TO_DECK_BOTTOM, SelectContext.TO_PRIZE):
            return self.score_low_value_card(opt)
        if self.select.type == SelectType.ATTACK or ctx == SelectContext.ATTACK:
            return self.score_attack_option(opt)
        if typ == OptionType.ATTACK:
            return self.score_attack_option(opt)
        if typ == OptionType.CARD:
            return self.score_card_to_hand(opt)
        return 1.0 / (idx + 1)

    def score_main_option(self, opt) -> float:
        typ = self.opt_value(opt, "type")
        source_id = self.option_card_id(opt)

        if typ == OptionType.EVOLVE:
            return self.score_evolve_choice(opt) + 760
        if typ == OptionType.ABILITY:
            card_id = self.option_card_id(opt)
            if card_id == DRAKLOAK:
                return 850
            if card_id == FEZANDIPITI_EX:
                return 820
            if card_id == MEOWTH_EX:
                return 790
            return 700
        if typ == OptionType.PLAY:
            return self.score_play_card(source_id, opt)
        if typ == OptionType.ATTACH:
            return self.score_attach_option(opt, source_id)
        if typ == OptionType.ATTACK:
            return self.score_attack_option(opt)
        if typ == OptionType.RETREAT:
            return self.score_retreat()
        if typ == OptionType.END:
            return -100
        if typ == OptionType.DISCARD:
            return 50
        return 0

    def score_play_card(self, card_id: int | None, opt) -> float:
        if card_id is None:
            return 0
        turn = self.turn()
        hand_size = len(self.hand_ids())
        setup_need = self.setup_need()
        energy_need = self.energy_need()

        if card_id == BUDDY_BUDDY_POFFIN:
            return 930 if self.bench_space() > 0 and self.count_ours(DREEPY) < 3 else 300
        if card_id == RARE_CANDY:
            return 940 if DRAGAPULT_EX in self.hand_ids() else 620
        if card_id == ULTRA_BALL:
            return 880 if setup_need > 0 else 420
        if card_id == POKE_PAD:
            return 820 if self.count_ours(DREEPY) < 2 or self.count_ours(DRAKLOAK) < 1 else 360
        if card_id == CRUSHING_HAMMER:
            return 720 if STYLE == "control" else 540
        if card_id == UNFAIR_STAMP:
            return 780
        if card_id == NIGHT_STRETCHER:
            return 630 if self.discard_has([DREEPY, DRAKLOAK, DRAGAPULT_EX, FIRE_ENERGY, PSYCHIC_ENERGY]) else 120
        if card_id == LUCKY_HELMET:
            return 460 if self.active_id() in (BUDEW, DRAGAPULT_EX, DREEPY, DRAKLOAK) else 180
        if card_id == WATCHTOWER:
            return 390

        if card_id == CRISPIN:
            return 900 if energy_need > 0 else 360
        if card_id == BROCK_SCOUTING:
            return 860 if setup_need > 0 else 320
        if card_id == LILLIE_DETERMINATION:
            if hand_size <= 3:
                return 840
            if turn <= 4 and setup_need > 0:
                return 650
            return 260
        if card_id == BOSS_ORDERS:
            return 760 if self.has_attack_option(PHANTOM_DIVE) or self.has_ready_dragapult() else 180

        if card_id == DREEPY:
            return 780 if self.count_ours(DREEPY) < 3 and self.bench_space() > 0 else 120
        if card_id == BUDEW:
            return 760 if turn <= 3 and self.count_ours(BUDEW) == 0 and self.bench_space() > 0 else 180
        if card_id == MEOWTH_EX:
            return 690 if self.bench_space() > 0 and self.setup_need() > 0 else 220
        if card_id == LATIAS_EX:
            return 560 if self.bench_space() > 0 and self.active_id() not in (DRAGAPULT_EX, BUDEW) else 160
        if card_id == FEZANDIPITI_EX:
            return 530 if self.bench_space() > 0 else 100
        if card_id in (DRAKLOAK, DRAGAPULT_EX):
            return 100
        return 100

    def score_attack_option(self, opt) -> float:
        attack_id = self.opt_value(opt, "attackId")
        if attack_id == PHANTOM_DIVE:
            return 735
        if attack_id == ITCHY_POLLEN:
            return 700 if self.turn() <= 6 else 420
        if attack_id == JET_HEADBUTT:
            return 610
        if attack_id is not None:
            return 520
        return 300

    def score_evolve_choice(self, opt) -> float:
        card_id = self.option_card_id(opt)
        target = self.target_pokemon(opt)
        if card_id == DRAGAPULT_EX:
            return 260 + (60 if self.is_active_target(opt) else 0)
        if card_id == DRAKLOAK:
            return 210 + (35 if self.is_active_target(opt) else 0)
        if target is not None and self.card_id(target) == DREEPY:
            return 150
        return 50

    def score_attach_option(self, opt, source_id: int | None) -> float:
        target = self.target_pokemon(opt)
        if target is None:
            return 0
        score = self.score_energy_target(target, source_id)
        if self.is_active_target(opt):
            score += 25
        return 610 + score

    def score_attach_or_target(self, opt) -> float:
        card_id = self.option_card_id(opt)
        if card_id in (FIRE_ENERGY, PSYCHIC_ENERGY):
            return 500 + self.score_card_need(card_id)
        target = self.target_pokemon(opt) or self.option_pokemon(opt)
        if target is not None:
            return 500 + self.score_energy_target(target, None)
        return self.score_card_to_hand(opt)

    def score_retreat(self) -> float:
        active = self.active_pokemon()
        if active is None:
            return 0
        active_id = self.card_id(active)
        if active_id == DRAGAPULT_EX:
            return 120
        best_bench = max([self.score_promote_pokemon(p) for p in self.your().bench], default=0)
        if active_id == BUDEW and self.turn() <= 4:
            return 60
        if best_bench >= 800:
            return 690
        if active_id in (DREEPY, DRAKLOAK, MEOWTH_EX, LATIAS_EX, FEZANDIPITI_EX) and best_bench > 500:
            return 610
        return 80

    def score_active_choice(self, opt) -> float:
        pokemon = self.option_pokemon(opt)
        card_id = self.card_id(pokemon) if pokemon is not None else self.option_card_id(opt)
        if card_id is None:
            return 0
        going_second = self.state is not None and self.state.firstPlayer != -1 and self.state.firstPlayer != self.yi
        if card_id == BUDEW and going_second:
            return 920
        if card_id == DRAGAPULT_EX:
            return 900 + (self.energy_attached_score(pokemon) if pokemon is not None else 0)
        if card_id == DREEPY:
            return 820
        if card_id == DRAKLOAK:
            return 780
        if card_id == BUDEW:
            return 760
        if card_id == LATIAS_EX:
            return 520
        if card_id == FEZANDIPITI_EX:
            return 480
        if card_id == MEOWTH_EX:
            return 400
        return 100

    def score_bench_choice(self, opt) -> float:
        card_id = self.option_card_id(opt)
        if card_id == DREEPY:
            return 900 - 50 * self.count_ours(DREEPY)
        if card_id == BUDEW:
            return 760 if self.turn() <= 4 and self.count_ours(BUDEW) < 1 else 350
        if card_id == LATIAS_EX:
            return 540
        if card_id == FEZANDIPITI_EX:
            return 510
        if card_id == MEOWTH_EX:
            return 500 if self.setup_need() > 0 else 220
        return self.score_card_need(card_id)

    def score_card_to_hand(self, opt) -> float:
        card_id = self.option_card_id(opt)
        return self.score_card_need(card_id)

    def score_card_need(self, card_id: int | None) -> float:
        if card_id is None:
            return 0
        hand = self.hand_ids()
        turn = self.turn()
        dreepy_count = self.count_ours(DREEPY)
        drakloak_count = self.count_ours(DRAKLOAK)
        dragapult_count = self.count_ours(DRAGAPULT_EX)
        need_energy = self.energy_need()

        hand_dreepy = hand.count(DREEPY)
        hand_drakloak = hand.count(DRAKLOAK)
        hand_dragapult = hand.count(DRAGAPULT_EX)

        if card_id == DRAGAPULT_EX:
            return 1000 if dragapult_count + hand_dragapult == 0 else 760
        if card_id == DRAKLOAK:
            if hand_drakloak >= 2:
                return 360
            if dreepy_count + hand_dreepy > drakloak_count + dragapult_count + hand_drakloak:
                return 920
            return 500
        if card_id == DREEPY:
            if dreepy_count + hand_dreepy < 2 and self.bench_space() > 0:
                return 990
            return 900 if dreepy_count < 2 and self.bench_space() > 0 else 460
        if card_id == BUDEW:
            return 840 if turn <= 3 and self.count_ours(BUDEW) == 0 else 240
        if card_id == RARE_CANDY:
            return 900 if DRAGAPULT_EX in hand or dreepy_count > 0 else 520
        if card_id == CRISPIN:
            return 880 if need_energy > 0 else 320
        if card_id == BROCK_SCOUTING:
            return 850 if self.setup_need() > 0 else 300
        if card_id == BUDDY_BUDDY_POFFIN:
            return 840 if turn <= 3 and self.bench_space() > 0 else 260
        if card_id == ULTRA_BALL:
            return 820 if self.setup_need() > 0 else 340
        if card_id == POKE_PAD:
            return 760 if dreepy_count < 2 or drakloak_count < 1 else 280
        if card_id == LILLIE_DETERMINATION:
            return 700 if len(hand) <= 4 else 260
        if card_id == BOSS_ORDERS:
            return 640 if self.has_ready_dragapult() else 200
        if card_id == CRUSHING_HAMMER:
            return 580 if STYLE == "control" else 360
        if card_id == NIGHT_STRETCHER:
            return 560 if self.discard_has([DREEPY, DRAKLOAK, DRAGAPULT_EX, FIRE_ENERGY, PSYCHIC_ENERGY]) else 170
        if card_id == UNFAIR_STAMP:
            return 540
        if card_id == LATIAS_EX:
            return 500 if self.count_ours(LATIAS_EX) == 0 else 80
        if card_id == FEZANDIPITI_EX:
            return 480 if self.count_ours(FEZANDIPITI_EX) == 0 else 80
        if card_id == MEOWTH_EX:
            return 460 if self.count_ours(MEOWTH_EX) == 0 and self.setup_need() > 0 else 120
        if card_id == FIRE_ENERGY:
            return 760 if self.needs_energy_type(FIRE_ENERGY) else 260
        if card_id == PSYCHIC_ENERGY:
            return 760 if self.needs_energy_type(PSYCHIC_ENERGY) else 260
        if card_id == WATCHTOWER:
            return 260
        return 100

    def score_discard_choice(self, opt) -> float:
        card_id = self.option_card_id(opt)
        if card_id is None:
            return 0
        hand = self.hand_ids()
        if card_id in (FIRE_ENERGY, PSYCHIC_ENERGY):
            return 850 if hand.count(card_id) > 1 or not self.needs_energy_type(card_id) else 120
        if card_id == WATCHTOWER:
            return 760
        if card_id == CRUSHING_HAMMER:
            return 650 if STYLE != "control" else 420
        if card_id == BOSS_ORDERS:
            return 630 if not self.has_ready_dragapult() else 160
        if card_id == LILLIE_DETERMINATION:
            return 600 if hand.count(LILLIE_DETERMINATION) > 1 else 180
        if card_id == BUDDY_BUDDY_POFFIN:
            return 560 if self.count_ours(DREEPY) >= 2 else 150
        if card_id == POKE_PAD:
            return 520 if self.count_ours(DREEPY) >= 2 else 130
        if card_id == ULTRA_BALL:
            return 420 if self.setup_need() <= 0 else 80
        if card_id == RARE_CANDY:
            return 390 if hand.count(RARE_CANDY) > 1 and DRAGAPULT_EX not in hand else 40
        if card_id == DRAGAPULT_EX:
            return 300 if hand.count(DRAGAPULT_EX) > 1 else 20
        if card_id in (DRAKLOAK, DREEPY):
            return 260 if self.count_ours(card_id) >= 2 else 30
        return 350

    def score_low_value_card(self, opt) -> float:
        return self.score_discard_choice(opt)

    def score_damage_target(self, opt) -> float:
        target = self.option_pokemon(opt)
        if target is None:
            return 0
        card_id = self.card_id(target)
        hp = self.hp(target)
        score = 600 - min(hp, 300)
        if card_id in (DREEPY, DRAKLOAK, BUDEW):
            score += 220
        if card_id in (DRAGAPULT_EX, FEZANDIPITI_EX, LATIAS_EX, MEOWTH_EX):
            score += 160
        if hp <= 60:
            score += 500
        elif hp <= 120:
            score += 240
        return score

    def score_promote_pokemon(self, pokemon) -> float:
        card_id = self.card_id(pokemon)
        if card_id == DRAGAPULT_EX:
            return 900 + self.energy_attached_score(pokemon)
        if card_id == BUDEW and self.turn() <= 5:
            return 760
        if card_id == DRAKLOAK:
            return 520
        if card_id == DREEPY:
            return 500
        return 250

    def score_energy_target(self, pokemon, source_id: int | None) -> float:
        card_id = self.card_id(pokemon)
        energies = self.energy_types(pokemon)
        score = 0
        if card_id == DRAGAPULT_EX:
            score += 180
            if source_id == FIRE_ENERGY and FIRE_ENERGY not in energies:
                score += 180
            elif source_id == PSYCHIC_ENERGY and PSYCHIC_ENERGY not in energies:
                score += 180
            elif len(energies) < 2:
                score += 90
        elif card_id in (DREEPY, DRAKLOAK):
            score += 145
            if source_id in (FIRE_ENERGY, PSYCHIC_ENERGY) and source_id not in energies:
                score += 120
        elif card_id == BUDEW:
            score += 25
        else:
            score += 55
        return score

    def energy_attached_score(self, pokemon) -> float:
        energies = self.energy_types(pokemon)
        return 80 * int(FIRE_ENERGY in energies) + 80 * int(PSYCHIC_ENERGY in energies) + 10 * len(energies)

    def setup_need(self) -> int:
        need = 0
        if self.count_ours(DREEPY) < 2:
            need += 2
        if self.count_ours(DRAKLOAK) + self.count_ours(DRAGAPULT_EX) < 1:
            need += 1
        if self.count_ours(DRAGAPULT_EX) < 1:
            need += 2
        return need

    def energy_need(self) -> int:
        best = 2
        for p in self.your_pokemon():
            card_id = self.card_id(p)
            if card_id in (DRAGAPULT_EX, DRAKLOAK, DREEPY):
                missing = int(FIRE_ENERGY not in self.energy_types(p)) + int(PSYCHIC_ENERGY not in self.energy_types(p))
                best = min(best, missing)
        return best

    def needs_energy_type(self, energy_card_id: int) -> bool:
        for p in self.your_pokemon():
            if self.card_id(p) in (DRAGAPULT_EX, DRAKLOAK, DREEPY) and energy_card_id not in self.energy_types(p):
                return True
        return False

    def has_ready_dragapult(self) -> bool:
        return any(self.card_id(p) == DRAGAPULT_EX and FIRE_ENERGY in self.energy_types(p)
                   and PSYCHIC_ENERGY in self.energy_types(p) for p in self.your_pokemon())

    def has_attack_option(self, attack_id: int) -> bool:
        return any(self.opt_value(opt, "type") == OptionType.ATTACK and self.opt_value(opt, "attackId") == attack_id
                   for opt in self.select.option)

    def count_ours(self, card_id: int) -> int:
        return sum(1 for p in self.your_pokemon() if self.card_id(p) == card_id)

    def discard_has(self, ids) -> bool:
        wanted = set(ids)
        return any(self.card_id(c) in wanted for c in self.your().discard)

    def bench_space(self) -> int:
        ps = self.your()
        return max(0, ps.benchMax - len(ps.bench))

    def active_id(self):
        active = self.active_pokemon()
        return self.card_id(active) if active is not None else None

    def active_pokemon(self):
        active = self.your().active
        if active:
            return active[0]
        return None

    def your(self):
        return self.state.players[self.yi]

    def opp(self):
        return self.state.players[self.oi]

    def turn(self) -> int:
        return self.state.turn if self.state is not None else 0

    def hand_ids(self) -> list[int]:
        hand = self.your().hand or []
        return [self.card_id(c) for c in hand if c is not None]

    def your_pokemon(self):
        ps = self.your()
        cards = []
        if ps.active:
            cards.extend([p for p in ps.active if p is not None])
        cards.extend(ps.bench)
        return cards

    def option_card_id(self, opt):
        explicit = self.opt_value(opt, "cardId")
        if explicit is not None:
            return explicit

        typ = self.opt_value(opt, "type")
        if typ in (OptionType.PLAY,):
            return self.card_id_at(AreaType.HAND, self.opt_value(opt, "index"), self.yi)
        if typ in (OptionType.ATTACH, OptionType.EVOLVE, OptionType.ABILITY, OptionType.DISCARD, OptionType.CARD,
                   OptionType.TOOL_CARD, OptionType.ENERGY_CARD):
            return self.card_id_at(self.opt_value(opt, "area"), self.opt_value(opt, "index"), self.opt_value(opt, "playerIndex", self.yi))
        return self.card_id_at(self.opt_value(opt, "area"), self.opt_value(opt, "index"), self.opt_value(opt, "playerIndex", self.yi))

    def option_pokemon(self, opt):
        return self.pokemon_at(self.opt_value(opt, "area"), self.opt_value(opt, "index"), self.opt_value(opt, "playerIndex", self.yi))

    def target_pokemon(self, opt):
        return self.pokemon_at(self.opt_value(opt, "inPlayArea"), self.opt_value(opt, "inPlayIndex"), self.yi)

    def is_active_target(self, opt) -> bool:
        return self.opt_value(opt, "inPlayArea") == AreaType.ACTIVE

    def card_id_at(self, area, index, player):
        card = self.card_at(area, index, player)
        return self.card_id(card)

    def pokemon_at(self, area, index, player):
        card = self.card_at(area, index, player)
        if card is not None and hasattr(card, "hp"):
            return card
        return None

    def card_at(self, area, index, player):
        if area is None or index is None or self.state is None:
            return None
        try:
            if area == AreaType.DECK:
                deck = self.select.deck or []
                return deck[index] if 0 <= index < len(deck) else None
            if area == AreaType.HAND:
                hand = self.state.players[player].hand or []
                return hand[index] if 0 <= index < len(hand) else None
            if area == AreaType.DISCARD:
                cards = self.state.players[player].discard
                return cards[index] if 0 <= index < len(cards) else None
            if area == AreaType.ACTIVE:
                cards = self.state.players[player].active
                return cards[index] if 0 <= index < len(cards) else None
            if area == AreaType.BENCH:
                cards = self.state.players[player].bench
                return cards[index] if 0 <= index < len(cards) else None
            if area == AreaType.PRIZE:
                cards = self.state.players[player].prize
                return cards[index] if 0 <= index < len(cards) else None
            if area == AreaType.STADIUM:
                cards = self.state.stadium
                return cards[index] if 0 <= index < len(cards) else None
            if area == AreaType.LOOKING:
                cards = self.state.looking or []
                return cards[index] if 0 <= index < len(cards) else None
        except Exception:
            return None
        return None

    @staticmethod
    def card_id(card):
        return getattr(card, "id", None) if card is not None else None

    @staticmethod
    def hp(pokemon) -> int:
        value = getattr(pokemon, "hp", None)
        return value if value is not None else 999

    @staticmethod
    def energy_types(pokemon) -> list[int]:
        return list(getattr(pokemon, "energies", []) or [])

    @staticmethod
    def opt_value(opt, name, default=None):
        value = getattr(opt, name, default)
        return default if value is None else value


def agent(obs_dict: dict, config=None) -> list[int]:
    obs: Observation = to_observation_class(obs_dict)
    if obs.select is None:
        return DECK.copy()
    return _DragapultPolicy(obs).choose()
