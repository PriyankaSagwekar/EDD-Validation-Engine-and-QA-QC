"""Reference data for the fictional site, lab and analytical suite.

This module is the single source of truth for lookup values. It is used to
generate sql/06_seed_reference.sql (loaded into the ref_* tables) and by the
simulator to generate realistic, clean lab data. The validation engine never
imports it: the engine reads limits from the database, like a real system.

All screening criteria are ILLUSTRATIVE values loosely based on UK drinking
water standards and generic assessment criteria. They are not for real use.
"""

SITE = {
    "site_code": "RIE01",
    "site_name": "Riverside Industrial Estate (fictional)",
    "county": "West Yorkshire",
    "grid_crs": "EPSG:27700",
}

LAB = {
    "lab_code": "FAL",
    "lab_name": "Fictional Analytical Laboratories Ltd",
    "accreditation": "UKAS ISO 17025 / MCERTS (fictional)",
}

# location_code, type, easting, northing, ground level mOD, final depth m, screen top m, screen base m
LOCATIONS = [
    ("MW01", "MW", 430120.0, 433410.0, 52.31, 12.0, 4.0, 10.0),
    ("MW02", "MW", 430215.0, 433380.0, 52.05, 12.0, 4.0, 10.0),
    ("MW03", "MW", 430290.0, 433305.0, 51.62, 10.0, 3.0, 8.0),
    ("MW04", "MW", 430340.0, 433260.0, 51.40, 10.0, 3.0, 8.0),
    ("MW05", "MW", 430395.0, 433210.0, 51.12, 10.0, 3.0, 8.0),
    ("MW06", "MW", 430180.0, 433250.0, 51.88, 15.0, 6.0, 13.0),
    ("MW07", "MW", 430470.0, 433380.0, 51.05, 15.0, 6.0, 13.0),
    ("MW08", "MW", 430540.0, 433330.0, 50.81, 15.0, 6.0, 13.0),
    ("MW09", "MW", 430610.0, 433270.0, 50.60, 12.0, 4.0, 10.0),
    ("MW10", "MW", 430075.0, 433290.0, 52.44, 12.0, 4.0, 10.0),
    ("BH01", "BH", 430250.0, 433360.0, 51.95, 6.0, None, None),
    ("BH02", "BH", 430310.0, 433280.0, 51.55, 6.0, None, None),
    ("BH03", "BH", 430500.0, 433350.0, 50.95, 6.0, None, None),
    ("TP01", "TP", 430160.0, 433330.0, 52.10, 3.0, None, None),
    ("TP02", "TP", 430420.0, 433300.0, 51.20, 3.0, None, None),
]

MONITORING_WELLS = [loc[0] for loc in LOCATIONS if loc[1] == "MW"]
SOIL_LOCATIONS = {"BH01": [0.5, 1.5, 3.0], "BH02": [0.5, 1.5, 3.0], "BH03": [0.5, 1.5, 3.0],
                  "TP01": [0.3, 1.2], "TP02": [0.3, 1.2]}

# cas_rn, name, group, is_surrogate, common_lab_contaminant, sum_into_cas
ANALYTES = [
    # metals
    ("7440-38-2", "Arsenic", "METALS", 0, 0, None),
    ("7440-43-9", "Cadmium", "METALS", 0, 0, None),
    ("7440-47-3", "Chromium", "METALS", 0, 0, None),
    ("7440-50-8", "Copper", "METALS", 0, 0, None),
    ("7439-92-1", "Lead", "METALS", 0, 0, None),
    ("7440-02-0", "Nickel", "METALS", 0, 0, None),
    ("7440-66-6", "Zinc", "METALS", 0, 0, None),
    # VOCs incl. BTEX
    ("71-43-2", "Benzene", "VOC", 0, 0, "BTEX-TOT"),
    ("108-88-3", "Toluene", "VOC", 0, 0, "BTEX-TOT"),
    ("100-41-4", "Ethylbenzene", "VOC", 0, 0, "BTEX-TOT"),
    ("179601-23-1", "m/p-Xylene", "VOC", 0, 0, "BTEX-TOT"),
    ("95-47-6", "o-Xylene", "VOC", 0, 0, "BTEX-TOT"),
    ("BTEX-TOT", "Total BTEX", "VOC", 0, 0, None),
    ("79-01-6", "Trichloroethene", "VOC", 0, 0, None),
    ("127-18-4", "Tetrachloroethene", "VOC", 0, 0, None),
    ("75-01-4", "Vinyl chloride", "VOC", 0, 0, None),
    ("75-09-2", "Dichloromethane", "VOC", 0, 1, None),
    # PAH-16
    ("91-20-3", "Naphthalene", "PAH", 0, 0, None),
    ("208-96-8", "Acenaphthylene", "PAH", 0, 0, None),
    ("83-32-9", "Acenaphthene", "PAH", 0, 0, None),
    ("86-73-7", "Fluorene", "PAH", 0, 0, None),
    ("85-01-8", "Phenanthrene", "PAH", 0, 0, None),
    ("120-12-7", "Anthracene", "PAH", 0, 0, None),
    ("206-44-0", "Fluoranthene", "PAH", 0, 0, None),
    ("129-00-0", "Pyrene", "PAH", 0, 0, None),
    ("56-55-3", "Benz(a)anthracene", "PAH", 0, 0, None),
    ("218-01-9", "Chrysene", "PAH", 0, 0, None),
    ("205-99-2", "Benzo(b)fluoranthene", "PAH", 0, 0, None),
    ("207-08-9", "Benzo(k)fluoranthene", "PAH", 0, 0, None),
    ("50-32-8", "Benzo(a)pyrene", "PAH", 0, 0, None),
    ("193-39-5", "Indeno(1,2,3-cd)pyrene", "PAH", 0, 0, None),
    ("53-70-3", "Dibenz(a,h)anthracene", "PAH", 0, 0, None),
    ("191-24-2", "Benzo(ghi)perylene", "PAH", 0, 0, None),
    # TPH Criteria Working Group bands (pseudo-CAS codes, as EQuIS uses)
    ("TPH-ALI-C10C12", "TPH aliphatic >C10-C12", "TPH", 0, 0, "TPH-TOT-C10C40"),
    ("TPH-ALI-C12C16", "TPH aliphatic >C12-C16", "TPH", 0, 0, "TPH-TOT-C10C40"),
    ("TPH-ALI-C16C21", "TPH aliphatic >C16-C21", "TPH", 0, 0, "TPH-TOT-C10C40"),
    ("TPH-ALI-C21C35", "TPH aliphatic >C21-C35", "TPH", 0, 0, "TPH-TOT-C10C40"),
    ("TPH-ARO-C10C12", "TPH aromatic >C10-C12", "TPH", 0, 0, "TPH-TOT-C10C40"),
    ("TPH-ARO-C12C16", "TPH aromatic >C12-C16", "TPH", 0, 0, "TPH-TOT-C10C40"),
    ("TPH-ARO-C16C21", "TPH aromatic >C16-C21", "TPH", 0, 0, "TPH-TOT-C10C40"),
    ("TPH-ARO-C21C35", "TPH aromatic >C21-C35", "TPH", 0, 0, "TPH-TOT-C10C40"),
    ("TPH-TOT-C10C40", "Total TPH >C10-C40", "TPH", 0, 0, None),
    # surrogates
    ("1868-53-7", "Dibromofluoromethane (surr)", "SURROGATE", 1, 0, None),
    ("2037-26-5", "Toluene-d8 (surr)", "SURROGATE", 1, 0, None),
    ("460-00-4", "4-Bromofluorobenzene (surr)", "SURROGATE", 1, 0, None),
    ("321-60-8", "2-Fluorobiphenyl (surr)", "SURROGATE", 1, 0, None),
    ("1718-51-0", "p-Terphenyl-d14 (surr)", "SURROGATE", 1, 0, None),
    ("84-15-1", "o-Terphenyl (surr)", "SURROGATE", 1, 0, None),
]

ANALYTE_NAME = {a[0]: a[1] for a in ANALYTES}
ANALYTE_GROUP = {a[0]: a[2] for a in ANALYTES}

WATER_MATRICES = ("WG", "WQ")
MATRICES = ("WG", "WQ", "SO")

METHOD_GROUP = {
    "METALS-ICPMS": "METALS",
    "VOC-HSGCMS": "VOC",
    "PAH-GCMS": "PAH",
    "TPH-CWG-GC": "TPH",
}

# method -> matrix kind -> (holding_time_days, extraction_holding_days, temp_min, temp_max, ph_max, preservation)
# holding_time_days is measured from extraction when extraction_holding_days is set, else from sampling.
METHOD_RULES = {
    "METALS-ICPMS": {"W": (180, None, None, None, 2.0, "HNO3 to pH<2"),
                     "S": (180, None, None, None, None, "None")},
    "VOC-HSGCMS":   {"W": (14, None, 0.0, 6.0, 2.0, "HCl to pH<2, cool 0-6C"),
                     "S": (14, None, 0.0, 6.0, None, "Cool 0-6C")},
    "PAH-GCMS":     {"W": (40, 7, 0.0, 6.0, None, "Cool 0-6C, amber glass"),
                     "S": (40, 14, 0.0, 6.0, None, "Cool 0-6C, amber glass")},
    "TPH-CWG-GC":   {"W": (40, 7, 0.0, 6.0, None, "Cool 0-6C, amber glass"),
                     "S": (40, 14, 0.0, 6.0, None, "Cool 0-6C, amber glass")},
}

METHOD_NAMES = {
    "METALS-ICPMS": "Metals by ICP-MS",
    "VOC-HSGCMS": "VOCs by headspace GC-MS",
    "PAH-GCMS": "Speciated PAH-16 by GC-MS",
    "TPH-CWG-GC": "TPH CWG banding by GC-FID",
}


def matrix_kind(matrix: str) -> str:
    return "S" if matrix == "SO" else "W"


# Detection limits: cas -> {"W": (mdl, rl), "S": (mdl, rl)}; units ug/L water, mg/kg soil
_METAL_LIMITS = {
    "7440-38-2": ((0.1, 0.5), (0.2, 1.0)),
    "7440-43-9": ((0.02, 0.1), (0.05, 0.2)),
    "7440-47-3": ((0.2, 1.0), (0.5, 1.0)),
    "7440-50-8": ((0.2, 1.0), (0.5, 1.0)),
    "7439-92-1": ((0.1, 0.5), (0.5, 2.0)),
    "7440-02-0": ((0.2, 1.0), (0.5, 1.0)),
    "7440-66-6": ((0.5, 2.0), (1.0, 5.0)),
}


def _limits():
    out = {}
    for cas, (w, s) in _METAL_LIMITS.items():
        out[("METALS-ICPMS", cas)] = {"W": w, "S": s}
    for a in ANALYTES:
        cas, grp, surr = a[0], a[2], a[3]
        if surr:
            continue
        if grp == "VOC":
            w = (0.1, 0.3) if cas == "75-01-4" else (0.3, 1.0)
            if cas == "BTEX-TOT":
                w = (1.0, 3.0)
            s = (0.001, 0.005) if cas != "BTEX-TOT" else (0.005, 0.015)
            out[("VOC-HSGCMS", cas)] = {"W": w, "S": s}
        elif grp == "PAH":
            out[("PAH-GCMS", cas)] = {"W": (0.005, 0.01), "S": (0.01, 0.05)}
        elif grp == "TPH":
            if cas == "TPH-TOT-C10C40":
                out[("TPH-CWG-GC", cas)] = {"W": (10.0, 50.0), "S": (5.0, 10.0)}
            else:
                out[("TPH-CWG-GC", cas)] = {"W": (5.0, 10.0), "S": (0.5, 1.0)}
    return out


METHOD_ANALYTE_LIMITS = _limits()

UNITS = {"W": "ug/L", "S": "mg/kg"}

SURROGATES = {
    "VOC-HSGCMS": [("1868-53-7", 70, 130), ("2037-26-5", 70, 130), ("460-00-4", 70, 130)],
    "PAH-GCMS": [("321-60-8", 70, 130), ("1718-51-0", 70, 130)],
    "TPH-CWG-GC": [("84-15-1", 60, 140)],
}

# qc_type -> (lower, upper, rpd_max by method)
SPIKE_LIMITS = {"MS": (70, 130), "LCS": (80, 120)}
SPIKE_RPD_MAX = {"METALS-ICPMS": 20, "VOC-HSGCMS": 30, "PAH-GCMS": 30, "TPH-CWG-GC": 30}

# Illustrative screening criteria sets. Water ug/L, soil mg/kg. The primary set for each
# matrix is used by DET-04 and drawn as the criterion line on charts.
SCREENING_SETS = {
    "DWS": {
        "kind": "W", "primary": True,
        "name": "Illustrative UK drinking water standard",
        "values": {"7440-38-2": 10, "7440-43-9": 5, "7440-47-3": 50, "7440-50-8": 2000,
                   "7439-92-1": 10, "7440-02-0": 20, "7440-66-6": 5000,
                   "71-43-2": 1, "108-88-3": 700, "100-41-4": 300, "179601-23-1": 500, "95-47-6": 500,
                   "79-01-6": 10, "127-18-4": 10, "75-01-4": 0.5, "75-09-2": 20,
                   "91-20-3": 2, "50-32-8": 0.01},
    },
    "EQS-FW": {
        "kind": "W", "primary": False,
        "name": "Illustrative freshwater environmental quality standard",
        "values": {"7440-38-2": 50, "7440-43-9": 0.25, "7440-47-3": 4.7, "7440-50-8": 1,
                   "7439-92-1": 1.2, "7440-02-0": 4, "7440-66-6": 10.9,
                   "71-43-2": 10, "108-88-3": 74, "79-01-6": 10, "127-18-4": 10, "75-09-2": 20,
                   "91-20-3": 2, "50-32-8": 0.00017},
    },
    "GAC-RES": {
        "kind": "S", "primary": True,
        "name": "Illustrative residential generic assessment criterion",
        "values": {"7440-38-2": 37, "7440-43-9": 11, "7440-47-3": 910, "7440-50-8": 2400,
                   "7439-92-1": 200, "7440-02-0": 130, "7440-66-6": 3700,
                   "71-43-2": 0.087, "108-88-3": 130, "100-41-4": 47, "179601-23-1": 56, "95-47-6": 56,
                   "79-01-6": 0.016, "127-18-4": 0.18, "75-01-4": 0.01, "91-20-3": 2.3, "50-32-8": 2.2},
    },
}

VALID_VALUES = {
    "sample_type": {"N": "Normal field sample", "FD": "Field duplicate", "FB": "Field blank",
                    "EB": "Equipment blank", "TB": "Trip blank", "MB": "Method blank",
                    "LCS": "Laboratory control sample", "MS": "Matrix spike",
                    "MSD": "Matrix spike duplicate"},
    "matrix": {"WG": "Groundwater", "WQ": "Water for QC samples", "SO": "Soil"},
    "result_type": {"TRG": "Target analyte", "SUR": "Surrogate"},
    "detect_flag": {"Y": "Detected", "N": "Not detected"},
    "fraction": {"T": "Total", "D": "Dissolved", "N": "Not applicable"},
    "unit": {"ug/L": "micrograms per litre", "mg/kg": "milligrams per kilogram", "%": "percent"},
    "yes_no": {"Y": "Yes", "N": "No"},
    "validator_qualifier": {
        "U": "Not detected at the reported limit",
        "J": "Estimated value",
        "J+": "Estimated, likely biased high",
        "J-": "Estimated, likely biased low",
        "UJ": "Not detected; reported limit is estimated",
        "B": "Analyte also found in an associated blank",
        "R": "Rejected, unusable",
    },
    "reason_code": {"H": "Holding time exceeded"},
}

FIELD_TYPES = ("N", "FD", "FB", "EB", "TB", "MS", "MSD")
LAB_QC_TYPES = ("MB", "LCS")

# rule_id, family, name, severity, default qualifier, description
RULES = [
    ("COMP-01", "Completeness", "Required field missing", "CRITICAL", None, "A field required for this sample type is blank."),
    ("COMP-02", "Completeness", "Invalid code", "CRITICAL", None, "A coded field holds a value not in ref_Valid_Value."),
    ("COMP-03", "Completeness", "Unparseable number or date", "CRITICAL", None, "A numeric or date field cannot be parsed."),
    ("COMP-04", "Completeness", "Duplicate result", "CRITICAL", None, "Same sample, method, fraction, analyte and result type reported twice."),
    ("COMP-05", "Completeness", "Unit does not match method", "CRITICAL", None, "Reported unit differs from the unit in ref_Method_Analyte."),
    ("REF-01", "Referential integrity", "Unknown location", "CRITICAL", None, "Location code not in ref_Location."),
    ("REF-02", "Referential integrity", "Unknown method or analyte", "CRITICAL", None, "Method, CAS number or method/analyte pair not in reference tables."),
    ("REF-03", "Referential integrity", "QC parent sample missing", "WARNING", None, "FD/MS/MSD parent sample not found in batch or master database."),
    ("REF-04", "Referential integrity", "Missing associated blank", "WARNING", None, "No method blank in the lab batch, or no trip blank for VOC samples."),
    ("REF-05", "Referential integrity", "Inconsistent sample header", "CRITICAL", None, "Sample attributes conflict across rows, or a lab sample id maps to several samples."),
    ("STR-01", "Structural / depth", "Depth top below depth base", "CRITICAL", None, "depth_top_m is greater than depth_base_m."),
    ("STR-02", "Structural / depth", "Depth outside borehole", "CRITICAL", None, "Depth is negative or deeper than the location's final depth."),
    ("STR-03", "Structural / depth", "Depth missing or outside screen", "WARNING", None, "Soil sample without depths, or groundwater sample outside the well screen."),
    ("STR-04", "Structural / depth", "Illogical dates", "CRITICAL", None, "Analysis or extraction before sampling, receipt before sampling, or future sample date."),
    ("STR-05", "Structural / depth", "Possible duplicate sampling", "WARNING", None, "Two normal samples share location, depth and date."),
    ("PRES-01", "Thermal preservation", "Cooler temperature out of range", "WARNING", "J", "Receipt temperature outside method range; above 10 C the data are rejected."),
    ("PRES-02", "Thermal preservation", "Chemical preservation failure", "WARNING", "J-", "Sample pH above the method limit."),
    ("PRES-03", "Thermal preservation", "Custody or receipt problem", "WARNING", None, "Custody seal broken or receipt details missing."),
    ("HT-01", "Holding time", "Analysis holding time exceeded", "WARNING", "J", "Analysis outside holding time; more than 2x is rejected."),
    ("HT-02", "Holding time", "Extraction holding time exceeded", "WARNING", "J", "Extraction outside holding time; more than 2x is rejected."),
    ("DET-01", "Detection boundary", "Detect below MDL", "WARNING", "U", "Result reported as detected but below the MDL."),
    ("DET-02", "Detection boundary", "Detect between MDL and RL not flagged", "WARNING", "J", "Detect below the RL without a lab J flag."),
    ("DET-03", "Detection boundary", "Non-detect with a value", "WARNING", None, "Non-detect carries a result value other than the RL."),
    ("DET-04", "Detection boundary", "RL above screening criterion", "WARNING", None, "Non-detect cannot demonstrate compliance with the screening criterion."),
    ("DET-05", "Detection boundary", "Detection limits inconsistent", "WARNING", None, "RL below MDL, or limits differ from reference without dilution."),
    ("BLK-01", "Blank contamination", "Method blank contamination", "WARNING", "B", "Method blank detect above MDL; associated samples qualified."),
    ("BLK-02", "Blank contamination", "Field/equipment blank contamination", "WARNING", "B", "Field or equipment blank detect above MDL."),
    ("BLK-03", "Blank contamination", "Trip blank contamination", "WARNING", "B", "Trip blank VOC detect above MDL."),
    ("SUR-01", "Surrogates", "Surrogate recovery out of limits", "WARNING", "J", "Surrogate %REC outside limits; below 10% is rejected."),
    ("MS-01", "Matrix spike", "MS/MSD recovery out of limits", "WARNING", "J", "Matrix spike %REC outside limits; below 10% is rejected."),
    ("MS-02", "Matrix spike", "MS/MSD RPD too high", "WARNING", "J", "Relative percent difference between MS and MSD above limit."),
    ("MS-03", "Matrix spike", "Spike not assessable", "INFO", None, "Parent result more than 4x the spike added."),
    ("LCS-01", "Lab control sample", "LCS recovery out of limits", "WARNING", "J", "LCS %REC outside limits; below 10% is rejected."),
    ("FD-01", "Field duplicates", "Field duplicate imprecision", "WARNING", "J", "RPD or absolute difference between FD and parent too high."),
    ("PLB-01", "Plausibility", "Dissolved exceeds total", "WARNING", None, "Dissolved metal more than 10% above total metal."),
    ("PLB-02", "Plausibility", "Components exceed total", "WARNING", None, "Sum of BTEX or TPH components more than 10% above the reported total."),
]
