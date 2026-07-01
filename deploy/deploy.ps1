# AI Studio — Docker 一键部署（Windows，本地或 Windows Server）
# 用法：在项目根目录执行  powershell -ExecutionPolicy Bypass -File deploy\deploy.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Info($msg)  { Write-Host "[deploy] $msg" -ForegroundColor Cyan }
function Warn($msg)  { Write-Host "[deploy] 警告: $msg" -ForegroundColor Yellow }
function Abort($msg) { Write-Host "[deploy] 错误: $msg" -ForegroundColor Red; exit 1 }

function New-RandomSecret {
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return ([BitConverter]::ToString($bytes) -replace "-", "").ToLower()
}

function Need-Replace([string]$val) {
    return [string]::IsNullOrWhiteSpace($val) -or $val -like "*change-me*"
}

function Ensure-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Abort "未安装 Docker Desktop，请先安装: https://www.docker.com/products/docker-desktop/"
    }
    docker compose version 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { Abort "未找到 docker compose，请确认 Docker Desktop 已启动" }
}

function Ensure-RootEnv {
    if (-not (Test-Path ".env")) {
        Info "创建 .env"
        Copy-Item ".env.example" ".env"
    }
    $lines = Get-Content ".env" -ErrorAction SilentlyContinue
    $envMap = @{}
    foreach ($line in $lines) {
        if ($line -match "^([^#=]+)=(.*)$") { $envMap[$Matches[1].Trim()] = $Matches[2].Trim() }
    }
    $append = @()
    if (Need-Replace $envMap["POSTGRES_PASSWORD"]) {
        $append += "POSTGRES_PASSWORD=$(New-RandomSecret)"
        Info "已自动生成 POSTGRES_PASSWORD"
    }
    if (Need-Replace $envMap["REDIS_PASSWORD"]) {
        $append += "REDIS_PASSWORD=$(New-RandomSecret)"
        Info "已自动生成 REDIS_PASSWORD"
    }
    if ($append.Count -gt 0) {
        Add-Content ".env" ($append -join "`n")
        Warn "请妥善保存 .env 中的数据库与 Redis 密码"
    }
}

function Ensure-BackendEnv {
    if (-not (Test-Path "backend\.env")) {
        Info "创建 backend\.env"
        Copy-Item "backend\.env.example" "backend\.env"
    }
    $content = Get-Content "backend\.env" -Raw
    if ($content -match "JWT_SECRET=change-me" -or $content -notmatch "JWT_SECRET=.+" ) {
        $jwt = (New-RandomSecret) + (New-RandomSecret)
        if ($content -match "(?m)^JWT_SECRET=.*$") {
            $content = $content -replace "(?m)^JWT_SECRET=.*$", "JWT_SECRET=$jwt"
        } else {
            $content += "`nJWT_SECRET=$jwt"
        }
        Info "已自动生成 JWT_SECRET"
    }
    if ($content -notmatch "(?m)^APP_ENV=production") {
        if ($content -match "(?m)^APP_ENV=.*$") {
            $content = $content -replace "(?m)^APP_ENV=.*$", "APP_ENV=production"
        } else {
            $content += "`nAPP_ENV=production"
        }
    }
    Set-Content "backend\.env" $content.TrimEnd()

    if ($content -match "COMFYUI_URL=http://127\.0\.0\.1") {
        Warn "COMFYUI_URL 仍为本地地址，请在 backend\.env 改为可访问的 ComfyUI 地址"
    }
    if ($content -notmatch "DASHSCOPE_API_KEY=\S+") {
        Warn "请在 backend\.env 填写 DASHSCOPE_API_KEY（文本生成需要）"
    }
}

Info "AI Studio Docker 一键部署"
Ensure-Docker
Ensure-RootEnv
Ensure-BackendEnv

Info "构建并启动容器..."
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Abort "docker compose 启动失败" }

$port = 80
if (Test-Path ".env") {
    $m = Select-String -Path ".env" -Pattern "^HTTP_PORT=(\d+)" | Select-Object -First 1
    if ($m) { $port = $m.Matches.Groups[1].Value }
}

Start-Sleep -Seconds 5
try {
    Invoke-WebRequest -Uri "http://127.0.0.1:$port/health" -UseBasicParsing -TimeoutSec 10 | Out-Null
    Info "健康检查通过"
} catch {
    Warn "健康检查暂未通过，可稍后访问 http://127.0.0.1:$port/health"
}

Write-Host ""
Info "部署完成"
Write-Host "  访问地址: http://localhost:$port"
Write-Host "  查看状态: docker compose ps"
Write-Host "  查看日志: docker compose logs -f"
Write-Host ""
Warn "ComfyUI 未包含在 Compose 中，需单独运行并在 backend\.env 配置 COMFYUI_URL"
