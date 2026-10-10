"""字段定义表 —— 决定每台设备生成哪些实体。

设计原则：
- 海信云对同一台设备会上报 100~200 个字段，其中绝大多数是 `fault.F123` / `cl_Error_x`
  这类**故障位**（正常时全是 "--"）。给它们逐个建实体会把 UI 淹没，
  因此故障位统一由 `FaultSensor` 汇总（只报第一个非 "--" 的故障码）。
- 其余有意义的字段按「数值 / 开关 / 枚举」三类各建一个实体，这是与 App 功能对齐的主体。
- 新增设备只要往表里加一行即可，不需要改平台代码。
"""

from __future__ import annotations

from typing import Any

from .programs import PROGRAM_OPTIONS

# kind: num = 数值传感器, bool = 开关型二进制传感器, val = 枚举/原始值传感器
# 云端 label `clothing_material_time` 原样给出「衣物材质编号 → 默认烘干分钟数」：
#   "0:15,1:20,2:20,3:30,4:30,6:10,8:40,9:30,10:30,11:20,12:25,13:20,15:25,16:40,17:30"
# 它同时说明**本机支持的材质编号**（0-17 中除 5、7、14 之外）。
MATERIAL_DEFAULT_MINUTES: dict[str, int] = {
    "0": 15, "1": 20, "2": 20, "3": 30, "4": 30, "6": 10, "8": 40, "9": 30,
    "10": 30, "11": 20, "12": 25, "13": 20, "15": 25, "16": 40, "17": 30,
}

FIELDS: dict[str, list[dict[str, Any]]] = {
    "洗衣机": [
        # ---- 进度 ----
        {"key": "remainRunTime", "name": "剩余时间", "kind": "num", "unit": "min", "dc": "duration", "sc": "measurement"},
        {"key": "totalRunTime", "name": "总时长", "kind": "num", "unit": "min", "dc": "duration", "sc": "measurement"},
        {"key": "washTime", "name": "洗涤时间", "kind": "num", "unit": "min", "dc": "duration", "sc": "measurement"},
        {"key": "remainWashTime", "name": "剩余洗涤时间", "kind": "num", "unit": "min", "dc": "duration", "sc": "measurement"},
        {"key": "remainSpinTime", "name": "剩余脱水时间", "kind": "num", "unit": "min", "dc": "duration", "sc": "measurement"},
        {"key": "orderTime.Minute", "name": "预约时间", "kind": "num", "unit": "min", "dc": "duration", "sc": "measurement"},
        {"key": "workMode", "name": "洗涤程序", "kind": "val"},
        {"key": "runStatus", "name": "运行状态", "kind": "val"},
        {"key": "startPauseStatus", "name": "启停状态", "kind": "val"},
        # ---- 可设参数 ----
        {"key": "washTemperature", "name": "洗涤温度", "kind": "num", "unit": "°C", "dc": "temperature"},
        {"key": "dehydrationSpeed", "name": "脱水转速", "kind": "num", "unit": "rpm", "icon": "mdi:speedometer"},
        {"key": "rotarySpeed", "name": "当前转速", "kind": "num", "unit": "rpm", "icon": "mdi:speedometer"},
        {"key": "rinsingFrequency", "name": "漂洗次数", "kind": "num", "unit": "次", "icon": "mdi:water-sync"},
        {"key": "remainRinsingFrequency", "name": "剩余漂洗次数", "kind": "val"},
        {"key": "waterLevel", "name": "水位档位", "kind": "num", "unit": "档", "icon": "mdi:waves"},
        {"key": "addRinse", "name": "追加漂洗", "kind": "num", "unit": "次", "icon": "mdi:water-plus"},
        # ---- 能耗 ----
        {"key": "powerConsumption", "name": "耗电量", "kind": "num", "unit": "kWh", "dc": "energy", "sc": "measurement"},
        {"key": "waterConsumption", "name": "耗水量", "kind": "num", "unit": "L", "dc": "water", "sc": "measurement"},
        {"key": "sterilizationRate", "name": "除菌率", "kind": "num", "unit": "%", "icon": "mdi:shield-check", "sc": "measurement"},
        {"key": "removeMitesRate", "name": "除螨率", "kind": "num", "unit": "%", "icon": "mdi:bug-outline", "sc": "measurement"},
        # ---- 开关 ----
        {"key": "powerStatus", "name": "电源", "kind": "bool", "icon": "mdi:power"},
        {"key": "childLock", "name": "童锁", "kind": "bool", "icon": "mdi:lock"},
        {"key": "aiAdaption", "name": "AI智洗", "kind": "bool", "icon": "mdi:auto-fix"},
        {"key": "uvDegermingSwitch", "name": "UV除菌", "kind": "bool", "icon": "mdi:lightbulb-on-outline"},
        {"key": "sterilizationOn", "name": "高温除菌", "kind": "bool", "icon": "mdi:thermometer-plus"},
        {"key": "removeMitesOn", "name": "除螨", "kind": "bool", "icon": "mdi:bug-outline"},
        {"key": "airingSwitch", "name": "新风净味", "kind": "bool", "icon": "mdi:weather-windy"},
        {"key": "washDryLinkSwitch", "name": "洗烘联动", "kind": "bool", "icon": "mdi:link-variant"},
        {"key": "antiWrinkleAdjust", "name": "防皱", "kind": "bool", "icon": "mdi:iron-outline"},
        {"key": "detergentLackStatus", "name": "洗涤剂不足", "kind": "bool", "icon": "mdi:cup-off"},
        {"key": "remoteControlFlag", "name": "远程控制已开启", "kind": "bool", "icon": "mdi:remote"},
        # ---- 原始值（含义与档位表相关，先原样透出）----
        {"key": "doorStatus", "name": "机门状态", "kind": "val"},
        {"key": "doorLockStatus", "name": "门锁状态", "kind": "val"},
        {"key": "detergentMode", "name": "投放模式", "kind": "val"},
        {"key": "detergentDosage", "name": "投放量", "kind": "val"},
        {"key": "aiAdaptionCloud", "name": "云端AI智洗", "kind": "val"},
        {"key": "selfProgramIndex", "name": "自定义程序位", "kind": "val"},
        {"key": "onekeySmartWashIndex", "name": "一键智洗位", "kind": "val"},
    ],
    "干衣机": [
        # ---- 进度 ----
        {"key": "remainRunTime", "name": "剩余时间", "kind": "num", "unit": "min", "dc": "duration", "sc": "measurement"},
        {"key": "totalRunTime", "name": "总时长", "kind": "num", "unit": "min", "dc": "duration", "sc": "measurement"},
        {"key": "drySetTime", "name": "设定烘干时间", "kind": "num", "unit": "min", "dc": "duration", "sc": "measurement"},
        {"key": "remainOrderTime", "name": "预约剩余", "kind": "num", "unit": "min", "dc": "duration", "sc": "measurement"},
        {"key": "orderTime", "name": "预约时间", "kind": "num", "unit": "min", "dc": "duration", "sc": "measurement"},
        {"key": "runStatus", "name": "运行状态", "kind": "val"},
        {"key": "startPauseStatus", "name": "启停状态", "kind": "val"},
        {"key": "preHeatStatus", "name": "预热中", "kind": "bool", "icon": "mdi:fire"},
        # ---- 烘干参数（本机无对应可写命令，只读）----
        # dryingMethod 实测与 drySetTime 同源：有值=定时烘干该分钟数，"--"=该程序不做定时（自动判干）
        {"key": "dryingMethod", "name": "烘干方式", "kind": "val", "icon": "mdi:weather-windy",
         "values": {"--": "自动判干", "": "自动判干"}, "format_num": "定时 {v} 分钟"},
        {"key": "dryTemperature", "name": "烘干温度档", "kind": "val",
         "values": {}, "format_num": "档位 {v}"},
        {"key": "dryLevel", "name": "烘干程度档", "kind": "val",
         "values": {}, "format_num": "档位 {v}"},
        {"key": "clotheMaterial", "name": "衣物材质", "kind": "val",
         "values": {k: f"材质{k}（默认{v}分钟）" for k, v in MATERIAL_DEFAULT_MINUTES.items()},
         "format_num": "材质 {v}"},
        # ---- 能耗 / 效果 ----
        {"key": "powerConsumption", "name": "耗电量", "kind": "num", "unit": "kWh", "dc": "energy", "sc": "measurement"},
        {"key": "waterRate", "name": "含水率", "kind": "num", "icon": "mdi:water-percent", "sc": "measurement"},
        {"key": "sterilizationRate", "name": "除菌率", "kind": "num", "unit": "%", "icon": "mdi:shield-check", "sc": "measurement"},
        {"key": "removeMitesRate", "name": "除螨率", "kind": "num", "unit": "%", "icon": "mdi:bug-outline", "sc": "measurement"},
        # ---- 开关 ----
        {"key": "powerStatus", "name": "电源", "kind": "bool", "icon": "mdi:power"},
        {"key": "childLock", "name": "童锁", "kind": "bool", "icon": "mdi:lock"},
        {"key": "childLockSettingStatus", "name": "童锁设置中", "kind": "bool", "icon": "mdi:lock-clock"},
        {"key": "antiWrinkleSwitch", "name": "防皱", "kind": "bool", "icon": "mdi:iron-outline"},
        {"key": "antiWrinkle", "name": "防皱进行中", "kind": "bool", "icon": "mdi:iron"},
        {"key": "uvDegermingSwitch", "name": "UV除菌", "kind": "bool", "icon": "mdi:lightbulb-on-outline"},
        {"key": "sterilizationOn", "name": "高温除菌", "kind": "bool", "icon": "mdi:thermometer-plus"},
        {"key": "removeMitesOn", "name": "除螨", "kind": "bool", "icon": "mdi:bug-outline"},
        {"key": "steamUnwaterAlarm", "name": "蒸汽缺水报警", "kind": "bool", "icon": "mdi:water-alert"},
        {"key": "dryingBracketDisplay", "name": "烘干支架提示", "kind": "bool", "icon": "mdi:propane-tank-outline"},
        {"key": "aiAdaption", "name": "AI智烘", "kind": "bool", "icon": "mdi:auto-fix"},
        {"key": "doorStatus", "name": "机门状态", "kind": "val"},
        {"key": "doorLockStatus", "name": "门锁状态", "kind": "val"},
    ],
    # 未知品类：只给最小通用集，保证"识别不了也不会一片空白"
    "其他": [
        {"key": "powerStatus", "name": "电源", "kind": "bool", "icon": "mdi:power"},
        {"key": "onlineStatus", "name": "在线状态", "kind": "val"},
    ],
}

# 注：故障位前缀定义在 const.py 的 FAULT_PREFIXES（供 sensor.py 使用）


# ============================================================================
# 可控项（全部经真机验证：命令名 + 参数名 + 生效条件）
# ----------------------------------------------------------------------------
# 命名规律：connector.device.command.Set<字段名驼峰>，params = {<字段名>: {"value": n}}
# 生效条件：**机器必须处于开机态**，关机态会返回 conflictCommand / errorcode=7
# 已确认不可用（返回 notSupported，勿再尝试）：
#   SetWorkMode / SetModes / SetProgram / SetWashProgram / SetUvDegermingSwitch /
#   SetUVDegermingSwitch / SetSterilizationOn / SetAiringSwitch / SetAiring /
#   SetFreshAirSwitch / SetDrySetTime / SetDryTemperature / SetDryLevel /
#   SetAntiWrinkleSwitch / SetAiAdaption / SetWashDryLinkSwitch / SetSelfProgramIndex
#   → 这些功能 App 很可能走 label/batchSave 通道，而非 command
# ============================================================================
CONTROLS: dict[str, dict[str, list[dict[str, Any]]]] = {
    "洗衣机": {
        "numbers": [
            {"key": "washTemperature", "name": "洗涤温度", "cmd": "SetWashTemperature",
             "min": 0, "max": 95, "step": 5, "unit": "°C", "icon": "mdi:thermometer"},
            {"key": "rinsingFrequency", "name": "漂洗次数", "cmd": "SetRinsingFrequency",
             "min": 1, "max": 5, "step": 1, "unit": "次", "icon": "mdi:water-sync"},
            {"key": "dehydrationSpeed", "name": "脱水转速", "cmd": "SetDehydrationSpeed",
             "min": 0, "max": 1400, "step": 100, "unit": "rpm", "icon": "mdi:speedometer"},
            {"key": "waterLevel", "name": "水位档位", "cmd": "SetWaterLevel",
             "min": 1, "max": 5, "step": 1, "unit": "档", "icon": "mdi:waves"},
            {"key": "washTime", "name": "洗涤时间", "cmd": "SetWashTime",
             "min": 1, "max": 120, "step": 1, "unit": "min", "dc": "duration", "icon": "mdi:timer-outline"},
            {"key": "orderTime.Minute", "param": "orderTime", "name": "预约时间",
             "cmd": "SetOrderTime", "min": 0, "max": 1440, "step": 1, "unit": "min",
             "dc": "duration", "icon": "mdi:clock-outline"},
            {"key": "detergentMode", "name": "投放模式", "cmd": "SetDetergentMode",
             "min": 0, "max": 5, "step": 1, "icon": "mdi:cup-water"},
        ],
        "selects": [
            {"key": "workMode", "name": "洗涤程序", "cmd": "SetModes", "param": "modes",
             "icon": "mdi:washing-machine", "options": PROGRAM_OPTIONS["洗衣机"]},
        ],
        "switches": [
            {"key": "powerStatus", "name": "电源", "power": True, "icon": "mdi:power"},
            {"key": "smartNightWashSwitch", "name": "夜间洗", "cmd": "SetSmartNightWashSwitch",
             "icon": "mdi:weather-night"},
        ],
        "buttons": [
            {"name": "启动", "cmd": "Start", "params": {"startStop": {"value": 1}}, "icon": "mdi:play"},
            {"name": "暂停", "cmd": "Pause", "params": {"startStop": {"value": 0}}, "icon": "mdi:pause"},
            {"name": "开启远程控制", "cmd": "SetRemoteControlFlag",
             "params": {"remoteControlFlag": {"value": 1}}, "icon": "mdi:remote"},
        ],
    },
    "干衣机": {
        "numbers": [
            {"key": "orderTime", "name": "预约时间", "cmd": "SetOrderTime",
             "min": 0, "max": 1440, "step": 1, "unit": "min", "dc": "duration", "icon": "mdi:clock-outline"},
            # 注：SetClotheMaterial 虽然返回 SUCCESS，但**实测不改变设备状态**（回读仍是 0），
            # 因此不提供可写实体，只保留只读的「衣物材质」传感器。
        ],
        "selects": [
            {"key": "workMode", "name": "烘干程序", "cmd": "SetModes", "param": "modes",
             "icon": "mdi:tumble-dryer", "options": PROGRAM_OPTIONS["干衣机"]},
        ],
        "switches": [
            {"key": "powerStatus", "name": "电源", "power": True, "icon": "mdi:power"},
            {"key": "childLock", "name": "童锁", "cmd": "SetChildLock", "icon": "mdi:lock"},
        ],
        "buttons": [
            {"name": "启动", "cmd": "Start", "params": {"startStop": {"value": 1}}, "icon": "mdi:play"},
            {"name": "暂停", "cmd": "Pause", "params": {"startStop": {"value": 0}}, "icon": "mdi:pause"},
            {"name": "开启远程控制", "cmd": "SetRemoteControlFlag",
             "params": {"remoteControlFlag": {"value": 1}}, "icon": "mdi:remote"},
        ],
    },
}


# 枚举值→中文名映射。同样是"服务端不给名字"的部分：
# 在 App 里看到对应档位的实际叫法后，填到这里即可（例如 干衣机.dryTemperature → {0:"冷风",1:"低温",2:"中温",3:"高温"}）。
# 键为「品类 → states 字段名 → {原始值: 显示名}」。
VALUE_LABELS: dict[str, dict[str, dict[str, str]]] = {
    "洗衣机": {},
    "干衣机": {
        "dryTemperature": {},
        "dryLevel": {},
        "clotheMaterial": {},
    },
}
