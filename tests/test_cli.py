"""Public CLI remains usable when the application tree is read-only."""
import os
from pathlib import Path
import shutil
import subprocess
import sys


def test_pipeline_help_does_not_create_data_or_outputs_in_read_only_application(tmp_path):
    application = tmp_path / 'app'
    application.mkdir()
    source = Path(__file__).resolve().parents[1]
    shutil.copytree(source / 'src', application / 'src', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(source / 'pyradiomics_config.yaml', application)
    application.chmod(0o555)
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'src.pipeline', '--help'],
            cwd=application,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE':'1', 'MPLCONFIGDIR':str(tmp_path/'matplotlib')},
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert '--stage' in result.stdout
        assert not (application / 'data').exists()
        assert not (application / 'outputs').exists()
    finally:
        application.chmod(0o755)
