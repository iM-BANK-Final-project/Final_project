import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_root_package_exposes_integrated_dev_launcher():
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    scripts = package["scripts"]

    assert scripts["dev:backend"] == (
        "python -m uvicorn src.backend.app:app "
        "--host 127.0.0.1 --port 8000 --reload"
    )
    assert scripts["dev:frontend"] == (
        "npm --prefix src/frontend/rm-insight-copilot run dev"
    )
    assert "concurrently --kill-others" in scripts["dev"]
    assert "--names BACKEND,FRONTEND" in scripts["dev"]
    assert package["devDependencies"]["concurrently"]


def test_root_package_manifests_are_not_gitignored():
    result = subprocess.run(
        ["git", "check-ignore", "package.json", "package-lock.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1, result.stdout
