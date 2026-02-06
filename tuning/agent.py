"""
Agentic AI workflow for PFLOTRAN parameter tuning.

This module implements an AI agent that intelligently orchestrates the
parameter tuning process, making decisions based on domain knowledge
and observed results rather than following a fixed algorithm.

The agent:
1. Analyzes simulation results and identifies patterns
2. Reasons about which parameters to adjust and why
3. Adapts its strategy based on what it learns
4. Diagnoses simulation failures and proposes solutions
5. Interprets results in the context of biogeochemistry
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict, field
import numpy as np

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

from .config import (
    PARAMETERS, PARAM_BY_NAME, get_parameter_names,
    get_parameter_bounds, get_default_values,
    transform_to_linear, SPECIES_WEIGHTS, get_species_for_meander,
    get_parameters_for_meander, SIMULATION_CONFIGS
)
from .simulation_runner import SimulationRunner
from .objective import ObjectiveFunction, compute_objective_with_details
from .template_modifier import TemplateModifier
from .visualization import TuningVisualizer

logger = logging.getLogger(__name__)


# Define tuning phases and their associated parameters
# Order follows the redox ladder: aerobic → denitrification → Fe(III) reduction → sulfate reduction
TUNING_PHASES = {
    'aerobic': {
        'parameters': ['aerobic_rate_constant', 'aerobic_o2_half_sat', 'aerobic_soc_half_sat'],
        'target_species': ['DO'],
        'description': 'Tune aerobic respiration parameters (top of redox ladder)',
        'next_phase': 'nitrate',
        'min_iterations': 3,
        'max_iterations': 8,
    },
    'aerobic_verify': {
        # Special phase for MCP: verify DO is consumed but don't tune
        'parameters': [],  # No parameters to tune
        'target_species': ['DO'],
        'description': 'Verify anaerobic conditions (DO < 1e-6 M beyond 0.5m from upstream boundary)',
        'next_phase': 'nitrate',
        'min_iterations': 1,
        'max_iterations': 1,  # Just one verification iteration
    },
    'nitrate': {
        'parameters': ['nitrate_rmax', 'nitrate_k_donor', 'nitrate_k_acceptor'],
        'target_species': ['NO3'],
        'description': 'Tune denitrification parameters',
        'next_phase': 'fe',
        'min_iterations': 3,
        'max_iterations': 8,
    },
    'fe': {
        'parameters': ['ferrihydrite_rmax', 'goethite_rmax', 'fe_oxidation_forward_rate'],
        'target_species': ['Fe'],
        'description': 'Tune Fe(III) reduction parameters',
        'next_phase': 'sulfate',
        'min_iterations': 3,
        'max_iterations': 8,
    },
    'sulfate': {
        'parameters': ['sulfate_rmax', 'sulfate_k_donor', 'sulfate_k_acceptor'],
        'target_species': ['SO4'],
        'description': 'Tune sulfate reduction parameters (bottom of redox ladder)',
        'next_phase': 'root_respiration',
        'min_iterations': 3,
        'max_iterations': 8,
    },
    'root_respiration': {
        'parameters': ['root_respiration_dissolution_rate'],
        'target_species': ['TIC', 'pH'],
        'description': 'Tune root respiration using DIC and pH for calibration (final adjustment)',
        'next_phase': 'refinement',
        'min_iterations': 2,
        'max_iterations': 5,
    },
    'refinement': {
        'parameters': None,  # All parameters available
        'target_species': None,  # All species
        'description': 'Fine-tune all parameters for overall optimization',
        'next_phase': None,
        'min_iterations': 1,
        'max_iterations': None,  # Continue until max_iterations
    },
}

# Meander-specific starting phases
# MCP: Known anaerobic system - skip aerobic tuning, just verify DO consumption
# MZT: Tune aerobic respiration normally
MEANDER_STARTING_PHASE = {
    'mcp': 'aerobic_verify',
    'mzt': 'aerobic',
}


# Domain knowledge for the agent
DOMAIN_KNOWLEDGE = """
You are an expert in reactive transport modeling of hyporheic zone biogeochemistry.

## Tuning Objective
Adjust model parameters to minimize the objective function (1 - weighted KGE).
The objective function quantifies the discrepancy between simulated and observed values.

## Sequential Tuning Strategy - Following the Redox Ladder
This tuning workflow uses a PHASED APPROACH following the thermodynamic sequence of
terminal electron accepting processes (TEAPs) - the "redox ladder":

**Phase 1: AEROBIC RESPIRATION** - Top of redox ladder (most energetically favorable)
   - Parameters: aerobic_rate_constant, aerobic_o2_half_sat, aerobic_soc_half_sat
   - Target: Get DO (dissolved oxygen) concentrations to match observations
   - Controls the oxic-anoxic transition zone

**Phase 2: DENITRIFICATION** - Second step down the redox ladder
   - Parameters: nitrate_rmax, nitrate_k_donor, nitrate_k_acceptor
   - Target: Get NO3 concentrations to match observations
   - Occurs when O2 is depleted; NO3- serves as electron acceptor

**Phase 3: FE(III) REDUCTION** - Third step down the redox ladder
   - Parameters: ferrihydrite_rmax, goethite_rmax, fe_oxidation_forward_rate
   - Target: Get Fe++ concentrations to match observations
   - Dominant TEAP in this system; produces dissolved Fe++

**Phase 4: SULFATE REDUCTION** - Bottom of redox ladder (least favorable)
   - Parameters: sulfate_rmax, sulfate_k_donor, sulfate_k_acceptor
   - Target: Get SO4 concentrations to match observations
   - Occurs in the most reducing (anoxic) zones

**Phase 5: ROOT RESPIRATION** - Final adjustment for carbonate system
   - Parameters: root_respiration_dissolution_rate
   - Target: Calibrate using TIC (DIC) and pH observations
   - Adjusts overall CO2/DIC production from plant root metabolism
   - Tuned LAST because it affects the entire carbonate equilibrium

**Phase 6: REFINEMENT** - Fine-tune all parameters
   - All parameters available for final optimization
   - Focus on overall objective function improvement

IMPORTANT: You can ONLY adjust parameters that belong to the current phase.
Wait for phase transitions before tuning other parameter groups.

RATIONALE: Tuning in redox ladder order ensures that upstream processes (aerobic,
denitrification) are calibrated before downstream processes (Fe, sulfate) that
depend on the redox conditions established by the upstream reactions.

## Meander-Specific Behavior

**MCP Meander (Anaerobic System):**
- Known to be anaerobic - aerobic respiration is NOT tuned
- Instead, we VERIFY that DO < 1e-6 M beyond 0.5m from upstream boundary
- Default aerobic rates should be sufficient to consume all oxygen
- Tuning starts at denitrification phase after verification

**MZT Meander:**
- Full redox gradient present
- Aerobic respiration IS tuned normally
- Starts at aerobic phase

## Biogeochemical Context
The PFLOTRAN model simulates a river meander hyporheic zone where:
- River water infiltrates through the riverbed and flows through alluvial sediments
- Redox conditions change from oxic near the river to anoxic deeper in the subsurface
- Sequential terminal electron accepting processes (TEAPs) occur:
  1. Aerobic respiration (O2 reduction) - fastest, near river
  2. Denitrification (NO3- reduction) - minor due to low NO3- (~1e-6 M)
  3. Iron reduction (Fe(III) → Fe(II)) - MAJOR PROCESS, creates dissolved Fe++
  4. Sulfate reduction (SO4-- → HS-) - important in deep anoxic zones

## Fe Reduction and Carbonate Chemistry (PRIMARY FOCUS)
Iron reduction is a dominant TEAP in this system and strongly influences carbonate chemistry:
- Two Fe(III) mineral phases with different reduction thermodynamics:
  - Ferrihydrite: More thermodynamically favorable for reduction (less crystalline)
  - Goethite: Less favorable for reduction (more crystalline, lower free energy)
- If conditions are near equilibrium for goethite reduction, they are still favorable
  for ferrihydrite reduction → ferrihydrite reduction rates remain high
- Iron reduction produces Fe++ and consumes H+, affecting pH
- Fe++ can precipitate as carbonates (siderite) or sulfides (FeS), linking Fe to C and S cycles
- Carbonate equilibrium is sensitive to pH changes from Fe reduction

Rate formulations use the Jin and Bethke (2002, 2003) approach:
- Explicitly accounts for electron transport chain kinetics
- Rates depend on thermodynamic driving force (energy available from reaction)
- As conditions approach equilibrium, rates decrease following thermodynamic constraints
- This coupling means ferrihydrite and goethite reduction rates are not independent

Key parameters for Fe-carbonate coupling:
- ferrihydrite_rmax, goethite_rmax: Maximum Fe(III) reduction rates (thermodynamically coupled)
- Root_Respiration: Controls CO2/DIC production → affects pH and carbonate equilibrium
- Aerobic respiration: Competes for organic C, controls redox transition

## DIC Sources and Carbonate Chemistry
Multiple processes contribute to DIC exports:
- Root respiration: Direct CO2 input from plant root metabolism
- Aerobic respiration: Oxidation of organic matter produces CO2/DIC
- Anaerobic respiration (especially Fe and sulfate reduction): Major DIC sources
- Carbonate mineral dissolution/precipitation: Affected by CO2/pH

## Meander-Specific Notes
### MZT Transect
- Observations indicate mostly anoxic conditions
- Fe reduction likely dominates anaerobic respiration
- Tuning focuses on: Fe reduction, carbonate chemistry, root respiration
- Key species: DIC (TIC), pH, Ca++, Fe++, and O2
- Porosity range: +/- 20% from default values

### MCP Transect
- More complete redox gradient observed
- Fe reduction dominates and outcompetes sulfate reduction, nitrate reduction is limited 
- Key species: TIC, pH, Ca++, Fe++, SO4--, NPOC, DO

## Parameter-Species Relationships
- ferrihydrite_rmax, goethite_rmax: Control Fe++ production → affects Fe, pH, TIC
  - These are thermodynamically coupled via Jin-Bethke kinetics
  - Ferrihydrite reduction is more favorable; goethite reduction occurs under more reducing conditions
  - When tuning, consider that increasing goethite_rmax has less effect if conditions
    don't favor goethite reduction thermodynamically
- sulfate_rmax: Controls sulfate reduction → affects SO4--, HS-, TIC
- Root_Respiration: Controls CO2/DIC production → affects TIC, pH, Ca/Mg equilibrium
- Aerobic respiration rates: Control O2 consumption → affects DO, redox zonation
- nitrate_rmax: LOW PRIORITY - minimal impact due to low NO3- concentrations (~1e-6 M)

## Parameter Interactions
- Fe reduction consumes H+, raising pH → affects carbonate saturation
- Higher Fe reduction rates → more Fe++ → potential siderite precipitation
- Ferrihydrite vs goethite: Both use Jin-Bethke kinetics with thermodynamic constraints
  - Ferrihydrite reduction proceeds until near-equilibrium, then slows
  - Goethite reduction only significant under strongly reducing conditions
  - Tuning goethite_rmax alone may have limited effect if ferrihydrite dominates
- Porosity affects residence times: longer residence = more anaerobic processing
- O2 half-saturation controls transition depth from oxic to Fe-reducing conditions
"""


@dataclass
class AgentState:
    """Tracks the agent's current state and history."""
    iteration: int
    phase: str  # 'aerobic'/'aerobic_verify', 'nitrate', 'fe', 'sulfate', 'root_respiration', 'refinement'
    best_objective: float
    best_params: Dict[str, float]
    history: List[Dict[str, Any]]
    insights: List[str]
    current_focus: List[str]  # Parameters currently being focused on
    failed_simulations: int
    phase_iteration: int = 0  # Iterations within current phase
    phase_best_objective: float = float('inf')  # Best objective in current phase
    phase_history: List[Dict[str, Any]] = field(default_factory=list)  # History for current phase


class TuningAgent:
    """
    AI agent for intelligent PFLOTRAN parameter tuning.

    Uses Claude to reason about results and make decisions about
    which parameters to adjust and how.
    """

    SYSTEM_PROMPT = f"""You are an AI agent tuning parameters for a PFLOTRAN reactive transport model.

{DOMAIN_KNOWLEDGE}

Your task is to iteratively reduce the objective function by adjusting
reaction rate parameters. You will receive:
1. Current parameter values
2. Objective function value (lower is better, based on KGE)
3. Per-species metrics (KGE, RMSE for each chemical species)
4. History of previous iterations
5. CURRENT TUNING PHASE and allowed parameters

CRITICAL: This workflow uses SEQUENTIAL TUNING. You must:
1. Focus on the TARGET SPECIES for the current phase
2. ONLY adjust parameters that are allowed in the current phase
3. Set "phase_complete": true when target species show good fit (after minimum iterations)
4. Do NOT try to optimize all species at once - trust the sequential process

Based on this information, you should:
1. Focus on the target species for this phase
2. Propose adjustments ONLY to the phase-allowed parameters
3. Track which parameter changes improve the target species
4. Request phase completion when target species are well-fit

Explain your reasoning in terms of the underlying biogeochemistry.
"""

    def __init__(self,
                 year: str,
                 meander: str,
                 api_key: Optional[str] = None,
                 output_dir: Optional[Path] = None,
                 max_iterations: int = 30,
                 reference_checkpoint: Optional[Path] = None,
                 skip_spin: bool = False):
        """
        Initialize the tuning agent.

        Args:
            year: Simulation year
            meander: Meander identifier
            api_key: Anthropic API key (or set ANTHROPIC_API_KEY env var)
            output_dir: Directory for results
            max_iterations: Maximum number of tuning iterations
            reference_checkpoint: Optional path to a pre-computed spin checkpoint.
                If provided, spin simulations will be skipped and this checkpoint
                will be used instead.
            skip_spin: If True, use fast mode by skipping spin simulations.
                If no reference_checkpoint is provided, one will be automatically
                generated on the first run. This speeds up tuning iterations
                significantly (from ~1-2 hours to ~20-30 minutes per iteration).
        """
        if not HAS_ANTHROPIC:
            raise ImportError(
                "anthropic package required for agent. "
                "Install with: pip install anthropic"
            )

        self.year = year
        self.meander = meander
        self.max_iterations = max_iterations
        self.skip_spin = skip_spin

        # Initialize Anthropic client
        # If api_key is None, the client will use ANTHROPIC_API_KEY env var
        if api_key:
            self.client = anthropic.Anthropic(api_key=api_key)
        else:
            self.client = anthropic.Anthropic()  # Uses env var automatically

        # Output directory
        self.output_dir = output_dir or Path(f'agent_{meander}_{year}')
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Handle reference checkpoint / skip_spin mode
        self.reference_checkpoint = self._setup_reference_checkpoint(reference_checkpoint)

        # Initialize simulation components
        self.runner = SimulationRunner(
            year=year,
            meander=meander,
            reference_checkpoint=self.reference_checkpoint
        )
        self.objective_func = ObjectiveFunction(year=year, meander=meander)

        if self.reference_checkpoint:
            logger.info(f"Using reference checkpoint: {self.reference_checkpoint}")
            logger.info("Spin simulations will be skipped - transient only mode")

        # Get meander-specific parameter list for tuning
        self.param_names = get_parameters_for_meander(meander)
        self.bounds = get_parameter_bounds(self.param_names, log_scale=False)
        self.defaults = {
            name: PARAM_BY_NAME[name].default
            for name in self.param_names
        }

        # Get meander-specific species list for tuning
        self.tuning_species = get_species_for_meander(meander)

        # Get simulation config for visualization
        config_key = (year, self.meander)
        sim_config = SIMULATION_CONFIGS[config_key]
        self.startdate = np.datetime64(sim_config['startdate'])

        # Initialize visualizer for figure generation
        self.visualizer = TuningVisualizer(
            year=year,
            meander=meander,
            output_dir=self.output_dir,
            startdate=self.startdate
        )

        logger.info(f"Tuning {meander} with {len(self.param_names)} parameters: {self.param_names}")
        logger.info(f"Evaluating against species: {self.tuning_species}")

        # Initialize state - starting phase depends on meander
        # MCP: anaerobic system, start with aerobic_verify (just check DO is consumed)
        # MZT: start with aerobic tuning
        starting_phase = MEANDER_STARTING_PHASE.get(self.meander.lower(), 'aerobic')
        starting_params = TUNING_PHASES[starting_phase].get('parameters', [])

        self.state = AgentState(
            iteration=0,
            phase=starting_phase,
            best_objective=float('inf'),
            best_params=self.defaults.copy(),
            history=[],
            insights=[],
            current_focus=starting_params if starting_params else [],
            failed_simulations=0,
            phase_iteration=0,
            phase_best_objective=float('inf'),
            phase_history=[]
        )

        logger.info(f"Meander {meander}: starting with phase '{starting_phase}'")

    def _setup_reference_checkpoint(self, reference_checkpoint: Optional[Path]) -> Optional[Path]:
        """
        Set up the reference checkpoint for fast mode.

        If a checkpoint path is provided, validates it exists.
        If skip_spin is True but no checkpoint provided, looks for default location
        and generates one if not found.

        Args:
            reference_checkpoint: User-provided checkpoint path, or None

        Returns:
            Path to the reference checkpoint, or None if not using fast mode.
        """
        from .simulation_runner import generate_reference_checkpoint

        # If explicit checkpoint provided, use it
        if reference_checkpoint:
            checkpoint_path = Path(reference_checkpoint)
            if not checkpoint_path.exists():
                raise FileNotFoundError(f"Reference checkpoint not found: {checkpoint_path}")
            return checkpoint_path

        # If skip_spin not enabled, don't use reference checkpoint
        if not self.skip_spin:
            return None

        # skip_spin enabled but no checkpoint provided - look for default or generate
        simulations_dir = Path('/home/christiandewey/Code/dewey-etal_meanders/pflotran/simulations')
        subdir = f"{self.meander}{self.year[-2:]}"
        default_checkpoint = simulations_dir / subdir / 'reference_spin_checkpoint.chk'

        if default_checkpoint.exists():
            logger.info(f"Found existing reference checkpoint: {default_checkpoint}")
            return default_checkpoint

        # Need to generate reference checkpoint
        logger.info("No reference checkpoint found - generating one (this may take 1-2 hours)...")
        logger.info("This only needs to be done once per meander/year combination.")

        checkpoint_path = generate_reference_checkpoint(
            year=self.year,
            meander=self.meander,
            output_path=default_checkpoint
        )

        if checkpoint_path is None:
            logger.error("Failed to generate reference checkpoint")
            logger.warning("Falling back to full spin mode for each iteration")
            return None

        return checkpoint_path

    def _call_claude(self,
                     user_message: str,
                     max_tokens: int = 2000) -> str:
        """Call Claude API with the tuning context."""
        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            system=self.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}]
        )
        return response.content[0].text

    def _format_aerobic_verify_prompt(self,
                                        params: Dict[str, float],
                                        results: Dict[str, Any],
                                        do_verification: Optional[Dict[str, Any]] = None) -> str:
        """Format prompt for aerobic_verify phase (MCP meander only)."""
        msg = f"""
## Iteration {self.state.iteration} (Phase: AEROBIC_VERIFY)

### ANAEROBIC CONDITIONS VERIFICATION (MCP Meander)

This is the MCP meander which is known to be an anaerobic system. We are NOT tuning
aerobic respiration parameters - instead, we verify that the default reaction rates
are sufficient to consume all oxygen.

**Verification Criteria:**
- DO (dissolved oxygen) should be < 1e-6 M
- Except within 0.5 m of the upstream boundary (where oxygenated river water enters)

"""
        if do_verification:
            verified = do_verification.get('verified', False)
            error_msg = do_verification.get('error')
            status = "✓ PASSED" if verified else ("✗ ERROR" if error_msg else "✗ FAILED")

            if error_msg:
                msg += f"""### DO Verification Results: {status}

**Error during verification:** {error_msg}

Unable to verify anaerobic conditions. Proceeding with tuning.

"""
            else:
                max_do = do_verification.get('max_interior_do', 0)
                mean_do = do_verification.get('mean_interior_do', 0)
                threshold = do_verification.get('threshold', 1e-6)
                boundary = do_verification.get('boundary_distance', 0.5)
                location_results = do_verification.get('location_results', [])

                msg += f"""### DO Verification Results: {status}

**Threshold:** DO < {threshold:.0e} M at observation wells beyond {boundary}m

| Location | Distance (m) | DO (M) | Status |
|----------|--------------|--------|--------|
"""
                for loc in location_results:
                    do_val = f"{loc['do_value']:.2e}" if loc['do_value'] is not None else "N/A"
                    msg += f"| {loc['location']} | {loc['distance']} | {do_val} | {loc['status']} |\n"

                msg += f"""
**Summary:**
- Maximum DO at interior wells: {max_do:.2e} M
- Mean DO at interior wells: {mean_do:.2e} M

"""
            if verified:
                msg += """**Anaerobic conditions confirmed.** The default aerobic respiration rates are
sufficient to consume oxygen. Proceeding to next phase (denitrification).

"""
            else:
                msg += f"""**WARNING: Anaerobic conditions NOT fully established.**
{do_verification.get('message', '')}

This may indicate an issue with the simulation. However, since MCP is known to be
anaerobic, we will proceed with tuning and monitor DO levels.

"""
        else:
            msg += "DO verification data not available.\n\n"

        msg += f"""### Current Aerobic Respiration Parameters (NOT being tuned)
```
aerobic_rate_constant: {params.get('aerobic_rate_constant', 'N/A')}
aerobic_o2_half_sat: {params.get('aerobic_o2_half_sat', 'N/A')}
aerobic_soc_half_sat: {params.get('aerobic_soc_half_sat', 'N/A')}
```

### Objective Value
{results['objective']:.4f} (lower is better)

### Per-Species Metrics
| Species | KGE | Weight | Contribution |
|---------|-----|--------|--------------|
"""
        for species, metrics in results.get('species_metrics', {}).items():
            if species not in self.tuning_species:
                continue
            kge = metrics.get('KGE', float('nan'))
            weight = SPECIES_WEIGHTS.get(species, 0.5)
            contrib = metrics.get('weighted_loss', float('nan'))
            msg += f"| {species} | {kge:.3f} | {weight} | {contrib:.3f} |\n"

        msg += f"""
This is a verification phase only. No parameter adjustments are needed.

Respond with:
```json
{{
    "analysis": "Assessment of anaerobic conditions and DO consumption",
    "reasoning": "Whether the system is properly anaerobic",
    "adjustments": {{}},
    "phase_complete": true,
    "insight": "Observation about DO levels and anaerobic status"
}}
```
"""
        return msg

    def _get_phase_parameters(self) -> List[str]:
        """Get the list of parameters available for the current tuning phase."""
        phase_config = TUNING_PHASES.get(self.state.phase, {})
        phase_params = phase_config.get('parameters')

        if phase_params is None:
            # Refinement phase - all parameters available
            return self.param_names

        # Filter to only include parameters that exist for this meander
        return [p for p in phase_params if p in self.param_names]

    def _format_results_for_agent(self,
                                   params: Dict[str, float],
                                   results: Dict[str, Any],
                                   do_verification: Optional[Dict[str, Any]] = None) -> str:
        """Format simulation results for the agent to analyze."""
        phase_config = TUNING_PHASES.get(self.state.phase, {})
        phase_params = self._get_phase_parameters()
        target_species = phase_config.get('target_species') or self.tuning_species

        # Special handling for aerobic_verify phase (MCP meander)
        if self.state.phase == 'aerobic_verify':
            return self._format_aerobic_verify_prompt(params, results, do_verification)

        msg = f"""
## Iteration {self.state.iteration} (Phase: {self.state.phase.upper()}, Phase Iteration: {self.state.phase_iteration})

### CURRENT TUNING PHASE: {self.state.phase.upper()}
{phase_config.get('description', '')}

**IMPORTANT: You can ONLY adjust these parameters in this phase:**
{', '.join(phase_params) if phase_params else 'All parameters'}

**Target species for this phase:** {', '.join(target_species)}

### Current Parameters (all)
```
{json.dumps({k: f"{v:.2e}" for k, v in params.items()}, indent=2)}
```

### Objective Value
{results['objective']:.4f} (lower is better)

### Per-Species Metrics (tuning on: {', '.join(self.tuning_species)})
| Species | KGE | Weight | Contribution | Phase Target |
|---------|-----|--------|--------------|--------------|
"""
        for species, metrics in results.get('species_metrics', {}).items():
            # Only show species that are in the tuning list
            if species not in self.tuning_species:
                continue
            kge = metrics.get('KGE', float('nan'))
            weight = SPECIES_WEIGHTS.get(species, 0.5)
            contrib = metrics.get('weighted_loss', float('nan'))
            is_target = "**YES**" if species in target_species else ""
            msg += f"| {species} | {kge:.3f} | {weight} | {contrib:.3f} | {is_target} |\n"

        msg += f"""
### History Summary
- Total iterations: {len(self.state.history)}
- Phase iterations: {self.state.phase_iteration}
- Best objective overall: {self.state.best_objective:.4f}
- Best objective this phase: {self.state.phase_best_objective:.4f}
- Failed simulations: {self.state.failed_simulations}

### Phase Progress
- Current phase: {self.state.phase}
- Min iterations for phase: {phase_config.get('min_iterations', 'N/A')}
- Max iterations for phase: {phase_config.get('max_iterations', 'N/A')}
- Next phase: {phase_config.get('next_phase', 'None (final phase)')}

### Available Parameters for This Phase
"""
        for name in phase_params:
            if name in PARAM_BY_NAME:
                p = PARAM_BY_NAME[name]
                current_val = params.get(name, p.default)
                msg += f"- {name}: current={current_val:.2e}, bounds=[{p.bounds[0]:.2e}, {p.bounds[1]:.2e}]\n"

        msg += f"""
### Previous Insights
{chr(10).join('- ' + i for i in self.state.insights[-5:])}

Based on these metrics, focus on improving the TARGET SPECIES for this phase.
Adjust ONLY the parameters available in this phase.

Propose specific parameter adjustments in this JSON format:

```json
{{
    "analysis": "Analysis of target species metrics and what adjustments are needed",
    "reasoning": "Biogeochemical justification for proposed parameter changes",
    "adjustments": {{
        "parameter_name": new_value,
        ...
    }},
    "phase_complete": false,
    "insight": "Key observation about parameter-species relationships from this iteration"
}}
```

Set "phase_complete": true if you believe this phase has achieved good results for its target species
and we should move to the next phase. Only do this after at least {phase_config.get('min_iterations', 3)} iterations.

Only adjust parameters from the current phase list. Values must be within bounds.
"""
        return msg

    def _parse_agent_response(self,
                               response: str) -> Tuple[Dict[str, float], Dict[str, Any]]:
        """Parse the agent's response to extract parameter adjustments."""
        # Find JSON block in response
        import re
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)

        if not json_match:
            # Try to find raw JSON
            json_match = re.search(r'\{[^{}]*"adjustments"[^{}]*\{[^{}]*\}[^{}]*\}',
                                   response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                logger.warning("Could not parse agent response, using defaults")
                return {}, {"analysis": "Parse error", "insight": "", "phase_complete": False}
        else:
            json_str = json_match.group(1)

        try:
            parsed = json.loads(json_str)
            adjustments = parsed.get('adjustments', {})

            # Get phase-allowed parameters
            phase_params = self._get_phase_parameters()

            # Validate adjustments are within bounds AND in current phase
            valid_adjustments = {}
            for name, value in adjustments.items():
                # Check if parameter is allowed in current phase
                if name not in phase_params:
                    logger.warning(f"Parameter {name} not allowed in phase '{self.state.phase}', skipping")
                    continue

                if name in self.param_names:
                    idx = self.param_names.index(name)
                    lower, upper = self.bounds[idx]
                    value = float(value)
                    if lower <= value <= upper:
                        valid_adjustments[name] = value
                    else:
                        logger.warning(f"Parameter {name}={value} outside bounds, clipping")
                        valid_adjustments[name] = np.clip(value, lower, upper)

            return valid_adjustments, parsed

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return {}, {"analysis": "Parse error", "insight": "", "phase_complete": False}

    def _verify_anaerobic_conditions(self, h5_path: Path) -> Dict[str, Any]:
        """
        Verify that DO is consumed (anaerobic conditions) for MCP meander.

        Checks DO at observation well locations (excluding the first location
        at 0.5m which is at the upstream boundary). DO should be < 1e-6 M
        at interior observation points.

        Args:
            h5_path: Path to simulation HDF5 output

        Returns:
            Dictionary with verification results
        """
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
        from processing.pflotran import PflotranProcessor

        try:
            do_threshold = 1.0e-6  # M
            boundary_distance = 0.5  # m - first observation location to skip

            meander_code = 'MZ' if 'mz' in self.meander else 'MC'
            processor = PflotranProcessor(
                h5_path=str(h5_path),
                meander=meander_code,
                perpendicular_axis='x'
            )

            # Get observation locations for this meander
            config = processor.config
            distances = config['distances']  # [0.5, 16, 31, 46, 60] for MCP
            depths = config['depths']
            obs_locs = config['obs_locs']

            # Find O2 component name in simulation
            o2_component = None
            o2_names = ['O2(aq) [M]', 'Total_O2(aq) [M]']
            for name in o2_names:
                if hasattr(processor, 'component_list') and name in processor.component_list:
                    o2_component = name
                    break

            if o2_component is None:
                available = list(processor.component_list)[:10] if hasattr(processor, 'component_list') else []
                return {
                    'verified': False,
                    'error': f'O2 component not found. Available: {available}'
                }

            # Get DO time series at observation locations
            results, times = processor.get_histories(
                depths=depths,
                components=[o2_component]
            )

            # Check DO at each observation location (skip first at boundary)
            location_results = []
            all_below_threshold = True

            for i, (dist, depth, loc_name) in enumerate(zip(distances, depths, obs_locs)):
                if dist <= boundary_distance:
                    # Skip boundary location
                    location_results.append({
                        'location': loc_name,
                        'distance': dist,
                        'status': 'skipped (boundary)',
                        'do_value': None
                    })
                    continue

                # Get DO at this location (use mean of last 10% of simulation)
                if dist in results and o2_component in results[dist]:
                    do_timeseries = results[dist][o2_component]
                    # Use mean of last 10% of timesteps
                    n_last = max(1, len(do_timeseries) // 10)
                    do_mean = float(np.mean(do_timeseries[-n_last:]))

                    is_below = do_mean < do_threshold
                    if not is_below:
                        all_below_threshold = False

                    location_results.append({
                        'location': loc_name,
                        'distance': dist,
                        'do_value': do_mean,
                        'below_threshold': is_below,
                        'status': 'OK' if is_below else 'HIGH DO'
                    })
                else:
                    location_results.append({
                        'location': loc_name,
                        'distance': dist,
                        'status': 'no data',
                        'do_value': None
                    })

            # Calculate summary statistics for interior locations
            interior_do_values = [r['do_value'] for r in location_results
                                  if r['do_value'] is not None]

            if not interior_do_values:
                return {'verified': False, 'error': 'No DO data at observation locations'}

            max_do = max(interior_do_values)
            mean_do = np.mean(interior_do_values)

            # Build message
            msg_parts = ["DO at observation wells:"]
            for r in location_results:
                if r['do_value'] is not None:
                    msg_parts.append(f"  {r['location']} ({r['distance']}m): {r['do_value']:.2e} M [{r['status']}]")
                else:
                    msg_parts.append(f"  {r['location']} ({r['distance']}m): {r['status']}")

            return {
                'verified': all_below_threshold,
                'max_interior_do': max_do,
                'mean_interior_do': mean_do,
                'threshold': do_threshold,
                'boundary_distance': boundary_distance,
                'location_results': location_results,
                'o2_component': o2_component,
                'message': '\n'.join(msg_parts)
            }

        except Exception as e:
            import traceback
            logger.error(f"Error verifying anaerobic conditions: {e}")
            logger.error(traceback.format_exc())
            return {'verified': False, 'error': str(e)}

    def _check_phase_transition(self, agent_requested: bool) -> bool:
        """
        Check if we should transition to the next tuning phase.

        Args:
            agent_requested: Whether the agent requested phase completion

        Returns:
            True if phase should transition, False otherwise
        """
        phase_config = TUNING_PHASES.get(self.state.phase, {})
        min_iters = phase_config.get('min_iterations', 3)
        max_iters = phase_config.get('max_iterations')
        next_phase = phase_config.get('next_phase')

        # Can't transition if there's no next phase
        if next_phase is None:
            return False

        # Must complete minimum iterations
        if self.state.phase_iteration < min_iters:
            return False

        # Transition if agent requested and minimum met
        if agent_requested:
            logger.info(f"Agent requested phase completion after {self.state.phase_iteration} iterations")
            return True

        # Transition if maximum iterations reached
        if max_iters and self.state.phase_iteration >= max_iters:
            logger.info(f"Phase '{self.state.phase}' reached maximum iterations ({max_iters})")
            return True

        return False

    def _transition_to_next_phase(self):
        """Transition to the next tuning phase."""
        phase_config = TUNING_PHASES.get(self.state.phase, {})
        next_phase = phase_config.get('next_phase')

        if next_phase is None:
            logger.info("No next phase - staying in current phase")
            return

        logger.info("=" * 60)
        logger.info(f"PHASE TRANSITION: {self.state.phase.upper()} -> {next_phase.upper()}")
        logger.info("=" * 60)

        # Record phase summary
        self.state.insights.append(
            f"Phase '{self.state.phase}' completed after {self.state.phase_iteration} iterations. "
            f"Best objective in phase: {self.state.phase_best_objective:.4f}"
        )

        # Transition to next phase
        old_phase = self.state.phase
        self.state.phase = next_phase
        self.state.phase_iteration = 0
        self.state.phase_best_objective = float('inf')
        self.state.phase_history = []

        # Update current focus to new phase parameters
        new_phase_config = TUNING_PHASES.get(next_phase, {})
        new_params = new_phase_config.get('parameters')
        if new_params:
            self.state.current_focus = [p for p in new_params if p in self.param_names]
        else:
            self.state.current_focus = self.param_names

        logger.info(f"New phase parameters: {self.state.current_focus}")

    def _run_iteration(self, params: Dict[str, float]) -> Tuple[Dict[str, Any], Optional[Path]]:
        """Run a single simulation and evaluate results.

        Returns:
            Tuple of (results_dict, h5_path) where h5_path is the simulation output file
        """
        run_id = f"agent_{self.state.iteration:03d}"

        logger.info(f"Running simulation {run_id}")
        h5_path, metadata = self.runner.run_simulation(
            param_values=params,
            run_id=run_id,
            keep_files=True  # Keep files for visualization
        )

        if h5_path is None:
            self.state.failed_simulations += 1
            return {
                'objective': self.objective_func.penalty_value,
                'error': metadata.get('error', 'Unknown error'),
                'species_metrics': {},
                'component_results': {}
            }, None

        results = compute_objective_with_details(
            h5_path, year=self.year, meander=self.meander
        )
        return results, h5_path

    def run(self,
            initial_params: Optional[Dict[str, float]] = None,
            resume: bool = False) -> Dict[str, Any]:
        """
        Run the agentic tuning workflow.

        Args:
            initial_params: Starting parameter values (defaults if None)
            resume: Whether to resume from checkpoint

        Returns:
            Dictionary with final results
        """
        if resume:
            self._load_checkpoint()

        # Initialize parameters
        current_params = initial_params or self.defaults.copy()

        logger.info("="*60)
        logger.info("Starting Agentic Parameter Tuning")
        logger.info("="*60)

        best_h5_path = None

        while self.state.iteration < self.max_iterations:
            self.state.iteration += 1
            self.state.phase_iteration += 1
            logger.info(f"\n=== Iteration {self.state.iteration}/{self.max_iterations} "
                       f"(Phase: {self.state.phase}, Phase Iter: {self.state.phase_iteration}) ===")

            # Run simulation with current parameters
            results, h5_path = self._run_iteration(current_params)

            # Check for improvement (global)
            if results['objective'] < self.state.best_objective:
                self.state.best_objective = results['objective']
                self.state.best_params = current_params.copy()
                best_h5_path = h5_path
                logger.info(f"New best overall! Objective: {results['objective']:.4f}")

            # Check for improvement (phase)
            if results['objective'] < self.state.phase_best_objective:
                self.state.phase_best_objective = results['objective']
                logger.info(f"New best for phase '{self.state.phase}'! Objective: {results['objective']:.4f}")

            # Record history (global and phase)
            history_entry = {
                'iteration': self.state.iteration,
                'phase': self.state.phase,
                'phase_iteration': self.state.phase_iteration,
                'params': current_params.copy(),
                'objective': results['objective'],
                'species_metrics': results.get('species_metrics', {}),
                'timestamp': datetime.now().isoformat()
            }
            self.state.history.append(history_entry)
            self.state.phase_history.append(history_entry)

            # Generate figures for this iteration
            if h5_path is not None:
                try:
                    fig_paths = self._generate_iteration_figures(h5_path, results)
                    if fig_paths:
                        logger.info(f"Saved {len(fig_paths)} figures for iteration {self.state.iteration}")
                    else:
                        logger.warning(f"No figures generated for iteration {self.state.iteration}")
                except Exception as e:
                    import traceback
                    logger.error(f"Failed to generate figures for iteration {self.state.iteration}: {e}")
                    logger.error(traceback.format_exc())

            # Early stopping if objective is below threshold
            if results['objective'] < 0.4:
                logger.info("Objective below threshold (< 0.4), stopping early")
                break

            # For aerobic_verify phase, run DO verification
            do_verification = None
            if self.state.phase == 'aerobic_verify' and h5_path is not None:
                logger.info("Running anaerobic conditions verification for MCP...")
                do_verification = self._verify_anaerobic_conditions(h5_path)
                if do_verification.get('verified', False):
                    logger.info("✓ Anaerobic conditions verified - DO properly consumed")
                    self.state.insights.append(
                        f"Anaerobic verification passed: max interior DO = "
                        f"{do_verification.get('max_interior_do', 0):.2e} M"
                    )
                else:
                    logger.warning(f"⚠ Anaerobic verification: {do_verification.get('message', 'Check failed')}")

            # Ask agent to analyze and propose adjustments
            prompt = self._format_results_for_agent(current_params, results, do_verification)

            logger.info("Consulting agent for next parameters...")
            agent_response = self._call_claude(prompt)

            # Parse agent's suggestions
            adjustments, metadata = self._parse_agent_response(agent_response)

            # Log agent's reasoning
            if 'analysis' in metadata:
                logger.info(f"Agent analysis: {metadata['analysis'][:200]}...")
            if 'insight' in metadata:
                self.state.insights.append(metadata['insight'])
                logger.info(f"Agent insight: {metadata['insight']}")

            # Check for phase transition
            agent_requested_complete = metadata.get('phase_complete', False)
            if self._check_phase_transition(agent_requested_complete):
                self._transition_to_next_phase()

            # Apply adjustments
            if adjustments:
                for name, value in adjustments.items():
                    logger.info(f"  Adjusting {name}: {current_params.get(name, 'N/A'):.2e} → {value:.2e}")
                    current_params[name] = value
            elif self.state.phase != 'aerobic_verify':
                # If no adjustments, try small random perturbations within phase parameters
                # Skip this for aerobic_verify phase which has no tunable parameters
                logger.info("No adjustments proposed, trying random exploration within phase")
                phase_params = self._get_phase_parameters()
                if phase_params:
                    n_to_adjust = min(2, len(phase_params))
                    for name in np.random.choice(phase_params, size=n_to_adjust, replace=False):
                        if name in PARAM_BY_NAME:
                            p = PARAM_BY_NAME[name]
                            lower, upper = p.bounds
                            # Random value in log space
                            log_val = np.random.uniform(np.log10(lower), np.log10(upper))
                            current_params[name] = 10 ** log_val
                            logger.info(f"  Random adjustment: {name} = {current_params[name]:.2e}")

            # Checkpoint
            if self.state.iteration % 5 == 0:
                self._save_checkpoint()

        # Final save
        self._save_checkpoint()
        self._save_final_results()

        # Generate summary figures
        try:
            self._generate_summary_figures(best_h5_path)
        except Exception as e:
            logger.warning(f"Failed to generate summary figures: {e}")

        return {
            'best_objective': self.state.best_objective,
            'best_params': self.state.best_params,
            'n_iterations': self.state.iteration,
            'insights': self.state.insights,
            'history': self.state.history,
            'figures_dir': str(self.visualizer.figures_dir)
        }

    def _save_checkpoint(self):
        """Save agent state to checkpoint."""
        checkpoint = {
            'state': asdict(self.state),
            'timestamp': datetime.now().isoformat()
        }

        with open(self.output_dir / 'checkpoint.json', 'w') as f:
            json.dump(checkpoint, f, indent=2, default=str)

        logger.info(f"Checkpoint saved to {self.output_dir}")

    def _load_checkpoint(self):
        """Load agent state from checkpoint."""
        checkpoint_path = self.output_dir / 'checkpoint.json'
        if checkpoint_path.exists():
            with open(checkpoint_path) as f:
                checkpoint = json.load(f)

            state_dict = checkpoint['state']

            # Handle migration from old checkpoints without phase fields
            if 'phase_iteration' not in state_dict:
                state_dict['phase_iteration'] = 0
            if 'phase_best_objective' not in state_dict:
                state_dict['phase_best_objective'] = float('inf')
            if 'phase_history' not in state_dict:
                state_dict['phase_history'] = []

            # Map old phase names to new sequential phases
            old_phase = state_dict.get('phase', 'aerobic')
            if old_phase in ('exploration', 'exploitation', 'diagnosis'):
                # Start from beginning of sequential tuning based on meander
                state_dict['phase'] = MEANDER_STARTING_PHASE.get(self.meander.lower(), 'aerobic')

            self.state = AgentState(**state_dict)

            # Update current focus based on loaded phase
            phase_config = TUNING_PHASES.get(self.state.phase, {})
            phase_params = phase_config.get('parameters')
            if phase_params:
                self.state.current_focus = [p for p in phase_params if p in self.param_names]

            logger.info(f"Resumed from iteration {self.state.iteration}, phase: {self.state.phase}")

    def _save_final_results(self):
        """Save final results and insights."""
        # Get validation configuration (sampling locations and depths)
        validation_config = self._get_validation_config()

        # Summarize phase progression
        phase_summary = {}
        for entry in self.state.history:
            phase = entry.get('phase', 'unknown')
            if phase not in phase_summary:
                phase_summary[phase] = {'iterations': 0, 'best_objective': float('inf')}
            phase_summary[phase]['iterations'] += 1
            if entry['objective'] < phase_summary[phase]['best_objective']:
                phase_summary[phase]['best_objective'] = entry['objective']

        results = {
            'best_objective': self.state.best_objective,
            'best_params': self.state.best_params,
            'n_iterations': self.state.iteration,
            'final_phase': self.state.phase,
            'phase_summary': phase_summary,
            'insights': self.state.insights,
            'failed_simulations': self.state.failed_simulations,
            'history': self.state.history,
            'validation_config': validation_config
        }

        with open(self.output_dir / 'final_results.json', 'w') as f:
            json.dump(results, f, indent=2, default=str)

        # Also save just the best parameters
        with open(self.output_dir / 'best_params.json', 'w') as f:
            json.dump(self.state.best_params, f, indent=2)

        # Save insights as markdown with validation config
        with open(self.output_dir / 'insights.md', 'w') as f:
            f.write("# Tuning Report\n\n")

            # Validation configuration section
            f.write("## Validation Configuration\n\n")
            f.write(f"**Meander:** {validation_config['meander']}\n")
            f.write(f"**Year:** {validation_config['year']}\n")
            f.write(f"**Species evaluated:** {', '.join(self.tuning_species)}\n\n")

            f.write("### Observation Locations and Sampling Depths\n\n")
            f.write("| Well | Distance (m) | Depth (m) | Grid Cell (y, z) |\n")
            f.write("|------|--------------|-----------|------------------|\n")
            for loc_info in validation_config['locations']:
                f.write(f"| {loc_info['well']} | {loc_info['distance']} | {loc_info['depth']} | ({loc_info['grid_cell_y']}, {loc_info['grid_cell_z']}) |\n")
            f.write("\n")

            f.write(f"**Grid dimensions:** {validation_config['grid_dims']}\n")
            f.write(f"**Cell size:** dy={validation_config['cell_size_y']}m, dz={validation_config['cell_size_z']}m\n\n")

            # Phase progression section
            f.write("## Phase Progression\n\n")
            f.write("The sequential tuning strategy used these phases:\n\n")
            f.write("| Phase | Iterations | Best Objective |\n")
            f.write("|-------|------------|----------------|\n")
            for phase, info in phase_summary.items():
                f.write(f"| {phase} | {info['iterations']} | {info['best_objective']:.4f} |\n")
            f.write("\n")
            f.write(f"**Final phase reached:** {self.state.phase}\n\n")

            # Agent insights section
            f.write("## Agent Insights\n\n")
            for i, insight in enumerate(self.state.insights, 1):
                f.write(f"{i}. {insight}\n\n")

        logger.info(f"Final results saved to {self.output_dir}")

    def _get_validation_config(self) -> Dict[str, Any]:
        """Get validation configuration including sampling depths and grid cells."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
        from processing.pflotran import PflotranProcessor

        meander_code = 'MZ' if 'mz' in self.meander else 'MC'

        # Get meander configuration
        config = PflotranProcessor.MEANDER_CONFIG.get(meander_code, {})
        distances = config.get('distances', [])
        depths = config.get('depths', [])
        obs_locs = config.get('obs_locs', [])

        # Grid parameters (from PFLOTRAN template)
        dy = 0.5  # Cell size in y-direction (m)
        dz = 0.10  # Cell size in z-direction (m)
        ny = 122 if meander_code == 'MC' else 108
        nz = 26

        # Calculate grid cells for each location
        locations = []
        for i, (well, dist, depth) in enumerate(zip(obs_locs, distances, depths)):
            grid_y = int(dist / dy)
            grid_z = int(depth / dz)
            locations.append({
                'well': well,
                'distance': dist,
                'depth': depth,
                'grid_cell_y': grid_y,
                'grid_cell_z': grid_z
            })

        return {
            'meander': self.meander,
            'year': self.year,
            'locations': locations,
            'grid_dims': f"ny={ny}, nz={nz}",
            'cell_size_y': dy,
            'cell_size_z': dz
        }

    def _generate_iteration_figures(self,
                                     h5_path: Path,
                                     results: Dict[str, Any]) -> List[Path]:
        """Generate diagnostic figures for a single iteration."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
        from processing.pflotran import PflotranProcessor

        # Load observations
        obs_dir = Path('/home/christiandewey/Code/dewey-etal_meanders/data/observational/porewater')
        meander_prefix = 'mz' if 'mz' in self.meander else 'mc'
        import pandas as pd
        obs_file = obs_dir / f'{meander_prefix}_{self.year}_porewater.csv'
        chem_obs = pd.read_csv(obs_file)
        chem_obs['Date'] = pd.to_datetime(chem_obs['Date'], format='mixed')

        # Initialize processor
        meander_code = 'MZ' if 'mz' in self.meander else 'MC'
        processor = PflotranProcessor(
            h5_path=str(h5_path),
            meander=meander_code,
            perpendicular_axis='x'
        )

        # Calculate KGE to get observed/simulated arrays
        kge_results = processor.calculate_kge(
            startdate=self.startdate,
            chem_obs=chem_obs,
            print_summary=False
        )

        # Extract component results with obs/sim arrays
        # kge_results has structure: {'components': {...}, 'summary': ..., 'n_components': ...}
        component_results = {}
        components_dict = kge_results.get('components', {})
        for comp_name, comp_data in components_dict.items():
            if isinstance(comp_data, dict) and 'observed' in comp_data:
                obs_name = comp_data.get('obs_component', comp_name)
                component_results[obs_name] = comp_data

        logger.info(f"Found {len(component_results)} components with obs/sim data: {list(component_results.keys())}")

        if not component_results:
            logger.warning("No component results found for figure generation")
            return []

        # Generate figures - pass processor and observations for history plots
        return self.visualizer.generate_iteration_figures(
            iteration=self.state.iteration,
            kge_results={'component_results': component_results,
                         'species_metrics': results.get('species_metrics', {})},
            objective=results['objective'],
            processor=processor,
            chem_obs=chem_obs
        )

    def _generate_summary_figures(self, best_h5_path: Optional[Path]) -> List[Path]:
        """Generate summary figures for the complete tuning run."""
        best_kge_results = None
        processor = None
        chem_obs = None

        if best_h5_path is not None:
            try:
                import sys
                sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
                from processing.pflotran import PflotranProcessor
                import pandas as pd

                # Load observations
                obs_dir = Path('/home/christiandewey/Code/dewey-etal_meanders/data/observational/porewater')
                meander_prefix = 'mz' if 'mz' in self.meander else 'mc'
                obs_file = obs_dir / f'{meander_prefix}_{self.year}_porewater.csv'
                chem_obs = pd.read_csv(obs_file)
                chem_obs['Date'] = pd.to_datetime(chem_obs['Date'], format='mixed')

                # Initialize processor
                meander_code = 'MZ' if 'mz' in self.meander else 'MC'
                processor = PflotranProcessor(
                    h5_path=str(best_h5_path),
                    meander=meander_code,
                    perpendicular_axis='x'
                )

                # Calculate KGE for best results
                best_kge_results = processor.calculate_kge(
                    startdate=self.startdate,
                    chem_obs=chem_obs,
                    print_summary=False
                )
            except Exception as e:
                logger.warning(f"Could not load best results for summary figures: {e}")

        return self.visualizer.generate_summary_figures(
            history=self.state.history,
            best_kge_results=best_kge_results,
            processor=processor,
            chem_obs=chem_obs
        )


def run_agent_tuning(year: str = '2019',
                     meander: str = 'mzt',
                     max_iterations: int = 30,
                     api_key: Optional[str] = None,
                     reference_checkpoint: Optional[Path] = None,
                     skip_spin: bool = False,
                     **kwargs) -> Dict[str, Any]:
    """
    Run the agentic parameter tuning workflow.

    Args:
        year: Simulation year
        meander: Meander identifier
        max_iterations: Maximum iterations
        api_key: Anthropic API key
        reference_checkpoint: Optional path to a pre-computed spin checkpoint.
            If provided, spin simulations will be skipped and this checkpoint
            will be used instead.
        skip_spin: If True, use fast mode by skipping spin simulations.
            If no reference_checkpoint is provided, one will be automatically
            generated on the first run. This speeds up tuning iterations
            significantly (from ~1-2 hours to ~20-30 minutes per iteration).
        **kwargs: Additional arguments to TuningAgent

    Returns:
        Results dictionary
    """
    agent = TuningAgent(
        year=year,
        meander=meander,
        max_iterations=max_iterations,
        api_key=api_key,
        reference_checkpoint=reference_checkpoint,
        skip_spin=skip_spin,
        **kwargs
    )

    return agent.run()
