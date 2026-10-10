"""海信爱家 (HiSense AiHome) cloud API client.

协议要点（均为实机验证结果）：
  1. 登录   POST https://portal-account.hismarttv.com/mobile/se/signon
            **必须使用加密体**：loginName / signature 各自做 AES-256-CBC(PKCS7) 加密后 base64，
            header 需带 `appKey: commonweb` 与 `X-Sign-For = b64(md5(body+secret))`。
            → data.tokenInfo.{token, customerId}

            ⚠️ 严重陷阱：把 loginName 写成**明文**时，服务端会走进一个**完全不校验密码**的
            旧分支——空密码、乱填密码、甚至不存在的手机号都会返回 resultCode=0 和一个固定
            的假身份（该分支固定返回同一个 customerId，与任何真实账号无关，
            判定方法：用明显错误的密码多试几次，若 customerId 恒为同一个值，即中此陷阱）。
            因此**绝不能**用明文登录，
            否则会拿到一个"看似成功但根本不是你账号"的身份，表现为"云端 0 设备"。
  2. 家庭   GET  https://api-wg.hismarttv.com/wg/dm/getHomeList   ?accessToken=...
  3. 设备   POST https://iot-aihome.hismarttv.com/4.0/iot/devices/list
            payload {withMultiSplit, customerId, withState, sourceType:20, whitelist:1}
            顶层 deviceId 为固定占位值，appType='2'，appVersion='6.4.0.3'
            X-Sign-For = MD5(body + AIHOME_SIGN_KEY) 的 base64
  4. 详情   POST .../4.0/iot/devices/detail   同上（payload.deviceId 为真实设备）
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
import uuid
from typing import Any

import aiohttp

from .const import (
    AIHOME_APP_VERSION,
    AIHOME_DETAIL,
    AIHOME_DEVICES,
    AIHOME_EXECUTE,
    AIHOME_PLACEHOLDER_DEVICE_ID,
    AIHOME_SIGN_KEY,
    AIHOME_X_REAL_HOST,
    CMD_POWER,
    CONTROL_SOURCE_NAME,
    DEVICE_TYPE_RULES,
    PORTAL_APP_KEY,
    PORTAL_APP_SECRET,
    PORTAL_SIGNON,
    POWER_SOURCE_NAME,
    UNKNOWN_DEVICE_TYPE,
    WG_HOME_LIST,
)

_LOGGER = logging.getLogger(__name__)


class HisenseAuthError(Exception):
    """账号或密码错误。"""


class HisenseConnectionError(Exception):
    """网络或接口异常。"""


class HisenseControlError(Exception):
    """指令下发被设备或云端拒绝。"""


def _portal_encrypt(value: str) -> str:
    """按海信爱家 App 的方式加密登录字段：AES-256-CBC + PKCS7 + base64。"""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key = PORTAL_APP_SECRET.encode("ascii")          # 32 字节 → AES-256
    iv = PORTAL_APP_SECRET[:16].encode("ascii")      # 前 16 字节
    raw = value.encode("utf-8")
    pad = 16 - (len(raw) % 16)
    padded = raw + bytes([pad]) * pad                # PKCS7
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode("ascii")


def _md5_b64(value: str, secret: str) -> str:
    digest = hashlib.md5((value + secret).encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def classify_device(device: dict[str, Any]) -> str:
    """把设备映射到中文品类。识别不了就返回「其他」，绝不丢弃。"""
    product = device.get("product") or {}
    haystack = " ".join(
        str(v or "").lower()
        for v in (
            device.get("categoryCode"),
            device.get("deviceTypeName"),
            device.get("deviceName"),
            product.get("name"),
            product.get("code"),
        )
    )
    for keywords, label in DEVICE_TYPE_RULES:
        if any(kw.lower() in haystack for kw in keywords):
            return label
    return UNKNOWN_DEVICE_TYPE


class HisenseAiHomeClient:
    """无状态 async 客户端，session 由 HA 统一管理。"""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    # ------------------------------------------------------------------ login
    async def async_login(self, username: str, password: str) -> dict[str, Any]:
        """登录海信账号服务。

        **必须加密**：明文 loginName 会触发服务端一个不校验密码的旧分支，
        返回固定的假身份（表现为"登录成功但云端 0 设备"），因此这里只走加密体。
        """
        body = json.dumps(
            {
                "loginName": _portal_encrypt(username),
                "signature": _portal_encrypt(password),
                "serverCode": "9501",
                "distributeId": "2001",
                "termType": 2,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )
        params = {
            "lastUpdateTime": "0",
            "version": "1.0",
            "deviceType": "2",
            "appType": "100",
            "versionCode": "101",
            "adaptertRank": "720",
            "_": str(int(time.time() * 1000)),
        }
        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "appKey": PORTAL_APP_KEY,
            "X-Sign-For": _md5_b64(body, PORTAL_APP_SECRET),
        }
        try:
            async with self._session.post(
                PORTAL_SIGNON, headers=headers, data=body, params=params, timeout=30
            ) as resp:
                payload = await resp.json(content_type=None)
        except Exception as err:  # noqa: BLE001
            raise HisenseConnectionError(f"登录请求失败: {err}") from err

        data = (payload or {}).get("data") or {}
        if data.get("resultCode") != 0:
            code = data.get("errorCode")
            desc = data.get("errorDesc") or "登录失败"
            if str(code) == "202012":
                raise HisenseAuthError(
                    "海信账号服务拒绝了这组凭据（errorCode=202012）。请确认："
                    "① 密码是否为「海信爱家」App 当前使用的密码；"
                    "② 该账号是否用「手机号+密码」登录——若平时用的是短信验证码或"
                    "华为/微信一键登录，则可能根本没有设置密码，需先在 App 里设置一个密码。"
                )
            raise HisenseAuthError(f"{desc} (code={code})")

        token_info = data.get("tokenInfo") or {}
        token = token_info.get("token")
        customer_id = token_info.get("customerId")
        if not token or not customer_id:
            raise HisenseAuthError("登录响应缺少 token / customerId")

        return {
            "access_token": str(token),
            "customer_id": str(customer_id),
            "subscriber_id": str(token_info.get("subscriberId") or ""),
        }

    # ------------------------------------------------------------------ homes
    async def async_get_homes(self, access_token: str) -> list[dict[str, Any]]:
        params = {
            "sign": "",
            "languageId": "0",
            "version": "8.0",
            "accessToken": access_token,
            "timezone": "28800",
            "format": "1",
            "timeStamp": str(int(time.time() * 1000)),
        }
        headers = {
            "Host": "api.wg.hismarttv.com",
            "User-Agent": "okhttp/4.10.0",
            "Accept-Encoding": "gzip",
        }
        try:
            async with self._session.get(
                WG_HOME_LIST, headers=headers, params=params, timeout=30
            ) as resp:
                payload = await resp.json(content_type=None)
        except Exception as err:  # noqa: BLE001
            raise HisenseConnectionError(f"获取家庭列表失败: {err}") from err

        response = (payload or {}).get("response") or {}
        if response.get("resultCode") != 0:
            raise HisenseConnectionError(
                f"获取家庭列表返回异常: resultCode={response.get('resultCode')}"
            )
        homes = []
        for home in response.get("homeList") or []:
            home_id = home.get("homeId")
            if home_id is None:
                continue
            homes.append(
                {
                    "home_id": str(home_id),
                    "name": (home.get("homeName") or str(home_id)).strip(),
                    "address": home.get("address") or "",
                }
            )
        return homes

    # ---------------------------------------------------------------- devices
    def _aihome_headers(self, body: str) -> dict[str, str]:
        return {
            "Host": "iot-aihome.hismarttv.com",
            "Content-Type": "application/json; charset=utf-8",
            "Connection": "keep-alive",
            "Accept-Encoding": "gzip",
            "User-Agent": f"JHKMain/{AIHOME_APP_VERSION} (iPhone; iOS 26.4; Scale/3.00)",
            "X_REAL_HOST": AIHOME_X_REAL_HOST,
            "X-Sign-For": _md5_b64(body, AIHOME_SIGN_KEY),
        }

    async def _aihome_post(
        self, url: str, access_token: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        body = json.dumps(
            {
                "deviceId": AIHOME_PLACEHOLDER_DEVICE_ID,
                "appType": "2",
                "appVersion": AIHOME_APP_VERSION,
                "header": {"messageId": str(uuid.uuid4())},
                "accessToken": access_token,
                "payload": payload,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )
        try:
            async with self._session.post(
                url, headers=self._aihome_headers(body), data=body, timeout=30
            ) as resp:
                return await resp.json(content_type=None) or {}
        except Exception as err:  # noqa: BLE001
            raise HisenseConnectionError(f"爱家接口请求失败: {err}") from err

    async def async_get_devices(
        self, access_token: str, customer_id: str
    ) -> list[dict[str, Any]]:
        """列出账号下全部设备（**不做类型白名单过滤**）。"""
        result = await self._aihome_post(
            AIHOME_DEVICES,
            access_token,
            {
                "withMultiSplit": True,
                "customerId": str(customer_id),
                "withState": True,
                "sourceType": 20,
                "whitelist": 1,
            },
        )
        payload = result.get("payload") or {}
        if payload.get("status") != "SUCCESS":
            raise HisenseConnectionError(
                f"获取设备列表失败: {result.get('errorDesc') or payload.get('status')}"
            )

        devices = []
        for raw in payload.get("devices") or []:
            device_id = raw.get("deviceId")
            if not device_id:
                continue
            product = raw.get("product") or {}
            partner = raw.get("partner") or {}
            room = raw.get("room") or {}
            # 实时状态就在列表返回的 states 字段里（请求时带了 withState=True），
            # 因此无需再逐台调用 detail 接口 —— 少一次云端请求，降低被限流风险。
            states = raw.get("states") or {}
            online_raw = str(states.get("onlineStatus", "")).strip()
            devices.append(
                {
                    "device_id": str(device_id),
                    "category": classify_device(raw),
                    "category_code": raw.get("categoryCode") or "",
                    # nickname 才是人话名（洗衣机 / 干衣机），优先用它
                    "device_name": (
                        raw.get("nickname")
                        or raw.get("deviceName")
                        or product.get("name")
                        or str(device_id)
                    ),
                    "product_name": product.get("name") or "",
                    "product_code": product.get("code") or "",
                    "model": product.get("code") or raw.get("model") or "",
                    "room_name": room.get("name") or raw.get("roomName") or "",
                    "partner_id": str(partner.get("id") or "1001"),
                    "online": online_raw != "0",
                    "states": states,
                    "report_time": raw.get("reportTime") or "",
                    "raw": raw,
                }
            )
        return devices

    async def async_get_device_detail(
        self, access_token: str, customer_id: str, device_id: str, partner_id: str = "10005"
    ) -> dict[str, Any]:
        result = await self._aihome_post(
            AIHOME_DETAIL,
            access_token,
            {
                "deviceId": str(device_id),
                "sourceType": 20,
                "partnerId": str(partner_id),
                "customerId": str(customer_id),
            },
        )
        payload = result.get("payload") or {}
        if payload.get("status") != "SUCCESS":
            _LOGGER.debug(
                "设备 %s 状态查询返回异常: %s", device_id, result.get("errorDesc")
            )
            return {}
        return payload.get("device") or {}

    async def async_validate(self, username: str, password: str) -> dict[str, Any]:
        """登录 + 探活，返回 token 信息（配置流程用）。"""
        auth = await self.async_login(username, password)
        await self.async_get_homes(auth["access_token"])
        return auth

    # --------------------------------------------------------------- 控制
    async def async_execute(
        self,
        access_token: str,
        customer_id: str,
        device_id: str,
        partner_id: str,
        command: str,
        params: dict[str, Any],
        source_name: str | None = None,
    ) -> None:
        """下发一条 AIHome 指令；失败时抛出 HisenseControlError。

        body 形状（实机验证）：
          header / deviceId(占位) / appVersion / accessToken / appType="2" / sourceName
          payload: {deviceId(真实), sourceType:"20", exclusionFlag:1,
                    customerId, partnerId, actions:[{command, params}]}
        """
        body = json.dumps(
            {
                "header": {"messageId": str(uuid.uuid4())},
                "deviceId": AIHOME_PLACEHOLDER_DEVICE_ID,
                "appVersion": AIHOME_APP_VERSION,
                "payload": {
                    "deviceId": str(device_id),
                    "sourceType": "20",
                    "exclusionFlag": 1,
                    "customerId": str(customer_id),
                    "partnerId": str(partner_id),
                    "actions": [{"command": command, "params": params}],
                },
                "accessToken": access_token,
                "appType": "2",
                "sourceName": source_name or CONTROL_SOURCE_NAME,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )
        try:
            async with self._session.post(
                AIHOME_EXECUTE, headers=self._aihome_headers(body), data=body, timeout=30
            ) as resp:
                result = await resp.json(content_type=None) or {}
        except Exception as err:  # noqa: BLE001
            raise HisenseConnectionError(f"指令下发失败: {err}") from err

        payload = result.get("payload") or {}
        if payload.get("status") == "SUCCESS":
            return
        raise HisenseControlError(
            f"{payload.get('errorCode') or result.get('errorDesc') or '未知错误'}"
            f"（{payload.get('errorDesc') or ''}）"
        )

    async def async_set_power(
        self, access_token: str, customer_id: str, device_id: str, partner_id: str, on: bool
    ) -> None:
        """电源是特例：Power + {"onAndOff": {"code": "On"/"Off"}}，且 sourceName 需为 smartlifeApp。"""
        await self.async_execute(
            access_token,
            customer_id,
            device_id,
            partner_id,
            CMD_POWER,
            {"onAndOff": {"code": "On" if on else "Off"}},
            source_name=POWER_SOURCE_NAME,
        )
