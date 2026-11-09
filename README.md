# GitHub signing lab

公開・ダミーデータ専用の検証リポジトリです。業務データは扱いません。

手動の **Commit signing lab** Actions で以下を比較します。

- 未署名の `git commit` と push。
- Contents API による1ファイルのコミット。
- GraphQL `createCommitOnBranch` による2ファイルのコミット。
- 専用 GitHub App の未署名 push／PR マージと Ruleset Bypass。
- 署名とは別の Ruleset にある必須チェックが維持されるか。

`lab/signed`、`lab/bypass`、`lab/guarded` だけが実験対象です。
`main` は検証手順・証跡の保存用です。Actions は手動実行のみで、PR のコードは実行しません。

各実行は期待した成功・拒否を assert し、コミットの署名、前後のブランチ SHA、拒否理由を実行サマリーに残します。
拒否が期待される実験でも、期待どおりなら Actions は緑になります。

App の権限は Contents / Pull requests の Read & write と必須 Metadata の Read-only、
インストール先はこのリポジトリだけに限定します。GPG 秘密鍵は使いません。
App 用秘密鍵は Actions Secret にのみ登録し、公開リポジトリやログには含めません。

結果とスクリーンショットは `evidence/` に記録します。

検証は完了しています。[実測結果](RESULTS.md)を参照してください。専用 App と鍵は削除済みで、署名 Ruleset は Active・Bypass なしです。App を使う再実行には、新しい App と認証情報の設定が必要です。
