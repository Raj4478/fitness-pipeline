"""
Fitness niche topic pool.
TopicBank picks unused topics in rotation so videos never repeat.
"""

import json
import random
from pathlib import Path

TOPICS = {
    "fitness": [
        "protein myths",
        "vitamin D deficiency india",
        "walking vs running",
        "sleep and muscle growth",
        "sugar free drinks danger",
        "intermittent fasting facts",
        "gym myths busted",
        "sitting disease office workers",
        "creatine facts",
        "cardio vs weight training",
        "indian diet protein sources",
        "stress and belly fat",
        "overtraining signs",
        "morning workout vs evening",
        "hydration myths",
        "BMI is misleading",
        "processed food addiction",
        "gut health india",
        "yoga science benefits",
        "cold water after workout myth",
    ]
}

USED_TOPICS_FILE = Path("data/used_topics.json")


class TopicBank:
    def __init__(self):
        USED_TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        if USED_TOPICS_FILE.exists():
            self._used: dict = json.loads(USED_TOPICS_FILE.read_text())
        else:
            self._used = {}

    def pick_unused(self, niche: str) -> str:
        all_topics = TOPICS.get(niche, [])
        used = set(self._used.get(niche, []))
        unused = [t for t in all_topics if t not in used]

        # Reset if all used
        if not unused:
            unused = all_topics
            self._used[niche] = []

        topic = random.choice(unused)
        self._used.setdefault(niche, []).append(topic)
        USED_TOPICS_FILE.write_text(json.dumps(self._used, indent=2))
        return topic

    def mark_used(self, niche: str, topic: str) -> None:
        self._used.setdefault(niche, [])
        if topic not in self._used[niche]:
            self._used[niche].append(topic)
        USED_TOPICS_FILE.write_text(json.dumps(self._used, indent=2))
