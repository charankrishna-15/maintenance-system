"""Hand-written requests used ONLY to sanity-check generalisation.

The wording was chosen to differ from the phrases in ml/generate_dataset.py.
The set is small (a smoke test, not a rigorous benchmark) and is reported
separately from the hold-out accuracy, which is computed on data from the
same synthetic generator as the training data and is therefore optimistic.
"""

# (category, title, description, expected urgency)
EXAMPLES = [
    ("Plumbing", "Leak", "There is a steady leak from the pipe below the basin and the floor is soaked", "High"),
    ("Plumbing", "Slow basin", "Wash basin water is not going down quickly, it is partially clogged", "Medium"),
    ("Plumbing", "Flood", "Water is flooding my kitchen right now", "Critical"),
    ("Plumbing", "Loose fitting", "The soap holder in the bathroom is a bit loose", "Low"),
    ("Plumbing", "No water", "There is no water coming from any tap in the flat", "High"),
    ("Electrical", "Gas", "I can smell gas in the kitchen", "Critical"),
    ("Electrical", "Bulb", "The light bulb in the store room has gone and needs a new one", "Low"),
    ("Electrical", "Sparks", "The socket near my bed makes sparks when I plug anything in", "Critical"),
    ("Electrical", "Fan", "The fan in my bedroom is not working at all", "High"),
    ("Electrical", "Flicker", "My study lamp point flickers and works only sometimes", "Medium"),
    ("HVAC", "AC", "Our air conditioner blows only warm air and the flat is unbearably hot", "High"),
    ("HVAC", "Noise", "AC rattles loudly and the room takes ages to cool", "Medium"),
    ("HVAC", "Service", "Whenever someone is free, please look at the AC filter during the routine visit", "Low"),
    ("Appliance", "Fridge", "The fridge has gone warm inside and the milk and vegetables are spoiling", "High"),
    ("Appliance", "Washer", "My washer vibrates and makes a lot of noise", "Medium"),
    ("Appliance", "Display", "Time shown on the microwave display is not correct", "Low"),
    ("Appliance", "Fire", "The toaster oven caught fire and I put it out", "Critical"),
    ("Structural", "Paint", "The paint on my living room wall is flaking in a few places", "Low"),
    ("Structural", "Crack", "A thin crack ran across the bedroom wall and it seems to be widening", "Medium"),
    ("Structural", "Roof", "Rain water comes through the terrace slab and drips onto my bed", "High"),
    ("Structural", "Collapse", "A big piece of the ceiling has collapsed in the hall", "Critical"),
    ("Pest Control", "Ants", "I keep finding some ants near the dining table", "Medium"),
    ("Pest Control", "Rats", "Rats are in every room and spreading fast", "High"),
    ("Pest Control", "Spider", "One small spider web in the corner of the balcony", "Low"),
    ("Security", "Lock", "I am unable to open my front door because the lock mechanism jammed", "High"),
    ("Security", "Break-in", "Someone broke in through the window last night and the lock is damaged", "Critical"),
    ("Security", "Key", "I would like a spare key made for my flatmate", "Low"),
    ("Security", "Light", "Bulb outside my flat entrance is dead, so the passage is dark at night", "Medium"),
    ("General", "Lift", "Our building lift has been broken for three days and my father uses a wheelchair", "High"),
    ("General", "Garden", "Please prune the bushes near the entrance gate", "Low"),
    ("General", "Mailbox", "I cannot open my letterbox as the lock is stuck", "Medium"),
    ("General", "Elevator", "Lift has stopped between two floors and people are trapped inside", "Critical"),
]
