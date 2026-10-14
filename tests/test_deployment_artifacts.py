"""Static artifact delivery; no financial calculations or regenerated labels."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

spec = importlib.util.spec_from_file_location('artifact_init', Path(__file__).resolve().parents[1] / 'deploy/init_artifacts.py')
artifact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(artifact)


@pytest.fixture
def seed(tmp_path):
    source = tmp_path / 'image-seed'
    target = source / artifact.RELATIVE
    target.parent.mkdir(parents=True)
    target.write_bytes(b'existing-approved-target-file\n')
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (source / 'manifest.json').write_text(json.dumps({'format': 1, 'kind': 'artifacts', 'files': {'data/'+artifact.RELATIVE.as_posix(): digest}}))
    return source


def test_missing_artifact_seeded_and_recreation_preserves_it(tmp_path, seed):
    data = tmp_path / 'ebs/data';data.mkdir(parents=True)
    database = data / 'paper/workspace.sqlite3';database.parent.mkdir();database.write_bytes(b'untouched-private-state')
    assert artifact.ensure_artifact(data, seed) == 'seeded missing'
    target = data / artifact.RELATIVE
    before = (target.read_bytes(), target.stat().st_mtime_ns)
    # Fresh process represents startup after recreation/reboot with the same EBS.
    script = f"import runpy; m=runpy.run_path({str(Path(artifact.__file__).resolve())!r}); print(m['ensure_artifact'](m['Path']({str(data)!r}),m['Path']({str(seed)!r})))"
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and 'verified existing' in result.stdout
    assert (target.read_bytes(), target.stat().st_mtime_ns) == before
    assert database.read_bytes() == b'untouched-private-state'
    target.unlink()
    assert artifact.ensure_artifact(data, seed) == 'seeded missing'
    assert target.read_bytes() == before[0]


def test_existing_different_file_not_overwritten(tmp_path, seed):
    data=tmp_path/'data';target=data/artifact.RELATIVE;target.parent.mkdir(parents=True);target.write_bytes(b'other-approved-research')
    with pytest.raises(RuntimeError, match='refusing to overwrite'): artifact.ensure_artifact(data, seed)
    assert target.read_bytes() == b'other-approved-research'


def test_corrupt_seed_blocks_startup_before_copy(tmp_path, seed):
    data=tmp_path/'data';data.mkdir()
    (seed/artifact.RELATIVE).write_bytes(b'transfer-corruption')
    with pytest.raises(RuntimeError, match='checksum mismatch'): artifact.ensure_artifact(data, seed)
    assert not (data/artifact.RELATIVE).exists()


def test_missing_manifest_entry_blocks_startup(tmp_path, seed):
    data=tmp_path/'data';data.mkdir()
    (seed/'manifest.json').write_text('{"format":1,"kind":"artifacts","files":{}}')
    with pytest.raises(RuntimeError, match='manifest'): artifact.ensure_artifact(data, seed)


def test_mount_and_symlink_guards(tmp_path, seed):
    with pytest.raises(RuntimeError, match='mounted'): artifact.ensure_artifact(tmp_path/'absent', seed)
    data=tmp_path/'data';data.mkdir();outside=tmp_path/'outside';outside.mkdir();(data/'processed').symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match='escapes'): artifact.ensure_artifact(data, seed)
