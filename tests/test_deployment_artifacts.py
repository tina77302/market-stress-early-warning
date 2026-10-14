"""Approved artifact delivery only; no regenerated research, SHAP or models."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
from scripts import staging_state

spec = importlib.util.spec_from_file_location('artifact_init', Path(__file__).resolve().parents[1] / 'deploy/init_artifacts.py')
artifact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(artifact)
TARGET = Path('processed/korea/korea_targets.csv')


@pytest.fixture
def seed(tmp_path):
    source = tmp_path / 'image-seed'
    files = {}
    for relative in artifact.required_paths():
        target = source / 'data' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(('existing-approved-artifact:' + str(relative)).encode())
        files['data/'+relative.as_posix()] = artifact.sha256(target)
    # Models/private state are never installation destinations, even if a bundle
    # manifest contains unrelated entries alongside the approved data set.
    for relative in ['models/saved/model.joblib', 'data/paper/workspace.sqlite3', 'data/operations/refresh.sqlite3']:
        path=source/relative;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(b'not-to-be-installed')
        files[relative] = artifact.sha256(path)
    (source / 'manifest.json').write_text(json.dumps({'format': 1, 'kind': 'artifacts', 'files': files}))
    return source


def test_export_and_installer_share_exact_dependency_list():
    assert [path.as_posix() for path in artifact.required_paths()] == staging_state.REQUIRED
    assert 'processed/oos_predictions.csv' in staging_state.REQUIRED
    assert 'features/shap/latest_shap.json' in staging_state.REQUIRED
    assert 'processed/korea/korea_oos_predictions_10d.csv' in staging_state.REQUIRED


def test_all_missing_artifacts_seeded_and_recreation_preserves_them(tmp_path, seed):
    data = tmp_path / 'ebs/data';data.mkdir(parents=True)
    private = data / 'paper/workspace.sqlite3';private.parent.mkdir();private.write_bytes(b'untouched-private-state')
    result = artifact.ensure_artifacts(data, seed)
    assert set(result['seeded']) == set(staging_state.REQUIRED)
    before = {p.as_posix():(data/p).stat().st_mtime_ns for p in artifact.required_paths()}
    for relative in artifact.required_paths():
        assert (data/relative).read_bytes() == (seed/'data'/relative).read_bytes()
    assert not (data/'operations/refresh.sqlite3').exists()
    assert not (data/'models').exists()
    script = f"import runpy; m=runpy.run_path({str(Path(artifact.__file__).resolve())!r}); print(m['ensure_artifacts'](m['Path']({str(data)!r}),m['Path']({str(seed)!r})))"
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and "'seeded': []" in result.stdout
    assert {p.as_posix():(data/p).stat().st_mtime_ns for p in artifact.required_paths()} == before
    assert private.read_bytes() == b'untouched-private-state'
    (data/TARGET).unlink()
    assert artifact.ensure_artifacts(data, seed)['seeded'] == [TARGET.as_posix()]
    assert (data/TARGET).read_bytes() == (seed/'data'/TARGET).read_bytes()


def test_conflict_preflight_blocks_all_writes_without_overwrite(tmp_path, seed):
    data=tmp_path/'data';target=data/TARGET;target.parent.mkdir(parents=True);target.write_bytes(b'different-approved-research')
    with pytest.raises(RuntimeError, match='refusing to overwrite'): artifact.ensure_artifacts(data, seed)
    assert target.read_bytes() == b'different-approved-research'
    assert not (data/'raw/raw_market_data.csv').exists()
    assert not (data/'processed/oos_predictions.csv').exists()


def test_corrupt_seed_blocks_startup_before_copy(tmp_path, seed):
    data=tmp_path/'data';data.mkdir()
    (seed/'data/features/shap/latest_shap.json').write_bytes(b'transfer-corruption')
    with pytest.raises(RuntimeError, match='checksum mismatch'): artifact.ensure_artifacts(data, seed)
    assert not (data/TARGET).exists()


def test_missing_manifest_entry_blocks_startup(tmp_path, seed):
    data=tmp_path/'data';data.mkdir()
    manifest=json.loads((seed/'manifest.json').read_text())
    del manifest['files']['data/processed/oos_predictions.csv']
    (seed/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match='missing required artifact'): artifact.ensure_artifacts(data, seed)
    assert not (data/TARGET).exists()


def test_mount_and_symlink_guards(tmp_path, seed):
    with pytest.raises(RuntimeError, match='mounted'): artifact.ensure_artifacts(tmp_path/'absent', seed)
    data=tmp_path/'data';data.mkdir();outside=tmp_path/'outside';outside.mkdir();(data/'processed').symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match='escapes'): artifact.ensure_artifacts(data, seed)
    assert not (data/'raw/raw_market_data.csv').exists()


def test_installation_does_not_relabel_approved_shap_dates(tmp_path, seed):
    relative=Path('features/shap/latest_shap.json')
    source=seed/'data'/relative
    approved = Path(__file__).resolve().parents[1] / 'data/features/shap/latest_shap.json'
    source.write_bytes(approved.read_bytes())
    manifest=json.loads((seed/'manifest.json').read_text());manifest['files']['data/'+relative.as_posix()]=artifact.sha256(source)
    (seed/'manifest.json').write_text(json.dumps(manifest))
    data=tmp_path/'data';data.mkdir()
    artifact.ensure_artifacts(data, seed)
    assert (data/relative).read_bytes()==source.read_bytes()
    assert json.loads((data/relative).read_text())['date']=='2026-10-05'
