# JS 加密与去混淆配方

Web 前端加密的破解核心：**找到签名/加密函数 → 理解算法 → 用真实请求样例反验**。

---

## 1. 定位签名函数

在拉下来的 JS 里 grep（从便宜到贵）：

```bash
# 签名相关关键词
grep -n "sign\|signature\|auth_key\|token\|secret" js/*.js | head -20
# 哈希/加密库特征
grep -n "md5\|MD5\|sha1\|sha256\|hmac\|HMAC" js/*.js | head -10
grep -n "CryptoJS\|crypto-js\|aesjs\|jsencrypt\|JSEncrypt" js/*.js | head -10
# 加密调用模式
grep -n "encrypt(\|decrypt(\|\.toString()" js/*.js | head -20
```

webpack 打包后的代码里，函数名被压缩成单字母，但**字符串常量不会被混淆掉**：

- 搜 `"md5"`、`"sha256"` 等字符串字面量定位哈希库
- 搜 URL 路径片段定位接口定义处，再顺藤摸瓜找参数构造逻辑
- **请求头字段名是最好的锚点**：`grep -n 'x-sign\|x-key\|x-token\|X-Sign'` 往往直接命中拦截器

---

## 2. 常见签名模式

### 配方 A：时间戳 + 参数排序 + MD5（最常见）

```
sign = md5( sortedParams.join("&") + timestamp + salt )
```

识别：请求参数里有 `sign` / `timestamp` / `nonce` 三件套。
破解：读拼接顺序（有的先 sort，有的按固定 key 顺序），salt 是关键 —— 在 JS 里搜固定长度的随机字符串常量。

### 配方 B：CDN 防盗链 auth_key（阿里云系）

```
ts   = now/1000 + 3600                       # 1 小时有效
hash = MD5( path + "-" + ts + "-0-0-" + token )
URL  = path + "&auth_key=" + ts + "-0-0-" + hash
```

⚠️ **path 不含 query**（只到 `?` 前）—— 把 query 算进去会 `403 invalid md5hash`。
token 来源：接口下发（如域名池配置 JSON）或 JS 硬编码。

变体 authB：`md5( token + yyyyMMddHHmm + path )` 拼进 URL 路径。

### 配方 C：AES 加密请求体

识别：请求 body 是 Base64 大块，或 `{"data":"<base64>"}` 包裹。
破解：找 `CryptoJS.AES.encrypt(text, key)` 的 key —— 可能是：

- 字符串常量（直接用）
- `"passphrase"` 形式（CryptoJS 会做 EVP_BytesToKey 派生，需用同库复现）
- 接口下发的动态 key（先抓握手接口）

IV 常硬编码或取 key 前 16 字节。CBC/ECB 看 `CryptoJS.mode` 引用。

### 配方 D：RSA 加密敏感字段

识别：登录密码字段是长 hex/base64。
破解：公钥硬编码在 JS（搜 `-----BEGIN PUBLIC KEY-----` 或长 base64 常量）。RSA 只能加密不能解密 —— 但你可以**用自己的公钥替换**（需 MITM），或确认服务端只验签不加密时直接重放。

### 配方 E：自定义混淆签名

识别：函数名全是 `_0x4f2a` 这类，控制流被打平。
破解：
1. 先试 AST 工具（babel-plugin-transform-control-flow-statements）
2. 或浏览器 DevTools 断点：对签名函数下断，看输入输出
3. 或把整个函数扣出来放 Node 里跑（补齐 window/document mock）

---

## 3. 用真实请求反验（必做）

从浏览器网络面板（或 HAR）拿一条**已成功的请求**：

```
URL:    /api/list?page=1&timestamp=1692600760&sign=abc123...
Body:   {"uid":0,"page":1}
Header: X-Sign: abc123...
```

把已知参数代入你还原的算法：

- 输出 sign 一致 → 复现成功，可构造新请求
- 不一致 → 回去检查拼接顺序/salt/大小写/hex vs base64

**再加一个必败用例**：故意少传必填参数，若服务端返回 400/422（而不是也 200），说明参数确实进了签名/密文，而不是被忽略。

---

## 4. 提取有价值的解密目标

优先级：

1. API 域名 / CDN 域名（`grep -oE 'https?://[a-zA-Z0-9._-]+'`）
2. 硬编码 key / salt / secret（8+ 字符的随机串常量）
3. 接口路径与参数结构
4. 流媒体地址模板（`{room_id}.m3u8?auth_info=...`）
5. 第三方 SDK 的 appKey（地图/统计/推送等）

---

## 5. sourcemap 还原

```bash
curl -sL "<js_url>.map" -o js/main.js.map
python3 -c "
import json
m = json.load(open('js/main.js.map'))
for src, content in zip(m['sources'], m.get('sourcesContent') or []):
    print('='*20, src)
    print((content or '')[:2000])
"
```

有 sourcemap ≈ 直接读源码，还原度接近 100%。

---

## 6. 配方 F：jsvmp / 字节码虚拟机（重点）

### 识别特征

```js
// 典型结构
var e = n("XlkA")();          // 加载 VM 模块
var t = new e;                // 实例化
t.getGlobal()                 // 拿全局对象
t.createFunction("MD5", fn)   // 注册 native 给 VM 调用
t.setProperty(global, "MD5", h)
t.run("JTI1N0IlMjUyMm5hbWUlMjUyMiUzQSUyNTIy...")   // 超长 Base64 = 字节码
t.getProperty(global, "js_encrypt")
t.call(fn, global, t.createString(a), ...)
t.asString(result)
```

关键词：`createFunction` / `createString` / `asString` / `getGlobal` / `getProperty` / `run("JTI…")`。
**注意：这不是 WebAssembly**，不要去找 `.wasm`。

### 破解思路：不要硬读 opcode，先读"常量池"

字节码通常是一个 JSON 描述，字段含义：

| 字段 | 含义 |
|---|---|
| `vt` | 全局变量名表 |
| `ft[]` | 函数表（`ps` 参数名、`vt` 局部变量名、`opcode` 指令流） |
| `st[]` | **字符串常量池** ← 金矿 |
| `nt/et/dft` | 数字/其他常量 |

**没有加密的 `st` 会按顺序暴露整个算法**，包括硬编码盐、URL 模板、返回 JSON 的拼接格式。

解码链条一般是这样（可能多层）：

```python
raw  = base64.b64decode(b64).decode()   # → "%257B%2522name%2522..."
d1   = urllib.parse.unquote(raw)        # → "%7B%22name%22..."
d2   = urllib.parse.unquote(d1)         # → '{"name":"","vt":[...],"opcode":[...]}'
obj  = json.loads(d2)
print(obj["ft"][0]["st"])               # 直接读算法
```

### 运行路线：宿主化（推荐）

比反编译 opcode 快 10 倍。步骤：

1. 从主包/ chunk 里切出 VM 模块（`XlkA:function(e,t,n){…}`）
2. Node 里伪造 webpack `require`：
   ```js
   const fakeRequire = id =>
     id === 'BBhR' ? globalThis :          // 通常是 global/window shim
     id === 'JX3P' ? { Buffer } :          // Buffer polyfill
     (() => { throw new Error('unexpected ' + id) })();
   ```
3. `new Function('module','exports','require', 'return (' + src + ')(module,exports,require)')`
4. 按站点的方式注册 native（MD5/AES/ECDH…），用 Node `crypto` 等价实现
5. `vm.run(payload)` 后 `vm.call(js_encrypt, global, ...)`，与浏览器结果比对

**验证技巧**：在 native 里 `console.log` 入参 —— VM 调 `MD5(x)` 时打印 `x`，往往一眼看出签名拼接公式。

### 常见坑

- `self` 未定义：在 Node 顶部 `globalThis.self = globalThis`
- native 返回值必须是 VM 句柄（`vm.createString(...)`），不是裸字符串
- `getClient()` 这类只生成一次并缓存（第二次返回空串），不要在测试里重复实例化

---

## 7. 配方 G：ECDH + AES + MD5（请求/响应双加密）

### 识别特征

- 请求头有 `x-key`（Base64，解码后 **65 字节且首字节 0x04** = P-256 未压缩公钥）
- 请求体/query 有 Base64 密文（长度是 16 的倍数）
- 响应体也是 Base64 密文（不是 gzip！）
- 有 `/key` 之类的握手接口下发服务端公钥

### 典型流程

```
握手：GET /key            → {x-key: 服务端P-256公钥, x-kid: 版本}
生成：客户端临时密钥对    → priv/pub，pub 作为请求头 x-key
派生：share = ECDH(client_priv, server_pub)   # 32 字节
加密：params = AES-256-ECB/PKCS7( body, key=share )   # 输出 Base64
签名：sign = MD5( timestamp + "PC"|"H5" + 硬编码盐 )   # 注意可能不含 body
解密：resp   = AES-256-ECB-decrypt( 响应Base64, key=share )
```

### 常见设计缺陷（写进报告）

- 签名**与 body 无关** → 盐泄露即可离线批量生成
- MD5 而非 HMAC，**无 nonce** → 无重放保护
- 盐硬编码在 JS/字节码常量池
- 响应体同密钥加密 → 拿到一次会话密钥就能全解

### Python 等价实现要点

```python
priv = ec.generate_private_key(ec.SECP256R1())
share = priv.exchange(ec.ECDH(), server_pub)         # 32 字节
padder = padding.PKCS7(128).padder()
cipher = Cipher(algorithms.AES(share), modes.ECB())
```

⚠️ 密钥是 **派生出的 32 字节原始值**，不是 Base64 字符串本身；直接拿字符串当 key 会解出乱码。

---

## 8. 响应体是密文时（别误判"接口坏了"）

现象：`200 OK`，body 是一大段 Base64，`json.loads` 失败。
原因：服务端用会话密钥加密响应。
处理：

1. 先确认是否有 `js_decrypt` / `decrypt(` 调用（拦截器里通常在 `.then()` 里解密）
2. 用同一把 `share` 做 AES 解密
3. 解密成功但字段为空 → 才是真正的"接口没数据"
4. 解密也失败 → 检查是不是另一个密钥/另一套 IV
