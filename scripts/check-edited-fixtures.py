"""CI checks user-visible results, independently of the commit API used."""
import json
from pathlib import Path

root = Path('dummy/edit-ci')
assert json.loads((root / 'config.json').read_text()) == {'timeout': 60, 'label': 'dummy-only'}
assert not (root / 'delete-me.txt').exists(), 'Deleted file is still present'
assert not (root / 'rename-me.txt').exists(), 'Old rename path is still present'
assert (root / 'renamed.txt').read_bytes() == b'Dummy rename fixture.\nThis content must survive the rename byte for byte.\n'
assert (root / 'unchanged.txt').read_bytes() == b'This dummy sentinel must remain unchanged.\n'
print('PASS: existing JSON edited, file deleted, file renamed with identical bytes, sentinel unchanged')
