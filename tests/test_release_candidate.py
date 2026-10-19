"""Public proxy contracts required by the monitoring release."""
from pathlib import Path
import re


def test_monitoring_gets_are_allowed_before_public_api_fallback():
    source = (Path(__file__).resolve().parents[1] / 'deploy/Caddyfile').read_text()
    matcher = re.search(r'@market\s*\{([^}]+)\}', source).group(1)
    assert re.search(r'\bmethod GET\b', matcher)
    paths = re.search(r'\bpath ([^\n]+)', matcher).group(1).split()
    assert '/api/monitoring/latest' in paths
    assert '/api/monitoring/history' in paths
    assert not any('/auth' in path or '/admin' in path or '/paper' in path for path in paths)
    assert source.index('handle @market') < source.index('handle /api/*')
    assert 'handle /api/workspace/*' in source
    assert 'respond "Unknown endpoint" 404' in source
