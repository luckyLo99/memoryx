# Procedural Memory
# ?????

## English

### Overview
Transforms repeated episodic patterns into procedural knowledge,
supporting skill acquisition through pattern extraction and trigger matching.

### Components
| Component | Description |
|-----------|-------------|
| ProceduralMemory | Stores and manages procedural skills |
| ProceduralSkill | Skill dataclass with pattern, frequency, trigger keywords |

### Usage
`python
from memoryx.cognitive.procedural_memory import ProceduralMemory

pm = ProceduralMemory()

# Extract patterns from episodes
episodes = [
    {"content": "run deployment pipeline"},
    {"content": "run deployment pipeline"},
    {"content": "verify build status"},
]
skills = pm.extract_pattern(episodes)

# Execute a skill
result = pm.execute(skills[0].skill_id)

# Match trigger from query
skill = pm.match_trigger("run deployment")
if skill:
    print(f"Found skill: {skill.name}")
`

### References
- Squire & Zola (1996). Structure and function of memory systems.
- Doyon et al. (2009). Contributions of the basal ganglia.
- Anderson (1982). Acquisition of cognitive skill.

---

## ??

### ??
????????????????,
???????????????????

### ??
| ?? | ?? |
|------|------|
| ProceduralMemory | ?????????? |
| ProceduralSkill | ??????,???????????? |

### ????
`python
from memoryx.cognitive.procedural_memory import ProceduralMemory

pm = ProceduralMemory()

# ????????
episodes = [
    {"content": "???????"},
    {"content": "???????"},
]
skills = pm.extract_pattern(episodes)

# ?????
skill = pm.match_trigger("????")
if skill:
    print(f"????: {skill.name}")
`
