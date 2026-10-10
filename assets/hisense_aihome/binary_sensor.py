"""Binary sensor entities for 海信爱家 —— 按字段表批量生成。"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_DEVICE_IDS, DOMAIN
from .coordinator import HisenseCoordinator
from .entity import HisenseEntity

ON_VALUES = {"1", "true", "True", "on", "ON", "On"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    add_entities: AddEntitiesCallback,
) -> None:
    from .fields import FIELDS

    store = hass.data[DOMAIN][entry.entry_id]
    coordinator: HisenseCoordinator = store["coordinator"]
    selected = set(entry.data.get(CONF_DEVICE_IDS) or [])

    entities: list[BinarySensorEntity] = []
    for device_id, info in (coordinator.data or {}).items():
        if selected and device_id not in selected:
            continue
        entities.append(HisenseOnlineBinarySensor(coordinator, device_id))
        entities.append(HisenseRunningBinarySensor(coordinator, device_id))
        specs = FIELDS.get(info.get("category") or "", FIELDS["其他"])
        for spec in specs:
            if spec["kind"] == "bool":
                entities.append(HisenseFieldBinarySensor(coordinator, device_id, spec))
    add_entities(entities)


class HisenseOnlineBinarySensor(HisenseEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_name = "在线"

    def __init__(self, coordinator: HisenseCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_online"

    @property
    def is_on(self) -> bool:
        return self.is_online


class HisenseRunningBinarySensor(HisenseEntity, BinarySensorEntity):
    """运行中——可直接用于「洗好/烘干完成」自动化触发。"""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:play-circle-outline"
    _attr_name = "运行中"

    def __init__(self, coordinator: HisenseCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_running"

    @property
    def is_on(self) -> bool:
        return self.is_online and self.is_running


class HisenseFieldBinarySensor(HisenseEntity, BinarySensorEntity):
    """按字段表生成的开关型实体。"""

    def __init__(
        self, coordinator: HisenseCoordinator, device_id: str, spec: dict[str, Any]
    ) -> None:
        super().__init__(coordinator, device_id)
        self._key = spec["key"]
        self._spec = spec
        self._attr_unique_id = f"{device_id}_{self._key}"
        self._attr_name = spec["name"]

    @property
    def icon(self) -> str | None:
        return self._spec.get("icon")

    @property
    def is_on(self) -> bool | None:
        raw = self._states.get(self._key)
        if raw is None or str(raw) in ("", "--"):
            return None
        return str(raw) in ON_VALUES

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "cloud_key": self._key,
            "raw": self._states.get(self._key),
        }
