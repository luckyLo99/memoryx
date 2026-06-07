# Ebbinghaus Forgetting Curve & Spaced Repetition
# Ebbinghaus ?????????

## English

### Overview
The Ebbinghaus forgetting curve module implements the classic exponential forgetting
model (R = e^(-t/S)) with modern enhancements for AI memory systems.

### Key Components

| Component | Description |
|-----------|-------------|
| EbbinghausForgettingCurve | Core forgetting curve with retention calculation |
| MemoryStrength | Serializable memory strength dataclass |
| SpacedRepetitionScheduler | Leitner-system expanding intervals |
| RetrievalOutcome | PERFECT/GOOD/HARD/FAIL outcome enum |

### Scientific Foundations
- Ebbinghaus, H. (1885). *Memory: A Contribution to Experimental Psychology*
- Murre & Dros (2015). Replication of Ebbinghaus forgetting curve
- Kornell & Bjork (2008). Optimising self-regulated learning
- Cepeda et al. (2006). Distributed practice in verbal recall tasks

### Usage
`python
from memoryx.cognitive.ebbinghaus import EbbinghausForgettingCurve, MemoryStrength

# Initialize from importance
strength = EbbinghausForgettingCurve.initial_strength(importance=0.8)

# Calculate current retention
retention = EbbinghausForgettingCurve.retention(strength)

# Update after retrieval
strength = EbbinghausForgettingCurve.update_after_retrieval(
    strength, RetrievalOutcome.PERFECT
)

# Check if due for review
due = EbbinghausForgettingCurve.is_due_for_review(strength)
`

### Integration with Scoring
The ebbinghaus_decay_multiplier() function in memoryx/retrieval/scorer.py
replaces the legacy linear decay with Ebbinghaus-aware decay:

`python
from memoryx.retrieval.scorer import ebbinghaus_decay_multiplier
decay = ebbinghaus_decay_multiplier(importance=0.8, retrieval_count=3)
`

### Spaced Repetition Intervals
| Outcome | Interval 1 | Interval 2 | Interval 3 | ... | Interval 9 |
|---------|-----------|-----------|-----------|-----|-----------|
| PERFECT | 0s | 1h | 6h | ... | 90d |
| GOOD | 0s | 30min | 3h | ... | 60d |
| HARD | 0s | 10min | 1h | ... | 14d |
| FAIL | 0s | 1min | 10min | ... | 5d |

---

## ??

### ??
Ebbinghaus ?????????????????? (R = e^(-t/S)),
??? AI ?????????????

### ????

| ?? | ?? |
|------|------|
| EbbinghausForgettingCurve | ????????????? |
| MemoryStrength | ????????????? |
| SpacedRepetitionScheduler | Leitner ???????? |
| RetrievalOutcome | PERFECT/GOOD/HARD/FAIL ???? |

### ????
- Ebbinghaus (1885): ?????????
- Murre & Dros (2015): Ebbinghaus ??????
- Kornell & Bjork (2008): ????????
- Cepeda et al. (2006): ??????

### ????
`python
from memoryx.cognitive.ebbinghaus import EbbinghausForgettingCurve, MemoryStrength

# ???????
strength = EbbinghausForgettingCurve.initial_strength(importance=0.8)

# ???????
retention = EbbinghausForgettingCurve.retention(strength)

# ?????
strength = EbbinghausForgettingCurve.update_after_retrieval(
    strength, RetrievalOutcome.PERFECT
)

# ????????
due = EbbinghausForgettingCurve.is_due_for_review(strength)
`

### ????
memoryx/retrieval/scorer.py ?? ebbinghaus_decay_multiplier()
???????????? Ebbinghaus ?????
