"""Synthetic maintenance-request dataset generator.

The assignment specifies a *synthetic* dataset. Requests are built two ways:

  1. Curated phrases per (category, urgency) - realistic complete sentences.
  2. Compositional phrases - a component of the unit (e.g. "kitchen sink")
     combined with a severity cue ("is not working at all" -> High,
     "makes a slight noise" -> Low). This teaches the model the *cues*
     rather than memorising sentences, so it generalises to new wording.

Neutral prefixes / locations / suffixes are mixed in, and a small amount of
label noise is added on purpose so evaluation is not on perfectly clean data.

Run directly to write ml/maintenance_requests.csv:
    python -m ml.generate_dataset
"""

import random
from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).with_name("maintenance_requests.csv")

# ---------------------------------------------------------------- curated ---
ISSUE_BANK = {
    "Plumbing": {
        "Critical": [
            "water is flooding the floor from a burst pipe",
            "sewage is backing up into the bathtub and floor drain",
            "main water line broke and water is pouring into the unit",
            "pipe burst inside the wall and the room is flooded",
        ],
        "High": [
            "no water supply in the entire unit since morning",
            "the only toilet is clogged and will not flush",
            "continuous leak under the kitchen sink is soaking the cabinet",
            "water is dripping from the pipe and the cabinet is getting wet",
            "water keeps leaking from the ceiling pipe onto the floor",
        ],
        "Medium": [
            "bathroom sink is draining very slowly",
            "kitchen faucet drips constantly",
            "shower head has weak water pressure",
            "the drain is blocked and water drains slowly",
            "tap is dripping a little at night",
        ],
        "Low": [
            "toilet seat is loose and wobbles slightly",
            "faucet handle looks old and I would like it replaced",
            "small stain around the sink caulking needs touch up",
            "towel rod near the sink is slightly crooked",
        ],
    },
    "Electrical": {
        "Critical": [
            "sparks are coming from the wall outlet and there is a burning smell",
            "exposed live wires hanging from the ceiling light",
            "electric shock received when touching the switch",
            "switch board is smoking and has a burning smell",
        ],
        "High": [
            "complete power outage in the bedrooms while the rest works",
            "circuit breaker keeps tripping every few minutes",
            "kitchen outlets have stopped working completely",
            "no electricity in the whole unit since last night",
        ],
        "Medium": [
            "light fixture flickers often",
            "one outlet in the study is not working",
            "ceiling fan regulator is faulty and the fan runs unevenly",
            "tube light buzzes and turns on slowly",
        ],
        "Low": [
            "need a burnt out bulb replaced in the hallway",
            "doorbell chime is faint",
            "request to add a cover plate for a switch",
            "please change the bulb on the balcony",
        ],
    },
    "HVAC": {
        "Critical": [
            "gas smell near the furnace and the carbon monoxide alarm is going off",
            "heater is smoking and smells of burning plastic",
            "refrigerant leak with a loud hissing sound near the air handler",
        ],
        "High": [
            "air conditioner has stopped cooling during extreme heat",
            "heating is not working and the apartment is freezing",
            "no hot air from the vents and an elderly person lives here",
            "AC is not cooling at all and the room is very hot",
        ],
        "Medium": [
            "air conditioner is noisy and cools slowly",
            "thermostat display is blank at times",
            "vents have weak airflow in the bedroom",
            "AC remote works only sometimes",
        ],
        "Low": [
            "air filter replacement is due",
            "vent cover is dusty and rattles lightly",
            "request to check the thermostat schedule settings",
        ],
    },
    "Appliance": {
        "Critical": [
            "stove is leaking gas and smells strongly",
            "washing machine is sparking and smoking",
            "oven caught fire while heating",
        ],
        "High": [
            "refrigerator stopped cooling and food is spoiling",
            "water heater is not heating at all",
            "stove burners will not light so we cannot cook",
            "fridge is not cooling and the food is going bad",
        ],
        "Medium": [
            "dishwasher is not draining properly",
            "washing machine shakes loudly during spin",
            "microwave turntable does not rotate",
            "dryer takes very long to dry clothes",
        ],
        "Low": [
            "oven clock shows the wrong time",
            "fridge door shelf is cracked",
            "range hood light bulb needs replacing",
        ],
    },
    "Structural": {
        "Critical": [
            "part of the ceiling has collapsed in the room",
            "large wall crack and the balcony is pulling away from the building",
            "staircase railing has broken off and the stairs are dangerous",
        ],
        "High": [
            "roof is leaking into the bedroom during heavy rain",
            "window glass is broken and cannot be closed",
            "front door will not close properly",
            "water is seeping through the ceiling and dripping on the bed",
        ],
        "Medium": [
            "a hairline crack has appeared in the wall",
            "bathroom tile is cracked and loose",
            "door is sticking and hard to open",
            "small crack on the bedroom wall is getting longer",
        ],
        "Low": [
            "paint is peeling on the corridor wall",
            "scuff marks on the wall need touch up",
            "cabinet door hinge is slightly loose",
            "some paint is coming off in the hallway",
            "a tiny crack in the paint near the window frame",
        ],
    },
    "Pest Control": {
        "Critical": [
            "swarm of bees entered the bedroom and a family member is allergic",
            "snake spotted inside the unit near the children's room",
            "wasp nest inside the wall with many stings reported",
        ],
        "High": [
            "rats are seen in the kitchen and chewing food packets",
            "bed bugs found in the mattress and sofa",
            "cockroach infestation across all rooms",
            "termites are eating the wooden wardrobe and door frames",
        ],
        "Medium": [
            "ants are trailing along the counter",
            "mosquitoes are breeding in the balcony planter",
            "few cockroaches spotted near the sink",
            "flies keep coming from the drain",
        ],
        "Low": [
            "spider webs on the balcony ceiling",
            "request for a routine preventive pest spray",
            "a single lizard seen in the corridor",
        ],
    },
    "Security": {
        "Critical": [
            "main door lock is broken and the unit cannot be secured",
            "someone forced the door open and tried to break in",
            "fire alarm is blaring and smoke is coming from the corridor",
        ],
        "High": [
            "door key is stuck in the lock and will not turn",
            "balcony door latch is broken",
            "intercom is dead so visitors cannot be verified",
            "window lock is broken and the window will not close",
        ],
        "Medium": [
            "corridor light outside the unit is out at night",
            "peephole is cloudy and hard to use",
            "smoke detector keeps chirping with a low battery",
            "cctv camera image is blurry",
        ],
        "Low": [
            "need a duplicate key made",
            "request to relabel the nameplate on the door",
            "gate remote battery needs replacing",
        ],
    },
    "General": {
        "Critical": [
            "elevator is stuck between floors with people inside",
            "strong chemical smell spreading through the hallway making residents dizzy",
            "a fallen tree has blocked the building exit",
        ],
        "High": [
            "garbage chute is blocked and overflowing in the corridor",
            "water is leaking from the unit above into our ceiling",
            "lift is out of service and an elderly resident lives on the top floor",
            "overhead water tank is empty and the building has no water",
        ],
        "Medium": [
            "common area light is flickering",
            "parking gate sensor does not read my card",
            "mailbox lock is jammed",
            "laundry room machine is not working properly",
        ],
        "Low": [
            "suggest adding a notice board",
            "garden hedge needs trimming",
            "request to repaint the parking lot lines",
            "bench in the garden needs a fresh coat of paint",
        ],
    },
}

# ----------------------------------------------------------- compositional ---
COMPONENTS = {
    "Plumbing": ["kitchen sink", "bathroom sink", "toilet", "shower", "bathtub",
                 "washbasin", "tap", "drain pipe", "water pipe", "flush tank"],
    "Electrical": ["ceiling light", "wall socket", "switch board", "ceiling fan",
                   "tube light", "bedroom outlet", "circuit breaker", "extension board",
                   "doorbell", "lamp point"],
    "HVAC": ["air conditioner", "AC unit", "heater", "thermostat", "ventilation fan",
             "exhaust fan", "air vent", "furnace"],
    "Appliance": ["refrigerator", "washing machine", "dishwasher", "microwave", "oven",
                  "stove", "geyser", "dryer", "chimney"],
    "Structural": ["wall", "ceiling", "window", "door", "floor tiles", "balcony railing",
                   "roof", "staircase", "cabinet", "wardrobe"],
    "Security": ["front door lock", "main door", "balcony door latch", "intercom", "gate",
                 "window latch", "corridor light", "cctv camera"],
    "General": ["elevator", "parking gate", "mailbox", "corridor light", "garbage chute",
                "common area", "garden", "water tank", "laundry room", "terrace"],
}

# Severity cues that apply to any physical component.
COMPOSE = {
    "Low": [
        "{c} has minor cosmetic wear and could be touched up",
        "there is a small scratch on the {c}",
        "{c} looks old and I would like it replaced when convenient",
        "{c} makes a slight noise sometimes",
        "{c} is slightly loose",
        "request a routine check of the {c}",
        "{c} needs cleaning and a little paint",
        "paint is coming off near the {c}",
        "small marks around the {c}, purely cosmetic",
        "would like to upgrade the {c} sometime this month",
    ],
    "Medium": [
        "{c} is working but only intermittently",
        "{c} is slow and not performing well",
        "{c} is noisy and vibrates",
        "{c} stops working sometimes and then starts again",
        "{c} drips a little and needs repair",
        "{c} is damaged and needs to be fixed this week",
        "{c} is blocked and works slowly",
        "{c} has a crack that is getting bigger",
        "{c} is not working properly",
        "{c} gives weak performance since a few days",
    ],
    "High": [
        "{c} is not working at all",
        "{c} has completely stopped working since morning",
        "{c} is broken and we cannot use it",
        "{c} is leaking badly and the area around it is wet",
        "{c} has failed and there is no service in the unit",
        "{c} is badly damaged and unusable",
        "{c} stopped working and an elderly person depends on it",
        "{c} is totally dead, nothing works",
        "water is dripping from the {c} and things are getting wet",
        "{c} will not work and it is affecting the whole family",
    ],
}

# Category-specific Critical templates (kept physically sensible).
CRITICAL_COMPOSE = {
    "Plumbing": ["{c} burst and water is flooding the unit",
                 "{c} has broken and water is pouring everywhere"],
    "Electrical": ["{c} is sparking and giving off a burning smell",
                   "got an electric shock from the {c}",
                   "{c} is smoking and wires are exposed"],
    "HVAC": ["strong smell of gas near the {c}", "{c} is smoking and smells of burning"],
    "Appliance": ["{c} is sparking and smoking", "{c} caught fire", "{c} is leaking gas"],
    "Structural": ["{c} has collapsed and the area is dangerous",
                   "{c} is about to fall and people could be hurt"],
    "Security": ["{c} was forced open and someone tried to break in",
                 "{c} is broken and the unit cannot be secured at all"],
    "General": ["{c} has people trapped and they need help now",
                "{c} is on fire and residents are in danger"],
}

PEST_TERMS = ["ants", "cockroaches", "rats", "mosquitoes", "termites", "bed bugs",
              "lizards", "flies", "spiders", "mice"]
PEST_COMPOSE = {
    "Low": ["a single one of the {c} was seen once", "{c} spotted rarely near the balcony",
            "request for a preventive spray against {c}"],
    "Medium": ["a few {c} spotted in the kitchen", "{c} are visible every evening",
               "{c} are increasing slowly near the drain"],
    "High": ["{c} infestation in every room", "huge number of {c} and they are spreading fast",
             "{c} are damaging our food and belongings"],
    "Critical": ["swarm of {c} attacked a family member who needs medical help"],
}

PREFIXES = ["", "Hello, ", "Hi team, ", "Please note ", "Since yesterday ",
            "Since this morning ", "Just to report that ", "My "]
MOODS = ["", "", "", "Urgent: ", "Not urgent but ", "Whenever possible, "]
LOCATIONS = ["", "", " in the kitchen", " in the bedroom", " in the bathroom",
             " in the living room", " in my unit", " near the entrance"]
SUFFIXES = ["", "", ". Please fix soon.", ". Kindly check when possible.",
            ". Thank you.", ". Needs attention.", ". Please help."]

URGENCY_WEIGHTS = {"Low": 0.28, "Medium": 0.34, "High": 0.25, "Critical": 0.13}
_ORDER = ["Low", "Medium", "High", "Critical"]


def _phrase(rng: random.Random, category: str, urgency: str, curated_only: bool = False) -> str:
    """Pick either a curated sentence or build one from component + cue."""
    if curated_only or rng.random() < 0.4:
        return rng.choice(ISSUE_BANK[category][urgency])
    if category == "Pest Control":
        return rng.choice(PEST_COMPOSE[urgency]).format(c=rng.choice(PEST_TERMS))
    component = rng.choice(COMPONENTS[category])
    if urgency == "Critical":
        return rng.choice(CRITICAL_COMPOSE[category]).format(c=component)
    return rng.choice(COMPOSE[urgency]).format(c=component)


def make_request(rng: random.Random, category=None, urgency=None, curated_only=False):
    """Return (category, urgency, title, description) for one random request."""
    category = category or rng.choice(list(ISSUE_BANK))
    urgency = urgency or rng.choices(
        list(URGENCY_WEIGHTS), weights=list(URGENCY_WEIGHTS.values())
    )[0]
    phrase = _phrase(rng, category, urgency, curated_only)
    title = phrase[0].upper() + phrase[1:]
    if len(title) > 70:
        title = title[:67].rstrip() + "..."
    body = (
        rng.choice(MOODS) + rng.choice(PREFIXES) + phrase
        + rng.choice(LOCATIONS) + rng.choice(SUFFIXES)
    ).strip()
    body = body[0].upper() + body[1:]
    return category, urgency, title, body


def generate(n: int = 4000, seed: int = 42, label_noise: float = 0.04) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        category, urgency, title, body = make_request(rng)
        label = urgency
        if rng.random() < label_noise:  # reporter mis-judged severity by one level
            i = _ORDER.index(urgency)
            j = min(max(i + rng.choice([-1, 1]), 0), len(_ORDER) - 1)
            label = _ORDER[j]
        rows.append(
            {"category": category, "title": title, "description": body, "urgency": label}
        )
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = generate()
    df.to_csv(DATA_PATH, index=False)
    print(f"Wrote {len(df)} rows to {DATA_PATH}")
    print(df["urgency"].value_counts().to_string())
