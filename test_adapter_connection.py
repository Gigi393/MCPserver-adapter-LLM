import sys
import json
import logging
from typing import Any, Dict

# 配置日志，方便调试
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [TEST] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==========================================
# 第一部分：模拟你的现有代码 (Your Context)
# 实际使用时，请 import 你的真实 Simulator 类
# ==========================================

class MockSimulator:
    """代表你现有的 Simulator"""
    def __init__(self, config_path: str):
        self.status = "ready"
        logger.info(f"Simulator initialized with config: {config_path}")

    def run_simulation(self, steps: int, context: str) -> Dict[str, Any]:
        """模拟器核心方法，可能抛出异常或返回复杂数据"""
        if steps < 0:
            raise ValueError("Steps cannot be negative")
        
        # 模拟业务逻辑
        return {
            "status": "success",
            "steps_completed": steps,
            "result_data": f"Simulation result for {context}",
            "metrics": {"accuracy": 0.98}
        }

# ==========================================
# 第二部分：你的 Adapter 代码
# 实际使用时，请 import 你的真实 Adapter
# ==========================================

class SimulatorAdapter:
    """
    将 Simulator 包装成 MCP Tool 格式
    职责：
    1. 解析 MCP 传入的 arguments (dict)
    2. 调用 Simulator 的具体方法
    3. 将结果格式化为 MCP 友好的文本或 JSON
    """
    def __init__(self, simulator: MockSimulator):
        self.simulator = simulator

    def call_tool(self, arguments: dict) -> str:
        """这是 MCP Server 将调用的入口方法"""
        try:
            # 1. 参数提取与校验
            steps = arguments.get("steps", 10) # 默认值处理
            context = arguments.get("context", "default")
            
            logger.info(f"Adapter calling simulator with: steps={steps}, context={context}")

            # 2. 调用核心 Simulator
            raw_result = self.simulator.run_simulation(steps, context)

            # 3. 结果转换 (Adapter 的核心价值)
            # MCP 通常期望 Tool 返回字符串给 LLM
            output = (
                f"Simulation Complete.\n"
                f"Status: {raw_result['status']}\n"
                f"Accuracy: {raw_result['metrics']['accuracy']}\n"
                f"Data: {raw_result['result_data']}"
            )
            return output

        except Exception as e:
            error_msg = f"Error in simulator adapter: {str(e)}"
            logger.error(error_msg)
            return f"Tool Execution Failed: {error_msg}"

# ==========================================
# 第三部分：连接测试脚本 (Verification Script)
# ==========================================

def run_connection_test():
    print("--- 开始 Adapter <-> Simulator 连接测试 ---")

    # 1. 测试 Simulator 初始化
    try:
        print("[1/3] 初始化 Simulator...")
        # 这里的参数根据你实际 Simulator 的需求填写
        real_simulator = MockSimulator(config_path="./config.yaml") 
        print("      ✅ Simulator 初始化成功")
    except Exception as e:
        print(f"      ❌ Simulator 初始化失败: {e}")
        return

    # 2. 测试 Adapter 绑定
    try:
        print("[2/3] 初始化 Adapter...")
        adapter = SimulatorAdapter(real_simulator)
        print("      ✅ Adapter 绑定成功")
    except Exception as e:
        print(f"      ❌ Adapter 绑定失败: {e}")
        return

    # 3. 测试工具调用 (模拟 MCP 行为)
    print("[3/3] 测试数据流 (Round-trip)...")
    
    # 构造测试用例：模拟 LLM 发出的 JSON 参数
    test_cases = [
        {
            "name": "正常情况",
            "input": {"steps": 50, "context": "test_scenario_A"},
            "expect_success": True
        },
        {
            "name": "异常处理 (负数步骤)",
            "input": {"steps": -1, "context": "fail_scenario"},
            "expect_success": False # 预期 Adapter 会捕获错误并返回错误文本，而不是崩溃
        }
    ]

    for case in test_cases:
        print(f"\n   -> 运行用例: {case['name']}")
        result = adapter.call_tool(case['input'])
        
        print(f"      [Adapter 返回]: {result.replace(chr(10), ' | ')}") # 单行打印方便查看

        # 简单的断言逻辑
        if case['expect_success']:
            if "Simulation Complete" in result:
                print("      ✅ 通过: 包含预期关键词")
            else:
                print("      ❌ 失败: 返回格式不正确")
        else:
            if "Tool Execution Failed" in result:
                print("      ✅ 通过: 成功捕获并处理了异常")
            else:
                print("      ❌ 失败: 异常未被 Adapter 正确处理")

    print("\n--- 测试结束 ---")

if __name__ == "__main__":
    run_connection_test()