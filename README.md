# web-deep-reverse

> 对单个网站做深度逆向：前端资源拆解 → JS 加密/去混淆 → 接口签名还原 → 签名重放 → 流媒体抓取 → CDN 厂商定位 → 通俗版 HTML 报告。

一个面向 AI Agent 的**技能（Skill）**，用 Markdown 组织方法论与命令级配方。适用于 Claude Code / DeepSeek Harness 等支持 skill 约定的 Agent 运行时。

---

## 它能做什么

| 能力 | 说明 |
|---|---|
| 前端资源拆解 | 定位主包、异步 chunk、sourcemap，还原打包结构 |
| 加密/去混淆 | CryptoJS/AES/RSA、自定义签名、**jsvmp 字节码虚拟机** |
| 签名还原 | 从请求头反查签名函数，还原拼接顺序与盐 |
| 签名重放 | 用还原的算法在命令行构造请求，验证 200/400 双向证据 |
| 流媒体 | m3u8 主清单 → 子清单 → TS 分片逐级验证；定位直播地址来源 |
| CDN 厂商定位 | 四证交叉（CNAME/NS、响应头、ASN、内部自述）+ **多视角 GSLB 解析** |
| 报告产出 | 单文件 HTML，含概念科普、证据链、踩坑实录 |

## 不适合做什么

- 纯 UI 测试、截图、功能验证 → 用 `web-gui-tester`
- 目标为 Android App → 用 `apk-deep-reverse`
- 攻击、绕过付费墙、批量爬取 → **不做**

---

## 目录结构

```
web-deep-reverse/
├── SKILL.md                      # 主流程 + 坑位速查 + 时间盒
├── references/
│   ├── js-crypto-recipes.md      # 8 种加密配方（含 jsvmp、ECDH+AES+MD5）
│   ├── api-replay.md             # 重放纪律、403 排查顺序、流媒体三层验证
│   ├── cdn-vendor-id.md          # 九步取证线、指纹库、GSLB 多视角
│   └── html-report.md            # 报告规范（含"外行能看懂"第一原则）
├── assets/
│   ├── concept-glossary.md       # 可复用概念科普（DNS/CDN/GSLB/ECS/CLB）
│   ├── report.css                # 报告样式
│   └── cdn-report-template.html  # CDN 定位报告模板
└── scripts/
    ├── scan_web_assets.py        # 资源/密钥/接口扫描
    └── cdn_sign.py               # CDN 防盗链签名复算
```

---

## 安装

把整个目录放到 Agent 的 skills 目录下：

```bash
# Claude Code 常见位置
git clone git@github.com:<your-account>/web-deep-reverse.git ~/.claude/skills/web-deep-reverse

# 或 DeepSeek Harness / 兼容 ~/.agents/skills 的运行时
git clone git@github.com:<your-account>/web-deep-reverse.git ~/.agents/skills/web-deep-reverse
```

运行时会在任务匹配 `description` 中的触发词时自动加载。

---

## 使用示例

```
/web-deep-reverse https://www.example.com/match/123?tab=live
```

触发后按流程走：

```
① 输入/工作目录 → ② 资源清单 → ③ 技术栈识别
→ ④ JS 源码定位 → ⑤ 加密/签名破解
→ ⑥ 接口重放（需授权）→ ⑦ 流媒体抓取（需授权）
→ ⑧ HTML 报告
```

只想查 CDN 厂商时走轻量旁路（九步取证线），跳过 ④⑤⑥。

---

## 方法论要点

### 1. 签名重放是核心价值
现代 Web 把鉴权做成 JS 端签名，把流媒体做成带时效签名的 m3u8。
签名一旦可离线复现，整站 API 就是透明的。

### 2. 证据分级，禁止夸大
- 密钥分级：硬编码 / 接口下发 / 会话级 / 不可得
- 未验证的重放不写"已验证"
- 否定性证据也要写（403/空响应/门槛未探明）

### 3. 四证交叉，缺一不下结论
CNAME/NS 定"谁在调度"，Header 定"哪套软件"，ASN 定"跑在谁的网络上"，内部自述定"哪条产品线"。

### 4. 多视角解析（最容易翻车的地方）
同一个域名，从国内和海外解析会得到**不同节点**。单次解析只代表你所在的位置。
结论必须写"**在该解析视角下**返回…"。

```bash
dig example.com                                   # 本机视角
dig @119.29.29.29 example.com +subnet=1.2.4.0/24  # 模拟北京电信
dig @223.5.5.5 example.com +subnet=124.160.0.0/24 # 模拟浙江联通
```

### 5. 报告要让外行看懂
术语第一次出现必须给类比；每章开头一句"这章回答什么"；必须有三分钟版和踩坑实录。

---

## 坑位速查（节选）

| 现象 | 真实原因 |
|---|---|
| 按 `{id}.{hash}` 下载 chunk 全 403 | 真实命名是 `{name}.{hash}.async.js`，超长还会截断加 `~hash` |
| `grep "/api/"` 搜不到接口 | 路径用点号写法，运行时才 `replace(/\./g,"/")` |
| 接口 200 但返回 Base64 | 响应体被会话密钥加密了 |
| 抓到 `x-sign` 却找不到算法 | 签名被编译进 jsvmp 字节码 |
| VM 在 Node 里 require 报错 | 依赖 webpack 的 global / Buffer，需伪造 require |
| 断言 CDN 在海外被质疑 | GSLB 分线路，你只看了自己视角 |
| 清单 403 就写"地区封锁" | 多半是鉴权 token 过期 |

完整 10 条见 [`SKILL.md`](SKILL.md) §坑位速查。

---

## 伦理与免责

本项目**仅用于技术研究与学习**：

- 仅分析公开页面，不绕过登录或付费墙
- 不批量请求、不扫描、不下载完整流
- 提取的签名/密钥仅用于验证分析
- 使用者需自行确保对目标拥有合法授权

因使用本项目产生的任何法律责任，由使用者自行承担。

---

## License

未指定许可证时，默认保留所有权利。如需开源请自行添加 LICENSE 文件。
