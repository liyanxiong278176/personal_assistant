# E2E Full Flow Test Report

Generated: 2026-04-15T20:10:16.752608

## Test Results Summary

| Scenario ID | Name | Status | Duration (ms) |
|-------------|------|--------|---------------|
| 1 | 简单问答 | ✅ PASS | 3.56 |
| 2 | 多轮对话 | ❌ ERROR | 0.00 |
| 3 | 工具调用 | ❌ ERROR | 0.00 |
| 4 | 长对话压缩 | ❌ ERROR | 0.00 |
| 5 | 行程规划全流程 | ❌ FAIL | 0.46 |
| 6 | 多轮行程修改 | ❌ ERROR | 0.00 |
| 7 | 酒店推荐 | ✅ PASS | 0.34 |
| 8 | 预算控制 | ❌ ERROR | 0.00 |
| 9 | 异常输入处理 | ✅ PASS | 0.18 |
| 10 | 跨意图切换 | ❌ ERROR | 0.00 |

**Pass Rate:** 3/10 (30.0%)
- Passed: 3
- Failed: 1
- Errors: 6

## Flow Connectivity Assessment

### Connected Nodes:
- IntentRouter: ✅ Connected
- SlotExtractor: ✅ Connected
- ToolExecutor: ✅ Connected
- LLMClient: ✅ Connected
- MemoryInjector: ❌ Not Connected
- ContextCompressor: ❌ Not Connected

## Detailed Results

### Scenario 1: 简单问答
**Input:** 你好
**Status:** PASS
**Duration:** 3.56ms

**Node Outputs:**
- IntentRouter: 1.99ms
- SlotExtractor: 1.54ms
- LLMClient: 0.02ms

**Final Response:** 收到您的消息：你好。我是旅游助手，很高兴为您服务！...

### Scenario 2: 多轮对话
**Input:** 我想去北京旅游 -> 有什么好玩的 -> 天气怎么样
**Status:** ERROR
**Duration:** 0.00ms
**Error:** "IntentResult" object has no field "collected_slots"

**Node Outputs:**

**Final Response:** ...

### Scenario 3: 工具调用
**Input:** 北京今天天气怎么样
**Status:** ERROR
**Duration:** 0.00ms
**Error:** "IntentResult" object has no field "collected_slots"

**Node Outputs:**

**Final Response:** ...

### Scenario 4: 长对话压缩
**Input:** 20+轮对话
**Status:** ERROR
**Duration:** 0.00ms
**Error:** 'ContextCompressor' object has no attribute 'needs_compaction'

**Node Outputs:**

**Final Response:** ...

### Scenario 5: 行程规划全流程
**Input:** 杭州3天游，预算2000元，带老人
**Status:** FAIL
**Duration:** 0.46ms
**Error:** Missing required slots or incorrect intent

**Node Outputs:**
- IntentRouter: 0.23ms
- SlotExtractor: 0.15ms
- ToolExecutor: 0.06ms
- LLMClient: 0.03ms

**Final Response:** 根据您的预算，建议如下分配：交通30%、住宿40%、餐饮20%、景点10%。...

### Scenario 6: 多轮行程修改
**Input:** 规划北京3天游 -> 把第二天改成去颐和园
**Status:** ERROR
**Duration:** 0.00ms
**Error:** "IntentResult" object has no field "collected_slots"

**Node Outputs:**

**Final Response:** ...

### Scenario 7: 酒店推荐
**Input:** 帮我找杭州的酒店，预算500元以内
**Status:** PASS
**Duration:** 0.34ms

**Node Outputs:**
- IntentRouter: 0.20ms
- SlotExtractor: 0.09ms
- ToolExecutor: 0.03ms
- LLMClient: 0.01ms

**Final Response:** 为您推荐以下酒店：五星级酒店、精品酒店、经济型酒店等多种选择。...

### Scenario 8: 预算控制
**Input:** 去西安5天大概多少钱
**Status:** ERROR
**Duration:** 0.00ms
**Error:** "IntentResult" object has no field "collected_slots"

**Node Outputs:**

**Final Response:** ...

### Scenario 9: 异常输入处理
**Input:** @#$%^&*()
**Status:** PASS
**Duration:** 0.18ms

**Node Outputs:**
- IntentRouter: 0.16ms
- LLMClient: 0.01ms

**Final Response:** 收到您的消息：@#$%^&*()。我是旅游助手，很高兴为您服务！...

### Scenario 10: 跨意图切换
**Input:** 规划行程 -> 查询天气 -> 推荐酒店 -> 计算预算
**Status:** ERROR
**Duration:** 0.00ms
**Error:** "IntentResult" object has no field "collected_slots"

**Node Outputs:**

**Final Response:** ...

## Recommendations

### Issues Found:
- Scenario 2: "IntentResult" object has no field "collected_slots"
- Scenario 3: "IntentResult" object has no field "collected_slots"
- Scenario 4: 'ContextCompressor' object has no attribute 'needs_compaction'
- Scenario 5: Missing required slots or incorrect intent
- Scenario 6: "IntentResult" object has no field "collected_slots"
- Scenario 8: "IntentResult" object has no field "collected_slots"
- Scenario 10: "IntentResult" object has no field "collected_slots"

### Suggested Actions:
1. Review failed scenarios for configuration issues
2. Check LLM client connectivity and API credentials
3. Verify tool registration and execution
4. Test memory injection and context compression