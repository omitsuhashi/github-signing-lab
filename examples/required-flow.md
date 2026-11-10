# 結局、何を用意すればよいか

署名付きコミットの作成とリモートブランチ更新を GitHub API に任せる場合の、必要な流れです。

## どちらの方式でも必要

1. **準備**：checkout、認証、書き込み権限、更新先のリモートブランチを用意する。
2. **編集**：Python 等でファイルを編集・削除・名前変更する。
3. **公開対象を選ぶ**：下表の方法で、送る内容と削除パスを決める。
4. **コミット・ブランチ更新**：GraphQL を直接呼ぶか、ghcommit に呼ばせる。
5. **PR**：gh pr create で base / head を指定して作る。
6. **CI**：gh workflow run で source branch と PR head SHA / PR番号を渡して起動し、別実行の成功を確認する。

| 方法 | 編集後に必要な処理 |
|---|---|
| [自作 Python + gh api graphql](graphql/README.md) | git add → ステージ差分と全文を読む → JSON / Base64 を作る → gh api graphql |
| [ghcommit](ghcommit/README.md) | --add / --delete のパスを選ぶ → ghcommit を実行。JSON / Base64 はツールに任せる |

**標準 gh は、git add しただけの状態から自動で署名コミットを作るコマンドを提供していません。**
自作版は「Git index → API の JSON」の変換が必要で、サンプルのコミット用 Python が担当しています。
ghcommit 版は **git add 自体が不要**ですが、送る作業ファイルと削除パスの指定は必要です。
「JSON を自作しなくてよい」と「公開対象を何も指定しなくてよい」は別です。

## 終了する位置

```text
自作版    編集 → git add → PythonでJSON作成 → gh api graphql ┐
                                                           ├→ 署名コミット＋リモート更新 → PR → CI
ghcommit版 編集 → --add/--deleteの指定 → ghcommit             ┘
```

どちらも **git commit / git push を別途実行しません**。GitHub 側でコミットとリモートブランチ更新が完了します。
API 実行後もローカル HEAD / index は進まないため、サンプルは新しい checkout で1回コミットする構成です。

## このリポジトリで自分が行う操作

- **Actions から使う**：目的の workflow を main から Run workflow → Summary の署名と PR を確認 → CI の success と検査 SHA を確認。
- **別プロジェクトへ移す**：編集処理、公開対象パス、リポジトリ・base/source branch、CI のテストをその用途に合わせる。必要権限と PR 作成許可も確認する。

GITHUB_TOKEN による PR のイベント CI は承認待ちになり得るので、両サンプルは workflow_dispatch で CI を明示起動します。
署名成功は、PR レビューや必須チェックを免除しません。ダミー PR は main にマージせず、確認後に close します。

詳細・出典は [自作版](graphql/README.md) と [ghcommit 版](ghcommit/README.md)。
両方式とも署名コミット → PR → CI 成功まで実行済みで、各 README に確認済みの実行リンクを残しています。
