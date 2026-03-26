<p align="center">
  <a href="https://nonebot.dev/"><img src="https://nonebot.dev/logo.png" width="200" height="200" alt="nonebot"></a>
</p>

<div align="center">

# nonebot-adapter-claweixin

_✨ weixin clawbot 协议适配 ✨_

</div>

> [!NOTE]
> 目前处于早期阶段
> 
> 遇到问题可以反馈


## 配置

修改 NoneBot 配置文件 `.env` 或者 `.env.*`

### Driver

参考 [driver](https://nonebot.dev/docs/appendices/config#driver) 配置项，添加 `HTTPClient` 支持

如：

```dotenv
DRIVER=~httpx
```

### 配置机器人

*可选依赖 nonebot-adapter-claweixin[qrcode] 用于终端中显示二维码*

第一步：登陆

方法一：

配置环境变量：

```dotenv
claweixin_login_qrcode_in_info=true
```

这个环境变量会在机器人启动时获取登陆二维码，然后扫描对应二维码（可以通过访问链接/或者安装qrcode 终端扫描）

即可完成登陆和机器人注册，如果需要持久化，可参考第二步

方法二：
有 nb-cil 环境可以使用
```shell
nb claweixin-login
```
无 nb-cil 环境可以直接使用
```shell
claweixin-login
```

此方法不能直接登陆使用，请执行第二步

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

- [微信官方 npm 包](https://www.npmjs.com/package/@tencent-weixin/openclaw-weixin) 参考接口实现
