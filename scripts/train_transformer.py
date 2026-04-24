from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transdssat.policy import (
    TransformerPolicy,
    collate_supervised_batch,
    iter_supervised_examples,
    training_readiness,
)


def build_batches(examples, batch_size: int):
    batch = []
    for example in examples:
        batch.append(example)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def evaluate(model, examples, batch_size: int):
    import torch
    from torch import nn

    if not examples:
        return {
            "loss": 0.0,
            "irrigation_accuracy": 0.0,
            "nitrogen_accuracy": 0.0,
            "example_count": 0,
        }

    criterion = nn.CrossEntropyLoss()
    model.eval()
    total_loss = 0.0
    total_examples = 0
    irrigation_correct = 0
    nitrogen_correct = 0

    with torch.no_grad():
        for batch in build_batches(examples, batch_size):
            features, padding_mask, irrigation_targets, nitrogen_targets = collate_supervised_batch(batch)
            irrigation_logits, nitrogen_logits = model(features, padding_mask=padding_mask)
            loss = criterion(irrigation_logits, irrigation_targets) + criterion(nitrogen_logits, nitrogen_targets)
            batch_size_actual = irrigation_targets.size(0)
            total_loss += float(loss.item()) * batch_size_actual
            total_examples += batch_size_actual
            irrigation_correct += int((irrigation_logits.argmax(dim=1) == irrigation_targets).sum().item())
            nitrogen_correct += int((nitrogen_logits.argmax(dim=1) == nitrogen_targets).sum().item())

    return {
        "loss": round(total_loss / max(1, total_examples), 6),
        "irrigation_accuracy": round(irrigation_correct / max(1, total_examples), 6),
        "nitrogen_accuracy": round(nitrogen_correct / max(1, total_examples), 6),
        "example_count": total_examples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the optional Transformer policy.")
    parser.add_argument("--dataset", required=True, help="Path to the JSONL training dataset.")
    parser.add_argument("--epochs", type=int, default=5, help="Number of training epochs.")
    parser.add_argument("--batch-size", type=int, default=8, help="Mini-batch size.")
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate.")
    parser.add_argument(
        "--output-dir",
        default="artifacts/transformer",
        help="Directory for checkpoints and metrics.",
    )
    args = parser.parse_args()

    readiness = training_readiness()
    if not readiness.torch_available:
        print(readiness.message)
        return 0

    import torch
    from torch import nn

    train_examples = list(iter_supervised_examples(args.dataset))
    if not train_examples:
        print(f"No supervised examples found in {args.dataset}")
        return 1

    dataset_path = Path(args.dataset)
    test_path = dataset_path.with_name("test.jsonl")
    test_examples = list(iter_supervised_examples(test_path)) if test_path.exists() else []

    model = TransformerPolicy()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    criterion = nn.CrossEntropyLoss()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    history = []
    best_state = None
    best_metric = None

    for epoch in range(1, args.epochs + 1):
        model.train()
        total_loss = 0.0
        total_examples = 0
        irrigation_correct = 0
        nitrogen_correct = 0

        for batch in build_batches(train_examples, args.batch_size):
            features, padding_mask, irrigation_targets, nitrogen_targets = collate_supervised_batch(batch)
            optimizer.zero_grad()
            irrigation_logits, nitrogen_logits = model(features, padding_mask=padding_mask)
            loss = criterion(irrigation_logits, irrigation_targets) + criterion(nitrogen_logits, nitrogen_targets)
            loss.backward()
            optimizer.step()

            batch_size_actual = irrigation_targets.size(0)
            total_loss += float(loss.item()) * batch_size_actual
            total_examples += batch_size_actual
            irrigation_correct += int((irrigation_logits.argmax(dim=1) == irrigation_targets).sum().item())
            nitrogen_correct += int((nitrogen_logits.argmax(dim=1) == nitrogen_targets).sum().item())

        train_metrics = {
            "loss": round(total_loss / max(1, total_examples), 6),
            "irrigation_accuracy": round(irrigation_correct / max(1, total_examples), 6),
            "nitrogen_accuracy": round(nitrogen_correct / max(1, total_examples), 6),
            "example_count": total_examples,
        }
        eval_metrics = evaluate(model, test_examples, args.batch_size)
        history.append({"epoch": epoch, "train": train_metrics, "test": eval_metrics})

        selection_metric = eval_metrics["loss"] if eval_metrics["example_count"] else train_metrics["loss"]
        if best_metric is None or selection_metric < best_metric:
            best_metric = selection_metric
            best_state = {
                "model_state_dict": model.state_dict(),
                "epoch": epoch,
                "train_metrics": train_metrics,
                "test_metrics": eval_metrics,
            }

        print(
            json.dumps(
                {
                    "epoch": epoch,
                    "train": train_metrics,
                    "test": eval_metrics,
                },
                ensure_ascii=False,
            )
        )

    assert best_state is not None
    checkpoint_path = output_dir / "transformer_policy.pt"
    metrics_path = output_dir / "metrics.json"
    torch.save(best_state, checkpoint_path)
    metrics_path.write_text(json.dumps({"history": history, "best_epoch": best_state["epoch"]}, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "checkpoint": str(checkpoint_path),
                "metrics": str(metrics_path),
                "best_epoch": best_state["epoch"],
                "train_examples": len(train_examples),
                "test_examples": len(test_examples),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
