"""The Colab fine-tuning notebook: valid, generated from its script, and every code cell parses."""

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "sft" / "colab_sft.ipynb"


def code_cells():
    nb = json.loads(NOTEBOOK.read_text())
    return [("".join(c["source"]), c) for c in nb["cells"] if c["cell_type"] == "code"]


def test_notebook_matches_its_generator(tmp_path):
    out = tmp_path / "nb.ipynb"
    subprocess.run([sys.executable, str(ROOT / "sft" / "tools" / "make_colab_notebook.py"), str(out)], check=True,
                   capture_output=True)
    assert out.read_text() == NOTEBOOK.read_text(), "run python sft/tools/make_colab_notebook.py sft/colab_sft.ipynb"


def test_every_code_cell_parses_and_has_no_outputs():
    for source, cell in code_cells():
        assert cell["outputs"] == [] and cell["execution_count"] is None
        python = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith(("!", "%")))
        ast.parse(python)


def test_it_uses_the_artifact_and_secret_names_the_workflow_writes():
    text = "\n".join(source for source, _ in code_cells())
    workflow = (ROOT / ".github" / "workflows" / "scripted.yml").read_text()
    assert "ttune-scripted.tar.gz.enc" in text and "ttune-scripted.tar.gz.enc" in workflow
    assert "-aes-256-cbc -pbkdf2 -iter 200000" in text and "-aes-256-cbc -pbkdf2 -iter 200000" in workflow
    assert 'userdata.get("TTUNE_TRAIN_SEED")' in text and "bundle/train.jsonl" in text
    # The passphrase is never printed.
    for source, _ in code_cells():
        for line in source.splitlines():
            assert not ("print" in line and "TTUNE_TRAIN_SEED" in line)
