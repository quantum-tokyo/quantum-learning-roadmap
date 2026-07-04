# Quantum Learning Roadmap

このページは [Quantum Tokyo](https://github.com/quantum-tokyo) コミュニティが作成した、IBM Quantum Challenge を題材とした量子コンピューティングの学習教材です。

IBM Quantum Challenge は2019年から IBM 主催で開催されている量子コンピュータのイベントです。    
オープンソース開発キットの Qiskit を使って、量子コンピューティングに関する問題に取り組みます。

本教材では過去の Quantum Challenge の問題を扱いながら量子コンピューティングの基礎を学ぶことが出来ます。

![](./resources/group-working.png)

## Labを始める前に
一部のLabでは実行するにあたってIBM QuantumのAPIトークンを必要とするものがあります。  
自分でハンズオンを進めたい方は以下の手順に沿ってAPIトークン情報の配置を行ってください。

![APIトークンの取得](./resources/ibmq_get_apitoken.png)

1.   [IBM Quantum Platform](https://quantum.ibm.com/)に移動します。
1.   右上にある API トークン (上の図参照) をクリックしてコピーします。
1.   このプロジェクトのルートディレクトリの配下に`.env`ファイルを作成します。
1.   `.env.sample`を参考に、3でコピーしたAPI トークンを`QXToken`の値に貼り付けます。

```
QXToken=[.envを作成し、ここにAPIトークンを貼り付けます]
```

## 過去の IBM Quantum Challenge一覧

- [2019年](https://github.com/quantum-challenge/2019#ibm-quantum-challenge%E3%81%B8%E3%82%88%E3%81%86%E3%81%93%E3%81%9D)(全notebook和訳あり)
- [2020年春](https://github.com/qiskit-community/may4_challenge_exercises)
- [2020年秋](https://github.com/qiskit-community/IBMQuantumChallenge2020#ibm-quantum-challenge%E3%81%B8%E3%82%88%E3%81%86%E3%81%93%E3%81%9D)(全notebook和訳あり)
- [2021年春](https://github.com/qiskit-community/ibm-quantum-challenge-2021)(全notebook和訳あり)
- [2021年アフリカ](https://github.com/qiskit-community/ibm-quantum-challenge-africa-2021) ([Lab1：リョウコと量子コンピューターで農地収穫量の最適化](https://github.com/purepureclub/IFCO2021DEC/blob/main/IFCO2021Dec_qiskit_handson.ipynb), [Lab3](https://github.com/kifumi/introduction/blob/main/materials/QuantumChallengeAfrica2021/lab3/lab3_ja.ipynb)のみ和訳あり)
- [2021年秋](https://github.com/qiskit-community/ibm-quantum-challenge-fall-2021)(全notebook和訳あり)
- [2022年春](https://github.com/qiskit-community/ibm-quantum-spring-challenge-2022)(全notebook和訳あり)
- [2022年秋](https://github.com/qiskit-community/ibm-quantum-challenge-fall-22)(全notebook和訳あり)
- [2023年春](https://github.com/qiskit-community/ibm-quantum-challenge-spring-2023)(全notebook和訳あり)
- [2024年](https://github.com/qiskit-community/ibm-quantum-challenge-2024)(全notebook和訳あり)・[解説動画(日本語)](https://www.youtube.com/playlist?list=PLA-UlvpIBvpsV3fqLjlvfpJdeZLcuowOf)