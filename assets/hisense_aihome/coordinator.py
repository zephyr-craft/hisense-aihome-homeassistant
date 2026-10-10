"""DataUpdateCoordinator for 海信爱家."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HisenseAiHomeClient, HisenseAuthError, HisenseConnectionError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class HisenseCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """轮询家庭内设备列表 + 每台设备的实时状态。"""

    def __init__(
        self,
        hass: HomeAssistant,
        client: HisenseAiHomeClient,
        access_token: str,
        customer_id: str,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval or DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self.access_token = access_token
        self.customer_id = customer_id
        self.devices: dict[str, dict[str, Any]] = {}

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            devices = await self.client.async_get_devices(
                self.access_token, self.customer_id
            )
        except HisenseAuthError as err:
            raise UpdateFailed(f"登录凭证失效: {err}") from err
        except HisenseConnectionError as err:
            raise UpdateFailed(str(err)) from err

        # 列表接口带 withState=True，已包含实时状态，无需逐台再查 detail
        result: dict[str, dict[str, Any]] = {d["device_id"]: d for d in devices}
        self.devices = result
        _LOGGER.debug("海信爱家本轮设备数: %d", len(result))
        return result
