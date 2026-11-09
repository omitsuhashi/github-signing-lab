"""Edit local dummy files, save signed API commits, then create a PR with gh."""
import base64
import json
import os
from pathlib import Path
from urllib.parse import urlencode

from experiment import api, command, read

repo = os.environ['GITHUB_REPOSITORY']
assert repo == 'omitsuhashi/github-signing-lab', 'This experiment only touches the public dummy lab'
method = os.environ['LAB_API']
assert method in {'contents', 'graphql'}
expected_pr = os.environ['LAB_PR_EXPECT']
assert expected_pr in {'allow', 'deny'}
ci_mode = os.environ['LAB_CI_MODE']
assert ci_mode in {'event', 'dispatch'}
base = 'lab/edit-base-20261110'
run_id = os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT']
branch = f'lab/edit-{method}-{run_id}'
endpoint = f'repos/{repo}'
base_sha = read(f'{endpoint}/git/ref/heads/{base}')['object']['sha']
evidence = dict(method=method, credential='GITHUB_TOKEN', expected_pr=expected_pr, ci_mode=ci_mode,
                base=base, base_sha=base_sha, head_branch=branch,
                producer_url=f'https://github.com/{repo}/actions/runs/{os.environ["GITHUB_RUN_ID"]}', commits=[])
command(['git', 'fetch', 'origin', base])
command(['git', 'checkout', '--detach', 'FETCH_HEAD'])
assert command(['git', 'rev-parse', 'HEAD']).stdout.strip() == base_sha
before = {p.name: p.read_bytes() for p in Path('dummy/edit-ci').iterdir()}
config = json.loads(before['config.json'])
assert config == {'timeout': 30, 'label': 'dummy-only'}
config['timeout'] = 60
Path('dummy/edit-ci/config.json').write_text(json.dumps(config, indent=2) + '\n')
Path('dummy/edit-ci/delete-me.txt').unlink()
Path('dummy/edit-ci/rename-me.txt').rename('dummy/edit-ci/renamed.txt')
command(['python3', 'scripts/check-edited-fixtures.py'])
command(['git', 'add', '--', 'dummy/edit-ci'])
changes = command(['git', 'diff', '--cached', '--name-status', '--no-renames']).stdout
assert set(changes.splitlines()) == {'M\tdummy/edit-ci/config.json', 'D\tdummy/edit-ci/delete-me.txt',
                                    'D\tdummy/edit-ci/rename-me.txt', 'A\tdummy/edit-ci/renamed.txt'}
evidence['local_changes'] = changes
after = {p.name: p.read_bytes() for p in Path('dummy/edit-ci').iterdir()}
assert after['unchanged.txt'] == before['unchanged.txt']
api(f'{endpoint}/git/refs', dict(ref='refs/heads/' + branch, sha=base_sha))


def file_at(name):
    return read(f'{endpoint}/contents/dummy/edit-ci/{name}?' + urlencode(dict(ref=branch)))


def record_commit(sha):
    result = read(f'{endpoint}/commits/{sha}')
    verification = result['commit']['verification']
    assert verification['verified'] and verification['reason'] == 'valid', verification
    evidence['commits'].append(dict(sha=sha, url=result['html_url'], verified=verification['verified'],
                                    reason=verification['reason'], files=result['files']))


initial = {name: file_at(name) for name in ['config.json', 'delete-me.txt', 'rename-me.txt']}
if method == 'contents':
    for name, operation in [('config.json', 'PUT'), ('delete-me.txt', 'DELETE'),
                            ('renamed.txt', 'PUT'), ('rename-me.txt', 'DELETE')]:
        payload = dict(message=f'Dummy {operation} {name} {run_id}', branch=branch)
        if operation == 'PUT':
            payload['content'] = base64.b64encode(after[name]).decode()
        if name in initial:
            payload['sha'] = initial[name]['sha']
        result = json.loads(api(f'{endpoint}/contents/dummy/edit-ci/{name}', payload, method=operation).stdout)
        record_commit(result['commit']['sha'])
    stale = api(f'{endpoint}/contents/dummy/edit-ci/config.json',
                dict(message='Dummy stale blob SHA must be rejected', branch=branch,
                     content=base64.b64encode(after['config.json']).decode(), sha=initial['config.json']['sha']),
                method='PUT', check=False)
    assert stale.returncode != 0 and '409' in stale.stderr, stale.stdout + stale.stderr
else:
    query = '''mutation($input: CreateCommitOnBranchInput!) {
      createCommitOnBranch(input: $input) { commit { oid signature { isValid wasSignedByGitHub } } }
    }'''
    payload = dict(query=query, variables=dict(input=dict(
        branch=dict(repositoryNameWithOwner=repo, branchName=branch), expectedHeadOid=base_sha,
        message=dict(headline='Dummy edit/delete/rename ' + run_id),
        fileChanges=dict(additions=[dict(path='dummy/edit-ci/' + name,
                                  contents=base64.b64encode(after[name]).decode())
                                  for name in ['config.json', 'renamed.txt']],
                         deletions=[dict(path='dummy/edit-ci/' + name)
                                    for name in ['delete-me.txt', 'rename-me.txt']]))))
    result = json.loads(api('graphql', payload).stdout)
    assert not result.get('errors'), result
    commit = result['data']['createCommitOnBranch']['commit']
    assert commit['signature'] == dict(isValid=True, wasSignedByGitHub=True)
    record_commit(commit['oid'])
    stale = api('graphql', payload, check=False)
    stale_response = json.loads(stale.stdout)
    assert stale.returncode != 0 and stale_response.get('errors'), stale_response
    assert any('expected' in e['message'].lower() for e in stale_response['errors']), stale_response

evidence['stale_write_rejected'] = dict(stdout=stale.stdout, stderr=stale.stderr)
head_sha = read(f'{endpoint}/git/ref/heads/{branch}')['object']['sha']
assert head_sha == evidence['commits'][-1]['sha'], 'Rejected stale request moved branch'
evidence['head_sha'] = head_sha
for name, content in after.items():
    assert base64.b64decode(file_at(name)['content']) == content, name
for name in ['delete-me.txt', 'rename-me.txt']:
    result = api(f'{endpoint}/contents/dummy/edit-ci/{name}?' + urlencode(dict(ref=branch)), check=False)
    assert result.returncode != 0 and '404' in result.stderr, result.stderr
result = command(['gh', 'pr', 'create', '--repo', repo, '--base', base, '--head', branch,
                  '--title', f'Dummy {method} edit/delete/rename {run_id}', '--body',
                  'Dummy-only experiment. Signed API commits after local edits; CI validates final files.'], check=False)
evidence['pr_command'] = dict(exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
if expected_pr == 'deny':
    assert result.returncode != 0 and 'not permitted to create or approve pull requests' in result.stderr, result.stderr
else:
    assert result.returncode == 0, result.stderr
    number = int(result.stdout.strip().rsplit('/', 1)[-1])
    pr = read(f'{endpoint}/pulls/{number}')
    assert pr['head']['sha'] == head_sha and pr['user']['login'] == 'github-actions[bot]'
    files = read(f'{endpoint}/pulls/{number}/files')
    statuses = {f['filename']: f['status'] for f in files}
    assert statuses == {'dummy/edit-ci/config.json': 'modified', 'dummy/edit-ci/delete-me.txt': 'removed',
                        'dummy/edit-ci/renamed.txt': 'renamed'}, statuses
    assert next(f for f in files if f['status'] == 'renamed')['previous_filename'] == 'dummy/edit-ci/rename-me.txt'
    evidence.update(pr_number=number, pr_url=pr['html_url'], pr_files=files)
    if ci_mode == 'dispatch':
        api(f'{endpoint}/actions/workflows/edit-ci.yml/dispatches',
            dict(ref=branch, inputs=dict(expected_sha=head_sha, pr_number=str(number))))
        evidence['explicit_ci_dispatch'] = dict(ref=branch, expected_sha=head_sha)
Path(os.environ['GITHUB_WORKSPACE'], 'edit-pr-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
summary = '## Edit → signed commit → PR evidence\n\n```json\n' + json.dumps(evidence, indent=2) + '\n```\n'
print(summary)
with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
    output.write(summary)
