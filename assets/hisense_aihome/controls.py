"""下发控制指令的公共入口（number / switch / 服务 共用）。"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later

from .api import HisenseControlError, HisenseConnectionError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _delayed_refresh(hass: HomeAssistant, entry: ConfigEntry):
    """云端状态同步有延迟，隔几秒再刷一次。"""

    async def _refresh(_now) -> None:
        store = (hass.data.get(DOMAIN) or {}).get(entry.entry_id)
        if store:
            await store["coordinator"].async_request_refresh()

    return _refresh


async def send_command(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device_id: str,
    command: str,
    params: dict[str, Any],
    source_name: str | None = None,
) -> None:
    """下发一条指令；失败时抛出 HomeAssistantError（UI 会直接显示原因）。"""
    store = (hass.data.get(DOMAIN) or {}).get(entry.entry_id)
    if not store:
        raise HomeAssistantError("海信爱家集成未就绪")

    coordinator = store["coordinator"]
    info = (coordinator.data or {}).get(device_id, {})
    partner_id = info.get("partner_id") or "1001"

    try:
        await store["client"].async_execute(
            coordinator.access_token,
            coordinator.customer_id,
            device_id,
            partner_id,
            command,
            params,
            source_name=source_name,
        )
    except HisenseControlError as err:
        # 关机态下发设置类命令会得到 conflictCommand（errorcode=7），
        # 明确告诉用户原因，而不是静默失败
        raise HomeAssistantError(
            f"海信设备拒绝了指令 {command.split('.')[-1]}：{err}"
            "（提示：设置类参数需要设备先开机）"
        ) from err
    except HisenseConnectionError as err:
        raise HomeAssistantError(f"指令下发失败：{err}") from err

    _LOGGER.debug("已下发指令 %s -> %s", command, params)
    # 云端状态有 2~5 秒的同步延迟：立即刷一次，再补刷一次，避免 UI 停在旧值
    await coordinator.async_request_refresh()
    async_call_later(hass, 8, _delayed_refresh(hass, entry))
