# Dual-Process Retrieval (System 1 / System 2)
# ????? (System 1 / System 2)

## English

### Overview
Implements Kahneman's dual-process theory for memory retrieval:
- **System 1**: Fast, automatic, cache-based retrieval for simple queries
- **System 2**: Slow, deliberate, hybrid retrieval for complex queries
- Automatic escalation when System 1 confidence is low

### Components
| Component | Description |
|-----------|-------------|
| QueryComplexityAnalyzer | Analyzes query complexity (word count, patterns, question marks) |
| System1Retriever | Fast FTS5 + cache retrieval path |
| System2Retriever | Full hybrid engine + conflict detection |
| DualProcessGateway | Orchestrates System 1 vs System 2 with confidence gating |

### Usage
`python
from memoryx.cognitive.dual_process import (
    DualProcessGateway, System1Retriever, System2Retriever
)

gateway = DualProcessGateway(
    System1Retriever(fts_retriever=my_fts),
    System2Retriever(hybrid_engine=my_engine),
    confidence_threshold=0.6
)
results, decision = await gateway.retrieve("complex query here?")
print(f"System used: {decision.system}")
print(f"Stats: {gateway.get_stats()}")
`

### References
- Kahneman, D. (2011). Thinking, Fast and Slow.
- Evans, J. St. B. T. (2008). Dual-processing accounts of reasoning.
- Pennycook, G. (2017). A perspective on dual process models.

---

## ??

### ??
?? Kahneman ??????????:
- **?? 1**: ?????????????????
- **?? 2**: ???????????????
- ?? 1 ?????????

### ??
| ?? | ?? |
|------|------|
| QueryComplexityAnalyzer | ???????(????????) |
| System1Retriever | ?? FTS5 + ?????? |
| System2Retriever | ?????? + ???? |
| DualProcessGateway | ?? System 1 ? System 2,?????? |

### ????
`python
from memoryx.cognitive.dual_process import (
    DualProcessGateway, System1Retriever, System2Retriever
)

gateway = DualProcessGateway(
    System1Retriever(fts_retriever=my_fts),
    System2Retriever(hybrid_engine=my_engine),
    confidence_threshold=0.6
)
results, decision = await gateway.retrieve("????")
print(f"?????: {decision.system}")
`
