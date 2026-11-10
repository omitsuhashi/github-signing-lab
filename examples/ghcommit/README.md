# ghcommit で署名コミット → PR → CI

**自作の JSON 組み立てをなくす**例です。ファイル編集用 Python は既存のものを使い、コミットを [planetscale/ghcommit](https://github.com/planetscale/ghcommit) に任せます。
まず [必要な流れの一覧](../required-flow.md) を読むと、どこまで自分で用意するかを確認できます。

## 構成と実行

- [編集用 Python](../../scripts/edit-graphql-example.py)：config の編集、obsolete の削除、before → after の名前変更。認証は扱わない。
- [ghcommit-example.yml](../../.github/workflows/ghcommit-example.yml)：ghcommit の準備 → 作業ブランチ作成 → 編集 → コミット → PR → CI 起動。
- [共通 CI](../../.github/workflows/graphql-example-ci.yml)：既存方式と同じファイル検査。編集/コミット処理を混ぜない。

1. 検証リポジトリの **Actions → Minimal ghcommit PR and CI → Run workflow → main** で実行する。
2. 生成側 Summary の Verified commit と PR を開き、署名と差分を確認する。
3. **Minimal GraphQL CI** の別実行が success になり、checked_sha が PR head と一致することを確認する。

権限は既存方式と同じです。生成側は contents / pull-requests / actions の write、CI は contents / pull-requests の read。
Settings → Actions → General の **Allow GitHub Actions to create and approve pull requests** も必要で、検証リポジトリではオンです。token の既定権限は read のままです。
gh は GH_TOKEN、ghcommit は GITHUB_TOKEN を読むので、workflow がそれぞれに github.token を渡します。別の鍵・App・Secret は作りません。

## コミット部分はこのコマンド

編集後、更新先の既存ブランチと更新前 SHA を指定して実行します。

```sh
ghcommit --repository "$GITHUB_REPOSITORY" --branch "$BRANCH" \
  --sha "$(git rev-parse HEAD)" --message "Update dummy files with ghcommit" \
  --add examples/graphql/files/config.json --add examples/graphql/files/after.txt \
  --delete examples/graphql/files/obsolete.txt --delete examples/graphql/files/before.txt
```

**この版では git add・git commit・git push は不要です。** --add は「このパスの今の作業ファイルを送る」、--delete は「リモートのこのパスを削除する」という指定です。
名前変更は旧パスの --delete と新パスの --add。ghcommit がファイルを読み、Base64・GraphQL JSON を作って送信します。
`--sha` は expectedHeadOid に相当し、更新先ブランチがその SHA から進んでいれば拒否されます。ローカルの HEAD は更新されません。
このバージョンはログにコミット URL を出力します。workflow は更新後のリモート SHA を取得し、verified=true / reason=valid を検査して後続へ渡します。

## 自作 Python 版との違い

| 項目 | [既存の Python + gh api 版](../graphql/README.md) | この ghcommit 版 |
|---|---|---|
| ファイル編集 | 同じ編集用 Python | 同じ編集用 Python |
| 公開対象の選択 | git add でステージする | --add / --delete にパスを指定する |
| 読み出す内容 | Git index の内容 | 指定した作業ファイルの現在の内容 |
| JSON / Base64 | 自作 Python | ghcommit 内部 |
| コミット・ブランチ更新 | createCommitOnBranch | 同じ mutation を ghcommit が呼ぶ |
| PR / CI 起動 | gh pr create / gh workflow run | 同じ |
| 追加依存 | Python 標準ライブラリと既存 helper | ghcommit バイナリ |

**git add 後に未ステージの編集がある場合、送られる内容が両方式で異なります。** ghcommit は Git index を送るツールではありません。
この例では変更パスが固定なので、一覧をそのまま --add / --delete に渡します。可変のファイルを扱う場合は対象パスの収集が別途必要です。JSON の自作は不要です。
両方式ともコミット後に git push せず、PR を作り、source branch を ref として共通 CI を明示 dispatch します。
CI は checkout / 入力 SHA / PR head / run SHA の一致と編集結果を検査します。生成側の緑だけでは CI の合格にはなりません。

## 確認済みの実行（2026-11-10）

[生成側 success](https://github.com/omitsuhashi/github-signing-lab/actions/runs/42734455420) →
[Verified コミット](https://github.com/omitsuhashi/github-signing-lab/commit/2dba9d25c3fc4513efc885fbbdd0ce5eecae1851) →
[PR #11](https://github.com/omitsuhashi/github-signing-lab/pull/11) →
[共通 CI success](https://github.com/omitsuhashi/github-signing-lab/actions/runs/42734486326) まで実行しました。
編集・削除・名前変更は1コミットで、CI の検査 SHA は PR head と一致。main の初期ダミーは維持しました。
公式の Mac バイナリ＋ダミー token＋ローカル模擬 API でも、未ステージの作業内容を送ること、HEAD/index 不変、API エラーと欠損ファイル時の失敗を確認しました。

## インストールと範囲

workflow は公式の **v0.1.78 / Linux amd64** を取得し、リリース資産の SHA-256 を固定値と照合してから実行します。
ローカルで使う場合は OS/CPU に合う[公式リリース](https://github.com/planetscale/ghcommit/releases/tag/v0.1.78)を使うか、Go があれば `go install github.com/planetscale/ghcommit@v0.1.78` で導入します。
ローカルでは GITHUB_TOKEN に加え、GitHub.com 向けなら GITHUB_GRAPHQL_URL=https://api.github.com/graphql を設定します。
バージョン・ハッシュを更新する際は、同じ試験をやり直してください。

通常ファイルの小さな固定ダミー専用です。Python 版にある非対応 file mode の検出は、この CLI への単純な置換で引き継がれません。symlink・実行権限・submodule・大容量へ一般化しません。
生成 PR は確認用で、初期ダミーを保つため **main にマージしない**でください。CI は PR head を検査するもので、必須チェック設定・マージ・本番適用は含めません。
API 呼び出し後の検証や PR 作成が失敗しても、作成済みコミットは残り得ます。状態を照合してから再実行してください。

出典（2026-11-10確認）：[公式 README](https://github.com/planetscale/ghcommit/tree/v0.1.78)、[CLI の実装・--sha とファイル読み出し](https://github.com/planetscale/ghcommit/blob/v0.1.78/main.go)。
