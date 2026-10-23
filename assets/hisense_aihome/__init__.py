"""海信爱家 integration setup."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HisenseAiHomeClient
from .const import (
    CONF_HOME_ID,
    CONF_HOME_NAME,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    CONF_PASSWORD,
    DOMAIN,
)
from .coordinator import HisenseCoordinator
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.SELECT,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = HisenseAiHomeClient(session)

    auth = await client.async_login(
        entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )

    coordinator = HisenseCoordinator(
        hass,
        client,
        auth["access_token"],
        auth["customer_id"],
        # token 会过期（实测数天），必须把凭据交给协调器才能自动续期
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        scan_interval=entry.data.get(CONF_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
        "home_id": entry.data.get(CONF_HOME_ID),
        "home_name": entry.data.get(CONF_HOME_NAME),
        "username": entry.data[CONF_USERNAME],
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_services(hass)

    # 首次刷新时把云端清单打到日志：排障时一眼就能看出云侧到底有几台设备
    devices = coordinator.data or {}
    if devices:
        lines = [
            f"  - [{info.get('category')}] {info.get('device_name')}"
            f"（品类码 {info.get('category_code') or '?'}，"
            f"{'在线' if info.get('online') else '离线'}）"
            for info in devices.values()
        ]
        _LOGGER.info(
            "海信爱家集成已就绪：家庭=%s，云端设备 %d 台\n%s",
            entry.data.get(CONF_HOME_NAME),
            len(devices),
            "\n".join(lines),
        )
    else:
        _LOGGER.error(
            "海信爱家集成已就绪，但云端返回 **0 台设备**（家庭=%s）。"
            "请确认该账号已在「海信爱家」App 中完成设备绑定；"
            "注意「海信爱家」与「海信智慧家」是两套云，数据不完全互通。",
            entry.data.get(CONF_HOME_NAME),
        )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded
