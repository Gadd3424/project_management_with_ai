# Evolutionary Project AI

説明可能なAI提案と、オフラインの進化的LoRAマージを備えたマルチテナント型プロジェクト管理MVPです。

AI提案は業務データを直接変更しません。根拠、確信度、参照元、リスクを表示し、ユーザーが採用した後も差分確認を経て適用します。モデル候補も人間の承認なしにはデプロイできません。

## 実装済みのMVP

- JWT＋HttpOnly Cookie認証、CSRF検証
- 組織単位のアクセス制御とOWNER/ADMIN/MEMBER/VIEWERロール
- Permissionベースのユーザー管理、招待、停止、論理削除、復元、所有権移譲
- 招待トークンのハッシュ保存、Outboxメール配信、管理操作の詳細監査ログ
- `auth_version`による権限変更・停止・削除後の即時セッション失効
- プロジェクト、タスク、コメント、カンバン
- プロジェクトの作成、編集、論理削除と楽観的ロック
- プロジェクト名からのAI初期値提案と、タスク状況に基づくAI変更案
- 目的・成功条件からの進化的マージモデルによる初期タスク提案
- タスクの作成、編集、論理削除と4列カンバンのドラッグ＆ドロップ
- `version`による楽観的ロック
- 期限遅延リスクと次アクションの説明可能な提案
- 提案の採用、却下、差分確認、適用、フィードバック
- 監査ログと相関ID
- `Idempotency-Key`による作成APIの再送保護
- AI提案生成のスライディングウィンドウ・レート制限
- モデル実験、キャンセル、候補登録、人間承認、シャドーデプロイ
- 再現可能な遺伝的アルゴリズム
- Safetensors限定のLoRA互換性検証と重み付きマージ
- PostgreSQL、Redis、MinIO、MLflowを含むDocker Compose
- API統合、組織分離、楽観ロック、ML再現性テスト

現在の期限予測と次アクション生成は、外部APIキー不要のデモ用ルールモデルです。学習済み構造化モデルおよびLLMを差し替える境界として、`services/inference`を分離しています。

## 必要環境

- Docker DesktopおよびDocker Compose v2
- ローカルで直接テストする場合はPython 3.12、Node.js 22

## Docker Composeで起動

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec api python -m scripts.seed_demo_data
```

Windows PowerShellでは次を使用できます。

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose exec api python -m scripts.seed_demo_data
```

起動後：

- Web: http://localhost:3000
- APIドキュメント: http://localhost:8000/api/v1/docs
- MLflow: http://localhost:5000
- MinIO Console: http://localhost:9001
- ユーザー管理: http://localhost:3000/admin/users

デモ認証情報：

```text
email: demo@example.com
password: DemoPass123!
```

## プロジェクト管理とAI提案

プロジェクト画面の「新規プロジェクト」から、概要、目的、成功条件、開始日、完了日を登録できます。
名前を入力して「AIで入力案を生成」を押すと、入力候補が表示されます。AI提案は自動保存されず、確認してフォームへ反映した後に保存します。

既存プロジェクトでは「編集」から「現在の状況からAI変更案を生成」を実行できます。タスクの完了率、期限超過、優先度、担当者設定などをサーバー側で集計し、変更前後の差分と根拠を表示します。

新規プロジェクトでは、目的と成功条件を入力して「AIでタスクを提案」を押すと、初期タスク候補が表示されます。候補を選択・編集し、手動で追加したタスクと一緒にプロジェクトを作成できます。初期タスクはすべて「未着手」で登録されます。

プロジェクト画面の「タスクを追加」から、タスク名、概要、補足事項、優先度、期限を登録できます。タスクは「未着手」「進行中」「保留」「終了」の4列に表示され、カードをドラッグ＆ドロップしてステータスと並び順を変更できます。カードの「編集」から内容の変更と論理削除ができます。

`AI_PROVIDER=mock`では外部モデルなしで決定論的な提案を返します。進化的マージモデルを利用する場合は、モデル実験で生成したSafetensors成果物を承認し、シャドーデプロイ後に昇格してください。`AI_ALLOW_MOCK_FALLBACK=false`にすると、推論障害時のmock切り替えを禁止できます。

ローカルで進化的マージを試すための小さなSafetensorsアダプターは、次のコマンドで生成できます。

```bash
docker compose exec worker python -m scripts.generate_demo_adapters
```

実験作成時の`adapter_paths`には、以下を指定します。

```text
artifacts/demo-adapters/planning.safetensors
artifacts/demo-adapters/delivery.safetensors
artifacts/demo-adapters/risk.safetensors
```

停止する場合：

```bash
docker compose down
```

DBや成果物も削除する操作は`docker compose down -v`ですが、永続データを削除するため注意してください。

## ローカル開発

バックエンド：

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -e ".[dev]"
$env:DATABASE_URL="sqlite+aiosqlite:///./project_ai.db"
alembic upgrade head
python -m scripts.seed_demo_data
uvicorn apps.api.app.main:app --reload
```

Web：

```bash
cd apps/web
npm install --global pnpm@10.17.1
pnpm install
pnpm run dev
```

推論サービス：

```bash
uvicorn services.inference.main:app --port 8001 --reload
```

ワーカーはRedis起動後に実行します。`--beat`によりOutboxも定期処理します。

```bash
celery -A apps.worker.celery_app worker --beat --loglevel=INFO
```

## テスト

```bash
ruff check .
pytest -q
cd apps/web
pnpm run build
```

テストDBは`test-project-ai.db`を使用し、DockerなしでAPI統合テストを実行します。

## 主要ディレクトリ

```text
apps/api/                      FastAPI業務API
apps/web/                      Next.js Web UI
apps/worker/                   Celeryワーカー
services/inference/            オンライン推論境界
services/evolutionary_merge/   GAとLoRAマージ
packages/ml_common/            ML共通コード用の拡張点
migrations/                    Alembicマイグレーション
scripts/                       デモデータ生成
tests/                         単体、統合、セキュリティ、MLテスト
docs/                          アーキテクチャ、ML、セキュリティ文書
```

## セキュリティ上の重要事項

- `.env.example`の`JWT_SECRET`は本番前に必ずランダム値へ変更してください。
- 本番では`COOKIE_SECURE=true`にし、TLS終端を必須にしてください。
- モデル成果物はSafetensorsとJSONのみを標準許可し、pickleをロードしません。
- RAG文書の本文をシステム命令として扱わないでください。
- AI提案の採用と実変更は分離されています。
- モデルのデプロイはOwner/Adminによる明示的承認後、最初はシャドー状態になります。
- 開発環境の招待URLはAPIレスポンスの`development_token`とワーカーの`DEV MAILBOX`ログで確認できます。本番環境ではトークンをレスポンスやログへ出力しません。
- 本番のメールプロバイダーは明示的に接続してください。未設定の本番環境ではOutboxイベントを処理済みにしません。
- 組織には常に1名以上の有効なOWNERが必要で、最後のOWNERと自分自身の停止・削除はAPIが拒否します。

詳細は[アーキテクチャ](docs/architecture/overview.md)、[ML設計](docs/ml/evolutionary-merge.md)、[セキュリティ](docs/security/threat-model.md)を参照してください。

## 現在の制限

- 担当者推薦UIと学習済みLightGBMモデルは次の増分対象です。
- pgvectorの拡張有効化と埋め込み列は、埋め込みモデル導入時の次期マイグレーションで追加します。
- 現在の管理APIレート制限は単一APIプロセス向けです。水平分散時はRedisバックエンドへ交換します。
- 添付ファイル用MinIOは起動しますが、アップロードAPIはMVP後の機能です。
- デモ実験はCPUで再現性を検証する代理適応度を使用します。実LoRA評価時は同じOptimizerへオフライン評価関数を注入します。
