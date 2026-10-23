"""DataUpdateCoordinator for 海信爱家.

⚠️ 关键背景：海信的 accessToken 有有效期（实测数天）。过期后所有接口都会返回
   `accessToken is illegal`，表现为**HA 里整台设备离线、但手机 App 一切正常**
   （因为 App 每次打开都会重新登录）。
   因此这里必须自己保存账号密码并做「过期 → 重登 → 重试」，
   否则用户只能手动重载集成才能恢复。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    HisenseAiHomeClient,
    HisenseAuthError,
    HisenseConnectionError,
    HisenseTokenExpiredError,
)
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class HisenseCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """轮询家庭内设备列表 + 每台设备的实时状态，并负责 token 的自动续期。"""

    def __init__(
        self,
        hass: HomeAssistant,
        client: HisenseAiHomeClient,
        access_token: str,
        customer_id: str,
        username: str = "",
        password: str = "",
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval or DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self.access_token = access_token
        self.customer_id = customer_id
        self.devices: dict[str, dict[str, Any]] = {}
        # 重登所需的凭据（来自 config_entry，不落盘、不写日志）
        self._username = username
        self._password = password
        self._login_lock = asyncio.Lock()

    # ------------------------------------------------------------ 重新登录
    async def async_relogin(self, stale_token: str) -> bool:
        """用保存的账号密码换一个新 token。

        并发保护：
          · 多个平台同时发现过期时只真正登录一次（_login_lock）；
          · 若别的任务已经换过（token 已不是当初那个失效值），直接复用，不重复登录。
        """
        if not self._username or not self._password:
            _LOGGER.warning(
                "海信 token 已失效，但配置项里没有账号密码，无法自动重新登录"
                "（请重新添加集成，或手动重载集成）"
            )
            return False

        async with self._login_lock:
            if self.access_token and self.access_token != stale_token:
                return True
            try:
                auth = await self.client.async_login(self._username, self._password)
            except HisenseAuthError as err:
                # 密码被拒：反复重试没有意义，但要明确告诉用户原因
                _LOGGER.error(
                    "海信自动重新登录被拒绝（请确认 App 里是否改过密码）: %s", err
                )
                return False
            except HisenseConnectionError as err:
                _LOGGER.warning("海信自动重新登录时网络异常: %s", err)
                return False
            self.access_token = auth["access_token"]
            self.customer_id = auth["customer_id"]
            _LOGGER.info("海信 token 已过期，已自动重新登录并续期")
            return True

    # ------------------------------------------------------------ 轮询
    async def _fetch(self) -> dict[str, dict[str, Any]]:
        """拉一次设备列表（列表带 withState，已含实时状态）。"""
        devices = await self.client.async_get_devices(
            self.access_token, self.customer_id
        )
        result: dict[str, dict[str, Any]] = {d["device_id"]: d for d in devices}
        self.devices = result
        _LOGGER.debug("海信爱家本轮设备数: %d", len(result))
        return result

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            return await self._fetch()
        except HisenseTokenExpiredError as err:
            _LOGGER.info("海信 token 失效（%s），尝试自动重新登录…", err)
            if not await self.async_relogin(self.access_token):
                raise UpdateFailed(f"登录凭证已过期且自动重登失败: {err}") from err
            try:
                return await self._fetch()
            except (HisenseConnectionError, HisenseTokenExpiredError) as err2:
                raise UpdateFailed(f"重新登录后仍失败: {err2}") from err2
        except HisenseConnectionError as err:
            raise UpdateFailed(str(err)) from err

    # ------------------------------------------------------------ 控制
    async def async_execute(
        self,
        device_id: str,
        partner_id: str,
        command: str,
        params: dict[str, Any],
        source_name: str | None = None,
    ) -> None:
        """下发指令；token 过期时自动重登并重试一次，避免"点了没反应"。"""

        async def _do() -> None:
            await self.client.async_execute(
                self.access_token,
                self.customer_id,
                device_id,
                partner_id,
                command,
                params,
                source_name=source_name,
            )

        try:
            await _do()
        except HisenseTokenExpiredError:
            _LOGGER.info("下发指令时发现 token 失效，自动重新登录后重试")
            if not await self.async_relogin(self.access_token):
                raise
            await _do()
