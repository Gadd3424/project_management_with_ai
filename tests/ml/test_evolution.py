import math
from pathlib import Path

from services.evolutionary_merge import EvolutionConfig, GeneticOptimizer


def fitness(weights: list[float]) -> tuple[float, dict[str, float]]:
    score = 1 - abs(weights[0] - 0.7)
    return score, {"quality": score, "latency": 0.01}


def test_evolution_is_reproducible(tmp_path: Path) -> None:
    config = EvolutionConfig(gene_count=3, population_size=8, generations=6, random_seed=123)
    first = GeneticOptimizer(config).run(fitness, tmp_path / "first.json")
    second = GeneticOptimizer(config).run(fitness, tmp_path / "second.json")
    assert first.best.weights == second.best.weights
    assert first.best.fitness == second.best.fitness
    assert first.history == second.history


def test_failed_individual_is_quarantined() -> None:
    optimizer = GeneticOptimizer(EvolutionConfig(gene_count=2, population_size=4, generations=1))
    population = optimizer.initial_population()

    def invalid(_: list[float]) -> tuple[float, dict[str, float]]:
        return math.nan, {"quality": math.nan}

    optimizer.evaluate(population, invalid)
    assert all(item.failed_reason for item in population)
    assert all(item.fitness == float("-inf") for item in population)


def test_genome_weights_are_normalized() -> None:
    population = GeneticOptimizer(EvolutionConfig(gene_count=3, population_size=4)).initial_population()
    for item in population:
        assert math.isclose(sum(item.weights), 1.0)
        assert all(weight >= 0 for weight in item.weights)


def test_evolution_resumes_from_checkpoint(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    config = EvolutionConfig(gene_count=3, population_size=8, generations=5, random_seed=77, patience=10)
    checks = 0

    def cancel_after_two_generations() -> bool:
        nonlocal checks
        checks += 1
        return checks > 2

    partial = GeneticOptimizer(config).run(fitness, checkpoint, cancel_after_two_generations)
    assert partial.completed_generations == 2
    resumed = GeneticOptimizer(config).run(fitness, checkpoint)
    assert resumed.completed_generations == 5
    assert len(resumed.history) == 5

