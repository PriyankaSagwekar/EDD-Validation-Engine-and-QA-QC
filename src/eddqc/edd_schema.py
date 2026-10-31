"""The EDD layout: canonical column names and header aliases accepted by the loader."""

EDD_COLUMNS = [
    "sys_sample_code", "lab_sample_id", "sample_type", "parent_sample_code", "location_code",
    "matrix", "sample_date", "depth_top_m", "depth_base_m", "coc_id", "cooler_id",
    "receipt_date", "cooler_temp_c", "custody_seal_intact", "sample_ph", "lab_code",
    "method_code", "fraction", "lab_batch_id", "extraction_date", "analysis_date",
    "dilution_factor", "cas_rn", "chemical_name", "result_value", "detect_flag", "mdl", "rl",
    "unit", "result_type", "spike_added", "percent_recovery", "lab_qualifier",
]

# Columns the file must contain before it is loaded at all.
REQUIRED_COLUMNS = [
    "sys_sample_code", "sample_type", "matrix", "method_code", "cas_rn", "result_value",
    "detect_flag", "unit", "result_type",
]

# Common header variants seen in lab deliverables, mapped to canonical names.
ALIASES = {
    "sample_id": "sys_sample_code",
    "sample_code": "sys_sample_code",
    "field_sample_id": "sys_sample_code",
    "lab_id": "lab_sample_id",
    "sample_type_code": "sample_type",
    "parent_sample": "parent_sample_code",
    "location": "location_code",
    "loc_id": "location_code",
    "matrix_code": "matrix",
    "sampled_date": "sample_date",
    "sample_datetime": "sample_date",
    "start_depth": "depth_top_m",
    "end_depth": "depth_base_m",
    "depth_top": "depth_top_m",
    "depth_base": "depth_base_m",
    "chain_of_custody": "coc_id",
    "date_received": "receipt_date",
    "receipt_temp": "cooler_temp_c",
    "temperature_c": "cooler_temp_c",
    "custody_seal": "custody_seal_intact",
    "ph": "sample_ph",
    "lab_name_code": "lab_code",
    "lab_anl_method_name": "method_code",
    "analysis_method": "method_code",
    "fraction_code": "fraction",
    "qc_batch": "lab_batch_id",
    "prep_date": "extraction_date",
    "prep_datetime": "extraction_date",
    "analysis_datetime": "analysis_date",
    "dilution": "dilution_factor",
    "cas_number": "cas_rn",
    "cas": "cas_rn",
    "analyte": "chemical_name",
    "result": "result_value",
    "result_text": "result_value",
    "detected": "detect_flag",
    "method_detection_limit": "mdl",
    "reporting_limit": "rl",
    "result_unit": "unit",
    "units": "unit",
    "result_type_code": "result_type",
    "qc_spike_added": "spike_added",
    "qc_spike_recovery": "percent_recovery",
    "recovery": "percent_recovery",
    "lab_qualifiers": "lab_qualifier",
}

DATE_FORMAT = "%Y-%m-%d %H:%M"
