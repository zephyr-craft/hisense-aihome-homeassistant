"""Number entities (可调参数) for 海信爱家.

注意：海信设备要求**先开机**才能接受参数设置；关机态下会返回 conflictCommand /
errorcode=7。这里不做拦截，直接把云端返回的错误抛给用户，避免"悄悄失败"。
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
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

    entities: list[NumberEntity] = []
    for device_id, info in (coordinator.data or {}).items():
        if selected and device_id not in selected:
            continue
        specs = (CONTROLS.get(info.get("category") or "", {}) or {}).get("numbers", [])
        for spec in specs:
            entities.append(HisenseNumber(coordinator, entry, device_id, spec))
    add_entities(entities)


class HisenseNumber(HisenseEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

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
        self._attr_native_min_value = spec.get("min", 0)
        self._attr_native_max_value = spec.get("max", 100)
        self._attr_native_step = spec.get("step", 1)
        if spec.get("unit"):
            self._attr_native_unit_of_measurement = spec["unit"]
        if dc := spec.get("dc"):
            try:
                self._attr_device_class = NumberDeviceClass(dc)
            except ValueError:
                pass

    @property
    def icon(self) -> str | None:
        return self._spec.get("icon")

    @property
    def native_value(self) -> float | None:
        raw = self._states.get(self._key)
        try:
            return float(str(raw))
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        await send_command(
            self.hass,
            self._entry,
            self._device_id,
            CMD_PREFIX + self._spec["cmd"],
            {self._spec.get("param", self._key): {"value": int(value)}},
        )
