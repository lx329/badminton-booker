# 北师羽毛球预约助手 - 开发文档

> 最后更新: 2026-06-18  
> 当前版本: v1.2 + v1.1 预热优化 + 时序修复  
> 仓库: [github.com/lx329/badminton-booker](https://github.com/lx329/badminton-booker)

---

## 1. 项目概述

**桌面自动化应用**，用于北京师范大学羽毛球场馆的自动预约。通过 Playwright 浏览器自动化实现定时抢场，支持 CAS 统一身份认证、验证码处理。

### 技术栈

| 层级 | 技术 |
|------|------|
| GUI | PySide6 (Qt) |
| 浏览器自动化 | Playwright (sync API, Chromium) |
| 验证码识别 | OpenCV (可选) + Vue 组件状态读取 |
| 定时调度 | Python threading |
| 打包 | PyInstaller |

### 目录结构

```
02 badminton/
├── main.py                    # 入口
├── gui/
│   └── app.py                 # PySide6 桌面 GUI (~670行)
├── booker/
│   ├── browser.py             # Playwright 浏览器管理
│   ├── authenticator.py       # CAS 登录认证
│   ├── scheduler.py           # 倒计时调度器
│   ├── booker.py              # 流程执行引擎 (FlowBooker)
│   ├── captcha_solver.py      # 旋转滑块验证码求解器 v1
│   └── captcha_solver_v2.py   # 验证码求解器 v2 (与v1相同)
├── flow_template.json         # 预约流程步骤定义 (10步)
├── config.json                # 用户配置 (校区/场地/时间/账号)
├── auth_state.json            # 登录状态缓存 (cookies + localStorage)
├── requirements.txt           # 依赖
├── setup.bat                  # 环境初始化
├── run.bat                    # 启动脚本
├── build.bat                  # EXE 打包脚本
├── screenshots/               # 截图输出
├── browser_data/              # 浏览器用户数据
└── temp/                      # 临时文件
```

---

## 2. 架构与数据流

```
main.py
  └── gui/app.py (BookingApp)
        ├── booker/scheduler.py    # 后台线程计时
        ├── booker/browser.py      # 浏览器生命周期
        │     └── auth_state.json  # 登录态持久化
        ├── booker/authenticator.py # CAS 登录
        └── booker/booker.py       # 流程执行
              ├── flow_template.json # 步骤定义
              └── booker/captcha_solver.py # 验证码
```

### 执行流程

```
用户点击"开始预约"
  │
  ├─ 启动时间未到 → 预热阶段
  │   1. 打开浏览器 → 导航到预约页
  │   2. 检测是否需要登录 → 自动/手动登录
  │   3. 保存 auth_state.json → 关闭浏览器
  │   4. Scheduler 后台倒计时
  │
  └─ 启动时间到达 → 执行阶段
      1. 新开浏览器 → 加载 auth_state.json (免登录)
      2. 快速导航到场地页 → 确认已登录
      3. FlowBooker 按 flow_template.json 逐步执行
      4. 浏览器保持 30 秒供用户确认 → 关闭
```

---

## 3. 核心模块详解

### 3.1 `gui/app.py` - 桌面界面

**BookingApp** (QMainWindow)，约670行。

| 功能区域 | 说明 |
|----------|------|
| 启动时间 | 何时开始抢票 (日期+时间) |
| 场地预约时间 | 目标日期 + 开始时间 + 时长 (1h/2h) |
| 场地选择 | 校区联动场地 (海淀14个/昌平8个) |
| 抢票策略 | 提前 N 秒预热 (1-30秒可调) |
| 认证信息 | CAS 学工号+密码 |
| 倒计时 | 实时显示距启动时间 |
| 运行日志 | 实时输出执行状态 |

关键方法:
- `_start_preheat()` — 预热: 打开浏览器, 登录, 保存 auth, 关浏览器
- `_execute_booking()` — 执行预约: 新浏览器+缓存auth, 跑流程
- `_collect_config()` — 收集 UI 配置

信号/槽:
- `status_signal` → 状态栏更新
- `log_signal` → 日志更新
- `countdown_signal` → 倒计时更新
- `booking_done_signal` → 预约完成后恢复 UI

### 3.2 `booker/browser.py` - 浏览器管理

- 启动带反检测参数的 Chromium (`--disable-blink-features=AutomationControlled`)
- 加载 `auth_state.json` 实现免登录
- `navigate_and_wait_for_button()` — 导航到预约页, 等待"立即预约"按钮出现, 返回 False 表示被重定向到登录页
- `save_auth_state()` — 保存 cookies + localStorage

### 3.3 `booker/authenticator.py` - CAS 登录

- 检测是否在登录页 (统一身份认证 / CAS)
- 自动填充学工号+密码并提交
- 支持手动登录模式 (留空密码时)

### 3.4 `booker/scheduler.py` - 定时调度

- 独立线程倒计时
- 精度策略: 最后60秒每0.5秒检查, 最后5分钟每2秒, 其余每5秒
- `advance_seconds` 支持提前触发

### 3.5 `booker/booker.py` - 流程执行引擎

读取 `flow_template.json`，替换模板变量，逐步执行。

**模板变量** (使用 `{{var}}` 语法):

| 变量 | 来源 | 示例 |
|------|------|------|
| `target_date` | 场地日期 | 2026-06-18 |
| `target_time` | 开始时间 | 20:00 |
| `time_slot` | 时间段 | 20:00-22:00 |
| `venue_name` | 场地名称 | 羽3 |
| `campus` | 校区 | 昌平校区 |
| `grid_row` | 表格行号 | start_hour - 7 |
| `grid_col` | 表格列号 | 场地索引 + 1 |
| `field_id` | 场地ID | 同 grid_col |

**支持的动作**:
- `click` — 点击元素 (支持 fallback_selectors)
- `fill` — 输入文本
- `js_click` — 执行 JS (用于表格格子点击)
- `switch_frame` — 切换到 iframe
- `switch_to_page` — 切回主页面
- `wait_manual_captcha` — 等待用户手动完成验证码
- `slide_captcha` — 自动求解旋转验证码

**新页面处理**: 监听 `context.on("page")` 事件, 每个步骤执行后自动检测并切换到新打开的标签页。

### 3.6 `booker/captcha_solver.py` - 验证码求解

旋转滑块验证码 (dd-core-captcha-slider) 自动求解:

1. **Vue 状态读取**: 遍历 `__vue__` 获取 `config.A[0]` (正确角度)
2. **OpenCV 识别 (fallback)**: Hough 直线检测 + 直方图分析
3. **模拟拖动**: TouchEvent → PointerEvent → Playwright mouse 多级回退

### 3.7 `flow_template.json` - 预约流程

当前流程 (v1.2, 10步):

| 步骤 | 动作 | 说明 |
|------|------|------|
| 1 | click | 点击"场馆预约"按钮 |
| 2 | switch_frame | 切换到预约表格 iframe |
| 3 | click | 选择昌平校园 (optional) |
| 4 | click | 羽毛球馆 Tab |
| 5 | click | 打开日期选择器 |
| 5b | click | 选最后一个可用日期 (optional) |
| 6 | js_click | XPath 精确定位行列格子并点击 |
| 7 | click | 点击预定按钮 |
| 8 | click | 点击提交按钮 |
| 9 | wait_manual_captcha | 等用户手动完成验证码 |

---

## 4. 版本历史

### 已修复的关键 Bug

| Bug | 修复提交 | 说明 |
|-----|----------|------|
| 新页面切换时序 | `66daa1f` | 步骤执行**前**检查新页面改为执行**后**检查，解决 iframe 找不到的问题 |
| 场地列定位丢失 | (已回退) | v1.1 的 `js_click` 遍历所有格子忽略了 `grid_col`，v1.2 XPath 定位保留 |

### 当前分支状态

```
master: 66daa1f
├── 82e207c v1.2 基础 (XPath场地定位 + 预热)
├── 6f9ab70 v1.1 预热增强 (登录跟踪、关浏览器、iframe等待、验证码检测)
└── 66daa1f 新页面时序修复
```

其他分支:
- `feature/fast-preheat` — v1.1 独立分支 (选择器文本匹配, 但场地定位有bug)
- `feature/preheat-only` — 与 master 一致

---

## 5. 已知问题与注意事项

1. **凭证明文存储**: `config.json` 中账号密码明文保存，不共享此文件
2. **VPN 依赖**: 目标站点通过 `onevpn.bnu.edu.cn` 访问，需在校园网或 VPN 环境下运行
3. **验证码自动求解不稳定**: Vue 组件内部状态读取依赖特定版本，页面更新可能导致失败
4. **硬编码选择器**: `flow_template.json` 中的 XPath 和 ID 选择器(如 `#tab-6018dde3-...`) 可能因页面更新失效
5. **Playwright 必须在主线程**: sync API 不是线程安全的，所有浏览器操作通过 `QTimer.singleShot` 调用
6. **一次性执行**: 每次预约需重新启动程序，不支持连续多轮自动预约

---

## 6. 开发指南

### 环境搭建

```bash
setup.bat     # 创建 venv + 安装依赖 + 安装 Chromium
```

### 运行

```bash
run.bat       # 激活 venv + python main.py
```

### 修改预约流程

编辑 `flow_template.json`，支持的变量见 3.5 节。修改后无需重启即可生效。

### 添加新场地

编辑 `gui/app.py` 中的 `CAMPUS_VENUES` 字典 和 `booker/booker.py` 中的 `CAMPUS_VENUES_MAP` 字典，保持两处一致。

### 打包 EXE

```bash
build.bat     # PyInstaller --onefile --windowed
```

### 调试

- 截图: 将 `flow_template.json` 中步骤的 `screenshot` 设为 `true`
- 日志: 查看 GUI 日志区或终端输出
- 单独测试验证码: 运行 `test_full_captcha.py`
