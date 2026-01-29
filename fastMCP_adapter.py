import os
import sys
import json
import logging
from typing import Any, Dict

import numpy as np
from mcp.server.fastmcp import FastMCP

# --------------------------------------------------------------------------------------
# Make sure the bundled `py_mgipsim` package is importable
# --------------------------------------------------------------------------------------

BASE_DIR = os.path.dirname(__file__)
PY_MGIPSIM_DIR = os.path.join(BASE_DIR, "py_mgipsim")

if PY_MGIPSIM_DIR not in sys.path:
    sys.path.append(PY_MGIPSIM_DIR)

from pymgipsim.Utilities.Scenario import load_scenario  # noqa: E402,F401
from pymgipsim.Utilities.paths import default_settings_path, results_path  # noqa: E402,F401
from pymgipsim.Utilities import simulation_folder  # noqa: E402
from pymgipsim.generate_settings import generate_simulation_settings_main  # noqa: E402
from pymgipsim.generate_subjects import generate_virtual_subjects_main  # noqa: E402
from pymgipsim.generate_inputs import generate_inputs_main  # noqa: E402
from pymgipsim.generate_results import generate_results_main  # noqa: E402
from pymgipsim.VirtualPatient.VirtualPatient import VirtualCohort  # noqa: E402,F401
from pymgipsim.Interface.parser import generate_parser_cli  # noqa: E402
from pymgipsim.InputGeneration.activity_settings import activity_args_to_scenario  # noqa: E402
from pymgipsim.Utilities.units_conversions_constants import UnitConversion  # noqa: E402

# --------------------------------------------------------------------------------------
# Logging & MCP server setup
# --------------------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("T1D Simulation Server")

_initialized = False


def _ensure_pymgipsim_initialized() -> None:
    """
    Run py_mgipsim initialization once (creates folders, default scenario, etc.).

    py_mgipsim expects to be run from inside its own folder for relative paths to work,
    so we temporarily switch into `PY_MGIPSIM_DIR` while importing `initialization`.
    """
    global _initialized
    if _initialized:
        return

    logger.info("Initializing py_mgipsim environment...")
    old_cwd = os.getcwd()
    try:
        os.chdir(PY_MGIPSIM_DIR)
        # Importing `initialization` executes its side effects (folder creation, etc.)
        import initialization  # type: ignore  # noqa: F401
    finally:
        os.chdir(old_cwd)

    _initialized = True
    logger.info("py_mgipsim initialized.")


@mcp.tool()
def simulate_glucose_dynamics(
    carbs_grams: float,
    insulin_bolus: float = 0.0,
    body_weight: float = 70.0,
    duration_minutes: int = 180,
) -> str:
    """
    Simulate glucose-insulin dynamics for a T1D patient based on meal and insulin intake,
    using the official pymgipsim pipeline (VirtualCohort + generate_* functions).

    Args:
        carbs_grams: Carbohydrate intake in grams.
        insulin_bolus: Bolus insulin units at mealtime (currently not wired into controller).
        body_weight: Target body weight in kg (best-effort mapping into scenario).
        duration_minutes: Simulation horizon in minutes.

    Returns:
        JSON string containing CGM trace and summary metrics.
    """
    try:
        logger.info(
            "Starting simulation with carbs=%s g, bolus=%s U, body_weight=%s kg, duration=%s min",
            carbs_grams,
            insulin_bolus,
            body_weight,
            duration_minutes,
        )

        _ensure_pymgipsim_initialized()

        # 1. Build default CLI-style args and override with our parameters
        parser = generate_parser_cli()
        # Parse with empty argv to get all defaults
        args = parser.parse_args([])

        # Map our duration (minutes) to days used by generate_simulation_settings_main
        days = max(1, int(np.ceil(duration_minutes / (24 * 60))))
        args.number_of_days = days

        # Keep the default controller/model, but you can override here if you want:
        # args.controller_name = "OpenLoop"
        # args.model_name = "T1DM.ExtHovorka"

        # Simple mapping of carbs into breakfast carb range (best-effort)
        if hasattr(args, "breakfast_carb_range"):
            args.breakfast_carb_range = [carbs_grams, carbs_grams]

        # Disable physical activity by default for tool calls.
        # (The default scenario has empty activity ranges; CLI normally applies
        # args into the scenario, but in library usage we must ensure lists are
        # non-empty to avoid IndexError during input generation.)
        if hasattr(args, "running_start_time"):
            args.running_start_time = ["00:00"]
        if hasattr(args, "cycling_start_time"):
            args.cycling_start_time = ["00:00"]
        if hasattr(args, "running_duration"):
            args.running_duration = [0.0]
        if hasattr(args, "cycling_duration"):
            args.cycling_duration = [0.0]
        if hasattr(args, "running_incline"):
            args.running_incline = [0.0]
        if hasattr(args, "running_speed"):
            args.running_speed = [0.0]
        if hasattr(args, "cycling_power"):
            args.cycling_power = [0.0]

        # We don't have a direct CLI arg for body_weight here;
        # it will be handled via the library's demographic sampling. You could
        # later extend this by editing the scenario object.

        # 2. Define results folder and load base scenario
        _, _, _, results_folder_path = simulation_folder.create_simulation_results_folder(
            results_path
        )

        settings_file = simulation_folder.load_settings_file(args, results_folder_path)

        # 3. Generate settings, subjects, and inputs if not using a pre-defined scenario
        if not args.scenario_name:
            settings_file = generate_simulation_settings_main(
                scenario_instance=settings_file,
                args=args,
                results_folder_path=results_folder_path,
            )
            settings_file = generate_virtual_subjects_main(
                scenario_instance=settings_file,
                args=args,
                results_folder_path=results_folder_path,
            )
            # Mirror the CLI flow: apply activity-related args onto the scenario
            # before generating input signals.
            activity_args_to_scenario(settings_file, args)
            settings_file = generate_inputs_main(
                scenario_instance=settings_file,
                args=args,
                results_folder_path=results_folder_path,
            )

        # 4. Run the core simulation via generate_results_main (VirtualCohort + solver)
        cohort, _ = generate_results_main(
            scenario_instance=settings_file,
            args=vars(args),
            results_folder_path=results_folder_path,
        )

        # For SingleScaleSolver, the singlescale model is the main one
        model = cohort.singlescale_model

        # States array shape: [subjects x states x samples]
        states = model.states.as_array
        # Use first subject (index 0)
        glucose_state_idx = model.glucose_state
        glucose_raw = states[0, glucose_state_idx, :]

        # Convert to mg/dL if the model is in mmol/L (follow generate_results_main logic)
        if model.states.state_units[glucose_state_idx] == "mmol/L":
            glucose = UnitConversion.glucose.concentration_mmolL_to_mgdL(
                glucose_raw / model.parameters.VG[0]
            )
        else:
            glucose = glucose_raw

        # Time array comes from model.time (in minutes from start)
        time_points = model.time.as_unix  # already in minutes

        # If user asked for shorter than total simulated time, we can truncate
        max_time = duration_minutes
        mask = time_points <= max_time
        time_points = time_points[mask]
        glucose = glucose[mask]

        # 5. Compute simple summary metrics
        min_glucose = float(np.min(glucose))
        max_glucose = float(np.max(glucose))
        final_glucose = float(glucose[-1])

        status = "Normal"
        if min_glucose < 70:
            status = "Hypoglycemia (Low)"
        elif max_glucose > 180:
            status = "Hyperglycemia (High)"

        # 6. Format JSON output (subsample for token efficiency)
        result_data: Dict[str, Any] = {
            "summary": {
                "status": status,
                "min_glucose_mg_dl": round(min_glucose, 1),
                "max_glucose_mg_dl": round(max_glucose, 1),
                "final_glucose_mg_dl": round(final_glucose, 1),
            },
            "cgm_trace": [
                {"time_min": float(t), "glucose_mg_dl": round(float(g), 1)}
                for i, (t, g) in enumerate(zip(time_points, glucose))
                if i % 15 == 0 or i == len(glucose) - 1
            ],
        }

        return json.dumps(result_data)

    except Exception as e:
        logger.exception("Simulation failed")
        return f"Error executing simulation: {str(e)}"


if __name__ == "__main__":
    # This starts the FastMCP server when you run:
    #   python fastMCP.py
    mcp.run()
