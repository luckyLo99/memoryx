# Cognitive Load Optimization
# ??????

## English

### Overview
Implements Cognitive Load Theory (Sweller) with Miller's Law chunking
for context budget optimization.

### Components
| Component | Description |
|-----------|-------------|
| CognitiveLoadOptimizer | Analyzes task complexity, optimizes context budget |
| CognitiveLoadProfile | Intrinsic/extraneous/germane load breakdown |

### Usage
`python
from memoryx.cognitive.cognitive_load import CognitiveLoadOptimizer

clo = CognitiveLoadOptimizer(chunk_limit=7)
profile = clo.analyze_task("complex task description", [{"id": "1"}, {"id": "2"}])
print(f"Intrinsic load: {profile.intrinsic_load}")
print(f"Recommended budget: {profile.recommended_context_budget}")

# Chunk items using Miller's Law
chunks = CognitiveLoadOptimizer.chunk_items(["a","b","c","d","e","f"], chunk_size=3)

# Optimize existing budget
new_budget = CognitiveLoadOptimizer.optimize_budget(4096, profile)
`

### References
- Miller (1956). The magical number seven, plus or minus two.
- Sweller (1988). Cognitive load during problem solving.
- Cowan (2001). The magical number 4 in short-term memory.
- Paas et al. (2003). Cognitive load theory and instructional design.

---

## ??

### ??
?? Sweller ??????? Miller ??????,
??????????

### ??
| ?? | ?? |
|------|------|
| CognitiveLoadOptimizer | ???????,??????? |
| CognitiveLoadProfile | ??/??/?????? |

### ????
`python
from memoryx.cognitive.cognitive_load import CognitiveLoadOptimizer

clo = CognitiveLoadOptimizer(chunk_limit=7)
profile = clo.analyze_task("??????", [{"id": "1"}, {"id": "2"}])
print(f"????: {profile.intrinsic_load}")

chunks = CognitiveLoadOptimizer.chunk_items(["a","b","c","d","e","f"], chunk_size=3)
new_budget = CognitiveLoadOptimizer.optimize_budget(4096, profile)
`
