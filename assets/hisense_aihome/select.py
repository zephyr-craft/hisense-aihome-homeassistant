"""Select entities（程序选择）for 海信爱家.

洗衣机/干衣机的程序都是通过 `connector.device.command.SetModes` + `{"modes": {"value": N}}`
选择的，`workMode` 会同步跟随。

注意：**程序名在 App 客户端本地字典里，服务端不返回**。因此选项默认用「程序N（时长·温度·转速）」
这种指纹形式，你可以对着 App 的程序列表一一对上；对上之后把名字填进 `fields.py` 的
`PROGRAM_NAMES` 即可，选项会自动显示成真实名称。
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CMD_PREFIX, CONF_DEVICE_IDS, DOMAIN
from .controls import send_command
from .coordinator import HisenseCoordinator
from .entity import HisenseEntity

_LOGGER = logging.getLogger(__name__)


def _label(category: str, value: int, spec: dict[str, Any]) -> str:
    """生成选项文本。

    ⚠️ 必须保证**唯一**：HA 的 select.set_option 是按文本匹配的，
    若有两条文本相同，选后者也会命中前者。因此未命名的程序一律带上「程序N」前缀
    （同一时长常有多个程序号，指纹会重复）。
    """
    from .programs import PROGRAM_NAMES

    finger = spec["options"].get(value, str(value))
    name = (PROGRAM_NAMES.get(category) or {}).get(value)
    return f"{name}｜{finger}" if name else f"程序{value}｜{finger}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    add_entities: AddEntitiesCallback,
) -> None:
    from .fields import CONTROLS

    store = hass.data[DOMAIN][entry.entry_id]
    coordinator: HisenseCoordinator = store["coordinator"]
    selected = set(entry.data.get(CONF_DEVICE_IDS) or [])

    entities: list[SelectEntity] = []
    for device_id, info in (coordinator.data or {}).items():
        if selected and device_id not in selected:
            continue
        specs = (CONTROLS.get(info.get("category") or "", {}) or {}).get("selects", [])
        for spec in specs:
            entities.append(HisenseSelect(coordinator, entry, device_id, info.get("category"), spec))
    add_entities(entities)


class HisenseSelect(HisenseEntity, SelectEntity):
    def __init__(
        self,
        coordinator: HisenseCoordinator,
        entry: ConfigEntry,
        device_id: str,
        category: str | None,
        spec: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, device_id)
        self._entry = entry
        self._cat = category or ""
        self._key = spec["key"]
        self._spec = spec
        self._attr_unique_id = f"{device_id}_{self._key}_sel"
        self._attr_name = spec["name"]
        # 只暴露本机确认支持的程序号
        self._labels = {v: _label(self._cat, v, spec) for v in spec["options"]}
        # 安全网：万一仍有同名文本，补上程序号后缀，确保 set_option 不会选错
        seen: dict[str, int] = {}
        for v, lab in list(self._labels.items()):
            if lab in seen:
                self._labels[v] = f"{lab}（程序{v}）"
            seen[self._labels[v]] = v
        self._label_to_value = {lab: v for v, lab in self._labels.items()}
        self._attr_options = list(self._labels.values())

    @property
    def icon(self) -> str | None:
        return self._spec.get("icon")

    @property
    def current_option(self) -> str | None:
        raw = self._states.get(self._key)
        if raw is None or str(raw) in ("", "--"):
            return None
        try:
            return self._labels.get(int(float(str(raw))))
        except (TypeError, ValueError):
            return None

    async def async_select_option(self, option: str) -> None:
        value = self._label_to_value.get(option)
        if value is None:
            return
        await send_command(
            self.hass,
            self._entry,
            self._device_id,
            CMD_PREFIX + self._spec["cmd"],
            {self._spec.get("param", self._key): {"value": int(value)}},
        )
