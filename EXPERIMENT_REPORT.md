# LLM Call Reduction Rate Experiment Report

**Generated**: 2026-04-12 16:16:20

**Sample Size**: 535

## 1. Core Results

- **LLM Call Reduction Rate**: **52.52%**
- **Control Accuracy**: 69.91%
- **Experiment Accuracy**: 76.26%
- **Accuracy Difference**: -6.36%

## 2. LLM Call Comparison

| Metric | Control | Experiment |
|--------|---------|-----------|
| LLM Calls | 535 | 254 |
| Avg Calls/Sample | 1.00 | 0.47 |

## 3. Tier Breakdown

| Tier | Rate |
|------|------|
| Cache Layer | 0.00% |
| Rule Layer | 52.52% |
| LLM Fallback | 47.48% |

## 4. Analysis by Intent Type

| Intent | Samples | LLM Calls | LLM Rate |
|--------|--------|-----------|----------|
| budget | 25 | 8 | 32.0% |
| chat | 110 | 70 | 63.6% |
| food | 25 | 11 | 44.0% |
| hotel | 50 | 13 | 26.0% |
| image | 10 | 5 | 50.0% |
| itinerary | 163 | 61 | 37.4% |
| query | 137 | 76 | 55.5% |
| transport | 15 | 10 | 66.7% |

## 5. Error Analysis

Misclassified samples: 127

### Error Cases (Top 10)

1. **sample_0002**
   - Input: 上海到广州多远...
   - Expected: query, Predicted: chat
   - Confidence: 0.50, Tier: llm
   - Category: high_frequency

2. **sample_0004**
   - Input: 北京到广州多远...
   - Expected: query, Predicted: chat
   - Confidence: 0.50, Tier: llm
   - Category: high_frequency

3. **sample_0008**
   - Input: 上海明天会下雨吗...
   - Expected: query, Predicted: chat
   - Confidence: 0.50, Tier: llm
   - Category: high_frequency

4. **sample_0012**
   - Input: 怎么去杭州...
   - Expected: query, Predicted: transport
   - Confidence: 0.81, Tier: rule
   - Category: high_frequency

5. **sample_0016**
   - Input: 重庆有什么好玩的...
   - Expected: itinerary, Predicted: chat
   - Confidence: 0.50, Tier: llm
   - Category: high_frequency

6. **sample_0022**
   - Input: 这个地方怎么去...
   - Expected: query, Predicted: transport
   - Confidence: 0.81, Tier: rule
   - Category: ambiguous

7. **sample_0024**
   - Input: 那边有什么好玩的...
   - Expected: query, Predicted: chat
   - Confidence: 0.50, Tier: llm
   - Category: ambiguous

8. **sample_0029**
   - Input: 那边有什么好玩的...
   - Expected: query, Predicted: chat
   - Confidence: 0.50, Tier: llm
   - Category: ambiguous

9. **sample_0036**
   - Input: 我想去一个有美食的地方玩几天...
   - Expected: itinerary, Predicted: food
   - Confidence: 0.90, Tier: rule
   - Category: ambiguous

10. **sample_0037**
   - Input: 上海明天会下雨吗...
   - Expected: query, Predicted: chat
   - Confidence: 0.50, Tier: llm
   - Category: high_frequency

