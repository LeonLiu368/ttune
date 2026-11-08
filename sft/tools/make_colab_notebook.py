"""Writes sft/colab_sft.ipynb (kept as a script so the notebook is reviewable and regenerable)."""
import json, sys
from pathlib import Path

cells = []
def md(text): cells.append({"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)})
def code(text): cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
                              "source": text.strip("\n").splitlines(keepends=True)})

md("""
# ttune: fine-tune Qwen3 4B on the scripted demonstrations (free Colab)

This notebook teaches Qwen3 4B Instruct the habits the agentic baseline lacked: read every document, run `benefits-calc`, write the answer file. It trains a LoRA adapter on the 1,000 scripted demonstrations from the secret training split, on Colab's free T4 GPU, for $0.

**Before you start**

1. **GPU runtime:** Runtime → Change runtime type → **T4 GPU**.
2. **The demonstrations:** on GitHub, open the latest **Scripted demonstrations** run under Actions and download the artifact `ttune-scripted-…` (a zip of about 1.6 MB). You'll upload it in step 2.
3. **The passphrase:** in Colab's left bar, open the key icon (Secrets), add a secret named `TTUNE_TRAIN_SEED` with the same value as the repository secret, and turn on notebook access. GitHub can't show a secret's value after it's saved, so use the copy you kept when you created it.
4. **Optional:** a Hugging Face token with write access, as a Colab secret named `HF_TOKEN`, to upload the result to a private model repo at the end.

**Time:** about 10 minutes of setup and roughly 1 to 1.5 hours of training. Checkpoints go to your Google Drive every 25 steps, so if Colab disconnects, run everything again and it picks up where it stopped.

The demonstrations contain training answers. The notebook keeps them inside this session, and the notebook itself never prints a case.
""")

md("## 1. Check the GPU and install")
code("""
import subprocess, torch
assert torch.cuda.is_available(), "No GPU: Runtime → Change runtime type → T4 GPU, then run this cell again."
print(torch.cuda.get_device_name(0), f"{torch.cuda.get_device_properties(0).total_memory / 2**30:.0f} GB")
""")
code("""
%%capture
# Unsloth: 4-bit LoRA training that fits a 4B model with 10k-token examples on a free T4.
!pip install -q unsloth
""")

md("""
## 2. Upload and decrypt the demonstrations

Choose the `ttune-scripted-….zip` file you downloaded. The passphrase comes from the `TTUNE_TRAIN_SEED` Colab secret and is never printed.
""")
code("""
import glob, json, os, subprocess, zipfile
from google.colab import files, userdata

os.makedirs("/content/data", exist_ok=True)
os.chdir("/content/data")
if not glob.glob("bundle/train.jsonl"):
    uploaded = files.upload()  # pick ttune-scripted-*.zip
    for name in uploaded:
        if name.endswith(".zip"):
            zipfile.ZipFile(name).extractall(".")
    enc = glob.glob("**/ttune-scripted.tar.gz.enc", recursive=True)
    assert enc, "Couldn't find ttune-scripted.tar.gz.enc in the upload: upload the artifact zip from the Scripted demonstrations run."
    env = dict(os.environ, TTUNE_TRAIN_SEED=userdata.get("TTUNE_TRAIN_SEED"))
    decrypt = subprocess.run(
        f"openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:TTUNE_TRAIN_SEED -in '{enc[0]}' | tar -xzf -",
        shell=True, env=env, capture_output=True, text=True)
    assert decrypt.returncode == 0 and os.path.exists("bundle/train.jsonl"), (
        "Decryption failed: check that the TTUNE_TRAIN_SEED Colab secret matches the repository secret.")

def read(path):
    with open(path) as fh:
        return [json.loads(line)["messages"] for line in fh]

train_rows, val_rows = read("bundle/train.jsonl"), read("bundle/validation.jsonl")
print(f"{len(train_rows)} training and {len(val_rows)} validation demonstrations")
""")

md("## 3. Load Qwen3 4B in 4-bit and add LoRA")
code("""
from unsloth import FastLanguageModel

MAX_LEN = 10240  # every demonstration fits (the longest is about 9,000 tokens)
model, tokenizer = FastLanguageModel.from_pretrained(
    "unsloth/Qwen3-4B-Instruct-2507", max_seq_length=MAX_LEN, load_in_4bit=True)
model = FastLanguageModel.get_peft_model(
    model, r=16, lora_alpha=16, lora_dropout=0, bias="none",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    use_gradient_checkpointing="unsloth", random_state=0)
""")

md("""
## 4. Format the conversations

Each demonstration becomes one chat in Qwen's template, the same template llama.cpp uses at evaluation. Only the assistant turns are trained (step 5); the instruction and the terminal output are context.
""")
code("""
from datasets import Dataset

def to_text(rows):
    texts = [tokenizer.apply_chat_template(m, tokenize=False) for m in rows]
    lengths = [len(tokenizer(t, add_special_tokens=False).input_ids) for t in texts]
    kept = [t for t, n in zip(texts, lengths) if n <= MAX_LEN]
    print(f"{len(kept)} of {len(texts)} fit in {MAX_LEN} tokens; longest {max(lengths)}, median {sorted(lengths)[len(lengths) // 2]}")
    return Dataset.from_dict({"text": kept})

train_ds, val_ds = to_text(train_rows), to_text(val_rows[:20])
""")

md("""
## 5. Train

One pass over the 1,000 demonstrations: 125 steps of 8 examples, at learning rate 2e-4 with a cosine decay. Checkpoints go to `MyDrive/ttune-sft/` every 25 steps.
""")
code("""
import inspect
from google.colab import drive
from trl import SFTConfig, SFTTrainer
from unsloth import is_bfloat16_supported
from unsloth.chat_templates import train_on_responses_only

drive.mount("/content/drive")
OUT = "/content/drive/MyDrive/ttune-sft"
os.makedirs(OUT, exist_ok=True)

settings = dict(
    output_dir=f"{OUT}/checkpoints", dataset_text_field="text",
    per_device_train_batch_size=1, gradient_accumulation_steps=8, num_train_epochs=1,
    learning_rate=2e-4, lr_scheduler_type="cosine", warmup_ratio=0.03, weight_decay=0.0,
    optim="adamw_8bit", fp16=not is_bfloat16_supported(), bf16=is_bfloat16_supported(),
    logging_steps=5, eval_strategy="steps", eval_steps=25, save_steps=25, save_total_limit=2,
    per_device_eval_batch_size=1, seed=0, report_to="none")
# TRL renamed max_seq_length to max_length; pass whichever this version takes.
accepted = inspect.signature(SFTConfig).parameters
settings["max_length" if "max_length" in accepted else "max_seq_length"] = MAX_LEN

# Newer TRL calls the tokenizer processing_class.
takes = inspect.signature(SFTTrainer.__init__).parameters
tok = {"processing_class" if "processing_class" in takes else "tokenizer": tokenizer}
trainer = SFTTrainer(model=model, train_dataset=train_ds, eval_dataset=val_ds, args=SFTConfig(**settings), **tok)
trainer = train_on_responses_only(trainer, instruction_part="<|im_start|>user\\n",
                                  response_part="<|im_start|>assistant\\n")

before = trainer.evaluate()["eval_loss"]
print(f"validation loss before training: {before:.3f}")
resume = bool(glob.glob(f"{OUT}/checkpoints/checkpoint-*"))
trainer.train(resume_from_checkpoint=resume or None)
after = trainer.evaluate()["eval_loss"]
print(f"validation loss: {before:.3f} before, {after:.3f} after")
""")

md("""
## 6. Look at one turn

The model gets the first message of a validation task, the instruction and an empty terminal, and writes its first reply. A trained model lists `/app/case/` and reads the application with `pdftotext`. This shows the model's own reply, not a case's answers.
""")
code("""
FastLanguageModel.for_inference(model)
prompt = tokenizer.apply_chat_template(val_rows[0][:1], tokenize=False, add_generation_prompt=True)
inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
out = model.generate(**inputs, max_new_tokens=300, do_sample=False)
reply = tokenizer.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
print(reply)
print("\\nreads the documents:", "pdftotext" in reply, "· valid JSON:", reply.strip().startswith("{"))
""")

md("""
## 7. Save the adapter and a GGUF for evaluation

The LoRA adapter goes to `MyDrive/ttune-sft/lora`. A merged `q4_k_m` GGUF, the same format the evaluation workflows serve with llama.cpp, goes to `MyDrive/ttune-sft/gguf` (this takes about 15 minutes).
""")
code("""
model.save_pretrained(f"{OUT}/lora")
tokenizer.save_pretrained(f"{OUT}/lora")
model.save_pretrained_gguf(f"{OUT}/gguf", tokenizer, quantization_method="q4_k_m")
print(sorted(os.listdir(f"{OUT}/gguf")))
""")

md("""
## 8. Optional: upload the GGUF to a private Hugging Face repo

The evaluation workflows download models from Hugging Face. This uploads the GGUF to a **private** repo under your account, so only you (and a token you give GitHub) can read it.
""")
code("""
HF_REPO = "ttune-qwen3-4b-sft"  # created under your account
token = userdata.get("HF_TOKEN")
from huggingface_hub import HfApi
api = HfApi(token=token)
repo = f"{api.whoami()['name']}/{HF_REPO}"
api.create_repo(repo, private=True, exist_ok=True)
for name in os.listdir(f"{OUT}/gguf"):
    if name.endswith(".gguf"):
        api.upload_file(path_or_fileobj=f"{OUT}/gguf/{name}", path_in_repo=name, repo_id=repo)
print("uploaded to", repo)
""")

md("""
## Next

Tell Claude the Hugging Face repo name printed above (or that the GGUF is only on your Drive). Before that, add a Hugging Face token with **read** access (a separate one from the write token used here) as the GitHub repository secret `HF_TOKEN`, so the workflows can download the private repo.

The fine-tuned model then runs as an agent on the same 400 holdout tasks as the base model, for $0: the Baseline workflow with `model_repo` set to the repo and `compare_to` set to the base model's run. Those tasks are the ones the model has never trained on, so the before and after compare directly. [sft/README.md](https://github.com/LeonLiu368/ttune/blob/main/sft/README.md#evaluating-the-fine-tuned-model) has the steps.
""")

nb = {"cells": cells, "metadata": {"accelerator": "GPU", "colab": {"provenance": [], "gpuType": "T4"},
      "kernelspec": {"display_name": "Python 3", "name": "python3"}, "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 0}
Path(sys.argv[1]).write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n")
print("wrote", sys.argv[1], len(cells), "cells")
