import sys
import asyncio
import logging
import httpx
from pydantic import BaseModel

try:
    import qrcode # type: ignore
except ImportError:
    qrcode = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("claweixin-login")

class LoginConfig(BaseModel):
    api_root: str
    bot_type: str = "3"

async def fetch_qrcode(api_root: str, bot_type: str) -> dict:
    url = f"{api_root.rstrip('/')}/ilink/bot/get_bot_qrcode?bot_type={bot_type}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

async def poll_qr_status(api_root: str, qrcode_id: str) -> dict:
    url = f"{api_root.rstrip('/')}/ilink/bot/get_qrcode_status?qrcode={qrcode_id}"
    headers = {"iLink-App-ClientVersion": "1"}
    async with httpx.AsyncClient(timeout=40.0) as client:
        try:
            response = await client.get(url, headers=headers, timeout=35.0)
            response.raise_for_status()
            return response.json()
        except httpx.ReadTimeout:
            return {"status": "wait"}

def display_qr(qrcode_url: str):
    print(f"\n请使用微信扫描以下二维码或打开链接: \n{qrcode_url}\n")
    if qrcode:
        qr = qrcode.QRCode()
        qr.add_data(qrcode_url)
        qr.make()
        qr.print_ascii(invert=True)
    else:
        print("安装 qrcode 库可在终端直接显示二维码 (pip install qrcode)")

async def login_flow(api_root: str):
    logger.info("开始请求登录二维码...")
    try:
        qr_data = await fetch_qrcode(api_root, "3")
        qrcode_id = qr_data.get("qrcode")
        qrcode_url = qr_data.get("qrcode_img_content")
        
        if not qrcode_id or not qrcode_url:
            logger.error("获取二维码失败，返回数据异常")
            return
            
        display_qr(qrcode_url)
        
        logger.info("等待扫码...")
        while True:
            status_data = await poll_qr_status(api_root, qrcode_id)
            status = status_data.get("status")
            
            if status == "wait":
                pass # 继续等待
            elif status == "scaned":
                logger.info("已扫码，请在手机上确认登录...")
            elif status == "expired":
                logger.warning("二维码已过期，请重新运行脚本获取新的二维码。")
                break
            elif status == "confirmed":
                bot_id = status_data.get("ilink_bot_id")
                bot_token = status_data.get("bot_token")
                resolved_baseurl = status_data.get("baseurl") or api_root
                logger.info(f"登录成功！")
                logger.info(f"Bot ID: {bot_id}")
                logger.info(f"Resolved Base URL: {resolved_baseurl}")
                logger.info(f"\n请将以下内容添加到你的 .env 文件中：\n")
                print(f"CLAWEXIN_TOKEN=\"{bot_token}\"")
                print(f"CLAWEXIN_API_ROOT=\"{resolved_baseurl}\"")
                print("\n")
                break
            else:
                logger.error(f"未知状态: {status}")
                await asyncio.sleep(2)
                
    except Exception as e:
        logger.error(f"登录流程发生错误: {e}")

if __name__ == "__main__":
    api_root = sys.argv[1] if len(sys.argv) > 1 else "https://ilinkai.weixin.qq.com"
    asyncio.run(login_flow(api_root))
