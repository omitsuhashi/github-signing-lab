# git commit / git push を GraphQL に置き換える最小サンプル

Actions 内でファイルを編集し、**GitHub 側で署名付きコミットを作ってブランチを更新する**例です。
GITHUB_TOKEN を使い、GPG 秘密鍵・専用 App・追加の Python パッケージは用意しません。

## 読むファイルは3つ

| ファイル | 担当 |
|---|---|
| [edit-graphql-example.py](../../scripts/edit-graphql-example.py) | ダミーファイルの編集・削除・名前変更。API や認証は扱わない |
| [commit-with-graphql.py](../../scripts/commit-with-graphql.py) | git add 済みの変更を読み、GraphQL で署名付きコミットを作る。業務的な編集は行わない |
| [graphql-example.yml](../../.github/workflows/graphql-example.yml) | checkout → 作業ブランチ作成 → 編集 → git add → API コミットを順に実行 |

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
ローカルの HEAD/index は API コミットへ進みません。この workflow は1回コミットして終了します。

## 実行手順

1. GitHub の **Actions → Minimal GraphQL signed commit → Run workflow** を開く。
2. **Use workflow from: main** を選び、Run workflow を押す。
3. 実行の Summary にある commit_url を開き、**Verified** と変更内容を確認する。

ワークフローは `contents: write` を明示し、`GH_TOKEN: ${{ github.token }}` で gh を認証します。
この例はコミットまでなので、PR 作成許可・pull-requests: write・actions: write は不要です。
作成する `sample/graphql-RUN_ID-ATTEMPT` は毎回別の作業ブランチです。main と過去の実験ブランチは更新しません。
**main から新しく Run workflow** すれば毎回初期ダミーから始められます。

編集用 Python が行うこと：config.json の timeout を30→60に変更、obsolete.txt を削除、before.txt を after.txt に名前変更。
コミット側には特定のファイル名や編集値を埋め込んでいないので、編集用 Python を別の生成・整形処理に差し替えられます。
workflow の git add の対象も、その処理で公開したい範囲に合わせて変更してください。

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

## 範囲

- 小さな通常ファイル（Git mode 100644）向けです。実行権限付きファイル・symlink・submodule等は、モードを失わないよう送信前に拒否します。
- コミット用 Python は、ステージ済み差分がなければ API を呼びません。
- ローカルで実行する場合は git / Python 3 / gh と認証、GITHUB_REPOSITORY=OWNER/REPO、ローカル HEAD と同じ SHA の更新先ブランチが必要です。セルフチェックには Python 3.11 以上を使います。
- GitHub 側の Ruleset は適用されます。署名成功は、PR・レビュー・必須チェックの免除を意味しません。
- PR 作成・CI 連鎖・マージ・自動リトライ・大容量ファイル対応はこの最小例には含めません。
