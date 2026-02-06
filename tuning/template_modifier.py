"""
Template modifier for PFLOTRAN chemistry template files.

This module provides functions to parse the chemistry template, identify
$T-marked parameters, and replace parameter values for tuning.
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import numpy as np

from .config import PARAMETERS, PARAM_BY_NAME, Parameter


class TemplateModifier:
    """
    Parse and modify PFLOTRAN chemistry templates with $T markers.

    The $T marker indicates a tunable parameter line in the template.
    Format: $T KEYWORD value
    """

    # Pattern to match $T-marked parameter lines
    # Captures: keyword, mantissa, exponent (if present)
    PARAM_PATTERN = re.compile(
        r'(\$T)\s+(\w+)\s+'  # $T marker and keyword
        r'(-?\d+\.?\d*)'     # mantissa (e.g., 1.0, 2.5, -12.1)
        r'(?:[dDeE]([+-]?\d+))?'  # optional exponent (d-10, e-10, etc.)
        r'(.*?)$',           # rest of line (comments, etc.)
        re.MULTILINE
    )

    def __init__(self, template_path: Path):
        """
        Initialize the template modifier.

        Args:
            template_path: Path to the TEMPLATE-chemistry.txt file.
        """
        self.template_path = Path(template_path)
        self.original_content = self.template_path.read_text()
        self.current_content = self.original_content

        # Parse the template to find all $T markers and their context
        self._parse_template()

    def _parse_template(self):
        """Parse template to identify all $T-marked parameters and their context."""
        self.param_locations: Dict[str, List[dict]] = {}

        # Find all $T markers
        lines = self.current_content.split('\n')
        current_block = None

        for i, line in enumerate(lines):
            # Track which block we're in (reaction sandbox blocks, etc.)
            stripped = line.strip()

            # Identify block starts
            if 'Root_Respiration' in stripped and not stripped.startswith('!'):
                current_block = 'Root_Respiration'
            elif 'Fe++ oxidation' in stripped or ('Fe++' in stripped and 'GENERAL_REACTION' in lines[i+1] if i+1 < len(lines) else False):
                current_block = 'Fe_oxidation'
            elif 'HS- oxidation' in stripped:
                current_block = 'HS_oxidation'
            elif 'Aerobic respiration' in stripped or 'MICROBIAL_REACTION' in stripped:
                current_block = 'Aerobic_respiration'
            elif 'SOM_AC_FERMENTATION' in stripped:
                current_block = 'SOM_AC_FERMENTATION'
            elif 'FH_GT_MINERAL_RIPENING' in stripped:
                current_block = 'FH_GT_MINERAL_RIPENING'
            elif 'JINBETHKE_NITRATE_ACETATE' in stripped:
                current_block = 'JINBETHKE_NITRATE_ACETATE'
            elif 'JINBETHKE_FERRIHYDRITE_ACETATE' in stripped:
                current_block = 'JINBETHKE_FERRIHYDRITE_ACETATE'
            elif 'JINBETHKE_GOETHITE_ACETATE' in stripped:
                current_block = 'JINBETHKE_GOETHITE_ACETATE'
            elif 'JINBETHKE_SULFATE_ACETATE' in stripped:
                current_block = 'JINBETHKE_SULFATE_ACETATE'
            elif stripped in ['/', 'END', '/END']:
                # Block ends
                pass

            # Check for $T marker
            if '$T' in line:
                match = self.PARAM_PATTERN.search(line)
                if match:
                    keyword = match.group(2)
                    mantissa = float(match.group(3))
                    exp_str = match.group(4)
                    rest = match.group(5) if match.group(5) else ''

                    # Calculate actual value
                    if exp_str:
                        exponent = int(exp_str)
                        value = mantissa * (10 ** exponent)
                    else:
                        value = mantissa

                    # Determine which parameter this is
                    param_info = {
                        'line_num': i,
                        'line': line,
                        'block': current_block,
                        'keyword': keyword,
                        'value': value,
                        'mantissa': mantissa,
                        'exponent': int(exp_str) if exp_str else None,
                        'rest': rest,
                    }

                    # Find matching parameter
                    param_name = self._identify_parameter(current_block, keyword, i, lines)
                    if param_name:
                        if param_name not in self.param_locations:
                            self.param_locations[param_name] = []
                        self.param_locations[param_name].append(param_info)

    def _identify_parameter(self, block: str, keyword: str,
                           line_num: int, lines: List[str]) -> Optional[str]:
        """
        Identify which parameter a $T marker corresponds to.

        Some keywords appear multiple times (e.g., HALF_SATURATION_CONSTANT),
        so we need context from the surrounding lines.
        """
        # Direct block + keyword matches
        for param in PARAMETERS:
            if param.block == block and param.keyword == keyword:
                return param.name

        # Special handling for MONOD blocks in aerobic respiration
        if keyword == 'HALF_SATURATION_CONSTANT' and block == 'Aerobic_respiration':
            # Look back to find SPECIES_NAME
            for j in range(line_num - 1, max(0, line_num - 5), -1):
                if 'SPECIES_NAME' in lines[j]:
                    if 'O2' in lines[j]:
                        return 'aerobic_o2_half_sat'
                    elif 'SOC' in lines[j]:
                        return 'aerobic_soc_half_sat'

        # Try matching by block prefix for Aerobic_respiration variants
        if block and block.startswith('Aerobic_respiration'):
            for param in PARAMETERS:
                if param.keyword == keyword and 'aerobic' in param.name:
                    return param.name

        return None

    def get_current_values(self) -> Dict[str, float]:
        """Return current parameter values from the template."""
        values = {}
        for param_name, locations in self.param_locations.items():
            if locations:
                values[param_name] = locations[0]['value']
        return values

    def modify_parameters(self, param_values: Dict[str, float],
                          strip_markers: bool = True) -> str:
        """
        Modify the template with new parameter values.

        Args:
            param_values: Dictionary mapping parameter names to new values.
            strip_markers: If True, remove $T markers from output (for PFLOTRAN).
                          If False, keep markers (for template preservation).

        Returns:
            Modified template content as string.
        """
        lines = self.original_content.split('\n')

        for param_name, new_value in param_values.items():
            if param_name not in self.param_locations:
                print(f"Warning: Parameter '{param_name}' not found in template")
                continue

            for loc in self.param_locations[param_name]:
                line_num = loc['line_num']
                keyword = loc['keyword']
                rest = loc['rest']

                # Format the new value in Fortran notation
                new_value_str = self._format_value(new_value)

                # Reconstruct the line
                # Find indentation
                old_line = lines[line_num]
                indent = len(old_line) - len(old_line.lstrip())
                indent_str = old_line[:indent]

                # Build new line - strip $T marker for PFLOTRAN compatibility
                if strip_markers:
                    new_line = f"{indent_str}{keyword} {new_value_str}"
                else:
                    new_line = f"{indent_str}$T {keyword} {new_value_str}"

                if rest.strip():
                    new_line += f"  {rest.strip()}"

                lines[line_num] = new_line

        # Also strip any remaining $T markers that weren't in param_values
        if strip_markers:
            for i, line in enumerate(lines):
                if '$T ' in line:
                    lines[i] = line.replace('$T ', '')

        self.current_content = '\n'.join(lines)
        return self.current_content

    def _format_value(self, value: float) -> str:
        """
        Format a value in Fortran-compatible scientific notation.

        Uses 'd' notation (e.g., 1.0d-10) for PFLOTRAN compatibility.
        """
        if value == 0:
            return "0.d0"

        # Get exponent
        exponent = int(np.floor(np.log10(abs(value))))
        mantissa = value / (10 ** exponent)

        # Format with d notation
        if abs(exponent) > 2 or abs(value) < 0.01:
            return f"{mantissa:.2f}d{exponent:+d}".replace('+', '')
        else:
            return f"{value:.6g}d0"

    def write(self, output_path: Optional[Path] = None) -> Path:
        """
        Write the modified template to a file.

        Args:
            output_path: Path to write to. If None, overwrites original.

        Returns:
            Path to the written file.
        """
        if output_path is None:
            output_path = self.template_path

        output_path = Path(output_path)
        output_path.write_text(self.current_content)
        return output_path

    def reset(self):
        """Reset to original template content."""
        self.current_content = self.original_content
        self._parse_template()


def create_modified_template(template_path: Path,
                             param_values: Dict[str, float],
                             output_path: Optional[Path] = None,
                             strip_markers: bool = True) -> Path:
    """
    Convenience function to create a modified template.

    Args:
        template_path: Path to original TEMPLATE-chemistry.txt
        param_values: Dictionary of parameter name -> value
        output_path: Where to write modified template. If None, creates
                    a temporary file.
        strip_markers: If True, remove $T markers for PFLOTRAN compatibility.

    Returns:
        Path to the modified template file.
    """
    import tempfile

    modifier = TemplateModifier(template_path)
    modifier.modify_parameters(param_values, strip_markers=strip_markers)

    if output_path is None:
        fd, temp_path = tempfile.mkstemp(suffix='-chemistry.txt')
        output_path = Path(temp_path)

    return modifier.write(output_path)


def validate_template(template_path: Path) -> Tuple[bool, List[str]]:
    """
    Validate that a template has all expected $T markers.

    Args:
        template_path: Path to template file.

    Returns:
        Tuple of (is_valid, list of issues/warnings)
    """
    modifier = TemplateModifier(template_path)
    issues = []

    # Check that all expected parameters are found
    expected_params = set(p.name for p in PARAMETERS)
    found_params = set(modifier.param_locations.keys())

    missing = expected_params - found_params
    if missing:
        issues.append(f"Missing $T markers for parameters: {missing}")

    extra = found_params - expected_params
    if extra:
        issues.append(f"Unexpected $T markers found: {extra}")

    # Check values are within bounds
    for param_name, locations in modifier.param_locations.items():
        if param_name in PARAM_BY_NAME:
            param = PARAM_BY_NAME[param_name]
            value = locations[0]['value']
            if not (param.bounds[0] <= value <= param.bounds[1]):
                issues.append(
                    f"Parameter '{param_name}' value {value:.2e} outside bounds "
                    f"[{param.bounds[0]:.2e}, {param.bounds[1]:.2e}]"
                )

    is_valid = len(issues) == 0
    return is_valid, issues
