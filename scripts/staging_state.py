#!/usr/bin/env python3
"""Controlled artifact export and SQLite online backup/verified offline restore.

No credentials are read or exported. Bundles are private directories, not images.
"""
import argparse
from contextlib import closing
import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path

# One reviewed dependency list is shared by export and startup installation.
_spec = json.loads((Path(__file__).resolve().parents[1] / 'deploy/artifact_spec.json').read_text())
REQUIRED = _spec['required_data']
MODELS = _spec['models']


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_file(source, target):
    if source.is_symlink() or not source.is_file():
        raise ValueError('Bundle sources must be regular files.')
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copyfile(source, target)
    target.chmod(0o600)


def sqlite_backup(source, target):
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True, timeout=30)) as src:
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst, pages=256, sleep=0.1)
            dst.execute('PRAGMA journal_mode=DELETE')
            if dst.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise ValueError('SQLite backup integrity check failed.')
    target.chmod(0o600)


def finish(bundle, kind):
    files = {path.relative_to(bundle).as_posix(): checksum(path)
             for path in sorted(bundle.rglob('*')) if path.is_file()}
    (bundle / 'manifest.json').write_text(json.dumps({'format': 1, 'kind': kind, 'files': files}, indent=2) + '\n')
    (bundle / 'manifest.json').chmod(0o600)


def export_artifacts(data, models, bundle):
    for relative in REQUIRED:
        if not (data / relative).is_file():
            raise ValueError(f'Missing required deployment artifact: {relative}')
    for relative in MODELS:
        if not (models / relative).is_file():
            raise ValueError(f'Missing frozen model: {relative}')
    # Existing public research/seed files only. No regeneration or account state.
    for directory in ['raw', 'processed', 'features']:
        for source in sorted((data / directory).rglob('*')):
            if source.is_file() and source.suffix in {'.csv', '.json'}:
                copy_file(source, bundle / 'data' / source.relative_to(data))
    for relative in MODELS:
        copy_file(models / relative, bundle / 'models' / relative)
    finish(bundle, 'artifacts')


def backup(data, bundle):
    # Capture DBs using SQLite's online API, never raw copies of WAL-backed DBs.
    for relative in ['paper/workspace.sqlite3', 'operations/refresh.sqlite3']:
        if (data / relative).exists():
            sqlite_backup(data / relative, bundle / 'data' / relative)
    operations = bundle / 'data/operations/refresh.sqlite3'
    if operations.exists():
        with closing(sqlite3.connect(operations.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            rows = db.execute('SELECT market,snapshot_id,payload FROM snapshots').fetchall()
        for market, snapshot_id, encoded in rows:
            if hashlib.sha256((market + encoded).encode()).hexdigest() != snapshot_id:
                raise ValueError('Stored snapshot integrity check failed.')
            reference = json.loads(encoded).get('artifact_directory')
            if not reference:
                continue
            path = Path(reference)
            if path.is_absolute():
                if len(path.parts) < 3 or path.parts[-2] != 'staging':
                    raise ValueError('Unknown legacy snapshot artifact directory.')
                path = Path('staging') / path.name
            source = (data / 'operations' / path).resolve()
            if not source.is_relative_to((data / 'operations').resolve()) or not source.is_dir():
                raise ValueError('Snapshot artifacts missing or outside operations volume.')
            for item in source.rglob('*'):
                if item.is_file() and item.suffix in {'.csv', '.json'}:
                    copy_file(item, bundle / 'data/operations' / path / item.relative_to(source))
    for directory in ['raw', 'processed', 'features']:
        for source in (data / directory).rglob('*'):
            if source.is_file() and source.suffix in {'.csv', '.json'}:
                copy_file(source, bundle / 'data' / source.relative_to(data))
    finish(bundle, 'backup')


def restore(bundle, data, models=None):
    manifest = json.loads((bundle / 'manifest.json').read_text())
    if manifest.get('format') != 1 or manifest.get('kind') not in {'artifacts', 'backup'}:
        raise ValueError('Unsupported bundle format.')
    entries = []
    for name, expected in manifest['files'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or relative.parts[0] not in {'data', 'models'}:
            raise ValueError('Unsafe bundle path.')
        source = bundle / relative
        if source.is_symlink() or not source.resolve().is_relative_to(bundle.resolve()) or checksum(source) != expected:
            raise ValueError('Bundle checksum/path verification failed.')
        destination = data if relative.parts[0] == 'data' else models
        if destination is None:
            raise ValueError('Artifact restore requires a model root.')
        entries.append((source, destination / Path(*relative.parts[1:])))
    roots = {data} | ({models} if models is not None else set())
    if any(root.exists() and any(root.iterdir()) for root in roots):
        raise ValueError('Restore requires empty destination directories; keep old state for rollback.')
    for source, target in entries:
        copy_file(source, target)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['artifacts', 'backup', 'restore'])
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--models-root', type=Path)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--offline', action='store_true', help='Confirm all services using restore destinations are stopped.')
    args = parser.parse_args()
    if args.command == 'restore':
        if not args.offline:
            parser.error('Restore requires --offline and stopped application services.')
        restore(args.bundle, args.data_root, args.models_root)
    else:
        if args.command == 'artifacts' and not args.models_root:
            parser.error('Artifact export requires --models-root.')
        args.bundle.mkdir(parents=True, mode=0o700, exist_ok=False)
        if args.command == 'artifacts':
            export_artifacts(args.data_root, args.models_root, args.bundle)
        else:
            backup(args.data_root, args.bundle)
    print(f'{args.command}: verified bundle completed.')


if __name__ == '__main__':
    main()
