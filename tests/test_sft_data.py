import json

import pytest


@pytest.fixture
def sft_inputs(tmp_path, gold_path):
    from vireceipt.eval.io import load_gold

    labels = tmp_path / "train.jsonl"
    labels.write_bytes(gold_path.read_bytes())
    records = load_gold(labels)
    for record in records:
        image = tmp_path / record.image
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"synthetic image")
    return labels, tmp_path, tmp_path / "sft.jsonl", records


def test_examples_share_inference_prompt_and_roundtrip_labels(sft_inputs):
    from vireceipt.extractors.receipt_json import PROMPT_VERSION, build_prompt
    from vireceipt.training.sft_data import main, to_example

    labels, root, output, records = sft_inputs
    assert main([str(labels), "--images-root", str(root), "--out", str(output)]) == 0
    text = output.read_text(encoding="utf-8")
    rows = [json.loads(line) for line in text.split("\n") if line]
    assert [row["id"] for row in rows] == [record.id for record in records]
    for row, record in zip(rows, records, strict=True):
        assert row == to_example(record, record.image)
        assert row["prompt_version"] == PROMPT_VERSION and row["image"] == record.image
        assert row["messages"][0] == {"role": "system", "content": build_prompt()}
        assert row["messages"][1] == {
            "role": "user",
            "content": [{"type": "image", "image": record.image}],
        }
        assistant = row["messages"][2]
        assert (
            assistant["role"] == "assistant" and json.loads(assistant["content"]) == record.receipt
        )
        assert assistant["content"] == json.dumps(
            record.receipt, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
    assert "Cửa hàng" in text and "\\u" not in text and "base64" not in text


@pytest.mark.parametrize("location", ["input", "output"])
def test_test_filename_guard_runs_before_reading_labels(tmp_path, monkeypatch, location):
    from vireceipt.training.sft_data import main

    def forbidden(*args, **kwargs):
        raise AssertionError("Must reject test paths before loading any label")

    monkeypatch.setattr("vireceipt.training.sft_data.load_gold", forbidden)
    source, output = tmp_path / "train.jsonl", tmp_path / "out.jsonl"
    if location == "input":
        source = tmp_path / "test.jsonl"
    else:
        output = tmp_path / "TEST.jsonl"
    assert main([str(source), "--images-root", str(tmp_path), "--out", str(output)]) == 1
    assert not output.exists()


def test_missing_images_fail_atomically_or_skip_explicitly(sft_inputs, capsys):
    from vireceipt.training.sft_data import main

    labels, root, output, records = sft_inputs
    (root / records[0].image).unlink()
    output.write_text("old output", encoding="utf-8")
    args = [str(labels), "--images-root", str(root), "--out", str(output)]
    assert main(args) == 1 and "image_missing" in capsys.readouterr().err
    assert output.read_text() == "old output"
    assert main(args + ["--skip-missing"]) == 0
    assert "skipped 1" in capsys.readouterr().out
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").split("\n") if line]
    assert [row["id"] for row in rows] == [record.id for record in records[1:]]


@pytest.mark.parametrize("scenario", ["source", "image", "escape", "replace_failure"])
def test_export_protects_sources_and_removes_failed_temporary_files(
    sft_inputs, monkeypatch, scenario
):
    from vireceipt.training.sft_data import main

    labels, root, output, records = sft_inputs
    if scenario == "source":
        output = labels
    elif scenario == "image":
        output = root / records[0].image
    else:
        output.write_text("old output", encoding="utf-8")
    if scenario == "escape":
        rows = [json.loads(line) for line in labels.read_text(encoding="utf-8").split("\n") if line]
        rows[0]["image"] = "../outside.png"
        labels.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    if scenario == "replace_failure":

        def fail(*args):
            raise OSError("synthetic replace failure")

        monkeypatch.setattr("vireceipt.training.sft_data.os.replace", fail)
    before = output.read_bytes()
    files = set(root.iterdir())
    assert main([str(labels), "--images-root", str(root), "--out", str(output)]) == 1
    assert output.read_bytes() == before and set(root.iterdir()) == files
