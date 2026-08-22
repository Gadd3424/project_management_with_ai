import csv
import random
from datetime import date, timedelta
from pathlib import Path


def main() -> None:
    random.seed(42)
    output = Path("data/demo/task_outcomes.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["project_group", "snapshot_date", "days_to_due", "priority", "workload", "delayed"],
        )
        writer.writeheader()
        for index in range(500):
            days = random.randint(-5, 30)
            workload = round(random.random(), 3)
            priority = random.choice(["low", "medium", "high", "urgent"])
            risk = 0.15 + (0.45 if days <= 2 else 0) + 0.3 * workload
            writer.writerow(
                {
                    "project_group": f"demo-{index // 10:03d}",
                    "snapshot_date": date(2025, 1, 1) + timedelta(days=index),
                    "days_to_due": days,
                    "priority": priority,
                    "workload": workload,
                    "delayed": int(random.random() < min(risk, 0.95)),
                }
            )
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
