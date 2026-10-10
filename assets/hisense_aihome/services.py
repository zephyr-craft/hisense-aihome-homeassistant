"""自定义服务：直接下发原始 AIHome 指令（便于继续摸索 App 的其它功能）。"""

from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import CMD_PREFIX, DOMAIN
from .controls import send_command

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_COMMAND = "send_command"
ATTR_DEVICE_ID = "device_id"
ATTR_COMMAND = "command"
ATTR_PARAMS = "params"

SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): str,
        vol.Required(ATTR_COMMAND): str,
        vol.Optional(ATTR_PARAMS, default="{}"): vol.Any(str, dict),
    }
)


def _find_entry_id(hass: HomeAssistant, device_id: str) -> str | None:
    for entry_id, store in (hass.data.get(DOMAIN) or {}).items():
        if device_id in ((store.get("coordinator").data) or {}):
            return entry_id
    return None


async def async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SEND_COMMAND):
        return

    async def _handle_send_command(call: ServiceCall) -> None:
        device_id = call.data[ATTR_DEVICE_ID]
        raw_cmd = str(call.data[ATTR_COMMAND]).strip()
        command = raw_cmd if raw_cmd.startswith(CMD_PREFIX) else CMD_PREFIX + raw_cmd

        params = call.data.get(ATTR_PARAMS) or "{}"
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError as err:
                raise HomeAssistantError(f"params 不是合法 JSON：{err}") from err

        entry_id = _find_entry_id(hass, device_id)
        if entry_id is None:
            raise HomeAssistantError(f"没有找到设备 {device_id} 对应的海信爱家配置项")

        entry = hass.config_entries.async_get_entry(entry_id)
        await send_command(hass, entry, device_id, command, params)
        _LOGGER.info("已下发原始指令 %s -> %s", command, params)

    hass.services.async_register(
        DOMAIN, SERVICE_SEND_COMMAND, _handle_send_command, schema=SCHEMA
    )
