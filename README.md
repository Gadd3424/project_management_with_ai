# Evolutionary Project AI

説明可能なAI提案と、オフラインの進化的LoRAマージを備えたマルチテナント型プロジェクト管理MVPです。

AI提案は業務データを直接変更しません。根拠、確信度、参照元、リスクを表示し、ユーザーが採用した後も差分確認を経て適用します。モデル候補も人間の承認なしにはデプロイできません。

## 実装済みのMVP

- JWT＋HttpOnly Cookie認証、CSRF検証
- 組織単位のアクセス制御とOwner/Admin/Manager/Member/Viewerロール
- プロジェクト、タスク、コメント、カンバン
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
docker compose exec api python scripts/seed_demo_data.py
```

Windows PowerShellでは次を使用できます。

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose exec api python scripts/seed_demo_data.py
```

起動後：

- Web: http://localhost:3000
- APIドキュメント: http://localhost:8000/api/v1/docs
- MLflow: http://localhost:5000
- MinIO Console: http://localhost:9001

デモ認証情報：

```text
email: demo@example.com
password: DemoPass123!
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
python scripts/seed_demo_data.py
uvicorn apps.api.app.main:app --reload
```

Web：

```bash
cd apps/web
corepack enable
pnpm install
pnpm run dev
```

推論サービス：

```bash
uvicorn services.inference.main:app --port 8001 --reload
```

ワーカーはRedis起動後に実行します。

```bash
celery -A apps.worker.celery_app worker --loglevel=INFO
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

詳細は[アーキテクチャ](docs/architecture/overview.md)、[ML設計](docs/ml/evolutionary-merge.md)、[セキュリティ](docs/security/threat-model.md)を参照してください。

## 現在の制限

- 担当者推薦UIと学習済みLightGBMモデルは次の増分対象です。
- pgvectorの拡張有効化と埋め込み列は、埋め込みモデル導入時の次期マイグレーションで追加します。
- 現在のレート制限は単一APIプロセス向けです。水平分散時はRedisバックエンドへ交換します。
- 添付ファイル用MinIOは起動しますが、アップロードAPIはMVP後の機能です。
- デモ実験はCPUで再現性を検証する代理適応度を使用します。実LoRA評価時は同じOptimizerへオフライン評価関数を注入します。
