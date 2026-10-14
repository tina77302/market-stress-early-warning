"""Install a verified static deployment artifact on EBS before any API/CLI starts.

No model training, label generation, calculation or existing-state replacement.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

RELATIVE = Path('processed/korea/korea_targets.csv')
SOURCE_ROOT = Path('/opt/market-stress/artifacts')


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            digest.update(block)
    return digest.hexdigest()


def verified_source(source_root):
    manifest = json.loads((source_root / 'manifest.json').read_text())
    name = 'data/' + RELATIVE.as_posix()
    expected = manifest.get('files', {}).get(name)
    source = source_root / RELATIVE
    if manifest.get('format') != 1 or manifest.get('kind') != 'artifacts' or not isinstance(expected, str):
        raise RuntimeError('Invalid release artifact manifest; build from the approved artifact export.')
    if source.is_symlink() or not source.is_file() or sha256(source) != expected:
        raise RuntimeError('Release Korea target artifact missing or checksum mismatch.')
    return source, expected


def ensure_artifact(data_root, source_root=SOURCE_ROOT):
    source, expected = verified_source(source_root)
    if not data_root.is_dir():
        raise RuntimeError('Persistent data root must already exist and be mounted.')
    with (data_root / '.deployment-artifacts.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        target = data_root / RELATIVE
        if not target.resolve().is_relative_to(data_root.resolve()) or target.is_symlink():
            raise RuntimeError('Korea artifact destination escapes the persistent data root.')
        if target.exists():
            if not target.is_file() or sha256(target) != expected:
                raise RuntimeError('Existing Korea target differs from approved release; refusing to overwrite it.')
            return 'verified existing'
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.targets-', delete=False) as output:
                temporary = Path(output.name)
                with source.open('rb') as input_stream:
                    for block in iter(lambda: input_stream.read(65536), b''):
                        output.write(block)
                output.flush()
                os.fsync(output.fileno())
            if sha256(temporary) != expected:
                raise RuntimeError('Korea artifact copy verification failed.')
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
        return 'seeded missing'


def main():
    if sys.argv[1:] == ['--verify-source']:
        verified_source(SOURCE_ROOT)
        print('Release Korea artifact checksum verified.', flush=True)
        return
    configured = os.getenv('MARKET_DATA_ROOT')
    if not configured or not sys.argv[1:]:
        raise RuntimeError('Staging artifact initialization requires MARKET_DATA_ROOT and a startup command.')
    state = ensure_artifact(Path(configured))
    print(f'Korea deployment artifact ready: {state}.', flush=True)
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == '__main__':
    main()
