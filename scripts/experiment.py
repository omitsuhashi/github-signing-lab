"""Manual dummy-data experiments. No user data or dependencies are needed."""
import base64
import json
import os
from pathlib import Path
import subprocess
import time


def command(args, *, data=None, check=True, env=None):
    result = subprocess.run(args, input=data, text=True, capture_output=True, env=env)
    if check and result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result


def api(path, data=None, method=None, check=True):
    args = ['gh', 'api', path]
    if method:
        args += ['--method', method]
    if data is not None:
        args += ['--input', '-']
    result = command(args, data=json.dumps(data) if data is not None else None, check=check)
    return result


def read(path):
    return json.loads(api(path).stdout)


def run():
    repo = os.environ['GITHUB_REPOSITORY']
    assert repo == 'omitsuhashi/github-signing-lab', 'Use this lab repository only'
    method, target, expected = (os.environ['LAB_' + k] for k in ['METHOD', 'TARGET', 'EXPECT'])
    assert method in {'unsigned', 'contents', 'graphql', 'pr', 'merge'}
    assert target in {'signed', 'bypass', 'guarded'}
    assert expected in {'allow', 'deny'}
    run_id = os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT']
    branch = 'lab/' + target
    endpoint = f'repos/{repo}'
    before = read(f'{endpoint}/git/ref/heads/{branch}')['object']['sha']
    name = f'dummy/{run_id}-a.txt'
    dummy = f'Dummy signing experiment {run_id}\n'
    encoded = base64.b64encode(dummy.encode()).decode()
    evidence = dict(run_id=run_id, credential=os.environ['LAB_CREDENTIAL'], method=method,
                    target=branch, expected=expected, before=before,
                    run_url=f'https://github.com/{repo}/actions/runs/{os.environ["GITHUB_RUN_ID"]}')
    sha = None
    if method in {'unsigned', 'pr'}:
        git_env = dict(os.environ, GIT_CONFIG_COUNT='1',
                       GIT_CONFIG_KEY_0='http.https://github.com/.extraheader',
                       GIT_CONFIG_VALUE_0='AUTHORIZATION: basic ' + base64.b64encode(
                           ('x-access-token:' + os.environ['GH_TOKEN']).encode()).decode())
        command(['git', 'fetch', 'origin', branch], env=git_env)
        command(['git', 'checkout', '--detach', 'FETCH_HEAD'])
        Path('dummy').mkdir(exist_ok=True)
        Path(name).write_text(dummy)
        command(['git', 'add', name])
        command(['git', '-c', 'user.name=Signing Lab', '-c', 'user.email=signing-lab@example.invalid',
                 '-c', 'commit.gpgsign=false', 'commit', '-m', f'Dummy unsigned experiment {run_id}'])
        sha = command(['git', 'rev-parse', 'HEAD']).stdout.strip()
        assert '\ngpgsig ' not in command(['git', 'cat-file', '-p', sha]).stdout
        destination = branch if method == 'unsigned' else 'lab/source-' + run_id
        result = command(['git', 'push', 'origin', f'HEAD:refs/heads/{destination}'], check=False, env=git_env)
        if method == 'pr':
            assert result.returncode == 0, result.stderr
            pr = json.loads(api(f'{endpoint}/pulls', dict(title=f'Dummy unsigned PR {run_id}',
                            head=destination, base=branch,
                            body='Dummy data only. Tests a narrowly scoped signing-rule bypass.')).stdout)
            evidence.update(pr_number=pr['number'], pr_url=pr['html_url'], head_sha=sha)
    elif method == 'contents':
        result = api(f'{endpoint}/contents/{name}', dict(message=f'Dummy Contents API {run_id}',
                     content=encoded, branch=branch), method='PUT', check=False)
        if result.returncode == 0:
            sha = json.loads(result.stdout)['commit']['sha']
    elif method == 'graphql':
        query = '''mutation($input: CreateCommitOnBranchInput!) {
          createCommitOnBranch(input: $input) { commit { oid signature { isValid wasSignedByGitHub state } } }
        }'''
        result = api('graphql', dict(query=query, variables=dict(input=dict(
            branch=dict(repositoryNameWithOwner=repo, branchName=branch), expectedHeadOid=before,
            message=dict(headline=f'Dummy GraphQL API {run_id}'),
            fileChanges=dict(additions=[dict(path=f'dummy/{run_id}-{part}.txt', contents=encoded)
                                        for part in ['a', 'b']])))), check=False)
        if result.returncode == 0:
            response = json.loads(result.stdout)
            assert not response.get('errors'), response
            commit = response['data']['createCommitOnBranch']['commit']
            sha = commit['oid']
            evidence['graphql_signature'] = commit['signature']
    if method in {'pr', 'merge'}:
        if method == 'merge':
            number = int(os.environ['LAB_PR_NUMBER'])
            pr = read(f'{endpoint}/pulls/{number}')
            assert pr['base']['ref'] == branch and pr['head']['repo']['full_name'] == repo
            sha = pr['head']['sha']
            evidence.update(pr_number=number, pr_url=pr['html_url'], head_sha=sha)
        for attempt in range(5):
            result = api(f'{endpoint}/pulls/{evidence["pr_number"]}/merge',
                         dict(merge_method='merge', sha=sha), method='PUT', check=False)
            if 'mergeable state is unknown' not in result.stderr.lower() + result.stdout.lower():
                break
            time.sleep(2)
        if result.returncode == 0:
            merged = json.loads(result.stdout)
            assert merged['merged'], merged
            evidence['merge_sha'] = merged['sha']
    evidence.update(succeeded=result.returncode == 0, stdout=result.stdout, stderr=result.stderr,
                    attempted_sha=sha, after=read(f'{endpoint}/git/ref/heads/{branch}')['object']['sha'])
    if sha and (result.returncode == 0 or method in {'pr', 'merge'}):
        commit = read(f'{endpoint}/commits/{sha}')
        verification = commit['commit']['verification']
        evidence['commit_url'] = commit['html_url']
        evidence['verification'] = {k: verification[k] for k in ['verified', 'reason', 'verified_at']}
        evidence['author'] = commit['commit']['author']
        evidence['committer'] = commit['commit']['committer']
        if method in {'contents', 'graphql'}:
            assert verification['verified'] and verification['reason'] == 'valid', verification
            assert len(commit['files']) == (2 if method == 'graphql' else 1)
        else:
            assert not verification['verified'] and verification['reason'] == 'unsigned', verification
    Path('evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    summary = '## Experiment evidence\n\n```json\n' + json.dumps(evidence, indent=2) + '\n```\n'
    print(summary)
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
        output.write(summary)
    assert evidence['succeeded'] == (expected == 'allow'), 'Unexpected operation result'
    if expected == 'deny':
        assert evidence['before'] == evidence['after'], 'Rejected operation changed target branch'
        errors = (result.stdout + result.stderr).lower()
        assert any(text in errors for text in ['verified signatures', 'required status check',
                    'must be signed', 'rule violations', 'protected branch']), errors
    else:
        assert evidence['before'] != evidence['after'], 'Successful operation did not update target'


if __name__ == '__main__':
    run()
