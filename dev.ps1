param(
    [Parameter(Position = 0)]
    [string]$Command = "help",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArguments
)

$ErrorActionPreference = "Stop"
if (Test-Path Variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}
$script:ComposeExecutable = ""
$script:ComposePrefix = @()
$script:CurrentStep = "初期化"
$originalLocation = Get-Location
Set-Location -LiteralPath $PSScriptRoot
$CommandArguments = @($CommandArguments | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })

function Show-Usage {
    @"
使い方:
  .\dev.ps1 apply [--clean] [--seed]
  .\dev.ps1 status
  .\dev.ps1 logs [service]
  .\dev.ps1 restart
  .\dev.ps1 stop

apply --clean はキャッシュを使わず、コンテナを停止して完全再構築します。
DockerボリュームとDBデータは、どのコマンドでも削除しません。
"@ | Write-Host
}

function Invoke-Compose {
    param([string[]]$Arguments)
    $allArguments = @($script:ComposePrefix) + $Arguments
    & $script:ComposeExecutable @allArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Composeが終了コード $LASTEXITCODE を返しました。"
    }
}

function Test-Compose {
    param([string[]]$Arguments)
    $allArguments = @($script:ComposePrefix) + $Arguments
    & $script:ComposeExecutable @allArguments *> $null
    return $LASTEXITCODE -eq 0
}

function Initialize-DevelopmentEnvironment {
    $script:CurrentStep = "Docker CLIの確認"
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "dockerコマンドが見つかりません。Docker Desktopをインストールしてください。"
    }

    $script:CurrentStep = "Docker Engineの接続確認"
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Engineに接続できません。Docker Desktopを起動してください。名前付きパイプが見つからない場合も起動状態を確認してください。"
    }

    $script:CurrentStep = "Docker Composeの確認"
    & docker compose version *> $null
    if ($LASTEXITCODE -eq 0) {
        $script:ComposeExecutable = "docker"
        $script:ComposePrefix = @("compose")
    }
    elseif (Get-Command docker-compose -ErrorAction SilentlyContinue) {
        & docker-compose version *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Docker Composeが利用できません。"
        }
        $script:ComposeExecutable = "docker-compose"
        $script:ComposePrefix = @()
        Write-Host "[注意] Docker Compose V1を使用します。可能であればCompose V2へ更新してください。"
    }
    else {
        throw "Docker Composeが見つかりません。Docker Compose V2を有効にしてください。"
    }

    $script:CurrentStep = "環境変数ファイルの確認"
    if (-not (Test-Path -LiteralPath ".env")) {
        Copy-Item -LiteralPath ".env.example" -Destination ".env"
        Write-Host "[準備] .env.exampleから.envを作成しました。"
        Write-Host "[注意] JWT_SECRETなどの開発用設定を確認してください。既存の.envは今後も上書きしません。"
    }

    $script:CurrentStep = "Docker Compose設定の検証"
    Invoke-Compose -Arguments @("config", "--quiet")
}

function Wait-ForApi {
    $script:CurrentStep = "APIとマイグレーションの起動確認"
    Write-Host "[確認] APIの起動とマイグレーション完了を待っています..."
    $probe = "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/openapi.json', timeout=2)"
    foreach ($attempt in 1..45) {
        if (Test-Compose -Arguments @("exec", "-T", "api", "python", "-c", $probe)) {
            Invoke-Compose -Arguments @("exec", "-T", "api", "alembic", "current")
            return
        }
        Start-Sleep -Seconds 2
    }
    Invoke-Compose -Arguments @("ps")
    throw "90秒以内にAPIの起動を確認できませんでした。"
}

function Show-EnvironmentResult {
    $script:CurrentStep = "コンテナ状態の確認"
    Invoke-Compose -Arguments @("ps")
    @"

開発環境を利用できます:
  Web:           http://localhost:3000
  API Docs:      http://localhost:8000/api/v1/docs
  MLflow:        http://localhost:5000
  MinIO Console: http://localhost:9001
"@ | Write-Host
}

try {
    switch ($Command) {
        "apply" {
            $unknown = @($CommandArguments | Where-Object { $_ -notin @("--clean", "--seed") })
            if ($unknown.Count -gt 0) {
                throw "applyの不明なオプションです: $($unknown -join ', ')"
            }
            $clean = "--clean" -in $CommandArguments
            $seed = "--seed" -in $CommandArguments
            Initialize-DevelopmentEnvironment
            if ($clean) {
                Write-Host "[実行] コンテナを停止し、アプリケーションをキャッシュなしで完全再構築します。"
                $script:CurrentStep = "既存コンテナの停止"
                Invoke-Compose -Arguments @("down")
                $script:CurrentStep = "アプリケーションイメージの完全再構築"
                Invoke-Compose -Arguments @("build", "--no-cache", "api", "worker", "inference", "web")
                $script:CurrentStep = "コンテナの強制再作成"
                Invoke-Compose -Arguments @("up", "-d", "--force-recreate")
            }
            else {
                Write-Host "[実行] ビルドキャッシュを利用して変更を反映します。"
                $script:CurrentStep = "開発環境への変更反映"
                Invoke-Compose -Arguments @("up", "-d", "--build", "--remove-orphans")
            }
            Wait-ForApi
            if ($seed) {
                $script:CurrentStep = "デモデータの投入"
                Invoke-Compose -Arguments @("exec", "-T", "api", "python", "-m", "scripts.seed_demo_data")
            }
            Show-EnvironmentResult
        }
        "status" {
            if ($CommandArguments.Count -gt 0) { throw "statusに引数は指定できません。" }
            Initialize-DevelopmentEnvironment
            $script:CurrentStep = "コンテナ状態の確認"
            Invoke-Compose -Arguments @("ps")
        }
        "logs" {
            if ($CommandArguments.Count -gt 1) { throw "logsで指定できるサービスは1つだけです。" }
            Initialize-DevelopmentEnvironment
            $script:CurrentStep = "コンテナログの表示"
            $arguments = @("logs", "--tail=200", "-f")
            if ($CommandArguments.Count -eq 1) { $arguments += $CommandArguments[0] }
            Invoke-Compose -Arguments $arguments
        }
        "restart" {
            if ($CommandArguments.Count -gt 0) { throw "restartに引数は指定できません。" }
            Initialize-DevelopmentEnvironment
            $script:CurrentStep = "コンテナの再起動"
            Invoke-Compose -Arguments @("restart")
            Wait-ForApi
            Show-EnvironmentResult
        }
        "stop" {
            if ($CommandArguments.Count -gt 0) { throw "stopに引数は指定できません。" }
            Initialize-DevelopmentEnvironment
            $script:CurrentStep = "コンテナの停止"
            Invoke-Compose -Arguments @("stop")
            Write-Host "[完了] コンテナを停止しました。DockerボリュームとDBデータは保持されています。"
        }
        { $_ -in @("help", "-h", "--help") } { Show-Usage }
        default {
            Show-Usage
            throw "不明なサブコマンドです: $Command"
        }
    }
}
catch {
    [Console]::Error.WriteLine("[エラー] $($script:CurrentStep) に失敗しました。$($_.Exception.Message)")
    Write-Host "Docker Desktopの起動状態と、上記のエラー内容を確認してください。"
    Write-Host "ログ確認: .\dev.ps1 logs または .\dev.ps1 logs api"
    exit 1
}
finally {
    Set-Location -LiteralPath $originalLocation
}
