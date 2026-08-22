# Security Threat Model

## 主な脅威と制御

| 脅威 | 制御 |
|---|---|
| 組織間データ漏洩 | membership照合、全クエリのtenant条件、分離テスト |
| CSRF | SameSite Cookieとdouble-submit CSRF token |
| XSS | Reactの標準エスケープ、任意HTMLを保存・描画しない |
| SQL injection | SQLAlchemyのパラメータ化クエリ |
| トークン窃取 | HttpOnly Cookie、短命access token、refresh rotation |
| モデル成果物改ざん | SHA-256、Safetensors、ロード元許可リスト用境界 |
| Prompt injection | 検索文書を非命令データとして分離し、引用元を限定 |
| AIによる無断変更 | 提案、採用、差分確認、適用の状態分離 |
| 人事上の不適切な自動判断 | センシティブ属性を特徴量から除外し、自動決定を禁止 |

## 本番前の必須作業

- TLS、Secure Cookie、HSTSを有効化
- Redisを利用した分散レート制限をAPIゲートウェイへ追加
- シークレットマネージャーを利用
- MinIO/S3の暗号化、期限付きURL、マルウェアスキャンを有効化
- PostgreSQL Row Level Securityを多層防御として検討
- 監査ログを変更不能な外部保管先へ転送
- 依存関係、コンテナ、モデル成果物の署名・脆弱性スキャンをCIへ追加

