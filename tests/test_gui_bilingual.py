from pathlib import Path


def test_gui_uses_chinese_with_english_technical_terms():
    text = (Path(__file__).parents[1] / "gui" / "src" / "main.tsx").read_text(encoding="utf-8")
    required_pairs = [
        "总览 Overview",
        "运行 Runs",
        "数据集 Datasets",
        "产物 Artifacts",
        "遗留资产 Legacy Assets",
        "节点检查 Node Doctor",
        "本地控制平面 Local Control Plane",
        "数据集版本 Dataset Revisions",
        "标准路径 Golden Path",
        "预检 Preflight",
        "实验 Experiment",
        "试验 Trial",
        "任务 Job",
        "执行尝试 ExecutionAttempt",
    ]
    for pair in required_pairs:
        assert pair in text, pair
