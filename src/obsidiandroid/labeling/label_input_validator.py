# Filename: ml_classification/labeling/label_input_validator.py
# Purpose  : Validate vendor metadata and ML model output structure before building classification labels

from obsidiandroid.cli.ui import display as du

# Validate structure and contents of vendor and model result inputs
def validate_label_resolution_inputs(vendor_records: dict, model_output: dict) -> bool:
    du.print_subheader("[VALIDATOR] Verifying Inputs for Structured Label Resolution")
    debug_fail = False

    # === Check vendor_records ===
    if not isinstance(vendor_records, dict) or not vendor_records:
        du.print_warning(
            "[LABEL_VALIDATOR] Vendor records are missing or empty."
            " Continuing without vendor metadata."
        )
    else:
        du.print_success(
            f"[LABEL_VALIDATOR] Vendor record validation passed with {len(vendor_records)} entries."
        )

    # === Check model_output structure ===
    if not isinstance(model_output, dict):
        du.print_error("[LABEL_VALIDATOR] Model output must be a dictionary.")
        du.print_debug(f"[LABEL_VALIDATOR] Got type: {type(model_output)}")
        return False
    if not model_output:
        du.print_error("[LABEL_VALIDATOR] Model output dictionary is empty.")
        return False
    du.print_success(f"[LABEL_VALIDATOR] Model output contains keys: {sorted(model_output.keys())}")

    # === Required keys must be present ===
    required_keys = ["predictions", "true_labels", "label_encoder", "metadata"]
    missing = [k for k in required_keys if k not in model_output]
    if missing:
        du.print_error(f"[LABEL_VALIDATOR] Missing required keys in model output: {missing}")
        du.print_info("[LABEL_VALIDATOR] Required keys: " + ", ".join(required_keys))
        debug_fail = True
    else:
        du.print_success("[LABEL_VALIDATOR] All required keys are present.")

    # === Type and size check for key fields ===
    for key in ["predictions", "true_labels", "metadata"]:
        val = model_output.get(key)
        if isinstance(val, list):
            du.print_warning(f"[LABEL_VALIDATOR] '{key}' is a list, expected a dictionary. Consider converting using sample IDs.")
            du.print_debug(f"[LABEL_VALIDATOR] First 3 entries (preview): {val[:3] if len(val) > 3 else val}")
            debug_fail = True
        elif not isinstance(val, dict):
            du.print_error(f"[LABEL_VALIDATOR] '{key}' must be a dictionary.")
            du.print_debug(f"[LABEL_VALIDATOR] '{key}' type: {type(val)}")
            debug_fail = True
        elif not val:
            du.print_error(f"[LABEL_VALIDATOR] '{key}' is an empty dictionary.")
            debug_fail = True
        else:
            du.print_debug(f"[LABEL_VALIDATOR] '{key}' contains {len(val)} entries.")

    # === Validate label_encoder ===
    le = model_output.get("label_encoder")
    if le is None:
        du.print_error("[LABEL_VALIDATOR] 'label_encoder' is missing or None.")
        debug_fail = True
    elif not hasattr(le, "classes_"):
        du.print_error("[LABEL_VALIDATOR] 'label_encoder' is malformed — missing 'classes_' attribute.")
        debug_fail = True
    else:
        du.print_debug(f"[LABEL_VALIDATOR] Label encoder has {len(le.classes_)} classes.")
        du.print_debug(f"[LABEL_VALIDATOR] Label classes: {list(le.classes_)}")
        du.print_success("[LABEL_VALIDATOR] Label encoder is valid.")

    if debug_fail:
        du.print_error("[LABEL_VALIDATOR] Input validation failed — check structure, keys, and types.")
        return False

    du.print_success("[LABEL_VALIDATOR] All inputs passed structural and type validation.")
    return True
