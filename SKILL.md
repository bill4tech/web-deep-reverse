---
name: web-deep-reverse
description: "对单个网站/Web 应用/网页做深度逆向：前端资源拆解、JS 加密与去混淆、接口签名还原、签名重放抓取接口与流媒体（m3u8/TS）、CDN/云厂商供应商定位、密钥与配置提取、输出通俗易懂的 HTML 报告。仅在用户明确要密钥/接口签名/流媒体地址/CDN厂家/深度逆向时使用；纯 UI 测试、页面截图、功能验证改走 web-gui-tester。触发词：逆向网站、拆解网页、挖接口、抓流地址、还原签名、网页加密破解、m3u8、前端逆向、识别CDN、CDN厂家、直播用哪家、供应商分析、jsvmp、字节码混淆、接口响应加密、ECDH 签名。"
---

# Web 深度逆向（前端 + 接口）

对**单个**网站做：资源拆解 → 前端 JS 分析 → 加密/签名破解 →（授权后）接口重放 → HTML 报告。

核心价值在**签名重放**：现代 Web 把接口鉴权做成 JS 端签名（sign/token/auth_key），把流媒体做成带时效签名的 m3u8。还原签名算法后，宿主机 curl 即可重放任意接口 —— 等于把浏览器网络面板的每条请求变成可编程的。

**用途**：技术对标、安全评估、CTF。不用于攻击他人系统。

`{skill_dir}` = 本 skill 根目录。脚本一律 `{skill_dir}/scripts/...`。

---

## 分流与门闩（先读再动手）

### 走错 skill 就停

满足任一条 → 改走 `web-gui-tester`，或只做 ①–③ 出浅层结论：

- 目标是"测功能/找 bug/截图验证"，不是逆向
- 用户没提密钥、接口、签名、流地址、加密
- 目标是 App 而非网站 → `apk-deep-reverse`

### 轻量旁路：只定位 CDN / 供应商

用户只问「CDN/云厂商是谁」、不需要密钥/签名还原 → 走 `references/cdn-vendor-id.md` 的**九步取证线**：

```
直连抓页面 → 定位播放地址 → 提取流域名 → CNAME 链+NS 反查 → 响应头指纹
→ 拉流单验（主清单→子清单，不下载TS）→ IP/ASN 归属 → 内部自述 → 分层结论报告
```

- 核心纪律：**四证交叉**（域名指纹/响应头/ASN/内部自述）才下结论，主站 CDN ≠ 视频 CDN
- **多视角强制**：单次解析只能代表你所在的网络位置，必须补 `dig +subnet=<大陆网段>` 对照，结论写「在该解析视角下」，见 `references/cdn-vendor-id.md` §GSLB 分线路
- 报告用模板 `assets/cdn-report-template.html`（分层结论 + 四证交叉表），命名 `<YYYYMMDD>-<HHmm>-cdn-vendor-id.html`

### 高成本/敏感动作先问

未获本轮明确授权，禁止：

- 对生产接口做签名重放、批量请求、拉流下载
- 绕过登录态/付费墙访问内容
- 抓取需登录/付费的数据

用户只说「看看这个网站」≠ 授权重放。

### 工具缺失就降级

检查：浏览器自动化（Playwright/`tabbit`/browser-use MCP）、`curl`、`node`/`python3`、`ffmpeg`（可选）。

- **无浏览器自动化是致命短板**：先找本机 Playwright（`~/Library/Caches/ms-playwright`、`node_modules/playwright`）或系统 Chrome，能起 headless 就起 —— 抓一次真实网络请求，胜过盲猜一小时（见 §坑 1）
- 无浏览器 → 只做静态资源分析（curl 拉 HTML/JS），并在报告标注降级

### 证据纪律

- 每个结论带证据：URL、文件名、代码片段、请求样例
- 密钥分级：硬编码 / 接口下发 / 猜测
- 未验证的重放不要写成"已验证"
- **否定性结论也要留证**：403/400/空响应体先排除"过期/参数/门槛"，再归因地区或封锁

---

## 流程

```
① 输入/工作目录 → ② 资源清单 → ③ 技术栈识别
→ ④ JS 源码定位 → ⑤ 加密/签名破解
→ ⑥ 接口重放（已授权）→ ⑦ 流媒体抓取（已授权）
→ ⑧ HTML 报告（必须通俗化，见 references/html-report.md）
```

① 机械；②③④⑤ 静态；⑥⑦ 是灵魂但需授权；⑧ 必交付。
只想定位 CDN 厂商 → 跳过 ④⑤⑥，按 `references/cdn-vendor-id.md` 走九步轻量线。

### 时间盒（防止在错误方向上一路狂奔）

| 阶段 | 建议上限 | 超时动作 |
|---|---|---|
| 找 JS 入口 | 15 min | 直接起 headless 浏览器抓网络，记录全部 URL |
| 解不开 chunk 命名 | 10 min | 同上：以浏览器实际请求为准，不要猜规则 |
| 签名算法定位 | 30 min | 换策略：从请求头字段名反查赋值处 |
| VM/混淆还原 | 60 min | 优先"宿主化运行"，不要硬读字节码 |
| 某接口空响应 | 5 min | 记为「门槛未探明」，继续主线 |

---

## ① 输入与工作目录

输入：URL 或已下载的 HTML/JS/HAR 文件。

```bash
mkdir -p work/<site>/{assets,js,api,report}
```

产物约定（可恢复：已有产物跳过）：

```
work/<site>/
  assets/    # HTML、CSS、图片
  js/        # 抓下来的 JS（含 chunks/ 子目录）
  api/       # 抓包记录、重放结果、清单与分片
  report/    # HTML 报告
```

---

## ② 资源清单

**首选：headless 浏览器**（一步拿到所有真实 URL + 签名头 + 响应体）：

```js
// node capture.js —— 依赖本机 playwright
page.on('request', r => log({url:r.url(), method:r.method(), headers:r.headers(), postData:r.postData()}));
page.on('response', async r => log({url:r.url(), status:r.status(), body: await r.text().catch(()=>null)}));
```

**兜底：curl**

```bash
curl -sL -A "Mozilla/5.0 ..." -D assets/index_headers.txt "<url>" -o assets/index.html
grep -oE 'src="[^"]*\.js[^"]*"' assets/index.html
grep -oE 'href="[^"]*\.css[^"]*"' assets/index.html
grep -c "<script>" assets/index.html      # 内联 script 常藏首屏数据/配置
```

重点看：`<script src>`、内联 `window.__INITIAL_STATE__`/`__NUXT__`、meta/link 配置、XHR/fetch。

---

## ③ 技术栈识别

| 信号 | 结论 |
|---|---|
| `__NUXT__` / `_nuxt/` | Nuxt.js |
| `__NEXT_DATA__` / `/_next/` | Next.js |
| `//! umi version` / `umi.xxxx.js` | **Umi**（React），常见 chunk 表 + 动态 import |
| `window.__INITIAL_STATE__` + app.js | Vue SPA |
| `ng-version` | Angular |
| `.map` 文件存在 | **有 sourcemap**（还原度大幅提升） |
| `createFunction` / `getProperty` / `run("<超长Base64>")` | **jsvmp 字节码保护**，见 ⑤ 配方 F |
| `x-sign` / `x-key` / `sign=` / `nonce` | 前端签名，见 ⑤ |
| m3u8/flv/rtmp 引用 | 流媒体 |

---

## ④ JS 源码定位

```bash
curl -sL "<js_url>" -o js/main.js
```

定位顺序（从便宜到贵）：

1. **sourcemap**：`app.js.map` → 直接还原源码结构
2. **grep 关键词**：
   ```bash
   grep -l "sign\|token\|auth\|encrypt\|secret" js/*.js
   grep -oE '"[a-zA-Z_]*[Kk]ey":"[^"]{8,}"' js/*.js     # 硬编码 key
   grep -oE 'https?://[a-zA-Z0-9._-]+' js/*.js | sort -u  # 全部域名
   ```
3. **接口路径（注意写法陷阱）**：
   ```bash
   grep -oE '"/[a-z-]+/[a-z-/]+"' js/*.js | sort -u
   # 若命中很少，试点号写法（运行时 replace(/\./g,'/') 转成路径）
   grep -oE '"[a-z][a-z0-9_]*(\.[a-z0-9_]+){1,5}"' js/*.js | sort -u
   ```
4. **签名函数**：搜 `md5`/`sha`/`hmac`/`AES`/`encrypt`/`sign(` 的调用点
5. **请求拦截器**：搜 `x-sign`、`Authorization`、`headers:`、`interceptors` —— 签名入口几乎总在这里

### chunk 抓取（webpack/umi 通用坑）

- 先找运行时映射表：`{id:"hash"}[e]+".async.js"`，附近通常还有 **`{id:"chunkName"}` 名字表**
- 真实文件名多为 **`{name}.{hash}.async.js`**，不是 `{id}.{hash}.async.js`
- webpack 会把超长 chunk 名**截断成 100 字符 + `~{hash}`**，例如
  `vendors~layouts__index~p__account-safe~…~881c5896.02bb38aa.async.js`
- 猜不中就直接**以浏览器实际请求的 URL 为准**（headless 抓一遍，脚本批量下载）

---

## ⑤ 加密/签名破解

配方见 `references/js-crypto-recipes.md`。决策顺序：

1. 明文（无加密，直接读）
2. 常见编码（Base64/hex → 直接解）
3. 标准库加密（CryptoJS/AES → 找 key）
4. 自定义签名（md5/sha 拼接 → 读拼接顺序）
5. jsvmp 字节码（配方 F）→ **优先宿主化运行**，不要硬读 opcode
6. 公钥体系（ECDH/RSA，配方 G）→ 用等价库重实现，再用真实请求验证

验证方式：**用浏览器网络面板里一条真实请求做样例**，把参数代入你的算法，输出一致 = 复现成功。
若响应体是密文，**先还原解密再判断"接口不可用"**。

---

## ⑥ 接口重放（已授权才进入）

配方见 `references/api-replay.md`。

```bash
# 用还原的签名算法构造请求
curl -s "<url>?sign=<computed>" -H "Referer: <site>" -H "User-Agent: ..." | jq .
```

纪律：

- 先用一条真实请求反验算法，再构造新请求
- 只打用户明确要的接口，不批量扫
- **准备一个"必败用例"**（少传必填参数 → 应 400/422），证明参数真的进了密文
- 响应保存到 `api/`，报告引用文件名

---

## ⑦ 流媒体抓取（已授权才进入）

配方见 `references/api-replay.md` §流媒体。

```bash
curl -s "<m3u8_url>" | head -20
curl -s "<ts_url>" -o segment.ts && file segment.ts   # 应输出 MPEG transport stream
```

要点：

- 直播地址常在详情接口的 **`addresses[]`** 里，按 `addr_type` 过滤（1=动画 2=视频直播 3=回放），或顶级 `live_url{m3u8,flv,rtmp}`
- 清单拿不到先查 **token 是否过期**（如腾讯云 `txTime` 是 hex 时间戳），别急着归因地区封锁
- 判定 CDN/供应商而非下载流 → 单次主清单→子清单即可，不下载 TS

---

## ⑧ HTML 报告

读 `references/html-report.md`，命名 `<YYYYMMDD>-<HHmm>-web-deep-reverse.html`，写当前工作目录，`open` 并告知路径。

**报告必须"外行能看懂"**，因此强制包含：

1. **三分钟版**（一句话结论 + 一张流程图）
2. **概念科普章**（DNS/递归/权威/CNAME/GSLB/ECS/边缘节点/CLB/跨境专线），直接内联 `assets/concept-glossary.md`
3. **踩坑实录章**（现象 → 原因 → 解法，来自任务真实经历，不要编）
4. 技术章：技术栈、接口清单、签名算法（含验证样例）、密钥表（分级）、流媒体、重放记录、安全评估、复盘

CDN/供应商定位类任务改用模板 `assets/cdn-report-template.html`，命名 `<YYYYMMDD>-<HHmm>-cdn-vendor-id.html`。

---

## 坑位速查（血泪版，按出现频率排序）

| # | 现象 | 真实原因 | 解法 |
|---|---|---|---|
| 1 | 按 `{id}.{hash}.async.js` 下载 chunk 全 403 | 真实命名是 `{name}.{hash}.async.js`，名字被截断加 `~hash` | headless 抓一次真实请求，照抄 URL |
| 2 | `grep "/api/"` 几乎没结果 | 路径用点号写法（`live.detail`），运行时才 `replace(/\./g,"/")` | 改 grep 点号模式 |
| 3 | 接口 200 但返回一堆 Base64 | **响应体被加密**（与请求同一把会话密钥） | 先还原解密，再判断成败 |
| 4 | 抓到 `x-sign` 但找不到算法 | 签名被塞进 jsvmp/VM，`n("XlkA")` 之类 | 找 VM 模块 → 读字符串常量池 → 宿主化运行 |
| 5 | VM 模块在 Node 里 require 失败 | 依赖 webpack 的 `n("BBhR")`(global)、`n("JX3P").Buffer` | 伪造 `require` 返回 `globalThis` / `{Buffer}` |
| 6 | 单点解析认定 CDN 在海外，被质疑"国内怎么打得开" | **GSLB 分线路**：同一域名对国内/海外返回不同节点 | `dig +subnet` 多视角，结论加"该视角下" |
| 7 | 清单 403 就写"地区限制" | token 过期（如 `txTime` 已过） | 解码时间戳核对，重新取地址 |
| 8 | 接口 200 但 body 为空 | 设备/会话门槛，不是签名错 | 标注"门槛未探明"，别外推 |
| 9 | 报告写"腾讯云新加坡 CDN"被用户打脸 | 把**边缘节点位置**当成**厂商归属** | 厂商看 CNAME/NS/Header，位置看 ASN，两者分开写 |
| 10 | 主包 6MB 里 grep 不到页面代码 | 代码在 async chunk 里，主包只有运行时 | 先下 chunk 再 grep |

---

## 概念内联（报告与自检都要用）

`assets/concept-glossary.md` 里有可直接粘进报告的通俗解释（DNS 三层角色、CDN 边缘节点、GSLB 与 ECS、CLB 与 GSLB 的区别、跨境专线为何无关）。
**写 CDN 相关结论前先自问**：我说的"厂商"是哪一层？我解到的"位置"是谁的视角？

---

## 伦理

- 仅安全研究、对标、CTF
- 提取的签名/密钥只用于验证分析
- 不绕付费墙、不打生产接口、不批量抓取
- 报告脚注：「仅用于技术研究与学习目的」
