"""IO utilities for logging trace events."""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from ..api_schema import TraceEvent

def ensure_dir(path: str | Path) -> Path:
    """Ensure directory exists, creating it if necessary."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path

class JsonlWriter:
    """JSONL file writer with proper flushing and error handling."""
    def __init__(self, path: str | Path):
        """Initialize writer for the given path."""
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = open(self.path, 'w', encoding='utf-8')
    
    def write(self, obj: Any) -> None:
        """Write an object as a JSON line."""
        self.file.write(json.dumps(obj) + '\n')
        self.file.flush()
    
    def close(self) -> None:
        """Close the file."""
        self.file.close()

def make_report_dir() -> Path:
    """Create a timestamped report directory."""
    base = Path("reports")
    # Include sub-second precision to avoid collisions when multiple runs finish
    # within the same second (common in demos/tests).
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = ensure_dir(base / ts)
    return path

def write_trace(path: Path, events: List[TraceEvent]) -> None:
    """Write trace events to a JSONL file."""
    writer = JsonlWriter(path / "trace.jsonl")
    for event in events:
        # If event is a pydantic object, use model_dump; if dict, use as is
        if hasattr(event, "model_dump"):
            writer.write(event.model_dump())
        else:
            writer.write(event)
    writer.close()

def write_scores(path: Path, scores: Dict[str, float]) -> None:
    """Write scores to a CSV file."""
    with open(path / "scores.csv", 'w', encoding='utf-8') as f:
        f.write("metric,score\n")
        for k, v in scores.items():
            f.write(f"{k},{v}\n")

def write_summary(path: Path, score: Dict[str, Any], trace: List[TraceEvent]) -> None:
    """Write a Markdown summary report."""
    with open(path / "summary.md", 'w', encoding='utf-8') as f:
        f.write("# PersonaGym-R Evaluation Report\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        # Scores table
        f.write("## Scores\n\n")
        f.write("| Metric | Score |\n")
        f.write("|--------|-------|\n")
        for k in ['P', 'B', 'S', 'E', 'R']:
            f.write(f"| {k} | {score[k]:.3f} |\n")
        
        # Break info
        f.write("\n## Break Analysis\n\n")
        if score['broke']:
            f.write(f"Break detected at turn {score['break_turn']}\n")
            f.write(f"Severity: {score['break_severity']}\n")
            f.write(f"Reason: {score['reason']}\n")
        else:
            f.write("No breaks detected\n")
        
        # Dialog summary
        f.write("\n## Dialog Summary\n\n")
        f.write(f"Total turns: {score['turns']}\n\n")
        for evt in trace:
            f.write(f"### Turn {evt.turn}\n\n")
            f.write(f"**Attacker**: {evt.attacker}\n\n")
            f.write(f"**White**: {evt.white}\n\n")
            if evt.break_signal:
                f.write(f"*Break detected: {evt.break_signal}*\n\n")