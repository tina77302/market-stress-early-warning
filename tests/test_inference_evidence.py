import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.operations.evidence import preserve


class EvidenceTests(unittest.TestCase):
    def test_exact_input_order_model_bytes_and_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            args = dict(columns=['b', 'a'], dtypes=['float64', 'float64'],
                        values=[1.25, -2.0], observation_date='2026-10-20',
                        model_bytes=b'frozen-model-fixture')
            evidence = preserve(directory, **args)
            self.assertEqual(evidence, preserve(directory, **args))
            path = Path(directory) / ('input-' + evidence['input_hash'] + '.json')
            data = path.read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), evidence['input_hash'])
            self.assertEqual(json.loads(data)['columns'], ['b', 'a'])
            model = Path(directory) / ('model-' + evidence['model_sha256'] + '.joblib')
            self.assertEqual(model.read_bytes(), args['model_bytes'])
            changed = preserve(directory, **{**args, 'values': [1.25, -3.0]})
            self.assertNotEqual(changed['input_hash'], evidence['input_hash'])
            self.assertEqual(path.read_bytes(), data)
            path.write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                preserve(directory, **args)

    def test_rejects_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            args = dict(columns=['a'], dtypes=['float64'], values=[1.0],
                        observation_date='2026-10-20', model_bytes=b'fixture')
            for change in [dict(values=[float('nan')]), dict(values=[float('inf')]),
                           dict(columns=['a', 'a']), dict(dtypes=[])]:
                with self.assertRaises(ValueError):
                    preserve(directory, **{**args, **change})


if __name__ == '__main__':
    unittest.main()
