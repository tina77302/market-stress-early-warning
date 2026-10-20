"""Content-addressed inference evidence; no training or retrospective relabelling."""
import hashlib
import json
import math
from pathlib import Path


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def preserve(directory, *, columns, dtypes, values, observation_date, model_bytes):
    """Persist exact numeric input order/types and model bytes in the run directory."""
    if not columns or len(columns) != len(set(columns)):
        raise ValueError('Unique nonempty feature columns required.')
    if not len(columns) == len(dtypes) == len(values):
        raise ValueError('Feature schema/value lengths differ.')
    values = [float(value) for value in values]
    if not all(math.isfinite(value) for value in values):
        raise ValueError('Finite inference values required.')
    encoded = canonical({'schema_version': 1, 'observation_date': observation_date,
                         'columns': list(columns), 'dtypes': list(dtypes), 'values': values})
    input_hash = hashlib.sha256(encoded).hexdigest()
    model_hash = hashlib.sha256(model_bytes).hexdigest()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in [(f'input-{input_hash}.json', encoded),
                          (f'model-{model_hash}.joblib', model_bytes)]:
        path = directory / name
        try:
            with path.open('xb') as stream:
                stream.write(content)
        except FileExistsError:
            if path.read_bytes() != content:
                raise ValueError('Existing inference evidence integrity failure.')
    return {'input_hash': input_hash, 'model_sha256': model_hash,
            'feature_schema_version': 1}
