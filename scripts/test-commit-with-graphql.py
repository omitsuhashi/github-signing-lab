"""Offline self-check: real Git index, mocked GitHub calls; no credentials needed."""
import base64
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

source = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('publisher', source / 'commit-with-graphql.py')
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


with tempfile.TemporaryDirectory() as folder, contextlib.chdir(folder):
    git('init', '-q', '-b', 'main')
    git('config', 'core.autocrlf', 'false')
    for name in ['edit.txt', 'delete.txt', 'before.txt']:
        Path(name).write_bytes(b'old\r\n')
    git('add', '.')
    git('-c', 'user.name=Dummy', '-c', 'user.email=dummy@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '-qm', 'Local dummy baseline')
    head = git('rev-parse', 'HEAD')
    assert not any(publisher.staged_file_changes().values())
    Path('edit.txt').write_bytes(b'staged\r\n')
    Path('delete.txt').unlink()
    Path('before.txt').rename('after name.txt')
    git('add', '-A')
    Path('edit.txt').write_bytes(b'UNSTAGED must not be published\n')
    changes = publisher.staged_file_changes()
    assert {f['path']: base64.b64decode(f['contents']) for f in changes['additions']} == {
        'edit.txt': b'staged\r\n', 'after name.txt': b'old\r\n'}
    assert {f['path'] for f in changes['deletions']} == {'before.txt', 'delete.txt'}
    sha = 'b' * 40

    def api(path, payload):
        assert path == 'graphql'
        data = payload['variables']['input']
        assert data == dict(branch=dict(repositoryNameWithOwner='test/dummy', branchName='sample/test'),
                            expectedHeadOid=head, message=dict(headline='Dummy update'), fileChanges=changes)
        commit = dict(oid=sha, url='https://example.invalid/commit/' + sha,
                      signature=dict(isValid=True, wasSignedByGitHub=True))
        return SimpleNamespace(stdout=json.dumps(dict(data=dict(createCommitOnBranch=dict(commit=commit)))))

    def read(path):
        if path == f'repos/test/dummy/commits/{sha}':
            return dict(commit=dict(verification=dict(verified=True, reason='valid')))
        assert path == 'repos/test/dummy/git/ref/heads/sample/test'
        return dict(object=dict(sha=sha))

    with patch.dict(os.environ, {'GITHUB_REPOSITORY': 'test/dummy'}), \
         patch.object(sys, 'argv', ['commit-with-graphql.py', 'sample/test', 'Dummy update']), \
         patch.object(publisher, 'api', side_effect=api) as request, \
         patch.object(publisher, 'read', side_effect=read), contextlib.redirect_stdout(io.StringIO()):
        os.environ.pop('GITHUB_STEP_SUMMARY', None)
        publisher.main()
        assert request.call_count == 1
        assert git('rev-parse', 'HEAD') == head
        assert Path('edit.txt').read_bytes() == b'UNSTAGED must not be published\n'
        with patch.object(publisher, 'api', return_value=SimpleNamespace(stdout='{"errors":[{"message":"stale head"}]}')):
            try:
                publisher.main()
            except RuntimeError as error:
                assert 'stale head' in str(error)
            else:
                raise AssertionError('GraphQL errors must stop publication')
        git('reset', '-q')
        request.reset_mock()
        publisher.main()
        request.assert_not_called()
        git('add', 'edit.txt')
        git('update-index', '--chmod=+x', 'edit.txt')
        try:
            publisher.main()
        except ValueError as error:
            assert 'ordinary non-executable files' in str(error)
        else:
            raise AssertionError('Executable mode must be rejected before the API call')
        request.assert_not_called()

print('PASS: staged bytes, rename/delete, expected head, one mutation, errors, no-op, unsupported modes')
