# CPU Optimizer Pro

Windows 平台 CPU 优先级优化工具，基于 PyQt5 构建。

## 环境要求

- Windows 10/11
- Python 3.8+
- 管理员权限

## 安装

```bash
pip install -r requirements.txt
```

## 运行

```bash
python cpu_optimizer.py
```

> 需要以管理员身份运行

## 功能

- **前台进程监控** - 自动检测当前活动窗口对应的进程
- **优先级调整** - 提高前台进程优先级，降低其他进程
- **CPU 亲和性** - 可选绑定 CPU 核心
- **实时显示** - 显示前台进程名、CPU 占用率
- **进程列表** - Top 6 高 CPU 占用进程
- **系统托盘** - 最小化到托盘，后台运行

## 三种优化模式

| 模式 | 前台进程 | 后台进程 | 绑核 |
|------|---------|---------|------|
| 平衡模式 | HIGH | NORMAL | 无 |
| 激进模式 | HIGH | LOW | 无 |
| 绑核模式 | HIGH + 前半核 | LOW | 有 |

## 打包exe

```bash
pip install pyinstaller
pyinstaller --onefile --icon=6.ico --noconsole cpu_optimizer.py
```

打包完成后，exe 文件在 `dist/` 目录下。

## 注意事项

- 仅支持 Windows
- 需要管理员权限（修改进程优先级）
- 系统关键进程（lsass、csrss 等）不受影响
