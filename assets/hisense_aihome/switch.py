"""Switch entities (电源 / 童锁) for 海信爱家."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
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

    entities: list[SwitchEntity] = []
    for device_id, info in (coordinator.data or {}).items():
        if selected and device_id not in selected:
            continue
        specs = (CONTROLS.get(info.get("category") or "", {}) or {}).get("switches", [])
        for spec in specs:
            entities.append(HisenseSwitch(coordinator, entry, device_id, spec))
    add_entities(entities)


class HisenseSwitch(HisenseEntity, SwitchEntity):
    def __init__(
        self,
        coordinator: HisenseCoordinator,
        entry: ConfigEntry,
        device_id: str,
        spec: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, device_id)
        self._entry = entry
        self._key = spec["key"]
        self._spec = spec
        self._attr_unique_id = f"{device_id}_{self._key}_ctl"
        self._attr_name = spec["name"]

    @property
    def icon(self) -> str | None:
        return self._spec.get("icon")

    @property
    def is_on(self) -> bool | None:
        raw = self._states.get(self._key)
        if raw is None or str(raw) in ("", "--"):
            return None
        return str(raw) in ("1", "true", "True", "on")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, on: bool) -> None:
        if self._spec.get("power"):
            # 电源走特例：Power + onAndOff.code + sourceName=smartlifeApp
            from .const import CMD_POWER, POWER_SOURCE_NAME

            await send_command(
                self.hass,
                self._entry,
                self._device_id,
                CMD_POWER,
                {"onAndOff": {"code": "On" if on else "Off"}},
                source_name=POWER_SOURCE_NAME,
            )
            return
        await send_command(
            self.hass,
            self._entry,
            self._device_id,
            CMD_PREFIX + self._spec["cmd"],
            {self._key: {"value": 1 if on else 0}},
        )
