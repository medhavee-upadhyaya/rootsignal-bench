from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
from pathlib import Path

from .validate_artifacts import directory_sha256


def main() -> None:
    parser = argparse.ArgumentParser(description="Reproducible LoRA tool-selection training")
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/tool-selector-lora"))
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--eval-split", type=float, default=0.2)
    parser.add_argument("--dataset-manifest", type=Path)
    parser.add_argument("--config", type=Path, default=Path("training/configs/tool-selector-lora.json"))
    args = parser.parse_args()
    if not args.dataset and not args.dataset_manifest:
        parser.error("one of --dataset or --dataset-manifest is required")
    random.seed(args.seed)
    try:
        from datasets import load_dataset
        from peft import LoraConfig
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
        from trl import SFTTrainer
    except ImportError as exc:
        raise SystemExit("Install the training dependencies with: pip install -e '.[train]'") from exc

    if args.dataset_manifest:
        dataset_manifest = json.loads(args.dataset_manifest.read_text(encoding="utf-8"))
        train_path = args.dataset_manifest.parent / dataset_manifest["train"]["path"]
        eval_path = args.dataset_manifest.parent / dataset_manifest["eval"]["path"]
        split = {
            "train": load_dataset("json", data_files=str(train_path), split="train"),
            "test": load_dataset("json", data_files=str(eval_path), split="train"),
        }
        dataset_digest = hashlib.sha256(args.dataset_manifest.read_bytes()).hexdigest()
    else:
        dataset = load_dataset("json", data_files=str(args.dataset), split="train").shuffle(seed=args.seed)
        split = dataset.train_test_split(test_size=args.eval_split, seed=args.seed)
        dataset_digest = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    tokenizer.pad_token = tokenizer.pad_token or tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.model, device_map="auto")

    def format_example(example: dict[str, object]) -> str:
        return tokenizer.apply_chat_template(example["messages"], tokenize=False)

    config = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, target_modules="all-linear")
    training_args = TrainingArguments(
        output_dir=str(args.output),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        learning_rate=2e-4,
        logging_steps=5,
        save_strategy="epoch",
        report_to="none",
        seed=args.seed,
    )
    trainer = SFTTrainer(
        model=model,
        train_dataset=split["train"],
        eval_dataset=split["test"],
        peft_config=config,
        args=training_args,
        formatting_func=format_example,
    )
    train_result = trainer.train()
    eval_metrics = trainer.evaluate()
    trainer.save_model(str(args.output))
    manifest_name = "rootsignal_manifest.json"
    manifest = {
        "schema_version": "3",
        "base_model": args.model,
        "base_model_revision": str(getattr(model.config, "_commit_hash", None) or "local-or-unpinned"),
        "seed": args.seed,
        "epochs": args.epochs,
        "dataset": str(args.dataset),
        "dataset_sha256": dataset_digest,
        "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
        "split_isolation": "incident_template" if args.dataset_manifest else "example",
        "train_examples": len(split["train"]),
        "eval_examples": len(split["test"]),
        "lora": {"rank": 16, "alpha": 32, "dropout": 0.05, "targets": "all-linear"},
        "train_metrics": train_result.metrics,
        "eval_metrics": eval_metrics,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "device": str(next(model.parameters()).device),
        },
        "adapter_sha256": directory_sha256(args.output, {manifest_name}),
    }
    (args.output / manifest_name).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
