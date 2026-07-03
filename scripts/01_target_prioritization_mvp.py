from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

from opentargets import search_disease, get_associated_targets
from io_relevance import annotate_io_relevance
from scoring import add_io_weighted_target_score


def main():
    print("Searching Open Targets for melanoma...")

    diseases = search_disease("melanoma", size=10)
    print("\nDisease search results:")
    print(diseases[["id", "name", "description"]].head(10))

    disease_id = diseases.iloc[0]["id"]
    print(f"\nUsing disease ID: {disease_id}")

    print("\nGetting associated targets...")
    targets = get_associated_targets(disease_id=disease_id, size=100)

    targets = annotate_io_relevance(targets)
    ranked_targets = add_io_weighted_target_score(targets)

    results_dir = PROJECT_ROOT / "results"
    results_dir.mkdir(exist_ok=True)

    output_file = results_dir / "top_targets_melanoma_io_weighted_v0_2.csv"
    ranked_targets.to_csv(output_file, index=False)

    print("\nTop 20 targets:")
    print(
        ranked_targets[
            [
                "target_symbol",
                "target_name",
                "disease_name",
                "opentargets_score",
                "immuno_oncology_score",
                "io_category",
                "final_score",
            ]
        ].head(20)
    )

    print(f"\nSaved results to: {output_file}")


if __name__ == "__main__":
    main()
