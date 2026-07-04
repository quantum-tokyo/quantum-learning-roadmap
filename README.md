# Quantum Learning Roadmap

[![Deploy Book](https://github.com/quantum-tokyo/quantum-learning-roadmap/actions/workflows/deploy-book.yml/badge.svg)](https://github.com/quantum-tokyo/quantum-learning-roadmap/actions/workflows/deploy-book.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE.md)

[Quantum Tokyo](https://github.com/quantum-tokyo) コミュニティが作成した、量子コンピューティングの学習教材です。学習ロードマップに沿って、IBM Quantum Challenge の過去問題をはじめとするさまざまなリソースを題材に、Qiskit を使いながら量子コンピューティングの基礎から応用までを段階的に学べます。

![](./src/resources/ibm-quantum-challenge.png)

## 📖 教材サイト

本教材は Web サイトとして公開しています。**まずはこちらからご覧ください。**

### 👉 https://quantum-tokyo.github.io/quantum-learning-roadmap/

各 Lab の解説を読みながら学習できます。手を動かして自分でハンズオンを進めたい方は、下記「ローカルで動かす」を参照してください。

## この教材について

- **対象**: 量子コンピューティングをこれから学ぶ方、Qiskit を触ってみたい方

### 収録コンテンツ

現在は IBM Quantum Challenge の過去問題を中心に、以下の章立てで学習コンテンツを提供しています。今後、学習ロードマップに沿って他のリソースを基にしたコンテンツも追加予定です。

| 章 | テーマ |
|---|---|
| Chapter 0 | イントロダクション（ハローワールド） |
| Chapter 1 | 量子回路の構築（加算器・テレポーテーション・Grover・量子位相推定 ほか） |
| Chapter 2 | 量子コンピューターの応用（Shor のアルゴリズム・量子機械学習） |
| Chapter 3 | エラー訂正・緩和（量子エラー訂正・実機上での VQC） |
| Chapter X | Qiskit を学ぶ（Runtime・Transpiler・Dynamic Circuits・Circuit Knitting ほか） |

## ローカルで動かす

ノートブックを自分の手で実行したい方向けの手順です。Python 3.12 以上と、パッケージ管理ツール [uv](https://docs.astral.sh/uv/) を使用します。

```bash
# 依存関係のインストール（Python も含めて uv が用意します）
uv sync

# 各 Lab のノートブックを Jupyter で開いて実行する
uv run jupyter lab

# 教材サイトをローカルでプレビューしたい場合
./scripts/build.sh
```

ノートブックは `src/` 以下にあります。`jupyter lab` で開き、セルを実行しながらハンズオンを進めてください。

一部の Lab では IBM Quantum の API トークンが必要です。リポジトリのルートに `.env` を作成し、[IBM Quantum Platform](https://quantum.ibm.com/) で取得したトークンを設定してください（`.env.sample` を参照）。

```
QXToken=<あなたの API トークン>
```

> 詳しい手順は教材サイトの [イントロダクション](https://quantum-tokyo.github.io/quantum-learning-roadmap/) を参照してください。

## コントリビューション

誤りの指摘・改善提案・新しい Lab の追加など、コントリビューションを歓迎します。[Issue](https://github.com/quantum-tokyo/quantum-learning-roadmap/issues) や Pull Request でお気軽にご連絡ください。

## ライセンス

本教材は [Apache License 2.0](./LICENSE.md) の下で公開されています。

## クレジット

- 作成: [Quantum Tokyo](https://github.com/quantum-tokyo) コミュニティ
- 題材: [IBM Quantum Challenge](https://quantum.ibm.com/) の過去問題ほか（Challenge 各年の元リポジトリは教材サイトの[イントロダクション](https://quantum-tokyo.github.io/quantum-learning-roadmap/)に一覧があります）
