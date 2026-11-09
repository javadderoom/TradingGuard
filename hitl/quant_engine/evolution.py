"""
TradingGuard HITL - Autonomous Quant Evolution & Machine Discovery Engine
Applies genetic programming / evolutionary rule search across the pure mathematical
state space without any human narrative or subjective heuristics.
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import random
import copy
import numpy as np
import pandas as pd

from .state_space import MathematicalStateSpace
from .rule_engine import QuantRule, FeaturePredicate
from .vectorized_backtester import VectorizedBacktester, BacktestResult


@dataclass
class EvolutionConfig:
    population_size: int = 50
    generations: int = 12
    min_predicates: int = 2
    max_predicates: int = 3
    crossover_prob: float = 0.50
    mutation_prob: float = 0.40
    elitism_ratio: float = 0.15
    min_trades_threshold: int = 10
    random_seed: int = 42


class QuantEvolutionEngine:
    """
    Autonomous genetic optimizer searching for high-fitness quantitative trading rules.
    """

    TP_GRID = [1.8, 2.2, 2.5, 3.0, 3.5, 4.0, 4.5]
    SL_GRID = [0.8, 1.0, 1.2, 1.5, 1.8, 2.0]
    BE_GRID = [None, 1.2, 1.5, 1.8, 2.0]
    TTL_GRID = [18, 24, 36, 48, 72]

    def __init__(
        self,
        symbol: str,
        state_df: pd.DataFrame,
        config: Optional[EvolutionConfig] = None,
        spread: Optional[float] = None
    ):
        self.symbol = symbol.upper()
        self.state_df = state_df
        self.cfg = config or EvolutionConfig()
        self.backtester = VectorizedBacktester(symbol=self.symbol, spread=spread)
        self.features = MathematicalStateSpace.get_feature_names()
        self.rng = random.Random(self.cfg.random_seed)
        np.random.seed(self.cfg.random_seed)

        # Pre-compute empirical quantiles for realistic threshold sampling
        self.feature_quantiles: Dict[str, np.ndarray] = {}
        for f in self.features:
            if f in self.state_df.columns:
                clean = self.state_df[f].dropna().values
                if len(clean) > 0:
                    self.feature_quantiles[f] = np.quantile(
                        clean, [0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95]
                    )

    def _sample_predicate(self) -> FeaturePredicate:
        """Samples a valid mathematical predicate from feature quantiles."""
        feat = self.rng.choice(self.features)
        quantiles = self.feature_quantiles.get(feat, np.array([0.0]))
        op = self.rng.choice(['<', '<=', '>', '>=', 'between'])

        if op == 'between' and len(quantiles) >= 2:
            idx1 = self.rng.randint(0, len(quantiles) - 2)
            idx2 = self.rng.randint(idx1 + 1, len(quantiles) - 1)
            thresh = (float(quantiles[idx1]), float(quantiles[idx2]))
        elif len(quantiles) > 0:
            if op == 'between':
                op = '<='
            thresh = float(self.rng.choice(quantiles))
        else:
            op = '<='
            thresh = 0.0

        return FeaturePredicate(feature=feat, op=op, threshold=thresh)

    def generate_random_rule(self, rule_id: str, direction: Optional[str] = None) -> QuantRule:
        """Synthesizes a random quantitative rule."""
        dir_val = direction or self.rng.choice(['BUY', 'SELL'])
        n_preds = self.rng.randint(self.cfg.min_predicates, self.cfg.max_predicates)

        # Pick distinct features
        used_feats = set()
        predicates = []
        for _ in range(n_preds * 2):
            pred = self._sample_predicate()
            if pred.feature not in used_feats:
                used_feats.add(pred.feature)
                predicates.append(pred)
            if len(predicates) >= n_preds:
                break

        tp = self.rng.choice(self.TP_GRID)
        sl = self.rng.choice(self.SL_GRID)
        be = self.rng.choice(self.BE_GRID)
        ttl = self.rng.choice(self.TTL_GRID)

        return QuantRule(
            rule_id=rule_id,
            direction=dir_val,
            predicates=predicates,
            tp_atr_mult=tp,
            sl_atr_mult=sl,
            be_ratchet_r=be,
            ttl_bars=ttl,
            cooldown_bars=6
        )

    def evaluate_fitness(self, rule: QuantRule) -> Tuple[float, BacktestResult]:
        """
        Evaluates risk-adjusted fitness with severe penalties for:
        - Statistical insignificance (< min_trades_threshold)
        - Sub-1.0 Profit Factor
        - Excessive Drawdown
        """
        res = self.backtester.run(self.state_df, rule)

        # 1. Reject if trade count is too low for statistical significance
        if res.total_fills < self.cfg.min_trades_threshold:
            penalty = -1000.0 + res.total_fills
            return penalty, res

        # 2. Reject if losing strategy
        if res.profit_factor < 1.0 or res.net_r <= 0.0:
            penalty = -500.0 + (res.profit_factor * 10.0)
            return penalty, res

        # 3. Multi-objective institutional fitness
        # Fitness = Sharpe * trade_frequency_factor * pf_surplus * (1 - dd_penalty)
        trade_freq_factor = min(1.0, res.total_fills / 30.0)
        pf_surplus = max(0.1, res.profit_factor - 0.9)
        dd_penalty = min(0.8, res.max_drawdown_r / 15.0)

        fitness = res.sharpe_ratio * trade_freq_factor * pf_surplus * (1.0 - dd_penalty)

        return float(fitness), res

    def _crossover(self, parent1: QuantRule, parent2: QuantRule, new_id: str) -> QuantRule:
        """Combines predicates and parameters from two parent rules."""
        child = copy.deepcopy(parent1)
        child.rule_id = new_id

        # Direction from parent1 or parent2
        child.direction = self.rng.choice([parent1.direction, parent2.direction])

        # Mix predicates
        all_preds = parent1.predicates + parent2.predicates
        # Deduplicate by feature
        unique_preds = {}
        for p in all_preds:
            if p.feature not in unique_preds:
                unique_preds[p.feature] = p

        sampled_count = self.rng.randint(self.cfg.min_predicates, self.cfg.max_predicates)
        sampled_keys = self.rng.sample(list(unique_preds.keys()), min(sampled_count, len(unique_preds)))
        child.predicates = [unique_preds[k] for k in sampled_keys]

        # Ensure child has at least min_predicates
        while len(child.predicates) < self.cfg.min_predicates:
            p_add = self._sample_predicate()
            if p_add.feature not in [p.feature for p in child.predicates]:
                child.predicates.append(p_add)

        # Mix parameters
        child.tp_atr_mult = self.rng.choice([parent1.tp_atr_mult, parent2.tp_atr_mult])
        child.sl_atr_mult = self.rng.choice([parent1.sl_atr_mult, parent2.sl_atr_mult])
        child.be_ratchet_r = self.rng.choice([parent1.be_ratchet_r, parent2.be_ratchet_r])
        child.ttl_bars = self.rng.choice([parent1.ttl_bars, parent2.ttl_bars])

        return child

    def _mutate(self, rule: QuantRule) -> QuantRule:
        """Applies stochastic mutations to a rule."""
        mutated = copy.deepcopy(rule)
        action = self.rng.choice([
            'perturb_threshold',
            'change_op',
            'replace_predicate',
            'add_predicate',
            'remove_predicate',
            'flip_direction',
            'mutate_param'
        ])

        if action == 'perturb_threshold' and mutated.predicates:
            idx = self.rng.randint(0, len(mutated.predicates) - 1)
            p = mutated.predicates[idx]
            quantiles = self.feature_quantiles.get(p.feature, np.array([0.0]))
            if p.op != 'between' and len(quantiles) > 0:
                p.threshold = float(self.rng.choice(quantiles))
            elif len(quantiles) >= 2:
                idx1 = self.rng.randint(0, len(quantiles) - 2)
                idx2 = self.rng.randint(idx1 + 1, len(quantiles) - 1)
                p.threshold = (float(quantiles[idx1]), float(quantiles[idx2]))

        elif action == 'change_op' and mutated.predicates:
            idx = self.rng.randint(0, len(mutated.predicates) - 1)
            p = mutated.predicates[idx]
            p.op = self.rng.choice(['<', '<=', '>', '>='])
            quantiles = self.feature_quantiles.get(p.feature, np.array([0.0]))
            if len(quantiles) > 0:
                p.threshold = float(self.rng.choice(quantiles))

        elif action == 'replace_predicate' and mutated.predicates:
            idx = self.rng.randint(0, len(mutated.predicates) - 1)
            mutated.predicates[idx] = self._sample_predicate()

        elif action == 'add_predicate' and len(mutated.predicates) < self.cfg.max_predicates:
            new_p = self._sample_predicate()
            if new_p.feature not in [p.feature for p in mutated.predicates]:
                mutated.predicates.append(new_p)

        elif action == 'remove_predicate' and len(mutated.predicates) > self.cfg.min_predicates:
            idx = self.rng.randint(0, len(mutated.predicates) - 1)
            mutated.predicates.pop(idx)

        elif action == 'flip_direction':
            mutated.direction = 'SELL' if mutated.direction == 'BUY' else 'BUY'

        elif action == 'mutate_param':
            mutated.tp_atr_mult = self.rng.choice(self.TP_GRID)
            mutated.sl_atr_mult = self.rng.choice(self.SL_GRID)
            mutated.be_ratchet_r = self.rng.choice(self.BE_GRID)
            mutated.ttl_bars = self.rng.choice(self.TTL_GRID)

        return mutated

    def run_evolution(
        self,
        verbose: bool = True
    ) -> List[Tuple[QuantRule, BacktestResult, float]]:
        """
        Executes the evolutionary cycle across generations.
        Returns top discovered rules sorted by fitness descending.
        """
        if verbose:
            print(f"🧬 Starting Autonomous Genetic Quant Evolution for {self.symbol}...")
            print(f"   Population: {self.cfg.population_size} | Generations: {self.cfg.generations}")

        # 1. Initialize population
        pop: List[QuantRule] = [
            self.generate_random_rule(f"R0_{i:03d}")
            for i in range(self.cfg.population_size)
        ]

        scored_pop: List[Tuple[QuantRule, BacktestResult, float]] = []

        for gen in range(self.cfg.generations):
            # Evaluate all individuals
            eval_results = []
            for rule in pop:
                fit, res = self.evaluate_fitness(rule)
                eval_results.append((rule, res, fit))

            # Sort descending by fitness
            eval_results.sort(key=lambda x: x[2], reverse=True)
            scored_pop = eval_results

            best_fit = scored_pop[0][2]
            best_res = scored_pop[0][1]
            profitable_count = sum(1 for _, r, f in scored_pop if f > 0)

            if verbose:
                print(
                    f"   Gen {gen + 1:2d}/{self.cfg.generations:2d} | "
                    f"Best Fit: {best_fit:6.2f} | "
                    f"WR: {best_res.win_rate:4.1f}% | "
                    f"Net R: {best_res.net_r:+6.1f}R | "
                    f"PF: {best_res.profit_factor:4.2f} | "
                    f"Trades: {best_res.total_fills:2d} | "
                    f"Profitable Rules: {profitable_count:2d}/{self.cfg.population_size}"
                )

            # Check if last generation
            if gen == self.cfg.generations - 1:
                break

            # Selection & Reproduction
            n_elite = max(2, int(self.cfg.population_size * self.cfg.elitism_ratio))
            new_pop: List[QuantRule] = [copy.deepcopy(item[0]) for item in scored_pop[:n_elite]]

            # Tournament selection pool
            pool = scored_pop[:max(n_elite * 2, int(self.cfg.population_size * 0.5))]

            while len(new_pop) < self.cfg.population_size:
                p1 = self.rng.choice(pool)[0]
                p2 = self.rng.choice(pool)[0]

                new_id = f"R{gen + 1}_{len(new_pop):03d}"

                if self.rng.random() < self.cfg.crossover_prob:
                    child = self._crossover(p1, p2, new_id)
                else:
                    child = copy.deepcopy(self.rng.choice([p1, p2]))
                    child.rule_id = new_id

                if self.rng.random() < self.cfg.mutation_prob:
                    child = self._mutate(child)

                new_pop.append(child)

            pop = new_pop

        # Filter and return unique high-fitness rules
        unique_results = []
        seen_formulas = set()
        for rule, res, fit in scored_pop:
            formula = rule.to_formula_str()
            if formula not in seen_formulas:
                seen_formulas.add(formula)
                unique_results.append((rule, res, fit))

        return unique_results
