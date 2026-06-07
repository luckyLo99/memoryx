# Predictive Coding & Active Inference
# ?????????

## English

### Overview
Implements Friston's Free Energy Principle for memory retrieval:
context-based expectation, prediction error computation, and free-energy gating.

### Components
| Component | Description |
|-----------|-------------|
| ContextPredictor | Builds topic expectations from retrieval history |
| PredictiveRetrieval | Computes prediction error and surprise |
| ActiveInferenceGate | Free-energy threshold gating for retrieve/update/ignore |

### Usage
`python
from memoryx.cognitive.predictive_coding import (
    ContextPredictor, PredictiveRetrieval, ActiveInferenceGate
)

predictor = ContextPredictor()
exp = predictor.update("user query", [{"content": "retrieved memory"}])

pe = PredictiveRetrieval.compute_prediction_error(exp, {"content": "memory"})

gate = ActiveInferenceGate(free_energy_threshold=0.3)
if gate.should_update(pe):
    print("Updating memory due to prediction error")
if gate.should_ignore(pe):
    print("Memory matches expectation, no update needed")
print(f"Free energy: {gate.free_energy(pe)}")
`

### References
- Friston, K. (2010). The free-energy principle: a unified brain theory.
- Clark, A. (2013). Whatever next? Predictive brains, situated agents.
- Friston et al. (2017). Active inference: a process theory.

---

## ??

### ??
?? Friston ??????????:
??????????????????????

### ??
| ?? | ?? |
|------|------|
| ContextPredictor | ??????????? |
| PredictiveRetrieval | ?????????? |
| ActiveInferenceGate | ???????(??/??/??) |

### ????
`python
from memoryx.cognitive.predictive_coding import (
    ContextPredictor, PredictiveRetrieval, ActiveInferenceGate
)

predictor = ContextPredictor()
exp = predictor.update("????", [{"content": "??????"}])
pe = PredictiveRetrieval.compute_prediction_error(exp, {"content": "??"})

gate = ActiveInferenceGate(free_energy_threshold=0.3)
if gate.should_update(pe):
    print("?????????")
print(f"???: {gate.free_energy(pe)}")
`
