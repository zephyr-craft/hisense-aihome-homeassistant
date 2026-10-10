"""Sensor entities for 海信爱家 —— 按字段表批量生成。"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_DEVICE_IDS, DOMAIN, FAULT_PREFIXES
from .coordinator import HisenseCoordinator
from .entity import HisenseEntity
from .fields import MATERIAL_DEFAULT_MINUTES

_LOGGER = logging.getLogger(__name__)

NO_VALUE = {"", "--", "None", "null"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    store = hass.data[DOMAIN][entry.entry_id]
    coordinator: HisenseCoordinator = store["coordinator"]
    selected = set(entry.data.get(CONF_DEVICE_IDS) or [])

    entities: list[SensorEntity] = []
    for device_id, info in (coordinator.data or {}).items():
        if selected and device_id not in selected:
            continue
        entities.append(HisenseStatusSensor(coordinator, device_id))
        entities.append(HisenseFaultSensor(coordinator, device_id))
        for spec in _field_specs(info.get("category")):
            if spec["kind"] in ("num", "val"):
                entities.append(HisenseFieldSensor(coordinator, device_id, spec))

    _LOGGER.info("海信爱家：已创建 %d 个传感器实体", len(entities))
    async_add_entities(entities)


def _field_specs(category: str | None) -> list[dict[str, Any]]:
    from .fields import FIELDS

    return FIELDS.get(category or "", FIELDS["其他"])


def _to_number(value: Any) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


class HisenseStatusSensor(HisenseEntity, SensorEntity):
    """整机状态：离线 / 运行中 / 已开机 / 待机。"""

    _attr_name = "状态"

    def __init__(self, coordinator: HisenseCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_status"

    @property
    def icon(self) -> str:
        return {
            "洗衣机": "mdi:washing-machine",
            "干衣机": "mdi:tumble-dryer",
            "洗碗机": "mdi:dishwasher",
            "冰箱": "mdi:fridge",
            "空调": "mdi:air-conditioner",
        }.get(self._category, "mdi:devices")

    @property
    def native_value(self) -> str:
        if not self.is_online:
            return "离线"
        states = self._states
        if not states:
            return "未知"
        if self.is_running:
            return "运行中"
        if self.is_powered:
            return "已开机"
        return "待机"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = self.status_snapshot()
        attrs["field_count"] = len(self._states)
        return attrs


class HisenseFaultSensor(HisenseEntity, SensorEntity):
    """故障汇总：正常时显示「正常」，否则显示第一个故障位。"""

    _attr_name = "故障"
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator: HisenseCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_fault"

    @property
    def _active_faults(self) -> dict[str, Any]:
        return {
            k: v
            for k, v in self._states.items()
            if k.startswith(FAULT_PREFIXES) and str(v) not in ("--", "", "0")
        }

    @property
    def native_value(self) -> str:
        active = self._active_faults
        if active:
            key = sorted(active)[0]
            return f"{key} = {active[key]}"
        summary = str(self._states.get("fault", "0"))
        return "正常" if summary in ("0", "") else f"故障码 {summary}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"active_faults": self._active_faults}


class HisenseFieldSensor(HisenseEntity, SensorEntity):
    """按字段表生成的单字段传感器。"""

    def __init__(
        self, coordinator: HisenseCoordinator, device_id: str, spec: dict[str, Any]
    ) -> None:
        super().__init__(coordinator, device_id)
        self._key = spec["key"]
        self._spec = spec
        self._attr_unique_id = f"{device_id}_{self._key}"
        self._attr_name = spec["name"]
        if spec.get("unit"):
            self._attr_native_unit_of_measurement = spec["unit"]
        if dc := spec.get("dc"):
            try:
                self._attr_device_class = SensorDeviceClass(dc)
            except ValueError:
                pass
        if sc := spec.get("sc"):
            try:
                self._attr_state_class = SensorStateClass(sc)
            except ValueError:
                pass

    @property
    def icon(self) -> str | None:
        return self._spec.get("icon")

    def _display(self, raw: Any) -> Any:
        """把原始值转成可读文本。

        优先级：用户填的 VALUE_LABELS → spec 内置 values → spec 的 format_num → 原始值。
        这样即使某些枚举的官方叫法拿不到，也不会只显示一个裸数字，
        而且用户对照 App 后只要往 VALUE_LABELS 里填名字就会自动生效。
        """
        from .fields import VALUE_LABELS

        key = str(raw)
        user = (VALUE_LABELS.get(self._category) or {}).get(self._key) or {}
        if key in user:
            return user[key]
        builtin = self._spec.get("values") or {}
        if key in builtin:
            return builtin[key]
        if fmt := self._spec.get("format_num"):
            try:
                return fmt.format(v=int(float(key)))
            except (TypeError, ValueError):
                pass
        return key

    @property
    def native_value(self) -> Any:
        raw = self._states.get(self._key)
        if raw is None or str(raw) in NO_VALUE:
            return None
        if self._spec["kind"] == "num":
            number = _to_number(raw)
            return int(number) if number is not None and number.is_integer() else number
        return self._display(raw)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        raw = self._states.get(self._key)
        attrs: dict[str, Any] = {"cloud_key": self._key, "raw": raw}
        if self._key == "clotheMaterial":
            # 云端标签给出「材质编号 → 建议烘干分钟数」，附上来更有参考价值
            attrs["material_default_minutes"] = MATERIAL_DEFAULT_MINUTES
        return attrs
