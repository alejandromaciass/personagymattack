"""Core orchestration logic for running evaluations."""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .api_schema import (Goal, Observation, PersonaCard, Rubric, Score, SeedCfg,
                        TraceEvent)
from .attacker.policy import AttackPolicy
from .baselines.white_prompt_only import WhiteAgent as PromptAgent
from .baselines.white_tool_user import WhiteAgent as ToolAgent
from .baselines.white_bad_agent import WhiteAgent as BadAgent
# from .baselines.local_model_agent import LocalModelAgent  # Optional dependency
from .graders import breakdetect, compose, efficiency, persona, safety
from .tools import io_bus

def load_task(task_dir: Union[str, Path]) -> Tuple[PersonaCard, Goal, Rubric, SeedCfg]:
    """Load task configuration from directory."""
    task_dir = Path(task_dir)
    
    # Load and parse each config file
    with open(task_dir / "persona.json") as f:
        persona_data = PersonaCard.model_validate(json.load(f))
    
    with open(task_dir / "goal.json") as f:
        goal_data = Goal.model_validate(json.load(f))
    
    with open(task_dir / "rubric.json") as f:
        rubric_data = Rubric.model_validate(json.load(f))
    
    with open(task_dir / "seed.json") as f:
        seed_data = SeedCfg.model_validate(json.load(f))
    
    return persona_data, goal_data, rubric_data, seed_data

def run_dialog(
    white: Any,
    persona_data: PersonaCard,
    goal: Goal,
    rubric: Rubric,
    seed: SeedCfg
) -> Tuple[Score, List[TraceEvent]]:
    """Run a complete dialog between attacker and white agent."""
    history: List[Dict[str, str]] = []
    trace: List[TraceEvent] = []
    
    # Initialize attacker
    attacker = AttackPolicy(seed.attack_set, seed.rng_seed)
    
    # Run dialog for specified turns
    for turn in range(1, goal.horizon + 1):
        # Get next attack message
        attack_msg = attacker.next_message(history, persona_data)
        
        # Build observation for white agent
        obs = Observation(
            turn=turn,
            attacker_msg=attack_msg,
            persona=persona_data,
            history_tail=history,  # Pass full history
            limits={"max_turns": goal.horizon}
        )
        
        # Get white agent response
        white_msg = white.respond(obs)
        
        # Update history
        history.append({
            "attacker": attack_msg,
            "white": white_msg
        })
        
        # Check for breaks
        break_signal = breakdetect.scan(white_msg, persona_data, history)
        
        # Record trace
        # break_signal is already a dict or None
        trace_event = TraceEvent(
            turn=turn,
            attacker=attack_msg,
            white=white_msg,
            break_signal=break_signal if break_signal else None
        )
        trace.append(trace_event)
        
        # Stop if break detected
        if break_signal:
            break
    
    # Get final response if dialog completed
    if not break_signal:
        final_msg = white.submit()
        history.append({"white": final_msg})
    
    # Compute scores
    persona_scores = persona.check_persona_adherence(
        white_msg,
        persona_data,
        rubric
    )
    safety_score = safety.score_safety(history)
    
    # Compute final score
    final_score = compose.final_score(
        persona_scores,
        break_signal,
        safety_score,
        len(history),
        goal.horizon
    )
    
    return final_score, trace

def write_reports(
    output_dir: Union[str, Path],
    score: Score,
    trace: List[TraceEvent]
) -> Path:
    """Write evaluation reports to directory."""
    # Create reports directory with timestamp
    report_dir = io_bus.make_report_dir()
    
    # Write trace events
    io_bus.write_trace(report_dir, trace)
    
    # Write scores
    scores_dict = {k: float(v) for k, v in score.model_dump().items() 
                  if k in ['P', 'B', 'S', 'E', 'R']}
    io_bus.write_scores(report_dir, scores_dict)
    
    # Write summary
    io_bus.write_summary(report_dir, score.model_dump(), trace)
    
    return report_dir

def run_task(
    task_dir: str,
    white_name: str,
    seed_override: Optional[int] = None
) -> int:
    """Run complete evaluation task.
    
    Args:
        task_dir: Path to task directory
        white_name: Name of white agent to use ('prompt' or 'tool')
        seed_override: Optional RNG seed override
    
    Returns:
        Exit code (0 for success, 1 for error)
    """
    try:
        # Load task configuration
        persona_data, goal, rubric, seed = load_task(task_dir)
        
        # Override seed if specified
        if seed_override is not None:
            seed.rng_seed = seed_override
        
        # Initialize white agent
        if white_name == "prompt":
            white = PromptAgent(persona_data)
        elif white_name == "tool":
            white = ToolAgent(persona_data)
        elif white_name == "bad":
            white = BadAgent(persona_data)
        elif white_name == "llm":
            # white = LocalModelAgent(persona_data, model_name="distilgpt2")  # Optional dependency
            raise ValueError("LocalModelAgent requires transformers - install with: pip install transformers torch")
        elif white_name == "openai":
            from .baselines.openai_model_agent import OpenAIModelAgent
            white = OpenAIModelAgent(persona_data, model_name="gpt-3.5-turbo")
        elif white_name == "claude":
            from .baselines.claude_model_agent import ClaudeModelAgent
            white = ClaudeModelAgent(persona_data, model_name="claude-sonnet-4-5")
        else:
            raise ValueError(f"Unknown white agent: {white_name}")
        
        # Run dialog
        score, trace = run_dialog(white, persona_data, goal, rubric, seed)
        
        # Write reports
        report_dir = write_reports(Path("reports"), score, trace)
        
        print(f"\nEvaluation complete. Reports written to: {report_dir}")
        return 0
        
    except Exception as e:
        print(f"Error running task: {e}")
        return 1