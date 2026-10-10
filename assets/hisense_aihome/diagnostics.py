"""Diagnostics support —— 导出的数据已剔除任何凭据。"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_PASSWORD, DOMAIN

TO_REDACT = {CONF_PASSWORD, "access_token", "token", "refreshToken", "customerId"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    store = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = store.get("coordinator")

    entry_data = {
        k: ("**REDACTED**" if k in TO_REDACT else v) for k, v in entry.data.items()
    }
    devices = []
    for device_id, info in (coordinator.data or {}).items() if coordinator else []:
        devices.append(
            {
                "device_id": device_id,
                "category": info.get("category"),
                "category_code": info.get("category_code"),
                "device_name": info.get("device_name"),
                "product_name": info.get("product_name"),
                "model": info.get("model"),
                "room_name": info.get("room_name"),
                "online": info.get("online"),
                "detail": info.get("detail"),
            }
        )
    return {"entry": entry_data, "device_count": len(devices), "devices": devices}
