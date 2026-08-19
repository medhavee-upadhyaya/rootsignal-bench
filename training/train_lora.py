from __future__ import annotations

import argparse
import json
import random
import hashlib
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Reproducible LoRA tool-selection training")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/tool-selector-lora"))
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--eval-split", type=float, default=0.2)
    args = parser.parse_args()
    random.seed(args.seed)
    try:
        from datasets import load_dataset
        from peft import LoraConfig
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
        from trl import SFTTrainer
    except ImportError as exc:
        raise SystemExit("Install the training dependencies with: pip install -e '.[train]'") from exc

    dataset = load_dataset("json", data_files=str(args.dataset), split="train").shuffle(seed=args.seed)
    split = dataset.train_test_split(test_size=args.eval_split, seed=args.seed)
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
    manifest = {
        "schema_version": "2",
        "base_model": args.model,
        "seed": args.seed,
        "epochs": args.epochs,
        "dataset": str(args.dataset),
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "train_examples": len(split["train"]),
        "eval_examples": len(split["test"]),
        "lora": {"rank": 16, "alpha": 32, "dropout": 0.05, "targets": "all-linear"},
        "train_metrics": train_result.metrics,
        "eval_metrics": eval_metrics,
    }
    (args.output / "rootsignal_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
