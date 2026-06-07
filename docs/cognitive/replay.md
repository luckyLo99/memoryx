# Memory Consolidation & Hippocampal Replay
# ??????????

## English

### Overview
Implements complementary learning systems theory with offline memory consolidation:
hippocampal replay, memory reconsolidation, and background scheduling.

### Components
| Component | Description |
|-----------|-------------|
| ReplayBuffer | Stores recent experiences, deque with max_size |
| HippocampalReplay | Simulates hippocampal replay during idle periods |
| MemoryReconsolidation | Updates memory traces with new related information |
| ConsolidationScheduler | Async background loop running consolidation passes |

### Usage
`python
from memoryx.consolidation.replay import (
    ConsolidationScheduler, HippocampalReplay,
    MemoryReconsolidation, ReplayBuffer, ReplayEvent
)

buffer = ReplayBuffer(max_size=1000)
buffer.add(ReplayEvent(event_id="e1", importance=0.9))

replay = HippocampalReplay(buffer, repository=repo)
rc = MemoryReconsolidation(repository=repo)

scheduler = ConsolidationScheduler(
    repository=repo, replay=replay,
    consolidation_engine=engine, idle_interval=300
)
scheduler.start()
result = await scheduler.run_once()
await scheduler.stop()
`

### References
- McClelland et al. (1995). Complementary learning systems.
- Nadel & Moscovitch (1997). Memory consolidation, retrograde amnesia.
- Dudai (2004). The neurobiology of consolidations.
- Lewis & Durrant (2011). Overlapping memory replay.

---

## ??

### ??
?????????????????:
?????????????????

### ??
| ?? | ?? |
|------|------|
| ReplayBuffer | ??????,deque ??,????? |
| HippocampalReplay | ??????????? |
| MemoryReconsolidation | ???????????? |
| ConsolidationScheduler | ???????????? |

### ????
`python
from memoryx.consolidation.replay import (
    ConsolidationScheduler, HippocampalReplay,
    MemoryReconsolidation, ReplayBuffer, ReplayEvent
)

buffer = ReplayBuffer(max_size=1000)
buffer.add(ReplayEvent(event_id="e1", importance=0.9))

scheduler = ConsolidationScheduler(
    repository=repo, replay=replay,
    consolidation_engine=engine, idle_interval=300
)
scheduler.start()
await scheduler.stop()
`
