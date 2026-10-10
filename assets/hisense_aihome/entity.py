"""Shared entity helpers for 海信爱家."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    POWERED_TRUE_VALUES,
    RUNNING_TRUE_VALUES,
    STATUS_KEYS_DOOR,
    STATUS_KEYS_ERROR,
    STATUS_KEYS_POWER,
    STATUS_KEYS_PROGRAM,
    STATUS_KEYS_REMAINING,
    STATUS_KEYS_RUNNING,
)
from .coordinator import HisenseCoordinator


def _first(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


class HisenseEntity(CoordinatorEntity[HisenseCoordinator]):
    """所有实体的基类：负责设备信息与状态字段解析。"""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HisenseCoordinator, device_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id

    # -------------------------------------------------------------- 基础信息
    @property
    def _info(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get(self._device_id, {})

    @property
    def _states(self) -> dict[str, Any]:
        """海信把实时状态放在 device 的 states 字段里。"""
        states = self._info.get("states")
        return states if isinstance(states, dict) else {}

    @property
    def _category(self) -> str:
        return self._info.get("category", "设备")

    @property
    def _name(self) -> str:
        return self._info.get("device_name", self._device_id)

    @property
    def device_info(self) -> DeviceInfo:
        info = self._info
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=info.get("device_name") or self._device_id,
            manufacturer="Hisense",
            model=info.get("model") or info.get("product_name") or info.get("category_code"),
            suggested_area=info.get("room_name") or None,
            sw_version=((info.get("raw") or {}).get("deviceInfo") or {}).get("swVersion"),
        )

    # -------------------------------------------------------------- 状态解析
    @property
    def is_online(self) -> bool:
        return bool(self._info.get("online", True))

    @property
    def is_powered(self) -> bool:
        value = _first(self._states, STATUS_KEYS_POWER)
        return value is not None and str(value).strip().lower() in POWERED_TRUE_VALUES

    @property
    def running_raw(self) -> Any:
        return _first(self._states, STATUS_KEYS_RUNNING)

    @property
    def is_running(self) -> bool:
        value = self.running_raw
        if value is None:
            return False
        return str(value).strip().lower() in RUNNING_TRUE_VALUES

    def status_snapshot(self) -> dict[str, Any]:
        """整理成便于展示/自动化的字典。"""
        s = self._states
        info = self._info
        return {
            "device_id": self._device_id,
            "category": self._category,
            "room": info.get("room_name") or None,
            "model": info.get("model") or None,
            "product": info.get("product_name") or None,
            "category_code": info.get("category_code") or None,
            "online": self.is_online,
            "powered": self.is_powered,
            "program": _first(s, STATUS_KEYS_PROGRAM),
            "remaining_time": _first(s, STATUS_KEYS_REMAINING),
            "door": _first(s, STATUS_KEYS_DOOR),
            "error_code": _first(s, STATUS_KEYS_ERROR),
            "run_status_raw": self.running_raw,
            "report_time": info.get("report_time") or None,
        }
