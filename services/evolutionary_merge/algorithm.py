from __future__ import annotations

import ast
import json
import math
import random
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Individual:
    genes: list[float]
    fitness: float | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    failed_reason: str | None = None

    @property
    def weights(self) -> list[float]:
        values = np.asarray(self.genes, dtype=np.float64)
        if not np.isfinite(values).all():
            raise ValueError("Genome contains NaN or infinity")
        shifted = values - values.max()
        exponent = np.exp(shifted)
        normalized = exponent / exponent.sum()
        return normalized.tolist()


@dataclass(frozen=True)
class EvolutionConfig:
    gene_count: int
    population_size: int = 8
    generations: int = 5
    mutation_rate: float = 0.2
    mutation_sigma: float = 0.15
    elite_count: int = 2
    tournament_size: int = 3
    patience: int = 3
    min_improvement: float = 1e-6
    random_seed: int = 42

    def validate(self) -> None:
        if self.gene_count < 2:
            raise ValueError("At least two adapters are required")
        if self.population_size < 4:
            raise ValueError("Population size must be at least four")
        if not 1 <= self.elite_count < self.population_size:
            raise ValueError("Elite count must be between one and population size")
        if self.generations < 1:
            raise ValueError("Generations must be positive")


@dataclass
class EvolutionResult:
    best: Individual
    history: list[dict[str, float]]
    completed_generations: int


FitnessFunction = Callable[[list[float]], tuple[float, dict[str, float]]]
CancelFunction = Callable[[], bool]


class GeneticOptimizer:
    def __init__(self, config: EvolutionConfig):
        config.validate()
        self.config = config
        self.random = random.Random(config.random_seed)
        self.np_random = np.random.default_rng(config.random_seed)

    def initial_population(self) -> list[Individual]:
        population = [Individual([0.0] * self.config.gene_count)]
        population.extend(
            Individual(self.np_random.normal(0, 1, self.config.gene_count).tolist())
            for _ in range(self.config.population_size - 1)
        )
        return population

    def evaluate(self, population: list[Individual], fitness_fn: FitnessFunction) -> None:
        for individual in population:
            if individual.fitness is not None or individual.failed_reason:
                continue
            try:
                fitness, metrics = fitness_fn(individual.weights)
                if not math.isfinite(fitness) or not all(math.isfinite(v) for v in metrics.values()):
                    raise ValueError("Fitness contains NaN or infinity")
                individual.fitness = float(fitness)
                individual.metrics = {key: float(value) for key, value in metrics.items()}
            except Exception as exc:
                individual.fitness = float("-inf")
                individual.failed_reason = f"{type(exc).__name__}: {exc}"

    def tournament(self, population: list[Individual]) -> Individual:
        choices = self.random.sample(population, min(self.config.tournament_size, len(population)))
        return max(choices, key=lambda item: item.fitness if item.fitness is not None else -math.inf)

    def crossover(self, first: Individual, second: Individual) -> Individual:
        blend = self.random.random()
        genes = [blend * a + (1 - blend) * b for a, b in zip(first.genes, second.genes, strict=True)]
        return Individual(genes)

    def mutate(self, individual: Individual) -> None:
        for index in range(len(individual.genes)):
            if self.random.random() < self.config.mutation_rate:
                individual.genes[index] += self.random.gauss(0, self.config.mutation_sigma)

    def next_generation(self, population: list[Individual]) -> list[Individual]:
        ranked = sorted(
            population,
            key=lambda item: item.fitness if item.fitness is not None else -math.inf,
            reverse=True,
        )
        next_population = [
            Individual(item.genes.copy(), item.fitness, item.metrics.copy(), item.failed_reason)
            for item in ranked[: self.config.elite_count]
        ]
        while len(next_population) < self.config.population_size:
            child = self.crossover(self.tournament(ranked), self.tournament(ranked))
            self.mutate(child)
            next_population.append(child)
        return next_population

    def save_checkpoint(
        self, path: Path, generation: int, population: list[Individual], history: list[dict[str, float]]
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generation": generation,
            "config": asdict(self.config),
            "population": [asdict(item) for item in population],
            "history": history,
            "random_state": repr(self.random.getstate()),
        }
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def run(
        self,
        fitness_fn: FitnessFunction,
        checkpoint_path: Path | None = None,
        should_cancel: CancelFunction | None = None,
    ) -> EvolutionResult:
        population = self.initial_population()
        history: list[dict[str, float]] = []
        start_generation = 0
        if checkpoint_path and checkpoint_path.exists():
            payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            if payload.get("config") != asdict(self.config):
                raise ValueError("Checkpoint configuration does not match the experiment")
            restored = [Individual(**item) for item in payload["population"]]
            self.random.setstate(ast.literal_eval(payload["random_state"]))
            population = self.next_generation(restored)
            history = payload["history"]
            start_generation = int(payload["generation"]) + 1
        best_score = -math.inf
        stale_generations = 0
        completed = 0
        for generation in range(start_generation, self.config.generations):
            if should_cancel and should_cancel():
                break
            self.evaluate(population, fitness_fn)
            valid = [item for item in population if item.fitness is not None and math.isfinite(item.fitness)]
            if not valid:
                raise RuntimeError("Every individual failed evaluation")
            best = max(valid, key=lambda item: item.fitness if item.fitness is not None else -math.inf)
            mean = float(np.mean([item.fitness for item in valid]))
            history.append({"generation": float(generation), "best_fitness": float(best.fitness), "mean_fitness": mean})
            completed = generation + 1
            improvement = float(best.fitness) - best_score
            if improvement > self.config.min_improvement:
                best_score = float(best.fitness)
                stale_generations = 0
            else:
                stale_generations += 1
            if checkpoint_path:
                self.save_checkpoint(checkpoint_path, generation, population, history)
            if stale_generations >= self.config.patience or generation == self.config.generations - 1:
                break
            population = self.next_generation(population)
        final_valid = [item for item in population if item.fitness is not None and math.isfinite(item.fitness)]
        return EvolutionResult(
            max(final_valid, key=lambda item: item.fitness if item.fitness is not None else -math.inf),
            history,
            completed,
        )

