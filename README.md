<p align="center">
  <a href="https://nonebot.dev/"><img src="https://nonebot.dev/logo.png" width="200" height="200" alt="nonebot"></a>
</p>

<div align="center">

# nonebot-adapter-claweixin

_✨ weixin clawbot 协议适配 ✨_

[![CodeFactor](https://www.codefactor.io/repository/github/5656565566/nonebot-adapter-claweixin/badge)](https://www.codefactor.io/repository/github/5656565566/nonebot-adapter-claweixin)
[![NoneBot](https://img.shields.io/badge/nonebot-2.5.0+-red)](https://nonebot.dev/)

</div>

## 配置

修改 NoneBot 配置文件 `.env` 或者 `.env.*`

### Driver

参考 [driver](https://nonebot.dev/docs/appendices/config#driver) 配置项，添加 `HTTPClient` 支持

如：

```dotenv
DRIVER=~httpx
```

### 配置机器人

- *可选依赖 nonebot-adapter-claweixin[qrcode] 用于终端中显示二维码*
- *可选依赖 nonebot-adapter-claweixin[login] 用于交互式登录流程*

环境变量介绍：

| 环境变量 | 默认值 | 作用 |
| --- | --- | --- |
| `CLAWEIXIN_TOKEN` | `[]` | 微信 bot token 列表。配置后适配器会为每个 token 创建一个 bot 并开始轮询消息。 |
| `CLAWEIXIN_LOGIN_QRCODE_IN_INFO` | `false` | 启动机器人时执行扫码登录流程，并通过日志输出二维码或二维码链接。 |
| `CLAWEIXIN_API_ROOT` | `https://ilinkai.weixin.qq.com` | 微信 iLink API 根地址。只有官方接口地址变化、测试环境、代理网关等场景才需要修改。 |
| `CLAWEIXIN_CDN_ROOT` | `https://novac2c.cdn.weixin.qq.com/c2c` | 微信 CDN 上传/下载根地址，用于图片、文件、视频等媒体上传下载。 |
| `CLAWEIXIN_BOT_AGENT` | `nonebot-adapter-claweixin` | 上报给官方接口的 bot 身份标识，类似 `User-Agent`，主要用于服务端观测和排查。 |
| `CLAWEIXIN_ROUTE_TAG` | 空字符串 | 可选路由标签，会作为 `SKRouteTag` 请求头发送，主要用于测试、灰度或特殊路由。 |


第一步：登陆

方法一：

配置环境变量：

```dotenv
CLAWEIXIN_LOGIN_QRCODE_IN_INFO=true
```
这个环境变量会在机器人启动时获取登陆二维码，然后扫描对应二维码（可以通过访问链接/或者安装qrcode 终端扫描）

即可完成登陆和机器人注册，如果需要持久化，可参考第二步

方法二：
有 nb-cli 环境可以使用
```shell
nb claweixin-login
```
无 nb-cli 环境可以直接使用
```shell
claweixin-login
```

此方法会执行完整 CLI 登录流程，支持扫码、已绑定识别、重定向轮询和手机配对码验证
登录成功后会输出 `CLAWEIXIN_TOKEN`，如需持久化请执行第二步

第二步：可选的持久化 Token

单个机器人

```dotenv
CLAWEIXIN_TOKEN=["xxx"]
```

多个机器人

```dotenv
CLAWEIXIN_TOKEN=["aaa","bbb"]
```

## 相关项目

- [openclaw-weixin](https://github.com/Tencent/openclaw-weixin) 参考接口实现
