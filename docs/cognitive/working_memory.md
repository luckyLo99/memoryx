# Baddeley Multi-Component Working Memory Model
# Baddeley ?????????

## English

### Overview
Implements Baddeley (2000) working memory model with four components:
Central Executive (attention controller), Phonological Loop (verbal buffer),
Visuospatial Sketchpad (visual buffer), and Episodic Buffer (cross-modal integration).

### Components
| Component | Capacity | Description |
|-----------|----------|-------------|
| CentralExecutive | 7 ? 2 chunks | Attention allocation, capacity management |
| PhonologicalLoop | ~2 seconds | Verbal/acoustic information, articulation loop |
| VisuospatialSketchpad | 4 items | Visual and spatial information |
| EpisodicBuffer | 4 episodes | Multi-dimensional episodic integration |

### Usage
`python
from memoryx.cognitive.working_memory import BaddeleyWorkingMemory, ModalityType

wm = BaddeleyWorkingMemory(capacity=7)
state = wm.process("hello world", modality=ModalityType.VERBAL)
print(wm.remaining_capacity())
print(wm.is_overloaded())
wm.clear()
`

### References
- Baddeley, A. D. (2000). The episodic buffer: a new component of working memory?
- Baddeley, A. D. (1992). Working memory. Science, 255(5044), 556-559.
- Miller, G. A. (1956). The magical number seven, plus or minus two.
- Cowan, N. (2001). The magical number 4 in short-term memory.

---

## ??

### ??
?? Baddeley (2000) ??????,??????:
?????(??????)?????(?????)?
??????(?????)??????(?????)?

### ??
| ?? | ?? | ?? |
|------|------|------|
| ????? | 7 ? 2 ?? | ?????,???? |
| ???? | ~2 ? | ??/????,???? |
| ?????? | 4 ? | ??????? |
| ????? | 4 ??? | ?????? |

### ????
`python
from memoryx.cognitive.working_memory import BaddeleyWorkingMemory, ModalityType

wm = BaddeleyWorkingMemory(capacity=7)
state = wm.process("hello world", modality=ModalityType.VERBAL)
print(wm.remaining_capacity())
print(wm.is_overloaded())
wm.clear()
`
