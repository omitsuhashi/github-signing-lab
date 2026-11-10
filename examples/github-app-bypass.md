# GitHub App・Actions・Bypass はどうつながるか

**今回の GitHub App は、専用の実行者として認証し、その権限を管理するための登録情報です。実際のコードは Actions の runner 上で動きます。**
Actions が App のトークンを使って操作すると、GitHub がその App の権限と Ruleset の Bypass を判定します。
この用途では別の常駐サーバーや Web アプリを作りません。一般の GitHub App は開発者のサーバーで処理する構成もありますが、今回は Actions が処理の実行場所です。

## それぞれ、どこに何があるか

| 要素 | 場所と役割 |
|---|---|
| GitHub App の登録 | GitHub 上。App の名前・権限・認証に使う公開鍵などを管理する |
| App のインストール | GitHub 上。「この App に、どのアカウントのどのリポジトリを操作させるか」を許可する |
| workflow / スクリプト | リポジトリに保存し、Actions runner が実行する。編集・commit・push・PR などの処理本体 |
| App 用秘密鍵 | Actions Secret に保存し、runner が App の認証に使う。コミット署名用の GPG 鍵とは別 |
| installation access token | 実行時に GitHub から取得する、対象・権限・期限のある認証情報 |
| Ruleset の Bypass list | GitHub 上。どの実行者に、その Ruleset の例外を認めるかを定義する |

「App を作る」は処理サーバーの構築ではなく専用の実行者の登録、「インストール」は操作対象の許可です。
App の登録・インストール・Bypass 設定は別の操作であり、どれか1つだけで全部が有効になるわけではありません。

## 準備時にすること

例えば `repository-update-bot` という用途専用の App を登録します。必要な Repository permissions は Contents: Read and write、PR を扱うなら Pull requests: Read and write、必須の Metadata: Read-only です。
App は対象リポジトリだけを選んでインストールします。今回は認証だけに使うので Webhook はオフにし、ユーザーとしての OAuth 認可も使いません。

App の Client ID を Actions Variable、App 用秘密鍵を Actions Secret に保存します。workflow は `actions/create-github-app-token` で installation token を取得します。
App の鍵で本人確認し、インストール時に許可した範囲の token を得る関係です。App ID と Client ID は別の識別子なので、利用する Action の input に合う値を渡します。

リポジトリ管理者は **署名必須だけの Ruleset** を用意し、Bypass list にこの App を追加します。App 自身に Ruleset を編集する Administration 権限を与える必要はありません。
Bypass は書き込み権限を新たに与える設定ではなく、許可済みの操作に対してルールの例外を認める設定です。

## 実行時の流れ

```text
Actions runner が workflow を実行
  ↓ App 用秘密鍵で認証し、GitHub から installation token を取得
runner がその token を使い、push / PR マージ等を要求
  ↓
GitHub が「この App による操作」と識別
  ↓ 対象リポジトリへのアクセス・操作権限を確認
対象ブランチの Ruleset を評価
  ↓ この App が Bypass に登録され、操作がモードの条件を満たすか
その Ruleset の例外を適用 ＋ 他の適用ルールを評価
  ↓
許可されればリモートブランチ更新、満たさなければ拒否
```

処理を動かすのは runner、認証の主体は App、許可・Bypass を判定するのは GitHub です。App の登録情報が自分でコードを実行するわけではありません。

**push やマージの認証に、その App の token を使うことが必須です。** App を Bypass に追加しても、通常の GITHUB_TOKEN や個人の token に自動で例外が引き継がれるわけではありません。
gh には GH_TOKEN として渡し、git push には checkout の token や Git の認証設定として渡します。GH_TOKEN を設定しただけでは、git push の認証まで切り替わりません。
git config の user.name / user.email はコミットの記録であり、GitHub が判定する認証主体の切り替えにはなりません。

## Bypass を使った結果は「署名が付く」ではない

署名ルールを Bypass した未署名コミットは、**未署名のまま例外として通ります**。App の作成・認証・Bypass 登録だけでコミットが Verified に変わるわけではありません。

| 署名 Ruleset の Bypass モード | 操作と条件 |
|---|---|
| Always allow | App の操作について、この Ruleset の直接 push にも例外を使える。ただし別のルールや権限も満たす必要がある |
| For pull requests only | 保護先への直接 push の例外には使えない。作業ブランチから PR を経由し、例外を使うマージ操作も App の token で行う |

PR の作成者が App であるだけでは、別の人が行うマージに App の例外を使えるわけではありません。
また、Bypass は選択した Ruleset 全体に効きます。署名だけの Ruleset に App の例外を付け、維持したいレビュー・CI 等は別の Ruleset にし、そこにはこの App の Bypass を付けません。

## このリポジトリのサンプルとの関係

[GraphQL / ghcommit の最小サンプル](required-flow.md)は、GITHUB_TOKEN で署名付きコミットを作る方式です。専用 App の作成や Bypass を前提にしていません。
この資料は、別案である「通常の未署名 git commit / git push を専用 App として行い、署名ルールだけを例外にする方式」の説明です。App で API 署名を行うこともできますが、認証方法と署名／Bypass は別の選択です。

2026-11-09の [既存の実測結果](../RESULTS.md#対策2専用-github-app-の-bypass)では、Bypass なしの拒否、Always allow の成功、PR 限定での直接 push 拒否と App による PR マージ成功を確認しました。
App token の取得と受け渡しは [当時の workflow](../.github/workflows/signing-lab.yml)、Git の認証設定は [検証スクリプト](../scripts/experiment.py)で確認できます。
検証 App・鍵・Secret・一時 Bypass は検証後に削除した記録があります。**今回の資料追加では再作成・設定変更・実験の再実行をしていません。**

## 公式資料（2026-11-10確認）

- [App の登録と権限](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app)
- [Actions で App として認証する手順](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/making-authenticated-api-requests-with-a-github-app-in-a-github-actions-workflow)
- [Ruleset の Bypass 設定](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository#granting-bypass-permissions-for-your-branch-or-tag-ruleset)
- [複数 Ruleset の適用](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets#about-rule-layering)
