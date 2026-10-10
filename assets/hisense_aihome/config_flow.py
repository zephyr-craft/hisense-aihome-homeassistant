"""Config flow for 海信爱家.

设计要点（重要）：
  设备列表接口取的是「账号维度」的全部设备，与家庭无关；而家庭列表接口
  来自另一套云（智慧家 api-wg）。两套云数据不完全互通，因此**不能**用
  「有没有家庭」来决定能不能接入 —— 否则会出现「爱家有设备、智慧家无家庭」
  时被误判为无法配置。这里的判定以**设备**为准，家庭仅用于展示与区域归属。
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HisenseAiHomeClient, HisenseAuthError, HisenseConnectionError
from .const import (
    CONF_DEVICE_IDS,
    CONF_HOME_ID,
    CONF_HOME_NAME,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class HisenseAiHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """账号 → （可选）家庭 → 设备。"""

    VERSION = 1

    def __init__(self) -> None:
        self._username = ""
        self._password = ""
        self._auth: dict[str, Any] = {}
        self._homes: list[dict[str, Any]] = []
        self._devices: list[dict[str, Any]] = []
        self._home_id = ""
        self._home_name = ""

    # ----------------------------------------------------------------- user
    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            client = HisenseAiHomeClient(async_get_clientsession(self.hass))
            try:
                auth = await client.async_login(
                    user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
                devices = await client.async_get_devices(
                    auth["access_token"], auth["customer_id"]
                )
                homes = await client.async_get_homes(auth["access_token"])
            except HisenseAuthError as err:
                _LOGGER.error("海信爱家登录被拒: %s", err)
                errors["base"] = "invalid_auth"
            except HisenseConnectionError as err:
                _LOGGER.error("海信爱家连接失败: %s", err)
                errors["base"] = "cannot_connect"
            else:
                if not devices:
                    _LOGGER.error(
                        "海信爱家账号 %s 云端返回 0 台设备（customerId=%s）。"
                        "该账号下没有任何已绑定设备——请先在「海信爱家」App 中"
                        "完成设备配网绑定。注意「海信爱家」与「海信智慧家」"
                        "是两套云，设备不互通。",
                        user_input[CONF_USERNAME],
                        auth["customer_id"],
                    )
                    errors["base"] = "no_homes" if not homes else "no_devices"
                else:
                    self._username = user_input[CONF_USERNAME]
                    self._password = user_input[CONF_PASSWORD]
                    self._auth = auth
                    self._devices = devices
                    self._homes = homes
                    _LOGGER.info(
                        "海信爱家账号登录成功：家庭 %d 个，云端设备 %d 台",
                        len(homes),
                        len(devices),
                    )
                    if homes:
                        return await self.async_step_home()
                    return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    # ----------------------------------------------------------------- home
    async def async_step_home(self, user_input=None):
        """选择家庭；仅影响实体归属区域的建议，不影响设备能否接入。"""
        if user_input is not None:
            self._home_id = user_input[CONF_HOME_ID]
            self._home_name = next(
                (h["name"] for h in self._homes if h["home_id"] == self._home_id), ""
            )
            return await self.async_step_device()

        return self.async_show_form(
            step_id="home",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOME_ID): vol.In(
                        {h["home_id"]: h["name"] for h in self._homes}
                    )
                }
            ),
            errors={},
        )

    # --------------------------------------------------------------- device
    async def async_step_device(self, user_input=None):
        errors: dict[str, str] = {}
        options = {
            d["device_id"]: f"{d['category']} · {d['device_name']}"
            + (f"（{d['room_name']}）" if d["room_name"] else "")
            for d in self._devices
        }

        if user_input is not None:
            selected = user_input[CONF_DEVICE_IDS]
            if not selected:
                errors["base"] = "no_devices"
            else:
                title = f"海信爱家 · {self._home_name}" if self._home_name else "海信爱家"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_USERNAME: self._username,
                        CONF_PASSWORD: self._password,
                        CONF_HOME_ID: self._home_id,
                        CONF_HOME_NAME: self._home_name,
                        CONF_DEVICE_IDS: selected,
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                    },
                )

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEVICE_IDS): cv.multi_select(options)}
            ),
            errors=errors,
            description_placeholders={"device_count": str(len(options))},
        )
