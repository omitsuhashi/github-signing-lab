"""Replace git commit + git push with one signed GraphQL commit on an existing branch."""
import base64
import json
import os
import subprocess
import sys

from experiment import api, command, read


def staged_file_changes():
    fields = command(['git', 'diff', '--cached', '--raw', '--no-renames', '-z']).stdout.split('\0')
    changes = dict(additions=[], deletions=[])
    for metadata, path in zip(fields[:-1:2], fields[1:-1:2]):
        old_mode, new_mode, _, _, status = metadata.lstrip(':').split()
        # FileChanges has no file-mode field; reject modes this sample cannot preserve.
        if status not in {'A', 'M', 'D'} or {old_mode, new_mode} - {'000000', '100644'}:
            raise ValueError(f'Only ordinary non-executable files are supported: {path}')
        if status == 'D':
            changes['deletions'].append(dict(path=path))
        else:
            content = subprocess.check_output(['git', 'show', ':' + path])
            changes['additions'].append(dict(path=path, contents=base64.b64encode(content).decode()))
    return changes


def main():
    if len(sys.argv) != 3:
        raise SystemExit('Usage: python3 scripts/commit-with-graphql.py BRANCH "Commit message"')
    branch, message = sys.argv[1:]
    command(['git', 'check-ref-format', '--branch', branch])
    if command(['git', 'rev-parse', '--show-prefix']).stdout.strip():
        raise SystemExit('Run from the repository root')
    files = staged_file_changes()
    if not any(files.values()):
        print('No staged changes; no API request sent.')
        return
    repo = os.environ['GITHUB_REPOSITORY']
    expected_head = command(['git', 'rev-parse', 'HEAD']).stdout.strip()
    query = '''mutation($input: CreateCommitOnBranchInput!) {
      createCommitOnBranch(input: $input) {
        commit { oid url signature { isValid wasSignedByGitHub } }
      }
    }'''
    result = json.loads(api('graphql', dict(query=query, variables=dict(input=dict(
        branch=dict(repositoryNameWithOwner=repo, branchName=branch),
        expectedHeadOid=expected_head, message=dict(headline=message), fileChanges=files)))).stdout)
    if result.get('errors'):
        raise RuntimeError(result['errors'])
    commit = result['data']['createCommitOnBranch']['commit']
    assert commit['signature'] == dict(isValid=True, wasSignedByGitHub=True), commit
    verification = read(f'repos/{repo}/commits/{commit["oid"]}')['commit']['verification']
    assert verification['verified'] and verification['reason'] == 'valid', verification
    remote_head = read(f'repos/{repo}/git/ref/heads/{branch}')['object']['sha']
    assert remote_head == commit['oid'], 'Remote branch changed after the API commit'
    evidence = dict(branch=branch, previous_sha=expected_head, commit_sha=commit['oid'],
                    commit_url=commit['url'], verified=True, reason=verification['reason'],
                    additions=[f['path'] for f in files['additions']],
                    deletions=[f['path'] for f in files['deletions']])
    print(json.dumps(evidence, indent=2))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
            output.write('## GraphQL signed commit\n\n```json\n' + json.dumps(evidence, indent=2) + '\n```\n')


if __name__ == '__main__':
    main()
