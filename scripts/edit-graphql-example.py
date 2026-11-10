"""Edit dummy files only; no GitHub API or authentication is used here."""
import json
from pathlib import Path

files = Path('examples/graphql/files')
config = json.loads((files / 'config.json').read_text())
assert config == {'timeout': 30, 'label': 'dummy-only'}
config['timeout'] = 60
(files / 'config.json').write_text(json.dumps(config, indent=2) + '\n')
(files / 'obsolete.txt').unlink()
(files / 'before.txt').rename(files / 'after.txt')
