"""Install approved static artifacts before staging API/CLI startup.

No model training, label/SHAP generation or replacement of existing state.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

SOURCE_ROOT = Path('/opt/market-stress/artifacts')
SPEC_PATH = Path(__file__).with_name('artifact_spec.json')


def required_paths():
    spec = json.loads(SPEC_PATH.read_text())
    if spec.get('format') != 1 or not isinstance(spec.get('required_data'), list):
        raise RuntimeError('Invalid deployment artifact specification.')
    paths = [Path(value) for value in spec['required_data']]
    for value in paths:
        if value.is_absolute() or '..' in value.parts or not value.parts or value.parts[0] not in {'raw', 'processed', 'features'} or value.suffix not in {'.csv', '.json'}:
            raise RuntimeError('Unsafe deployment artifact specification.')
    if not paths or len(set(paths)) != len(paths):
        raise RuntimeError('Empty or duplicate deployment artifact specification.')
    return paths


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            digest.update(block)
    return digest.hexdigest()


def verified_source(source_root):
    manifest = json.loads((source_root / 'manifest.json').read_text())
    if manifest.get('format') != 1 or manifest.get('kind') != 'artifacts' or not isinstance(manifest.get('files'), dict):
        raise RuntimeError('Invalid release artifact manifest; build from the approved export.')
    entries = {}
    for relative in required_paths():
        expected = manifest['files'].get('data/' + relative.as_posix())
        source = source_root / 'data' / relative
        if not isinstance(expected, str) or len(expected) != 64:
            raise RuntimeError(f'Release manifest missing required artifact: {relative}')
        if source.is_symlink() or not source.resolve().is_relative_to(source_root.resolve()) or not source.is_file() or sha256(source) != expected:
            raise RuntimeError(f'Release artifact missing or checksum mismatch: {relative}')
        entries[relative] = (source, expected)
    return entries


def install_missing(source, expected, target):
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.artifact-', delete=False) as output:
            temporary = Path(output.name)
            with source.open('rb') as input_stream:
                for block in iter(lambda: input_stream.read(65536), b''):
                    output.write(block)
            output.flush()
            os.fsync(output.fileno())
        if sha256(temporary) != expected:
            raise RuntimeError(f'Artifact copy verification failed: {target.name}')
        temporary.chmod(0o600)
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def ensure_artifacts(data_root, source_root=SOURCE_ROOT):
    entries = verified_source(source_root)
    if not data_root.is_dir():
        raise RuntimeError('Persistent data root must already exist and be mounted.')
    with (data_root / '.deployment-artifacts.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        missing, existing = [], []
        # Check every source and destination before installing anything. A
        # conflict is not a license to overwrite files, DBs or runtime history.
        for relative, (source, expected) in entries.items():
            target = data_root / relative
            if not target.resolve().is_relative_to(data_root.resolve()) or target.is_symlink():
                raise RuntimeError(f'Artifact destination escapes persistent root: {relative}')
            if target.exists():
                if not target.is_file() or sha256(target) != expected:
                    raise RuntimeError(f'Existing artifact differs from approved release; refusing to overwrite: {relative}')
                existing.append(relative.as_posix())
            else:
                missing.append((relative, source, expected))
        for relative, source, expected in missing:
            install_missing(source, expected, data_root / relative)
        return {'seeded': [relative.as_posix() for relative, _, _ in missing], 'verified': existing}


def main():
    if sys.argv[1:] == ['--verify-source']:
        entries = verified_source(SOURCE_ROOT)
        print(f'Approved deployment artifact checksums verified: {len(entries)}.', flush=True)
        return
    configured = os.getenv('MARKET_DATA_ROOT')
    if not configured or not sys.argv[1:]:
        raise RuntimeError('Artifact initialization requires MARKET_DATA_ROOT and a startup command.')
    state = ensure_artifacts(Path(configured))
    print(f'Deployment artifacts ready: seeded={len(state["seeded"])} verified={len(state["verified"])}.', flush=True)
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == '__main__':
    main()
