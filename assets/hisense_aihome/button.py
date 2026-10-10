"""Button entities（启动 / 暂停）for 海信爱家.

⚠️ 注意：`connector.device.command.Start` 在**关机态也可能被接受**（实测干衣机在
关机态返回 SUCCESS），因此这两个按钮是**真实动作**，请确认滚筒内情况后再按。
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CMD_PREFIX, CONF_DEVICE_IDS, DOMAIN
from .controls import send_command
from .coordinator import HisenseCoordinator
from .entity import HisenseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    add_entities: AddEntitiesCallback,
) -> None:
    from .fields import CONTROLS

    store = hass.data[DOMAIN][entry.entry_id]
    coordinator: HisenseCoordinator = store["coordinator"]
    selected = set(entry.data.get(CONF_DEVICE_IDS) or [])

    entities: list[ButtonEntity] = []
    for device_id, info in (coordinator.data or {}).items():
        if selected and device_id not in selected:
            continue
        specs = (CONTROLS.get(info.get("category") or "", {}) or {}).get("buttons", [])
        for spec in specs:
            entities.append(HisenseButton(coordinator, entry, device_id, spec))
    add_entities(entities)


class HisenseButton(HisenseEntity, ButtonEntity):
    def __init__(
        self,
        coordinator: HisenseCoordinator,
        entry: ConfigEntry,
        device_id: str,
        spec: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, device_id)
        self._entry = entry
        self._spec = spec
        self._attr_unique_id = f"{device_id}_btn_{spec['cmd']}"
        self._attr_name = spec["name"]
        self._attr_icon = spec.get("icon")

    async def async_press(self) -> None:
        await send_command(
            self.hass,
            self._entry,
            self._device_id,
            CMD_PREFIX + self._spec["cmd"],
            self._spec["params"],
        )
