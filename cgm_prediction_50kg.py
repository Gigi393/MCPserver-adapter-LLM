import os
import sys
sys.path.append(os.path.abspath("py_mgipsim"))
from pymgipsim.Settings.settings_args_to_scenario import generate_settings_main
from pymgipsim.VirtualPatient import VirtualPatient
from pymgipsim.ModelSolver import singlescale
import numpy as np

# Configuration for 50kg patient with T1D consuming 50g carbs
config = {
    "scenario_name": "adult_001",
    "body_weight": 50.0,  # Updated to 50kg patient
    "basal": [0.36] * 6,  # Adjusted basal for weight (0.5U/hr * 50kg/70kg)
    "start_time": 0,
    "end_time": 120,  # 2-hour prediction window
    "meals": [{
        "carbs": 100,  # 100g carbohydrate meal
        "time": 0,    # Meal consumed at simulation start
        "composition": {"carb": 1.0}  # 100% carb composition
    }]
}

# Initialize simulation environment
settings = generate_settings_main(config)
patient = VirtualPatient(settings)

# Execute glucose prediction model
t, states = singlescale(
    patient.model,
    patient.t0,
    patient.tf,
    patient.initial_conditions,
    t_eval=np.arange(0, 121, 15)  # 15min intervals for 2hrs
)

# Extract CGM-equivalent glucose values (mg/dL)
glucose = states[:, patient.model.glucose_index]
# Format results as markdown table
print("### CGM Prediction After 100g Carbohydrate Meal")
print("| Time (min) | Glucose (mg/dL) |")
print("|------------|-----------------|")
for t, g in zip(t, glucose):
    print(f"| {t:.0f}         | {g:.0f}             |")