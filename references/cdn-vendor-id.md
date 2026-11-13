# CDN / 直播供应商定位（轻量旁路流程）

适用：用户只问「这家网站/直播间用的是哪家 CDN/云厂商」，**不需要**还原签名、不需要重放接口。
典型问法/触发词：识别CDN、查CDN厂家、直播用谁家的流、对标CDN、供应商分析。

定位：这是 SKILL.md 主流程的**旁路** —— 跳过 ④ JS 源码定位、⑤ 加密破解、⑥ 接口重放，把 ②③⑦ 组合成一条九步取证线。产出仍是 HTML 报告，格式见本文末尾（模板：`assets/cdn-report-template.html`）。

> 方法来源：2026-09 / 11 多个真实站点实测（kick.com → AWS IVS；dnymrhz.com → 华为云海外；kqt600.com → 华为云国内；example.com → 腾讯云直播，海外/大陆双分支）。

---

## 核心思想：不给结论，给证据链

四类**互相独立**的证据交叉验证，单一证据都可能骗你：

1. **域名指纹** —— DNS CNAME 链，厂商的"门牌号"
2. **响应头指纹** —— HTTP Header，厂商的"口音"
3. **IP/ASN 归属** —— whois 查网络，厂商的"身份证"
4. **内部自述** —— 清单 `EXT-X-SESSION-DATA`、错误响应 JSON、token 载荷，厂商的"工牌"

经典误判反例：只看主站 `server: cloudflare` 就断定直播走 Cloudflare —— kick.com 主站是 Cloudflare，视频流量完全在 AWS。

**第二大误判（本 skill 2026-11 新增）：把"我解析到的边缘节点在哪"当成"这家 CDN 在哪"。** 见下文 §GSLB 分线路。

## 四层模型（结论必须分层写）

```
第1层 业务层（站点自己：房间/用户/礼物）
第2层 生产层（推流接入 → 转码 → 打包 HLS/FLV）     ← AWS IVS 转码栈、华为云 livehwc4 切片、腾讯云 CSS
第3层 分发层（CDN 就近分发）                        ← 通常"厂家"问的就是这层
第4层 承载层（边缘 IP 挂在谁的 ASN 上）             ← 自营 or 借网
```

两种商业形态，别混淆：

- **一体化平台**（AWS IVS / 腾讯云 CSS）：2+3 层打包买，4 层自营。换掉它 = 重构整条生产链。
- **自建+CDN**：业务自己写，只买第 3 层。换 CDN = 改一条 CNAME。

---

## 九步流程（命令级）

### 阶段一 · 侦察

**① 直连抓页面**

```bash
curl -sL -A "Mozilla/5.0 (Macintosh; …) Chrome/126…" -D headers.txt "<url>" -o index.html
```

看：HTTP code、`server`/`cf-ray`/`x-cache`、框架特征（`__NEXT_DATA__`=Next.js、`__NUXT__`=Nuxt、flight=Remix/CF）。

- 坑：本机代理（如 `127.0.0.1:7897`）影响可达性与**出口位置**；`HTTP 000` 先重试再下结论。

### 阶段二 · 定位

**② 定位播放地址**（按成本从低到高，三条路）

| 路线 | 做法 | 说明 |
|---|---|---|
| a. HTML 内联数据（先试） | JSON 解析 `__NEXT_DATA__` / `__NUXT__` / flight 流 | 关键词：`playAddr`、`playback_url`、`pullUrl`、`m3u8`、`flv` |
| b. XHR 接口 | DevTools Network 筛 XHR；或抓 JS chunk grep `playurl\|hls\|pull` | 内联没有时用 |
| c. 播放器配置/媒体过滤 | hls.js/flv.js 的 src；Network 面板过滤 `.m3u8\|.flv\|.ts` | 永远能看见真实拉流域名的兜底手段 |

- 坑 1：**正则截断鉴权参数** —— `\.m3u8` 收口会把 `?auth_key=…`/`?auth_info=…`/`?token=…` 丢掉 → 403。**能用 JSON 解析就不用正则。**
- 坑 2：**URL 粘连** —— 正则字符类含 `:` 时会把内联 JSON 里两个相邻 URL 粘成一坨。
- 坑 3：转义还原 —— Nuxt 载荷有 `\u002F`（= `/`），需 `codecs.decode(s,'unicode_escape')` 或 JSON 解析。
- 坑 4：**响应体加密** —— 接口 200 但 body 是 Base64 时，先解密再判断"没有播放地址"。

**③ 提取流媒体域名**：播放 URL 的 **host** 才是分析对象，主站域名退场。注意流域名与主站常毫无关系（独立域名、个人注册都正常）。

### 阶段三 · 取证（四证）

**④ DNS CNAME 链**

```bash
dig live.example.com          # 看完整链，别用 +short（会混 CNAME 与 A）
dig +short <指纹域名> NS      # 对指纹域名做 NS 归属二次确认（防仿冒，最硬的实锤）
```

**⑤ 响应头指纹**：`curl -sI`，失败用 `GET -D -`；必带 `Referer`/`Origin` + 完整鉴权参数。

- 坑：HEAD 可能被 IVS 404 —— **任何响应（含 403/404）的头部都是证据**。

**⑥ 拉流验证**：主清单 → 子清单，各一次 GET（带完整鉴权）。双 200 = 报告标「含流媒体验证」。**不下载 TS、不批量。**

- 坑：**403 先怀疑 token 过期**，不是地区封锁。云厂商的鉴权参数多是显式时间戳（腾讯云 `txTime` = **hex** 秒），一行命令就能核对：
  ```bash
  python3 -c "import time;print(int('6AF393E7',16), time.time())"
  ```

**⑦ IP/ASN 归属**

```bash
whois -h whois.cymru.com " -v <ip>"    # 一行返回 ASN/前缀/AS 名
```

区分**自营**（AS16509=Amazon CloudFront）与**借网**（移动各省、Zenlayer、Aceville —— 云厂商的海外/合作 POP）。CNAME 定"谁在调度"，ASN 定"跑在谁的网络上"，缺一不可。

**⑧ 内部自述**（彩蛋，产出架构信息）

- HLS 主清单 `EXT-X-SESSION-DATA`：kick 案例直接报出 `NODE=*.cloudfront.hls.live-video.net`、`TRANSCODESTACK=2025-Transcode-ELT-V1`
- token/JWT 载荷：IVS 的 `aws:channel-arn: arn:aws:ivs:us-west-2:<账号ID>:channel/xxx`
- 错误响应 JSON：`{"error_code":"invalid_playback_auth_token"}` 是 AWS 原生格式，也是指纹

### 阶段四 · 定论

**⑨ 交叉比对 → 分层结论 → HTML 报告**

---

## GSLB 分线路：最常见的翻车点（必做）

**问题**：CNAME 解析结果与"你从哪问"强相关。同一条 `xxx.txlivecdn.com`，国内权威和海外权威会返回**完全不同的调度分支和 IP 段**。

**真实案例（example.com，腾讯云直播）**：

| 解析视角 | 第三跳 CNAME | 边缘 IP | ASN |
|---|---|---|---|
| 海外（新加坡出口） | `all.hylivecdn.sched.ovscdns.net` | 43.174.x | AS139341 Aceville（腾讯云海外） |
| 北京·电信 | `tdns.l3.sched.dcloudlive.com` | 27.221.52.158 | AS4837 |
| 广东·电信 | 同上 | 14.29.101.116 | AS4134 |
| 浙江·联通 | 同上 | 61.241.178.207 | AS4837 |
| 移动 | 同上 | 120.220.155.196 | AS9808 |

同一域名、同一秒、六种答案。**没有哪个是"真身"，它们都是。**

### 强制动作：多视角解析

```bash
# 1) 本机视角（默认）
dig live.example.com

# 2) 模拟中国大陆各地（EDNS Client Subnet）
dig @119.29.29.29 live.example.com +subnet=1.2.4.0/24          # 北京电信
dig @119.29.29.29 live.example.com +subnet=116.25.0.0/24       # 广东电信
dig @223.5.5.5    live.example.com +subnet=124.160.0.0/24      # 浙江联通
dig @223.5.5.5    live.example.com +subnet=117.136.0.0/24      # 移动

# 3) 不带 ECS（模拟"不知道你在哪"的解析器，看默认回哪）
dig @8.8.8.8 live.example.com +short

# 4) 查 ASN
whois -h whois.cymru.com " -v <ip>"
```

### 结论措辞纪律

| ❌ 错误写法 | ✅ 正确写法 |
|---|---|
| "直播 CDN 在腾讯云新加坡" | "**在海外解析视角下**返回新加坡边缘（AS139341）；**大陆视角**返回电信/联通/移动节点" |
| "该站用了海外 CDN，国内访问需要梯子" | "CDN 为多地域部署，大陆用户被调度到国内节点，无需跨境" |
| "IP 在新加坡所以是新加坡公司" | "IP 落在 AS139341（Aceville，腾讯云海外主体），**调度方**仍是腾讯云" |

**判断口诀**：

- **厂商**看 CNAME / NS / 响应头
- **位置**看 ASN / IP 段
- **视角**看你的解析出口
- 三者分开写，任何一项都不单独下结论

### 为什么"海外 CDN"在国内往往能直连

1. 多地域部署 → 国内解析给国内节点，流量走国内骨干
2. 主站/接口可能在**香港**（如 `*.clb.hk-tencentclb.com`），香港线路国内可直连
3. 是否被墙是**域名/IP 层面**的事，与 CDN 归属无因果关系（此类站点常被间歇性封锁）

---

## 指纹库（按命中优先级；指纹只定方向，结论仍需 ASN/NS 交叉确认）

### CNAME / 域名指纹

| 指纹 | 厂商 | 备注 |
|---|---|---|
| `*.live-video.net` / `*.playback.live-video.net` | **AWS IVS**（直播平台） | 播放域自带区域（us-west-2 等），token 是 IVS JWT |
| `*.cloudfront.net` | **Amazon CloudFront** | IVS 的分发层 |
| `*.c.cdnhwc*.com`（含 `gslb`、`global.gslb`） | **华为云 CDN** | NS 反查 `huaweicloud-dns.*` 实锤；带 `global`=海外版 |
| `*.livehwc4.com` | **华为云直播**切片边缘 | `v4-<hash>.livehwc4.com`，URL 带 `edge_slice=true&sub_m3u8=true` |
| `*.txlivecdn.com` | **腾讯云直播 CSS（统一接入名）** | 再往下分国内/海外调度 |
| `*.sched.dcloudlive.com` | **腾讯云直播·国内调度** | 返回大陆运营商节点 |
| `*.sched.ovscdns.net` | **腾讯云直播·海外调度** | 返回海外节点（AS139341 等） |
| `*.cdn.dnsv1.com` / `*.dnsv1.com.cn` | **腾讯云 CDN** | NS 反查 dnspod |
| `*.kunlun*.com`（gr/sl/so） | **阿里云 CDN** | 响应头 `x-swift-*`、`eagleid` |
| `*.akamaized.net` / `*.akamaihd.net` | **Akamai** | `server: AkamaiGHost` |
| `*.cdn20.com` / `*.wscdns.com` | **网宿 Wangsu** | `x-ws-request-id` |
| `*.b-cdn.net` | Bunny | `x-served-by: cache-*` 是 Fastly |
| `*.rsc.cdn77.org` | **CDN77 / Datacamp** | AS60068 |
| 客户自有中转域（如 `ffcdn.xyz`） | 只是**转介层** | 别当成厂商；继续追下一跳 |

### 响应头指纹

| 响应头 | 厂商 |
|---|---|
| `cf-ray` + `server: cloudflare` | Cloudflare |
| `x-amz-cf-id` / `x-amz-cf-pop` / `x-amzn-trace-id` | AWS（`-pop` 值=边缘机房，如 `SIN2-P6`） |
| `server: MC_VCLOUD_LIVE` + `x-tlive-spanid` | **腾讯云直播**边缘 |
| `x-nws-log-uuid` | 腾讯云 CDN 系常见 |
| `x-swift-cachetime` / `eagleid` | 阿里云 |
| `x-ws-request-id` | 网宿 |
| `Server: Server`（泛化）+ `Access-Control-Allow-Origin: *` | 华为云边缘常见（弱特征） |

### 常见承载 ASN（借网识别）

| ASN | 主体 | 角色 |
|---|---|---|
| AS16509 | AMAZON-02 | CloudFront 自营 |
| AS139341 | **ACEVILLE PTE.LTD.**（腾讯云海外主体，SG） | 腾讯云海外 POP |
| AS132203 | TENCENT-NET-AP-CN | 腾讯云（含香港 CLB） |
| AS13335 / AS54113 | Cloudflare / Fastly | 自营 |
| AS21859 | Zenlayer | 常见于华为云海外 CDN 合作 POP |
| AS63199 | CDS Global Cloud | 同上 |
| AS4837 / AS4134 / AS9808 | 联通169 / 电信163 / 移动 | 国内 CDN 边缘常驻运营商 IDC |
| AS60068 | CDN77 - Datacamp | rsc.cdn77.org |

**AS 归属 ≠ 机房产权**：国内大量 CDN 节点是"租运营商 IDC 机柜 + 用运营商 IP"，所以 IP 在 AS4837 不代表联通自建 CDN。

---

## 鉴权强度分级（顺带产出，对标加分项）

| 等级 | 特征 | 实测案例 |
|---|---|---|
| 强 | 服务端签发 JWT/签名 token，分钟级时效，绑定资源 | AWS IVS JWT（ES384），~7min 过期 |
| 中 | 加密串 token（如 `Base64密文.hex段`），不可伪造但混淆弱 | auth_info |
| 中 | CDN 厂商 TypeD（`txSecret=MD5(key+stream+txTime)` + `txTime` hex） | 腾讯云 CSS，**但地址由业务接口明文下发 → 重放接口即得新签名** |
| 弱 | TypeA `ts-rand-uid-md5` 且过期校验缺失 | auth_key |

评估维度：伪造难度 / 时效 / 绑定粒度 / CORS 配置 / **是否可从业务接口重新获取**。

---

## 输出格式（报告必含）

命名 `<YYYYMMDD>-<HHmm>-cdn-vendor-id.html`，写工作目录，`open` 并告知路径。模板：`assets/cdn-report-template.html`。

结构（顺序固定，结论放最前）：

1. **结论速览**（分层表格：层级 / 域名 / 供应商 / 关键证据）
2. **核心思想提示**：主站 CDN ≠ 视频 CDN
3. **四证交叉表**：CNAME 链 / 响应头 / ASN / 内部自述
4. **多视角解析表**（强制）：海外视角 + 大陆 ≥3 地，标注 CNAME 分支与 ASN
5. **鉴权观察**：格式、验证样例（403/200）、强度分级
6. **未做项与坑**：TS 未下载、代理出口说明、token 过期经过
7. Footer：对象/时间/工具/产物路径 + 「仅用于技术研究与学习目的」

证据纪律：

- 每条结论后跟**实测数据**（真实 CNAME 串、真实响应头、真实 ASN 行）
- 引用保存的产物文件名：`assets/index.html`、`api/m3u8_headers.txt`、`api/master.m3u8`
- GSLB 结论必须注明解析视角；未验证的推断标「未验证」

## 伦理

- 单次验证性请求；不拉流下载 TS、不批量、不扫
- 仅公开页面；不绕登录/付费
- 报告脚注：「仅用于技术研究与学习目的」
