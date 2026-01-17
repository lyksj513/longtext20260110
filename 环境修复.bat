@echo off
chcp 65001 >nul
title 猫仔多文伴侣 - 环境修复工具
color 0A

echo ========================================
echo   猫仔多文伴侣 V2.0 - 环境修复工具
echo   作者: lovelycateman/www.52pojie.cn
echo ========================================
echo.

:: 管理员权限检测
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [✓] 已获取管理员权限
) else (
    echo [!] 警告：未以管理员身份运行，某些操作可能失败
    echo [提示] 请右键点击此文件，选择"以管理员身份运行"
    echo.
    pause
)

echo.
echo ========================================
echo   第一步：检测 Python 环境
echo ========================================
echo.

:: 检测Python是否已安装
python --version >nul 2>&1
if %errorLevel% == 0 (
    echo [✓] Python 已安装
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
    echo [信息] 当前版本: %PYTHON_VERSION%
    set PYTHON_INSTALLED=1
) else (
    echo [×] Python 未安装
    set PYTHON_INSTALLED=0
)

echo.

:: 如果Python未安装，下载并安装
if %PYTHON_INSTALLED%==0 (
    echo [开始] 准备安装 Python 3.12...
    echo [信息] 将从国内镜像下载 Python 安装包
    echo.
    
    :: 创建临时目录
    if not exist "%TEMP%\maozai_setup" mkdir "%TEMP%\maozai_setup"
    
    :: 使用华为云镜像下载Python 3.12
    set PYTHON_INSTALLER=%TEMP%\maozai_setup\python-installer.exe
    set PYTHON_URL=https://mirrors.huaweicloud.com/python/3.12.0/python-3.12.0-amd64.exe
    
    echo [下载] 正在从华为云镜像下载 Python 3.12...
    echo [URL] %PYTHON_URL%
    echo.
    
    :: 使用PowerShell下载
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'SilentlyContinue'; try { Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%' -UseBasicParsing -TimeoutSec 300; exit 0 } catch { Write-Host '[错误] 下载失败:' $_.Exception.Message; exit 1 }}"
    
    if %errorLevel% == 0 (
        echo [✓] Python 安装包下载成功
        echo.
        echo [安装] 正在安装 Python（请稍候，可能需要几分钟）...
        echo [提示] 安装程序会自动配置环境变量
        echo.
        
        :: 静默安装Python，添加到PATH，安装pip
        "%PYTHON_INSTALLER%" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1 Include_tcltk=1
        
        :: 等待安装完成
        timeout /t 60 /nobreak >nul
        
        :: 刷新环境变量
        echo [刷新] 正在刷新环境变量...
        call :RefreshEnv
        
        :: 再次检测Python
        python --version >nul 2>&1
        if %errorLevel% == 0 (
            echo [✓] Python 安装成功！
            for /f "tokens=2" %%i in ('python --version 2^>^&1') do echo [信息] 安装版本: %%i
        ) else (
            echo [×] Python 安装可能失败，请手动安装
            echo [提示] 请访问 https://www.python.org/downloads/ 下载安装
            echo [提示] 或使用华为云镜像：https://mirrors.huaweicloud.com/python/
            pause
            exit /b 1
        )
        
        :: 清理安装包
        del "%PYTHON_INSTALLER%" >nul 2>&1
    ) else (
        echo [×] Python 下载失败
        echo.
        echo [解决方案] 请尝试以下方法：
        echo   1. 检查网络连接
        echo   2. 手动下载 Python：
        echo      https://mirrors.huaweicloud.com/python/3.12.0/python-3.12.0-amd64.exe
        echo   3. 下载后双击安装，注意勾选 "Add Python to PATH"
        echo.
        pause
        exit /b 1
    )
)

echo.
echo ========================================
echo   第二步：检测 pip 包管理器
echo ========================================
echo.

:: 检测pip
python -m pip --version >nul 2>&1
if %errorLevel% == 0 (
    echo [✓] pip 已安装
    for /f "tokens=2" %%i in ('python -m pip --version') do echo [信息] 版本: %%i
) else (
    echo [×] pip 未安装，正在安装...
    python -m ensurepip --default-pip
    if %errorLevel% == 0 (
        echo [✓] pip 安装成功
    ) else (
        echo [×] pip 安装失败
        pause
        exit /b 1
    )
)

echo.
echo ========================================
echo   第三步：配置 pip 国内镜像源
echo ========================================
echo.

echo [配置] 正在设置清华大学 pypi 镜像源...
python -m pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
python -m pip config set install.trusted-host pypi.tuna.tsinghua.edu.cn

if %errorLevel% == 0 (
    echo [✓] pip 镜像源配置成功
    echo [信息] 使用清华大学镜像，加速包下载
) else (
    echo [!] 镜像源配置失败，将使用默认源
)

echo.
echo ========================================
echo   第四步：升级 pip 到最新版本
echo ========================================
echo.

echo [升级] 正在升级 pip...
python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple

if %errorLevel% == 0 (
    echo [✓] pip 升级成功
) else (
    echo [!] pip 升级失败，但不影响使用
)

echo.
echo ========================================
echo   第五步：安装必需的 Python 包
echo ========================================
echo.

:: 检测并安装 requests
echo [检测] 正在检查 requests 库...
python -c "import requests" >nul 2>&1
if %errorLevel% == 0 (
    echo [✓] requests 库已安装
    for /f "tokens=2" %%i in ('python -m pip show requests ^| findstr "Version"') do echo [信息] 版本: %%i
) else (
    echo [×] requests 库未安装
    echo [安装] 正在安装 requests...
    python -m pip install requests -i https://pypi.tuna.tsinghua.edu.cn/simple
    if %errorLevel% == 0 (
        echo [✓] requests 安装成功
    ) else (
        echo [×] requests 安装失败
        pause
        exit /b 1
    )
)

echo.

:: 检测tkinter（Python自带，但有时会缺失）
echo [检测] 正在检查 tkinter 库（GUI支持）...
python -c "import tkinter" >nul 2>&1
if %errorLevel% == 0 (
    echo [✓] tkinter 库可用
) else (
    echo [!] tkinter 库不可用
    echo [提示] tkinter 是 Python 自带库，如缺失请重新安装 Python
    echo [提示] 安装时确保勾选 "tcl/tk and IDLE" 选项
)

echo.
echo ========================================
echo   第六步：环境验证
echo ========================================
echo.

:: 创建测试脚本
echo import sys > "%TEMP%\test_env.py"
echo import requests >> "%TEMP%\test_env.py"
echo import tkinter >> "%TEMP%\test_env.py"
echo print("Python version:", sys.version) >> "%TEMP%\test_env.py"
echo print("requests version:", requests.__version__) >> "%TEMP%\test_env.py"
echo print("tkinter:", "OK") >> "%TEMP%\test_env.py"

echo [测试] 运行环境验证...
python "%TEMP%\test_env.py"

if %errorLevel% == 0 (
    echo.
    echo [✓] 环境验证通过！
) else (
    echo.
    echo [×] 环境验证失败
)

:: 清理测试文件
del "%TEMP%\test_env.py" >nul 2>&1

echo.
echo ========================================
echo   安装完成
echo ========================================
echo.
echo [✓] 所有必需组件已安装完成！
echo.
echo [下一步] 双击运行"猫仔多文伴侣.py"启动程序
echo.
echo [说明] 如果遇到问题，请：
echo   1. 重启命令提示符/PowerShell
echo   2. 重新运行此修复脚本
echo   3. 或联系作者 lovelycateman/www.52pojie.cn
echo.
echo ========================================

pause
exit /b 0

:: 刷新环境变量函数
:RefreshEnv
echo [提示] 正在刷新环境变量...
:: 刷新系统PATH
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SysPath=%%b"
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "UsrPath=%%b"
set "PATH=%SysPath%;%UsrPath%"
goto :eof
