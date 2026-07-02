"""Phase 6 contract: container files exist, wire the right entrypoints, and
share one data volume. Structural checks are dependency-free string asserts;
full compose validation shells out to docker and skips where it's absent.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_worker_runs_daemon():
    text = (ROOT / "Dockerfile.worker").read_text()
    assert "requirements-worker.txt" in text
    assert '"-m", "worker.main"' in text


def test_dockerfile_web_serves_streamlit():
    text = (ROOT / "Dockerfile.web").read_text()
    assert "requirements-web.txt" in text
    assert "ui/app.py" in text
    assert "8501" in text
    assert ".streamlit" in text  # theme chrome ships with the image


def test_compose_shares_one_data_volume():
    text = (ROOT / "docker-compose.yml").read_text()
    assert "Dockerfile.web" in text and "Dockerfile.worker" in text
    # Both services mount the same named volume where DATA_DIR points.
    assert text.count("goldadvisor-data:/data") == 2
    assert text.count("DATA_DIR: /data") == 2
    assert "8501:8501" in text
    assert text.count("restart: unless-stopped") == 2


def test_slim_images_get_zoneinfo_from_pip():
    # python-slim ships no system tzdata; zoneinfo falls back to the pip
    # package. Without it the worker's 17:00 local window crashes.
    for req in ("requirements-worker.txt", "requirements-web.txt"):
        assert "tzdata" in (ROOT / req).read_text(), req


@pytest.mark.skipif(shutil.which("docker") is None,
                    reason="docker not installed")
def test_compose_config_is_valid():
    subprocess.run(["docker", "compose", "config", "--quiet"],
                   check=True, cwd=ROOT)
