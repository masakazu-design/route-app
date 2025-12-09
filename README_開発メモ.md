# 環境整備スケジュール作成システム 開発メモ

## 公開先・リポジトリ

| 項目 | URL |
|------|-----|
| **本番アプリ** | https://o2-route-scheduler.streamlit.app/ |
| **GitHubリポジトリ** | https://github.com/masakazu-design/route-app |
| **ホスティング** | Streamlit Community Cloud（無料） |

---

## このシステムはどうやって作ったか

### 使用したツール

| ツール | 用途 |
|--------|------|
| **Claude Code (Anthropic)** | AIアシスタント。会話形式でプログラムを作成・修正。このシステムのほぼ全てのコードを生成 |
| **VS Code** | コードエディタ。Claude Codeと連携して使用 |
| **Python** | プログラミング言語 |
| **Streamlit** | Webアプリフレームワーク。Pythonだけでブラウザで動くアプリが作れる |
| **Streamlit Community Cloud** | 無料ホスティング。GitHubと連携して自動デプロイ |
| **GitHub** | ソースコード管理。プッシュすると自動でデプロイされる |
| **Google Maps API** | 住所→座標変換、移動時間計算 |
| **Google マイマップ** | 訪問先データの管理（KML形式で出力） |

---

## 開発の流れ

### 1. 要件を会話で伝える
Claude Codeに「こういうアプリが欲しい」と日本語で説明するだけ。

例：
- 「環境整備の訪問スケジュールを最適化するアプリを作って」
- 「きたえるーむは17:00固定で訪問したい」
- 「昼食は11:30〜13:00の間に取りたい」

### 2. Claude Codeがコードを生成
- 要件を理解してPythonコードを自動生成
- エラーがあれば自動で修正
- 「これでいい？」と確認してくれる

### 3. GitHubにプッシュ
- `git add` → `git commit` → `git push`
- これもClaude Codeが自動でやってくれる

### 4. 自動デプロイ
- Streamlit Community CloudがGitHubの変更を検知
- 1〜2分で本番環境に反映

---

## GitHub + Streamlit の連携設定（初回のみ）

### 1. GitHubアカウント作成
- https://github.com/ でアカウント作成
- リポジトリを作成（例: `route-app`）

### 2. ローカルからGitHubにプッシュ
```bash
git init
git add .
git commit -m "初回コミット"
git remote add origin https://github.com/masakazu-design/route-app.git
git push -u origin main
```

### 3. Streamlit Community Cloudでデプロイ
1. https://share.streamlit.io/ にアクセス
2. GitHubアカウントでログイン
3. 「New app」をクリック
4. リポジトリ、ブランチ（main）、メインファイル（app.py）を選択
5. 「Deploy」をクリック

### 4. シークレット設定（APIキー）
1. Streamlit Cloudのアプリ設定 → 「Secrets」
2. Google Maps APIキーなどを設定
```toml
GOOGLE_MAPS_API_KEY = "AIza..."
```

### 以降の更新
- `git push` するだけで自動的に本番に反映される

---

## なぜプログラミング経験がなくても作れたか

### Claude Codeの役割
1. **コード生成**: 「〇〇したい」と言うだけでコードを書いてくれる
2. **デバッグ**: エラーが出たら自動で原因を特定して修正
3. **Git操作**: コミットやプッシュも自動
4. **ドキュメント作成**: 使い方ガイドなども生成

### 人間（石田）の役割
1. **要件を伝える**: 「こうしたい」「ここが使いにくい」
2. **動作確認**: 実際に使って問題点を見つける
3. **判断**: 「これでOK」「もうちょっとこうして」

---

## 主要な技術的仕組み

### ルート最適化
- **TSP（巡回セールスマン問題）アルゴリズム**を使用
- 全ての訪問先を回る最短ルートを計算
- 「2-opt法」で解を改善

### 時間制約の処理
- 最初の訪問先は8:00到着固定
- きたえるーむは17:00固定
- 昼食休憩は11:30〜13:00の間

### 地図表示
- **Folium**ライブラリでインタラクティブな地図を表示
- Google Mapsと連携してナビリンクを生成

---

## ファイル構成

```
route_app/
├── app.py                 # メインのアプリケーション（約3000行）
├── requirements.txt       # 必要なPythonライブラリ
├── 使い方ガイド.md         # 社員向け操作マニュアル
├── README_開発メモ.md      # このファイル
└── .streamlit/
    └── secrets.toml       # APIキーなどの秘密情報
```

---

## 開発で学んだこと

### うまくいったこと
- 会話だけでアプリが作れる
- 修正も「ここをこうして」で済む
- エラーが出てもAIが直してくれる

### 注意点
- 一度に大きな変更を頼むとバグが出やすい
- 小さな修正を積み重ねるのがコツ
- 動作確認は人間がしっかりやる必要がある

---

## 今後のメンテナンス

### 修正が必要になったら
1. Claude Codeを起動
2. 「〇〇を修正して」と伝える
3. 動作確認してOKならプッシュ

### よくある修正例
- 「滞在時間を変更したい」→ 定数を修正
- 「新しい訪問先の種類を追加したい」→ 条件分岐を追加
- 「表示を変えたい」→ UI部分を修正

---

## 参考リンク

- [Streamlit公式](https://streamlit.io/)
- [Claude Code](https://claude.ai/)
- [Streamlit Community Cloud](https://share.streamlit.io/)

---

## 最後に

このシステムは、プログラミングの知識がほとんどなくても、AIアシスタント（Claude Code）との会話だけで作成できた。

重要なのは：
1. **何がしたいかを明確に伝える**
2. **実際に使って問題点を見つける**
3. **小さな修正を積み重ねる**

プログラミングの専門知識は不要。業務の知識（環境整備の流れ、制約条件など）の方が重要。
