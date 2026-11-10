# GraphQL の署名コミット → PR 作成 → CI の最小サンプル

Actions 内でファイルを編集し、**署名付きコミット → ブランチ更新 → PR 作成 → CI 起動**まで行う例です。
GITHUB_TOKEN を使い、GPG 秘密鍵・専用 App・追加の Python パッケージは用意しません。
[必要な流れの一覧](../required-flow.md)と、JSON の自作を省く [ghcommit 版](../ghcommit/README.md)も参照できます。

## 構成

| ファイル | 担当 |
|---|---|
| [edit-graphql-example.py](../../scripts/edit-graphql-example.py) | ダミーファイルの編集・削除・名前変更。API や認証は扱わない |
| [commit-with-graphql.py](../../scripts/commit-with-graphql.py) | git add 済みの変更を読み、GraphQL で署名付きコミットを作る。業務的な編集は行わない |
| [graphql-example.yml](../../.github/workflows/graphql-example.yml) | checkout → 作業ブランチ作成 → 編集 → git add → API コミット → PR → CI 起動 |
| [graphql-example-ci.yml](../../.github/workflows/graphql-example-ci.yml) | PR head と同じ SHA を checkout し、編集結果を検査する。書き込みは行わない |

コミット側は、既存の [experiment.py の command / api / read](../../scripts/experiment.py) を共通の Git/gh 呼び出しに再利用します。
別のリポジトリへ移す際はこの3関数も必要です。import だけでは既存の検証は実行されません。

## 何を置き換えるか

通常の処理：

```sh
python3 scripts/edit-graphql-example.py
git add -A -- examples/graphql/files
git commit -m "Update dummy files"
git push origin HEAD:"$BRANCH"
```

このサンプル：

```sh
python3 scripts/edit-graphql-example.py
git add -A -- examples/graphql/files
python3 scripts/commit-with-graphql.py "$BRANCH" "Update dummy files"
```

編集と `git add` は同じです。最後の2コマンドを Python の呼び出し1つに置き換えます。
**git add で選んだ内容だけ**を送り、ステージ後に行った未ステージの編集は送りません。
API がコミット作成とリモートブランチ更新を行うので、後続の git push は不要です。
ローカルの HEAD/index は API コミットへ進みません。以降の PR/CI には API が返した SHA を渡します。
編集用 Python は認証を扱わず、コミット用 Python に PR/CI 処理は入れません。PR/CI の呼び出しは workflow の担当です。

## 実行手順

1. **Settings → Actions → General → Workflow permissions** で **Allow GitHub Actions to create and approve pull requests** をオンにして保存する。既定の token 権限は read のままでよい。
2. **Actions → Minimal GraphQL signed commit → Run workflow** を開き、**Use workflow from: main** で実行する。
3. Summary の commit_url と PR のリンクを開き、Verified と変更内容を確認する。
4. **Minimal GraphQL CI** の実行も success になったことを確認する。CI Summary の checked_sha は PR head と一致する。

検証リポジトリでは手順1の許可を有効にしています。PR のレビュー承認を自動投稿する処理はありません。
YAML では生成側に次の権限を付け、`GH_TOKEN: ${{ github.token }}` で gh を認証します。CI 側は contents / pull-requests の read だけです。

| 権限 | 用途 |
|---|---|
| contents: write | ブランチ作成と GraphQL コミット |
| pull-requests: write | gh pr create |
| actions: write | gh workflow run による別 CI workflow の起動 |

作成する `sample/graphql-RUN_ID-ATTEMPT` は毎回別の作業ブランチです。main と過去の実験ブランチは更新しません。
**main から新しく Run workflow** すれば毎回初期ダミーから始められます。
生成 PR は検証専用です。main の初期ダミーを保つためマージせず、確認後に close してください。

編集用 Python が行うこと：config.json の timeout を30→60に変更、obsolete.txt を削除、before.txt を after.txt に名前変更。
コミット側には特定のファイル名や編集値を埋め込んでいないので、編集用 Python を別の生成・整形処理に差し替えられます。
workflow の git add の対象も、その処理で公開したい範囲に合わせて変更してください。

## PR 作成と CI 起動は gh の標準コマンド

GraphQL の後は、workflow にある次のコマンドを順に使います。PR_NUMBER は作成した PR の番号、COMMIT_SHA はコミット用 Python の出力です。

```sh
gh pr create --repo "$GITHUB_REPOSITORY" --base main --head "$BRANCH" \
  --title "Dummy GraphQL update" --body "Dummy-only example"
gh workflow run graphql-example-ci.yml --repo "$GITHUB_REPOSITORY" --ref "$BRANCH" \
  -f expected_sha="$COMMIT_SHA" -f pr_number="$PR_NUMBER"
```

`gh pr create` は PR の URL を返すので、workflow は末尾から PR 番号を取得します。
コミット用 Python は `GITHUB_OUTPUT` に commit_sha を書き、workflow は steps.commit.outputs.commit_sha で受け取ります。
`--ref` に source branch を指定するため、CI の run/check 自体もそのブランチの head に紐づきます。
CI は **checkout の HEAD = 入力 SHA = 現在の PR head = CI run の GITHUB_SHA** を検査してから、timeout=60・削除・名前変更後の内容を検査します。
CI の本体はこの短い assert 群です。実際の用途ではプロジェクトのテストコマンドに置き換えます。

GITHUB_TOKEN が作った PR の pull_request CI は承認待ちになり得ます。この例は **workflow_dispatch を明示的に起動**するので、人の承認待ちに依存しません。
CI workflow には workflow_dispatch だけを設定し、PR イベントとの二重起動も避けています。default branch にも両 workflow を配置する必要があります。
生成側の緑は「CI 起動要求まで成功」であり、CI 自体の成功は別の実行で確認します。後で PR を編集してもこの CI は自動再実行されません。
[起動条件の公式仕様](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)、
[gh pr create](https://cli.github.com/manual/gh_pr_create)、[gh workflow run](https://cli.github.com/manual/gh_workflow_run)。

### 確認済みの実行（2026-11-10）

[生成側](https://github.com/omitsuhashi/github-signing-lab/actions/runs/42732388471) →
[Verified コミット](https://github.com/omitsuhashi/github-signing-lab/commit/f44d42965839fdbe4fb87a35e819951223526ec3) →
[PR #8](https://github.com/omitsuhashi/github-signing-lab/pull/8) →
[CI success](https://github.com/omitsuhashi/github-signing-lab/actions/runs/42732415567) まで実行しました。CI の検査 SHA は PR head と同一です。
REST Checks API でも同じ SHA の check-files=success と PR #8 への関連を確認しましたが、`gh pr checks` の集約表示は空でした。
この実測では Actions の実行結果と検査 SHA を合否の根拠にしています。必須チェックによるマージ可否を確認したものではありません。

## コミット用 Python の中身

1. `git diff --cached --raw --no-renames -z` でステージ済みの追加・変更・削除を読む。
2. 追加・変更は `git show :PATH` で**ステージ上の全文**を読み、Base64 にして fileChanges.additions へ入れる。
3. 削除は fileChanges.deletions に path を入れる。名前変更も旧 path の削除＋新 path の追加になる。
4. `gh api graphql --input -` で createCommitOnBranch を呼ぶ。JSON は Python から標準入力へ渡す。
5. GitHub の署名、REST の verified=true / reason=valid、リモートブランチの SHA を検査する。

`branch` は更新先の既存ブランチ、`expectedHeadOid` はチェックアウト時のローカル HEAD です。
workflow で先に同じ SHA のリモートブランチを作ってあります。
誰かが先にそのブランチを進めた場合は expectedHeadOid の不一致で拒否され、上書きしません。
競合は最新版を取得して編集・ステージ・検査をやり直します。無条件で head を取り直して再送してはいけません。

GitHub が署名するので `git commit -S` は使いません。author / committer / signature も独自指定しません。
[署名と認証主体の公式仕様](https://docs.github.com/en/graphql/reference/commits#createcommitonbranch)、
[FileChanges の仕様](https://docs.github.com/en/graphql/reference/git#filechanges)。

API を呼ばないローカル確認は `python3 scripts/test-commit-with-graphql.py` で実行できます。
実際の Git index を使い、ステージ内容の保持・削除/名前変更・競合エラー・変更なし・非対応モードの拒否を確認します。

## 署名コミットは自作スクリプト必須か

**必須ではありません。** 2026-11-10時点で確認した選択肢です。

| 方法 | 自分で用意するもの |
|---|---|
| 標準 gh の `gh api graphql` | mutation とファイル内容の組み立て。今回の Python はこの部分を担当 |
| 既存 CLI [planetscale/ghcommit](https://github.com/planetscale/ghcommit) | CLI のインストールと対象ファイル一覧。createCommitOnBranch を内部で呼んで署名する |
| 既存 Action [peter-evans/create-pull-request](https://github.com/peter-evans/create-pull-request/blob/main/docs/concepts-guidelines.md#commit-signing) | `sign-commits: true` と必要な token/権限。署名コミットと PR 作成を任せられる |

[標準 gh のコマンド一覧](https://cli.github.com/manual/gh)には、git add 済みの変更を署名して送る組み込みの `gh commit` はありません。
`gh api graphql` は API を呼ぶ汎用コマンドであり、ステージ差分の検出・Base64 化まで自動で行うコマンドではありません。
gh の拡張でコマンドを追加する仕組みもありますが、標準機能とは区別します。上記 ghcommit は gh と別に導入する CLI です。

ghcommit をインストール済みなら、例えば次の形で自作のコミット用 Python を置き換える選択肢があります。

```sh
GITHUB_TOKEN="$GH_TOKEN" ghcommit -r "$GITHUB_REPOSITORY" -b "$BRANCH" -m "Update dummy files" \
  -a examples/graphql/files/config.json -a examples/graphql/files/after.txt \
  -d examples/graphql/files/obsolete.txt -d examples/graphql/files/before.txt
```

create-pull-request の bot 署名は GITHUB_TOKEN / GitHub App token が対象で、PAT ではこの bot 署名にならないという制約があります。
どちらの既存ツールでも、CI の起動条件は別です。GITHUB_TOKEN で PR を作っただけで、他の CI が必ず無人起動するとは扱いません。
このページの本体は自作 Python のままです。ghcommit は [別サンプル](../ghcommit/README.md)で署名コミット・PR・CI 成功まで実行済みです。create-pull-request Action は公式資料の確認のみで、実行していません。

## 範囲

- 小さな通常ファイル（Git mode 100644）向けです。実行権限付きファイル・symlink・submodule等は、モードを失わないよう送信前に拒否します。
- コミット用 Python は、ステージ済み差分がなければ API を呼びません。
- ローカルで実行する場合は git / Python 3 / gh と認証、GITHUB_REPOSITORY=OWNER/REPO、ローカル HEAD と同じ SHA の更新先ブランチが必要です。セルフチェックには Python 3.11 以上を使います。
- GitHub 側の Ruleset は適用されます。署名成功は、PR・レビュー・必須チェックの免除を意味しません。
- CI は PR head 自体を検査し、base と統合した merge ref のテストではありません。必須チェックの設定・PR マージ・自動リトライ・大容量対応は含めません。
