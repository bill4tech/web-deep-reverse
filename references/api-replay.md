# 接口重放与流媒体抓取

签名还原后的落地动作：**构造请求 → 验证 → 保存证据**。全部需要用户明确授权。

---

## 1. 接口重放

### 1.1 构造请求模板

```bash
curl -s "<base_url><path>?<params>&sign=<computed>" \
  -H "Referer: <site_origin>" \
  -H "Origin: <site_origin>" \
  -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ..." \
  -H "Cookie: <从浏览器复制的登录态，如需>" \
  -H "X-Requested-With: XMLHttpRequest" \
  | python3 -m json.tool
```

Header 纪律：

- `Referer`/`Origin` 常是防盗链校验点，必须带
- `User-Agent` 用真实浏览器 UA，不要用 curl 默认
- 登录态接口才带 Cookie/Token，游客接口不带
- **签名头要与浏览器完全一致**（大小写、字段名、空格），差一个字就 401

### 1.2 验证顺序（三步法）

1. **先重放一条浏览器里已成功的请求**（参数原样复制）→ 应返回相同数据。失败说明缺 header/cookie
2. **再改一个参数**（如翻页 page=2）→ 成功说明签名算法正确
3. **再构造全新请求** → 这才是真正的"重放能力"

### 1.3 加一个"必败用例"（强烈建议）

故意少传一个必填参数，或传一个非法值：

- 返回 `400/422` → **证明参数确实进了签名/密文**，不是被服务端忽略
- 依然 `200` 且返回数据 → 说明你对参数的理解有误

这条记录写进报告，比十句"已验证"都有说服力。

### 1.4 保存证据

```bash
curl -s "<url>" -o api/<endpoint_name>.json -w "%{http_code} %{size_download}\n"
```

报告引用文件名 + 关键字段摘录，不贴全量响应（可能含敏感数据）。

### 1.5 响应体是密文怎么办

现象：`200 OK`，body 是一大段 Base64，`json.loads` 直接失败。

1. 先别下"接口不可用"的结论
2. 回拦截器里找 `.then()` 中的解密调用（常见 `js_decrypt` / `decrypt(`）
3. 用会话密钥做对称解密（多为 AES-ECB + PKCS7）
4. 解密成功但字段空 → 这才是"真的没数据"
5. 解密失败 → 可能是另一把密钥/IV，或需要先完成握手

### 1.6 空响应体 ≠ 接口坏

`200` + 空 body 常见于**设备/会话门槛**（风控、必需设备指纹、登录态）。
处理：与浏览器同一请求对比（浏览器有密文、你没有 → 门槛在别处），
在报告里标「门槛未探明」，**不要外推成"接口不可用"或"已被封"**。

---

## 2. 流媒体抓取（m3u8 / HLS）

### 2.1 三层结构

```
主清单 (master m3u8)     ← 拉流接口下发，带 auth_info 签名
  └─ 子清单 (media m3u8)  ← 可能跳转到 CDN 域名
       └─ TS 分片          ← 真正的视频数据
```

逐级验证：

```bash
# L1 主清单
curl -s "<master_m3u8>" | head -20
# → #EXT-X-STREAM-INF 行给出子清单 URL

# L2 子清单
curl -s "<media_m3u8>" | head -20
# → #EXTINF 行给出 TS 分片相对路径

# L3 分片（相对路径要拼到子清单 URL 的目录下）
curl -s "<ts_url>" -o segment.ts && file segment.ts
# → 应输出 "MPEG transport stream data"
```

### 2.2 常见拦截点

| 现象 | 原因 | 处理 |
|---|---|---|
| 主清单 403 | **鉴权参数过期**（最常见） | 解码时间戳核对；重新调拉流接口拿新地址 |
| 子清单 403 | Referer 校验 | 加 `-H "Referer: <播放页>"` |
| 分片 404 | 会话绑定（user_session_id） | 用同一会话的完整分片 URL |
| 全部正常但播不了 | DRM / 加密分片 | 看 m3u8 里有无 `#EXT-X-KEY` |

**403 排查顺序（务必按此顺序）**：
① 时间戳是否过期 → ② Referer/Origin 是否缺失 → ③ 参数是否被截断 → ④ 才是地区封锁。

腾讯云 CSS 的 `txTime` 是 **hex 秒**，一行命令核对：

```bash
python3 -c "import time;print(int('6AF393E7',16), int(time.time()))"
```

### 2.3 直播地址从哪来

- 详情接口的 **`addresses[]`** 数组，按 `addr_type` 过滤（1=动画直播 2=视频直播 3=回放）
- 或顶级字段 `live_url {m3u8, flv, rtmp}`
- 前端通常会优先取 `addr_type===LIVEURL && addr_url` 的第一条

### 2.4 批量下载（验证用，勿滥用）

```bash
# 只下载前几个分片验证可用性，不要拉全片
for i in 0 1 2; do
  curl -s "<base>/segment_${i}.ts" -o seg_${i}.ts
done
ls -la seg_*.ts   # 每个 1-3MB 即正常
```

判定 CDN/供应商时**不要下载 TS**，主清单→子清单各一次即可。

---

## 3. 接口清单梳理

重放成功后，把目标站的核心接口整理成表：

| 接口 | 方法 | 参数 | 签名方式 | 返回关键数据 |
|---|---|---|---|---|
| /api/list | GET | page,timestamp | md5(params+salt) | 直播间列表 |
| /api/pull/info | GET | roomId | CDN auth_key | 流地址(多清晰度) |
| /api/user/login | POST | 账号密码(RSA) | 无 | token |

这张表是报告的核心资产 —— 它意味着**整站 API 对你透明**。

**注意路径写法**：很多站点前端用点号（`live.detail`），运行时才 `replace(/\./g,"/")`。
写清单时统一转成真实路径，并在备注里注明原始写法。

---

## 4. 安全评估要点

- 签名算法可离线复现 = 防护失效（防的是脚本小子，防不了逆向）
- 时效签名（1h）只增加重放成本，不阻止
- 真正有效的防护：服务端频控、设备指纹、行为验证码、WAF
- **鉴权代理由业务接口下发**（如 CDN 地址）→ 防盗链形同虚设
- 报告里按「防护措施 → 绕过难度 → 影响」三列评估

---

## 5. 重放纪律

- 只打用户明确要的接口，不批量扫
- 单次验证性请求，失败先排查本地问题（header/参数/时钟）
- 所有请求与响应落盘到 `api/`，报告引用文件名
- 涉及登录/付费内容 → 先问，未授权不做
