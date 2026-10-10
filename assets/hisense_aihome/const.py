"""Constants for the Hisense AiHome (海信爱家) integration."""

DOMAIN = "hisense_aihome"
NAME = "海信爱家"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_HOME_ID = "home_id"
CONF_HOME_NAME = "home_name"
CONF_DEVICE_IDS = "device_ids"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 120

# --- endpoints -------------------------------------------------------------
PORTAL_SIGNON = "https://portal-account.hismarttv.com/mobile/se/signon"
WG_HOME_LIST = "https://api-wg.hismarttv.com/wg/dm/getHomeList"
AIHOME_BASE = "https://iot-aihome.hismarttv.com"
AIHOME_DEVICES = AIHOME_BASE + "/4.0/iot/devices/list"
AIHOME_DETAIL = AIHOME_BASE + "/4.0/iot/devices/detail"

PORTAL_APP_KEY = "commonweb"

# ---------------------------------------------------------------------------
# 下面两个常量是**海信官方 App 的客户端常量**，不是任何人的账号凭据：
#   · PORTAL_APP_SECRET：登录时用来派生 AES 密钥/IV，并参与请求签名
#   · AIHOME_SIGN_KEY  ：爱家接口的请求签名密钥
# 它们随 App 一起下发到每个客户端，任何人从 APK 里都能提取出来；
# 并且**早已公开存在于多个开源项目中**（例如 sfairy/ha_hisense 的 utils.py、
# manymuch/HisenseHA dev 分支的 pyhisenseapi.py），因此在本仓库中出现
# 并不会新增任何暴露面。详见仓库根目录的 SECURITY.md。
#
# 它们能做什么：让第三方客户端能构造合法请求 —— 这正是本项目的用途。
# 它们不能做什么：访问任何人的账号、冒充用户、读取用户数据（登录仍需用户密码，
# 且由服务端校验）；本仓库不含任何用户数据。
#
# 如果你不放心，或海信更新 App 导致常量失效：
#   1) 自行抓包 App 流量，替换下面的字符串即可（其余代码无需改动）；
#   2) 或者把这两行改成从环境变量读取，自行注入：
#        PORTAL_APP_SECRET = os.getenv("HISENSE_PORTAL_SECRET", "")
#      注意：这种情况下集成需要用户自己配置好环境变量才能用。
# ---------------------------------------------------------------------------
PORTAL_APP_SECRET = "MORZRbkuiWxjp+SM4vR_GxY4pZxLZ6rn"  # noqa: S105 (客户端常量，非用户凭据)
AIHOME_SIGN_KEY = "AOSj8JBr0IpUzv5w+hURR6W4oINsI4o5"    # noqa: S105 (同上)
AIHOME_APP_VERSION = "6.4.0.3"
# App 在列表请求里固定使用的占位 deviceId
AIHOME_PLACEHOLDER_DEVICE_ID = (
    "862fff02fffefff00000fffe53b30aa3fdb331c013166f31a6089802"
)
AIHOME_X_REAL_HOST = "220.243.140.228"
AIHOME_EXECUTE = AIHOME_BASE + "/4.0/iot/devices/execute"

# --- 控制命令（均为实机验证结果）-------------------------------------------
# 命令族：connector.device.command.<X>，参数为 {<字段名>: {"value": <数字>}}
# 电源是特例：connector.device.command.Power + {"onAndOff": {"code": "On"/"Off"}}
# 且 sourceName 需为 smartlifeApp
CONTROL_SOURCE_NAME = "smartlifeAppH5"
POWER_SOURCE_NAME = "smartlifeApp"
CMD_PREFIX = "connector.device.command."
CMD_POWER = CMD_PREFIX + "Power"

# --- 设备类型识别 ----------------------------------------------------------
# 顺序很重要：先匹配更具体的关键词，避免「洗衣机」被「干衣」规则误伤。
# 关键原则：**不做白名单丢弃** —— 无法识别的设备归类为「其他」并照常建实体，
# 这样上游集成丢弃的干衣机/新品类设备也不会消失。
DEVICE_TYPE_RULES: list[tuple[tuple[str, ...], str]] = [
    (("washer", "washing", "laundry", "洗衣", "洗烘一体"), "洗衣机"),
    (("dryer", "drying", "干衣", "烘干机", "干衣机"), "干衣机"),
    (("dishwasher", "洗碗"), "洗碗机"),
    (("refrigerat", "fridge", "冰箱"), "冰箱"),
    (("aircondition", "air_condition", "air conditioner", "空调"), "空调"),
    (("waterheater", "water_heater", "热水"), "热水器"),
    (("oven", "烤箱", "蒸箱"), "烤箱"),
]
UNKNOWN_DEVICE_TYPE = "其他"

# --- 状态字段映射（依据海信爱家 App 真实上报键名）-------------------------
# 实测样本：
#   洗衣机 WG100I5 → onlineStatus / powerStatus / orderTime.Minute / washTime /
#                    airingSwitch / uvDegermingSwitch / aiAdaption / fault.F5x
#   干衣机 DG100I5 → onlineStatus / powerStatus / startStop / drySetTime /
#                    dryingMethod / doorLockStatus / steamUnwaterAlarm / fault.0x1A-1F
# 原则：认得出来的就用，认不出来的一律原样塞进 attributes，信息不丢。
STATUS_KEYS_RUNNING = ("startStop", "runStatus", "workStatus", "runningStatus", "machineStatus")
STATUS_KEYS_REMAINING = (
    "orderTime.Minute", "remainingTime", "remainTime", "leftTime", "surplusTime",
    "dryRemainTime", "washRemainTime", "remainMinute",
)
STATUS_KEYS_PROGRAM = (
    "programName", "workModeName", "modeName", "program", "dryingMethod", "washProgram",
)
STATUS_KEYS_DOOR = ("doorLockStatus", "doorStatus")
STATUS_KEYS_ERROR = ("errorCode", "faultCode", "alarmCode")
STATUS_KEYS_POWER = ("powerStatus", "onAndOff", "powerOn", "switchStatus")

# 运行中判定：这些值视为「运行中」
RUNNING_TRUE_VALUES = {"1", "2", "3", "4", "5", "6", "7", "running", "true", "on", "work"}
POWERED_TRUE_VALUES = {"1", "true", "on"}

# 故障位前缀：这些字段数量极多（单台设备可达 190 个）且正常时全为 "--"，
# 因此不逐个建实体，统一由「故障」传感器汇总。
FAULT_PREFIXES = ("fault", "cl_Error")
