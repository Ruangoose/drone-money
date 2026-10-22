"""Group USAspending recipients into companies by the recipient's own name.

USAspending's parent links can't be trusted for this: it applies today's parent to old contracts (Raytheon
Company's 2015 awards sit under RTX Corporation), files Sikorsky (Lockheed Martin's since November 2015)
under RTX, and files Huntington Ingalls and parts of Northrop Grumman under stale holding-company records
("Continental Maritime of San Diego", "Titan II"). So recipients are matched on their own names, with mergers
applied by fiscal year:
- Rockwell Collins joined United Technologies in November 2018 (FY2019);
- Orbital ATK joined Northrop Grumman in June 2018 (FY2018);
- L3 and Harris merged into L3Harris in June 2019 (FY2019);
- Raytheon and United Technologies merged into RTX in April 2020 (FY2020).
"""

# (company, patterns, first FY it exists as named, last FY). Checked in order; first match wins.
COMPANIES = [
    ("Lockheed Martin", ["LOCKHEED", "SIKORSKY"], 2000, 2100),
    ("RTX", ["RAYTHEON", "RTX", "PRATT & WHITNEY", "PRATT AND WHITNEY", "UNITED TECHNOLOGIES", "COLLINS AEROSPACE",
             "ROCKWELL COLLINS", "HAMILTON SUNDSTRAND"], 2020, 2100),
    ("Raytheon", ["RAYTHEON"], 2000, 2019),
    ("Rockwell Collins", ["ROCKWELL COLLINS"], 2000, 2018),
    # Before the merger, a recipient now named "RTX Corporation" is United Technologies under its new name.
    ("United Technologies", ["PRATT & WHITNEY", "PRATT AND WHITNEY", "UNITED TECHNOLOGIES", "HAMILTON SUNDSTRAND",
                             "COLLINS AEROSPACE", "ROCKWELL COLLINS", "UTC ", "RTX"], 2000, 2019),
    ("Boeing", ["BOEING", "INSITU"], 2000, 2100),
    ("General Dynamics", ["GENERAL DYNAMICS", "ELECTRIC BOAT", "BATH IRON WORKS", "NATIONAL STEEL AND SHIPBUILDING",
                          "GULFSTREAM"], 2000, 2100),
    ("Northrop Grumman", ["NORTHROP", "ORBITAL ATK", "ORBITAL SCIENCES"], 2018, 2100),
    ("Northrop Grumman", ["NORTHROP"], 2000, 2017),
    ("Orbital ATK", ["ORBITAL ATK", "ORBITAL SCIENCES", "ALLIANT TECHSYSTEMS"], 2000, 2017),
    ("Huntington Ingalls", ["HUNTINGTON INGALLS", "HII ", "NEWPORT NEWS", "INGALLS SHIPBUILDING",
                            "CONTINENTAL MARITIME"], 2000, 2100),
    ("L3Harris", ["L3HARRIS", "L-3", "L3 TECHNOLOGIES", "HARRIS CORP", "HARRIS TECHNICAL", "AEROJET"], 2019, 2100),
    ("L3 Technologies", ["L-3", "L3 TECHNOLOGIES"], 2000, 2018),
    ("Harris", ["HARRIS CORP", "HARRIS TECHNICAL"], 2000, 2018),
    ("Aerojet Rocketdyne", ["AEROJET"], 2000, 2023),
    ("BAE Systems (London-listed)", ["BAE SYSTEMS"], 2000, 2100),
    ("General Atomics (private)", ["GENERAL ATOMICS"], 2000, 2100),
    ("Anduril (private)", ["ANDURIL"], 2000, 2100),
    ("General Electric", ["GENERAL ELECTRIC", "GE AEROSPACE", "GE AVIATION"], 2000, 2100),
    ("Honeywell", ["HONEYWELL"], 2000, 2100),
    ("Textron", ["TEXTRON", "BELL TEXTRON", "BELL HELICOPTER"], 2000, 2100),
    ("Oshkosh", ["OSHKOSH"], 2000, 2100),
    ("Leidos", ["LEIDOS"], 2000, 2100),
    ("Booz Allen Hamilton", ["BOOZ ALLEN"], 2000, 2100),
    ("AeroVironment", ["AEROVIRONMENT", "BLUEHALO"], 2000, 2100),
    ("Kratos", ["KRATOS"], 2000, 2100),
    ("Red Cat", ["RED CAT", "TEAL DRONES"], 2000, 2100),
    ("Ondas", ["ONDAS", "AMERICAN ROBOTICS", "AIROBOTICS"], 2000, 2100),
    ("AgEagle", ["AGEAGLE"], 2000, 2100),
    ("Unusual Machines", ["UNUSUAL MACHINES"], 2000, 2100),
    ("Redwire", ["REDWIRE", "EDGE AUTONOMY"], 2000, 2100),
    ("Shield AI (private)", ["SHIELD AI"], 2000, 2100),
    ("Skydio (private)", ["SKYDIO"], 2000, 2100),
]

# Aerojet Rocketdyne joined L3Harris in July 2023 (FY2023, so from FY2024 it's L3Harris).
_AEROJET_TO_LHX = 2024

DRONE_BASKET = {"AeroVironment", "Kratos", "Red Cat", "Ondas", "AgEagle", "Unusual Machines", "Redwire"}
PRIMES = {"Lockheed Martin", "RTX", "Raytheon", "United Technologies", "Rockwell Collins", "Boeing",
          "General Dynamics", "Northrop Grumman", "Orbital ATK", "Huntington Ingalls", "L3Harris",
          "L3 Technologies", "Harris"}


def company(name, fy, parent=None):
    for text in (name, parent):
        n = (text or "").upper()
        if not n:
            continue
        if "AEROJET" in n:
            return "L3Harris" if fy >= _AEROJET_TO_LHX else "Aerojet Rocketdyne"
        for comp, pats, first, last in COMPANIES:
            if first <= fy <= last and any(p in n for p in pats):
                return comp
    return (parent or name or "").strip().title()


def group(comp):
    if comp in DRONE_BASKET:
        return "drone basket companies"
    if comp in PRIMES:
        return "primes"
    if "(private)" in comp:
        return "private"
    return "other"
