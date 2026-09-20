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
- 再開：設定が一致するチェックポイントから次世代を再構築

## 互換性

マージ前に次のメタデータが完全一致することを要求します。

- base model IDとrevision
- LoRA rank
- target modules
- Safetensorsのテンソル名、shape、dtype

不一致時にテンソルを無理に変換しません。上位のオーケストレーターがアンサンブル、ルーター、RAG、タスク別モデルへ切り替えます。

## 評価データ

業務データは`project_group`単位でまとめ、時間順にtrain/validation/testへ分割します。同一プロジェクトを複数splitへ入れません。進化探索はvalidationまでを使用し、testは最終候補の一度だけの評価に使います。

本番向け適応度では、品質、校正、根拠整合性、採用後実績から、レイテンシ、メモリ、安全性違反、公平性ギャップを差し引きます。スカラー値に加えて各指標を保存するため、将来NSGA-IIへ置換できます。

## プロジェクト提案モデル

各親アダプターには、同名の`.evaluation.json`を配置します。評価ファイルには次の0〜1指標を保存します。

- `schema_validity`
- `relevance`
- `groundedness`
- `safety`
- `latency_score`

ワーカーはこれらのバージョン固定済みオフライン評価から候補係数を探索し、最良係数で親アダプターを実際にマージして`merged-adapter.safetensors`を生成します。成果物には親パス、係数、評価データセット版、プロンプト版、チェックサムを記録します。

モデルは次の状態遷移を取ります。

1. 実験完了後に`pending / not_deployed`として登録
2. OwnerまたはAdminが承認
3. シャドーデプロイ
4. 比較確認後に`active`へ昇格

プロジェクト提案APIは、組織に対する最新の`approved / active`モデルだけを推論サービスへ渡します。推論サービスはチェックサムを検証してSafetensorsを読み込み、マージ済み重みの信号を構造化提案へ反映します。未承認モデルは選択されません。

開発環境では`AI_PROVIDER=mock`を利用できます。本番で意図しないフォールバックを禁止する場合は`AI_ALLOW_MOCK_FALLBACK=false`を設定します。ユーザーフィードバックは保存されますが、オンライン学習には使用せず、レビュー後の次回オフライン評価データ作成に利用します。


