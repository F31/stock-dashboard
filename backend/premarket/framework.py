"""
AI产业链分析框架定义与加载。

框架拆分为三个独立 JSON 结构，存储在 analysis_framework 表：
  layer_definition  — 层/列的元数据（ID、名称、类型、瓶颈标记、描述）
  keyword_dict      — 各层/列的关键词词典（中英文）
  entity_matrix     — 公司-矩阵位置映射（别名、所属层、所属列）

运行时由 get_framework() 组装为 build_patterns() 可用的统一结构。
若数据库无记录则使用内置默认值。
"""
import json
import logging
import re

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# §1  层级定义（layer_definition.json）
#     type="layer"  → 纵向8层
#     type="column" → 横向3列
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_LAYER_DEFINITION: list[dict] = [
    # ── 纵向 8 层 ──────────────────────────────────────────────────────────
    {"id": "L1", "type": "layer", "name": "L1·能源",      "physical_bottleneck": True,  "description": "数据中心耗电、电网、核电、动力电池"},
    {"id": "L2", "type": "layer", "name": "L2·制造",      "physical_bottleneck": True,  "description": "先进制程（5nm以下垄断）"},
    {"id": "L3", "type": "layer", "name": "L3·存储",      "physical_bottleneck": True,  "description": "HBM（SK Hynix/Samsung/Micron三家垄断）"},
    {"id": "L4", "type": "layer", "name": "L4·芯片+互联", "physical_bottleneck": False, "description": "GPU/NPU/NVLink/光模块"},
    {"id": "L5", "type": "layer", "name": "L5·算力服务",  "physical_bottleneck": False, "description": "Cloud/NeoCloud/边缘+仿真"},
    {"id": "L6", "type": "layer", "name": "L6·数据",      "physical_bottleneck": False, "description": "符号数据+具身数据"},
    {"id": "L7", "type": "layer", "name": "L7·模型+编排", "physical_bottleneck": False, "description": "Foundation Model/端侧小模型/VLA"},
    {"id": "L8", "type": "layer", "name": "L8·应用+执行", "physical_bottleneck": False, "description": "Agent/Actuation/机器人"},
    # ── 横向 3 列 ──────────────────────────────────────────────────────────
    {"id": "cloud",       "type": "column", "name": "云侧",   "physical_bottleneck": False, "description": "大规模云端训练和推理"},
    {"id": "edge",        "type": "column", "name": "端侧",   "physical_bottleneck": False, "description": "端侧推理、移动设备、边缘计算"},
    {"id": "physical_ai", "type": "column", "name": "物理AI", "physical_bottleneck": False, "description": "机器人、自动驾驶、具身智能等物理世界应用"},
]


# ══════════════════════════════════════════════════════════════════════════════
# §2  关键词词典（keyword_dict.json）
#     Key = layer/column ID；Value = 关键词列表（中英文）
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_KEYWORD_DICT: dict[str, list[str]] = {
    # ── L1 能源 ──────────────────────────────────────────────────────────────
    "L1": [
        "数据中心耗电", "电力需求", "用电量", "电力消耗", "能源消耗",
        "电网", "电力基础设施", "输电", "变电站", "配电",
        "核电", "核能", "小型核反应堆", "SMR", "NuScale", "核聚变", "托卡马克",
        "AI耗电", "算力耗电", "绿色能源", "可再生能源", "新能源",
        "储能", "动力电池", "UPS", "不间断电源", "PDU",
        "PUE", "WUE", "能效", "购电协议", "PPA", "虚拟电厂",
    ],
    # ── L2 制造 ──────────────────────────────────────────────────────────────
    "L2": [
        "先进制程", "5nm", "3nm", "2nm", "1.4nm", "1nm", "埃米制程",
        "台积电", "TSMC", "三星代工", "Samsung Foundry",
        "英特尔代工", "Intel Foundry", "英特尔晶圆",
        "晶圆代工", "半导体制造", "晶圆厂",
        "EUV", "极紫外", "ASML", "光刻机", "光刻",
        "光刻胶", "CVD", "ALD", "原子层沉积", "蚀刻", "CMP", "化学机械抛光",
        "先进封装", "CoWoS", "SoIC", "Chiplet", "chiplet",
        "北方华创", "中微公司", "拓荆科技", "华海清科",
    ],
    # ── L3 存储 ──────────────────────────────────────────────────────────────
    "L3": [
        "HBM", "HBM2e", "HBM3", "HBM3E", "HBM4", "高带宽内存", "存储带宽",
        "SK海力士", "SK Hynix", "三星存储", "Samsung Memory", "美光", "Micron",
        "存储垄断", "内存带宽", "内存墙",
        "DRAM", "LPDDR", "DDR5", "DDR6", "CXL", "GDDR7",
        "长鑫存储", "CXMT", "长江存储", "YMTC",
        "NAND", "3D NAND", "闪存", "存储芯片",
    ],
    # ── L4 芯片+互联 ─────────────────────────────────────────────────────────
    "L4": [
        "GPU", "NPU", "TPU", "ASIC", "AI芯片", "推理芯片", "训练芯片",
        "英伟达", "NVIDIA", "Blackwell", "Hopper", "H100", "H200", "B200", "GB200", "B300",
        "AMD", "MI300", "MI350", "MI400", "Instinct",
        "博通", "Broadcom", "ASIC定制",
        "高通", "Qualcomm", "Marvell",
        "NVLink", "NVSwitch", "集群互联", "互联带宽",
        "InfiniBand", "RoCE", "400G以太网",
        "光模块", "800G", "1.6T", "400G", "CPO", "硅光", "AOC",
        "剑桥科技", "中际旭创", "新易盛", "天孚通信", "光迅科技",
        "寒武纪", "海光信息", "龙芯中科", "澜起科技",
    ],
    # ── L5 算力服务 ──────────────────────────────────────────────────────────
    "L5": [
        "云计算", "云服务", "IaaS", "PaaS", "算力服务",
        "AWS", "Azure", "Google Cloud", "阿里云", "华为云", "腾讯云",
        "NeoCloud", "CoreWeave", "Lambda Labs", "Together AI",
        "算力集群", "GPU集群", "万卡集群", "万卡训练", "千卡",
        "边缘计算", "边缘推理", "边缘服务器",
        "仿真", "数字孪生", "Omniverse", "Isaac",
        "AI推理服务", "模型托管", "Inference API",
    ],
    # ── L6 数据 ──────────────────────────────────────────────────────────────
    "L6": [
        "数据集", "dataset", "训练数据", "数据质量", "数据工程",
        "符号数据", "合成数据", "synthetic data", "数据合成",
        "具身数据", "机器人数据", "运动轨迹数据", "遥操作数据",
        "数据标注", "数据清洗", "RLHF", "RLAIF", "DPO", "PPO",
        "版权数据", "数据授权", "数据许可", "数据爬取",
        "数据飞轮", "世界模型数据", "多模态数据", "视频数据",
    ],
    # ── L7 模型+编排 ─────────────────────────────────────────────────────────
    "L7": [
        "基础模型", "Foundation Model", "大模型", "LLM", "AGI", "多模态",
        "VLA", "视觉语言动作模型", "视觉语言模型", "VLM",
        "GPT-4", "GPT-5", "o1", "o3", "o4",
        "Claude", "Gemini", "Llama", "Llama3", "Llama4",
        "DeepSeek", "DeepSeek-V3", "DeepSeek-R1",
        "通义千问", "Qwen", "文心", "文心一言", "混元", "Kimi", "Grok",
        "端侧模型", "端侧大模型", "SLM", "小语言模型", "Phi", "Gemma",
        "端侧推理", "量化推理", "模型蒸馏", "知识蒸馏",
        "MoE", "稀疏模型", "专家混合", "上下文长度",
        "Agent框架", "MCP", "LangChain", "LlamaIndex", "AutoGen", "Dify",
        "OpenAI", "Anthropic", "Google DeepMind", "Meta AI", "xAI",
        "百川智能", "智谱AI", "零一万物", "月之暗面",
    ],
    # ── L8 应用+执行 ─────────────────────────────────────────────────────────
    "L8": [
        "AI Agent", "Agentic", "Multi-Agent", "自主Agent",
        "Copilot", "AI助手", "AIGC", "AI应用", "垂直应用",
        "具身智能", "人形机器人", "机器人", "Humanoid", "双足机器人",
        "宇树科技", "智元机器人", "傅利叶机器人", "特斯拉Optimus",
        "自动驾驶", "无人驾驶", "智能驾驶", "Waymo",
        "工业自动化", "工业机器人", "协作机器人", "AMR", "AGV",
        "Actuation", "执行器", "电机控制", "灵巧手", "灵巧操作",
        "AI医疗", "AI教育", "AI金融", "AI安防", "AI制造",
        "AI编程", "代码生成", "Cursor", "GitHub Copilot", "Devin",
        "科大讯飞", "商汤科技", "旷视科技",
    ],
    # ── 云侧列 ────────────────────────────────────────────────────────────────
    "cloud": [
        "数据中心", "云计算", "云服务", "大规模训练", "预训练",
        "万卡", "GPU集群", "算力集群", "云端推理", "AI云",
        "AWS", "Azure", "Google Cloud", "阿里云", "华为云", "腾讯云",
        "NeoCloud", "CoreWeave",
    ],
    # ── 端侧列 ────────────────────────────────────────────────────────────────
    "edge": [
        "端侧", "边缘", "移动端", "手机AI", "手机大模型",
        "端侧推理", "端侧部署", "端侧模型", "端侧智能",
        "SLM", "小模型", "轻量化", "量化", "剪枝",
        "NPU手机", "手机芯片", "高通骁龙", "联发科天玑",
        "可穿戴", "IoT", "嵌入式AI", "MCU",
    ],
    # ── 物理AI列 ──────────────────────────────────────────────────────────────
    "physical_ai": [
        "机器人", "人形机器人", "具身智能", "机器人控制", "物理AI",
        "自动驾驶", "无人驾驶", "智能驾驶",
        "工业自动化", "工业机器人", "协作机器人",
        "Actuation", "执行器", "灵巧手", "VLA",
        "Physical AI", "物理世界", "现实世界AI",
    ],
}


# ══════════════════════════════════════════════════════════════════════════════
# §3  公司-矩阵映射表（entity_matrix.json）
#     每条记录: name, symbol, market, aliases, layers, columns
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_ENTITY_MATRIX: list[dict] = [
    # ── 能源层 (L1) ───────────────────────────────────────────────────────────
    {"name": "NuScale",   "symbol": "SMR",   "market": "US", "aliases": ["NuScale"],                            "layers": ["L1"],       "columns": ["cloud"]},
    # ── 制造层 (L2) ───────────────────────────────────────────────────────────
    {"name": "台积电",    "symbol": "TSM",   "market": "US", "aliases": ["台积电", "TSMC"],                    "layers": ["L2"],       "columns": ["cloud"]},
    {"name": "ASML",      "symbol": "ASML",  "market": "US", "aliases": ["ASML"],                              "layers": ["L2"],       "columns": ["cloud"]},
    {"name": "英特尔",    "symbol": "INTC",  "market": "US", "aliases": ["英特尔", "Intel"],                   "layers": ["L2", "L4"], "columns": ["cloud", "edge"]},
    {"name": "北方华创",  "symbol": "002371","market": "A",  "aliases": ["北方华创"],                          "layers": ["L2"],       "columns": ["cloud"]},
    {"name": "中微公司",  "symbol": "688012","market": "A",  "aliases": ["中微公司"],                          "layers": ["L2"],       "columns": ["cloud"]},
    {"name": "拓荆科技",  "symbol": "688072","market": "A",  "aliases": ["拓荆科技"],                          "layers": ["L2"],       "columns": ["cloud"]},
    {"name": "华海清科",  "symbol": "688120","market": "A",  "aliases": ["华海清科"],                          "layers": ["L2"],       "columns": ["cloud"]},
    # ── 存储层 (L3) ───────────────────────────────────────────────────────────
    {"name": "美光",      "symbol": "MU",    "market": "US", "aliases": ["美光", "Micron"],                    "layers": ["L3"],       "columns": ["cloud"]},
    {"name": "SK海力士",  "symbol": None,    "market": None, "aliases": ["SK海力士", "SK Hynix"],              "layers": ["L3"],       "columns": ["cloud"]},
    {"name": "三星",      "symbol": None,    "market": None, "aliases": ["三星存储", "Samsung Memory"],        "layers": ["L3"],       "columns": ["cloud"]},
    {"name": "西部数据",  "symbol": "WDC",   "market": "US", "aliases": ["西部数据", "Western Digital"],       "layers": ["L3"],       "columns": ["cloud"]},
    {"name": "希捷",      "symbol": "STX",   "market": "US", "aliases": ["希捷", "Seagate"],                   "layers": ["L3"],       "columns": ["cloud"]},
    {"name": "长鑫存储",  "symbol": None,    "market": None, "aliases": ["长鑫存储", "CXMT"],                  "layers": ["L3"],       "columns": ["cloud"]},
    {"name": "长江存储",  "symbol": None,    "market": None, "aliases": ["长江存储", "YMTC"],                  "layers": ["L3"],       "columns": ["cloud"]},
    # ── 芯片+互联层 (L4) ──────────────────────────────────────────────────────
    {"name": "英伟达",    "symbol": "NVDA",  "market": "US", "aliases": ["英伟达", "NVIDIA", "Nvidia"],        "layers": ["L4"],       "columns": ["cloud", "physical_ai"]},
    {"name": "AMD",       "symbol": "AMD",   "market": "US", "aliases": ["AMD", "Advanced Micro Devices"],     "layers": ["L4"],       "columns": ["cloud", "edge"]},
    {"name": "博通",      "symbol": "AVGO",  "market": "US", "aliases": ["博通", "Broadcom"],                  "layers": ["L4"],       "columns": ["cloud"]},
    {"name": "高通",      "symbol": "QCOM",  "market": "US", "aliases": ["高通", "Qualcomm"],                  "layers": ["L4"],       "columns": ["edge"]},
    {"name": "ARM",       "symbol": "ARM",   "market": "US", "aliases": ["ARM", "安谋"],                       "layers": ["L4"],       "columns": ["cloud", "edge", "physical_ai"]},
    {"name": "Marvell",   "symbol": "MRVL",  "market": "US", "aliases": ["Marvell", "美满"],                   "layers": ["L4"],       "columns": ["cloud"]},
    {"name": "Arista",    "symbol": "ANET",  "market": "US", "aliases": ["Arista"],                            "layers": ["L4"],       "columns": ["cloud"]},
    {"name": "思科",      "symbol": "CSCO",  "market": "US", "aliases": ["思科", "Cisco"],                     "layers": ["L4"],       "columns": ["cloud", "edge"]},
    {"name": "寒武纪",    "symbol": "688256","market": "A",  "aliases": ["寒武纪"],                            "layers": ["L4"],       "columns": ["cloud"]},
    {"name": "海光信息",  "symbol": "688041","market": "A",  "aliases": ["海光信息", "海光"],                  "layers": ["L4"],       "columns": ["cloud"]},
    {"name": "龙芯中科",  "symbol": "688047","market": "A",  "aliases": ["龙芯中科", "龙芯"],                  "layers": ["L4"],       "columns": ["cloud", "edge"]},
    {"name": "澜起科技",  "symbol": "688008","market": "A",  "aliases": ["澜起科技", "澜起"],                  "layers": ["L4"],       "columns": ["cloud"]},
    {"name": "中际旭创",  "symbol": "300308","market": "A",  "aliases": ["中际旭创"],                          "layers": ["L4"],       "columns": ["cloud"]},
    {"name": "新易盛",    "symbol": "300502","market": "A",  "aliases": ["新易盛"],                            "layers": ["L4"],       "columns": ["cloud"]},
    {"name": "天孚通信",  "symbol": "300394","market": "A",  "aliases": ["天孚通信"],                          "layers": ["L4"],       "columns": ["cloud"]},
    {"name": "光迅科技",  "symbol": "002281","market": "A",  "aliases": ["光迅科技"],                          "layers": ["L4"],       "columns": ["cloud"]},
    {"name": "剑桥科技",  "symbol": "603083","market": "A",  "aliases": ["剑桥科技"],                          "layers": ["L4"],       "columns": ["cloud"]},
    {"name": "兆易创新",  "symbol": "603986","market": "A",  "aliases": ["兆易创新"],                          "layers": ["L4"],       "columns": ["edge"]},
    # ── 算力服务层 (L5) ───────────────────────────────────────────────────────
    {"name": "超微",      "symbol": "SMCI",  "market": "US", "aliases": ["超微", "Super Micro", "SMCI"],       "layers": ["L5"],       "columns": ["cloud"]},
    {"name": "Dell",      "symbol": "DELL",  "market": "US", "aliases": ["Dell"],                              "layers": ["L5"],       "columns": ["cloud"]},
    {"name": "亚马逊",    "symbol": "AMZN",  "market": "US", "aliases": ["亚马逊", "Amazon", "AWS"],           "layers": ["L5"],       "columns": ["cloud"]},
    {"name": "甲骨文",    "symbol": "ORCL",  "market": "US", "aliases": ["甲骨文", "Oracle"],                  "layers": ["L5"],       "columns": ["cloud"]},
    {"name": "CoreWeave", "symbol": None,    "market": None, "aliases": ["CoreWeave"],                         "layers": ["L5"],       "columns": ["cloud"]},
    # ── 数据层 (L6) ───────────────────────────────────────────────────────────
    {"name": "Snowflake", "symbol": "SNOW",  "market": "US", "aliases": ["Snowflake"],                         "layers": ["L6"],       "columns": ["cloud"]},
    # ── 模型+编排层 (L7) ──────────────────────────────────────────────────────
    {"name": "微软",      "symbol": "MSFT",  "market": "US", "aliases": ["微软", "Microsoft"],                 "layers": ["L5", "L7"], "columns": ["cloud", "edge"]},
    {"name": "谷歌",      "symbol": "GOOGL", "market": "US", "aliases": ["谷歌", "Google", "Alphabet"],        "layers": ["L5", "L7"], "columns": ["cloud", "edge"]},
    {"name": "Meta",      "symbol": "META",  "market": "US", "aliases": ["Meta", "Facebook"],                  "layers": ["L7"],       "columns": ["cloud", "edge"]},
    {"name": "OpenAI",    "symbol": None,    "market": None, "aliases": ["OpenAI"],                            "layers": ["L7"],       "columns": ["cloud"]},
    {"name": "Anthropic", "symbol": None,    "market": None, "aliases": ["Anthropic"],                         "layers": ["L7"],       "columns": ["cloud"]},
    {"name": "DeepSeek",  "symbol": None,    "market": None, "aliases": ["DeepSeek", "深度求索"],              "layers": ["L7"],       "columns": ["cloud", "edge"]},
    {"name": "Mistral",   "symbol": None,    "market": None, "aliases": ["Mistral"],                           "layers": ["L7"],       "columns": ["cloud", "edge"]},
    {"name": "xAI",       "symbol": None,    "market": None, "aliases": ["xAI"],                               "layers": ["L7"],       "columns": ["cloud"]},
    {"name": "百度",      "symbol": "BIDU",  "market": "US", "aliases": ["百度", "Baidu"],                     "layers": ["L7"],       "columns": ["cloud", "physical_ai"]},
    {"name": "科大讯飞",  "symbol": "002230","market": "A",  "aliases": ["科大讯飞", "讯飞"],                  "layers": ["L7", "L8"], "columns": ["cloud", "edge"]},
    {"name": "华为",      "symbol": None,    "market": None, "aliases": ["华为"],                              "layers": ["L4", "L7"], "columns": ["cloud", "edge"]},
    # ── 应用+执行层 (L8) ──────────────────────────────────────────────────────
    {"name": "苹果",      "symbol": "AAPL",  "market": "US", "aliases": ["苹果", "Apple"],                     "layers": ["L7", "L8"], "columns": ["edge"]},
    {"name": "特斯拉",    "symbol": "TSLA",  "market": "US", "aliases": ["特斯拉", "Tesla"],                   "layers": ["L8"],       "columns": ["physical_ai"]},
    {"name": "Salesforce","symbol": "CRM",   "market": "US", "aliases": ["Salesforce"],                        "layers": ["L8"],       "columns": ["cloud"]},
    {"name": "Palantir",  "symbol": "PLTR",  "market": "US", "aliases": ["Palantir"],                          "layers": ["L8"],       "columns": ["cloud"]},
    {"name": "商汤科技",  "symbol": "0020",  "market": "HK", "aliases": ["商汤科技", "商汤"],                  "layers": ["L7", "L8"], "columns": ["cloud", "physical_ai"]},
]


# ══════════════════════════════════════════════════════════════════════════════
# §4  默认框架（由上面三个数据结构组装，保持与 build_patterns() 兼容）
# ══════════════════════════════════════════════════════════════════════════════

def _assemble_framework(name: str, description: str,
                        layer_def: list[dict],
                        kw_dict: dict[str, list[str]],
                        entity_matrix: list[dict]) -> dict:
    """将三个 JSON 结构组装为 build_patterns() 可用的统一字典。"""
    layers = [
        {**d, "keywords": kw_dict.get(d["id"], [])}
        for d in layer_def if d.get("type") == "layer"
    ]
    columns = [
        {**d, "keywords": kw_dict.get(d["id"], [])}
        for d in layer_def if d.get("type") == "column"
    ]
    return {
        "name": name,
        "description": description,
        "layers": layers,
        "columns": columns,
        "entity_matrix": entity_matrix,
    }


DEFAULT_FRAMEWORK: dict = _assemble_framework(
    name="AI投资8层框架",
    description="纵向8层（L1-L3为★物理瓶颈层）× 横向3列（云侧/端侧/物理AI）",
    layer_def=DEFAULT_LAYER_DEFINITION,
    kw_dict=DEFAULT_KEYWORD_DICT,
    entity_matrix=DEFAULT_ENTITY_MATRIX,
)


# ══════════════════════════════════════════════════════════════════════════════
# §5  层级→扁平化（供路由层保存时派生 layer_definition / entity_matrix）
# ══════════════════════════════════════════════════════════════════════════════

def framework_data_to_flat(framework_data: dict) -> tuple[list, list]:
    """
    将 WYSIWYG 层级结构（layers→sectors→companies）转为扁平存储结构。
    返回 (layer_definition, entity_matrix)。
    - layer_definition 包含派生出的层 + 固定的3列定义
    - entity_matrix 合并同名公司跨层 layers 字段
    """
    layer_def: list[dict] = []
    entity_dict: dict[str, dict] = {}

    for layer in framework_data.get("layers", []):
        layer_def.append({
            "id":                  layer["id"],
            "type":                "layer",
            "name":                layer["name"],
            "physical_bottleneck": layer.get("physical_bottleneck", False),
            "description":         layer.get("description", ""),
        })
        lid = layer["id"]
        for sector in layer.get("sectors", []):
            for co in sector.get("companies", []):
                name = co["name"]
                if name not in entity_dict:
                    entity_dict[name] = {
                        "name":    name,
                        "symbol":  co.get("symbol"),
                        "market":  co.get("market"),
                        "aliases": list(co.get("aliases") or [name]),
                        "layers":  [lid],
                        "columns": list(co.get("columns") or []),
                    }
                else:
                    if lid not in entity_dict[name]["layers"]:
                        entity_dict[name]["layers"].append(lid)

    # Append fixed column definitions (cloud / edge / physical_ai)
    for item in DEFAULT_LAYER_DEFINITION:
        if item.get("type") == "column":
            layer_def.append(item)

    return layer_def, list(entity_dict.values())


# ══════════════════════════════════════════════════════════════════════════════
# §6  框架加载（优先从数据库 is_active=1 的记录读取）
# ══════════════════════════════════════════════════════════════════════════════

def get_framework(db=None) -> dict:
    """
    加载当前活跃框架，返回 build_patterns() 可用的统一结构。
    优先顺序：DB framework_data → DB layer_definition → DEFAULT_FRAMEWORK。
    """
    try:
        if db is not None:
            from models import AnalysisFramework as AFM
            row = db.query(AFM).filter(AFM.is_active == 1).first()
        else:
            from database import SessionLocal
            from models import AnalysisFramework as AFM
            _db = SessionLocal()
            try:
                row = _db.query(AFM).filter(AFM.is_active == 1).first()
            finally:
                _db.close()

        if row:
            kw_dict = json.loads(row.keyword_dict or "{}")
            # Path 1: hierarchical framework_data (new WYSIWYG format)
            fd_raw = row.framework_data or "null"
            fd = json.loads(fd_raw)
            if fd and fd.get("layers"):
                layer_def, entity_matrix = framework_data_to_flat(fd)
                fw = _assemble_framework(row.name, row.description or "",
                                         layer_def, kw_dict, entity_matrix)
                logger.debug("Framework loaded from DB (framework_data): %s", fw["name"])
                return fw
            # Path 2: legacy 3-field flat structure
            layer_def     = json.loads(row.layer_definition or "[]")
            entity_matrix = json.loads(row.entity_matrix or "[]")
            if not layer_def:
                logger.warning("Active framework row has empty layer_definition, using default")
            else:
                fw = _assemble_framework(row.name, row.description or "",
                                         layer_def, kw_dict, entity_matrix)
                logger.debug("Framework loaded from DB (layer_definition): %s", fw["name"])
                return fw
    except Exception as e:
        logger.warning("Framework DB load failed (%s), using default", e)
    return DEFAULT_FRAMEWORK


# ══════════════════════════════════════════════════════════════════════════════
# §7  编译正则模式（供 cleaner 使用）
# ══════════════════════════════════════════════════════════════════════════════

def build_patterns(framework: dict) -> dict:
    """
    将框架定义编译为高效正则匹配结构。
    返回:
      {
        "layers":  {layer_id: {"meta": {...}, "pattern": <Pattern>}},
        "columns": {col_id:   {"meta": {...}, "pattern": <Pattern>}},
      }
    """
    def _compile(kwds: list[str]):
        if not kwds:
            return re.compile(r"(?!x)x")
        return re.compile(
            "|".join(re.escape(k) for k in sorted(kwds, key=len, reverse=True)),
            re.IGNORECASE,
        )

    layers: dict = {}
    for layer in framework.get("layers", []):
        lid = layer["id"]
        layers[lid] = {"meta": layer, "pattern": _compile(layer.get("keywords", []))}

    columns: dict = {}
    for col in framework.get("columns", []):
        cid = col["id"]
        columns[cid] = {"meta": col, "pattern": _compile(col.get("keywords", []))}

    return {"layers": layers, "columns": columns}
