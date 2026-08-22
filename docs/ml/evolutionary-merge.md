# Evolutionary LoRA Merge

## MVPアルゴリズム

`GeneticOptimizer`は、LoRAアダプターごとのlogitをゲノムとして保持します。評価時にsoftmaxで非負かつ総和1の係数へ変換します。

- 初期個体群：等加重1個体＋seed固定の正規乱数個体
- 選択：トーナメント選択
- 交叉：blend crossover
- 突然変異：ガウスノイズ
- エリート保存：既定2個体
- 早期終了：改善幅とpatience
- 隔離：例外、NaN、Infinityを負の無限大として記録
- チェックポイント：世代ごとにJSONをatomic replace

## 互換性

マージ前に次のメタデータが完全一致することを要求します。

- base model IDとrevision
- LoRA rank
- target modules
- Safetensorsのテンソル名とshape

不一致時にテンソルを無理に変換しません。上位のオーケストレーターがアンサンブル、ルーター、RAG、タスク別モデルへ切り替えます。

## 評価データ

業務データは`project_group`単位でまとめ、時間順にtrain/validation/testへ分割します。同一プロジェクトを複数splitへ入れません。進化探索はvalidationまでを使用し、testは最終候補の一度だけの評価に使います。

本番向け適応度では、品質、校正、根拠整合性、採用後実績から、レイテンシ、メモリ、安全性違反、公平性ギャップを差し引きます。スカラー値に加えて各指標を保存するため、将来NSGA-IIへ置換できます。

