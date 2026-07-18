#!/usr/bin/env python3
"""One-time seed for data/schedule.json (MFW Exploration to 1850, 34 weeks).

Refuses to overwrite an existing schedule.json -- Brian's edits live there.
Week topics from MFW's published Lesson Overview; Week 8 grid transcribed
from the official sample PDF. Other weeks: empty editable cells.
"""
import json
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "schedule.json")

HISTORY = {
    1: "Leif Ericsson, Columbus, Cabot, Ponce de Leon, Balboa, De Soto",
    2: "Charles V, Spanish Conquistadors, William the Silent, Mary Queen of Scots, Sir Walter Raleigh",
    3: "King James, Jamestown, French Exploration, Champlain",
    4: "Henry Hudson, The Pilgrims",
    5: "Massachusetts Bay Colony, Rhode Island Colony, Salem Witchcraft Trials",
    6: "New York Colony, Tobacco in Virginia, Angola",
    7: "Thirty Years' War, Charles I, Cromwell, Charles II, Carolina Colonies, Maryland Colony",
    8: "Virginia Colony, Louis XIV of France, Frederick, First Prussian King",
    9: "King Philip's War, War in New France, William Penn, Pennsylvania Colony",
    10: "Georgia Colony, Newton, Locke, Farming",
    11: "Russia and Peter the Great, Persia, Ottoman Empire",
    12: "India",
    13: "Japan, China",
    14: "China, Benjamin Franklin",
    15: "Wars, George Washington, French and Indian War",
    16: "King George III, Catherine the Great, The Stamp Act",
    17: "Spanish Missions",
    18: "Daniel Boone, Revolutionary War",
    19: "Thomas Jefferson, Declaration of Independence",
    20: "Revolutionary War (continued)",
    21: "The U.S. Constitution, President George Washington",
    22: "Captain Cook and Australia, The French Revolution",
    23: "Catherine the Great",
    24: "Robert Fulton, Eli Whitney",
    25: "Opium in China, Napoleon",
    26: "Louisiana Purchase, Haiti, Factories, Lewis and Clark",
    27: "Napoleon's Wars, War of 1812, Waterloo, Simon Bolivar",
    28: "Mexican Independence, Abolitionists, Africa, Trail of Tears, Nat Turner's Revolt",
    29: "China's Opium War, Samuel Morse, The Alamo",
    30: "New Zealand, California Gold Rush",
}
SCIENCE = {
    1: "Creation",
    2: "Classification System, The Animal Kingdom, Vertebrates",
    3: "Mammals",
    4: "Monkeys and Apes, Aquatic Mammals",
    5: "Marsupials, Charles Darwin",
    6: "Birds",
    7: "Fish",
    8: "Amphibians, Reptiles",
    9: "Snakes, Lizards, Turtles and Crocodiles",
    10: "Invertebrates, Arthropods, Insects",
    11: "Insect Metamorphosis, Arachnids, Crustaceans",
    12: "Myriapods, Mollusks, Coelenterates",
    13: "Echinoderms, Sponges, Worms",
    14: "Protists, Monerans, Louis Pasteur",
    15: "Introduction to Botany",
    16: "Introduction to Botany",
    17: "Seeds",
    18: "Angiosperms (Flowers)",
    19: "Angiosperms (Flowers)",
    20: "Pollination",
    21: "Fruit",
    22: "Fruit",
    23: "Leaves",
    24: "Leaves",
    25: "Roots",
    26: "Stems",
    27: "Gardening",
    28: "Gardening",
    29: "Trees",
    30: "Gymnosperms",
}
STATE_REPORT_SCIENCE = "Seedless Vascular Plants, Nonvascular Plants, Mycology"

FAMILY_SUBJECTS = ["Bible", "History", "Book Basket", "Science", "Art & Music", "Read-Aloud"]

# Transcribed from MFW's official Teacher's Manual sample (Week 8 grid).
WEEK8_TOPICS = ["Virginia Colony", "", "Louis XIV of France, 1643-1715",
                "Frederick, First Prussian King, 1701", ""]
WEEK8 = [
    {
        "Bible": "Read/study James 1:22-25 (see notes)\nReview James 1:12-21\nLearn/copy v. 22\nEvening: review James 1:22",
        "History": "Exploring American History p24-26 John Smith (begin at The Decline of Jamestown)\nGr. 6-8: Building a City on a Hill p333-337\nNotebook: Virginia Colony summary",
        "Science": "World of Animals p54 Amphibians (see notes)\nGuide to God's Animals p84-85",
        "Art & Music": "God and the History of Art p293 (review top of page); Lesson #172 Sign of the Fish",
        "Read-Aloud": "Amos Fortune, Free Man p93 The Arrival at Jaffrey",
    },
    {
        "Bible": "Read 2x James 1:22-25\nReview James 1:1-11 and 1:12-22\nLearn/copy v. 23\nIn God We Trust p37 Father Jacques Marquette\nEvening: review James 1:23",
        "History": "The New England Primer (see notes)\nOptional Gr. 6-8: Building a City on a Hill p338-346",
        "Art & Music": "Music: Schubert (see notes)",
        "Read-Aloud": "Amos Fortune, Free Man p109-118 Hard Work Fills the Iron Kettle",
    },
    {
        "Bible": "Read 2x James 1:22-25\nReview James 1:12-23\nLearn/copy v. 24\nEvening: review James 1:24",
        "History": "The Story of the World p143 The Sun King of France\nWorld History p218-219 France and the Sun King\nNotebook: King Louis XIV summary\nTimeline: Louis XIV",
        "Science": "World of Animals p57 Amphibian Metamorphosis (see notes)",
        "Art & Music": "God and the History of Art (see notes)",
        "Read-Aloud": "Amos Fortune, Free Man p119-129",
    },
    {
        "Bible": "Read 2x James 1:22-25\nReview James 1:12-24\nLearn/copy v. 25\nEvening: review James 1:22-25",
        "History": "The Story of the World p151 Frederick, The First Prussian King",
        "Science": "World of Animals p60 Reptiles (see notes)\nGuide to God's Animals p104-105",
        "Art & Music": "God and the History of Art p316 Watteau (optional, no project)",
        "Read-Aloud": "Amos Fortune, Free Man p130 Amos on the Mountain",
    },
    {
        "Bible": "Test: James 1:22-25",
        "Science": "Frog video: mfwbooks.com/media",
        "Read-Aloud": "Amos Fortune, Free Man p146 Auctioned for Freedom",
    },
]


def build():
    weeks = []
    for n in range(1, 35):
        history = HISTORY.get(n, "State Report")
        science = SCIENCE.get(n, STATE_REPORT_SCIENCE)
        days = []
        for d in range(5):
            family = {s: "" for s in FAMILY_SUBJECTS}
            if d < 4:  # Book Basket runs days 1-4 every week in the manual
                family["Book Basket"] = "Free reading from the book basket"
            if n == 8:
                family.update(WEEK8[d])
            days.append({"topic": WEEK8_TOPICS[d] if n == 8 else "", "family": family})
        week = {"num": n, "history": history, "science": science, "hymn": "", "days": days}
        if n == 8:
            week["hymn"] = "Then Sings My Soul p16: Now Thank We All Our God"
        weeks.append(week)

    return {
        "curriculum": "Exploration to 1850",
        "publisher": "My Father's World",
        "startDate": "2026-08-17",
        "familySubjects": FAMILY_SUBJECTS,
        "children": [
            {"id": "c1", "name": "Child 1", "grade": 8,
             "subjects": ["Math", "English", "Writing", "Spelling", "Reading", "Science (Gr 7-8)"]},
            {"id": "c2", "name": "Child 2", "grade": 7,
             "subjects": ["Math", "English", "Writing", "Spelling", "Reading", "Science (Gr 7-8)"]},
            {"id": "c3", "name": "Child 3", "grade": 5,
             "subjects": ["Math", "English", "Writing", "Spelling", "Reading"]},
        ],
        "lessons": {},  # per-child lesson text: lessons[childId]["w.d.Subject"] = "..."
        "done": {},     # checkboxes: done["family"|childId]["w.d.Subject"] = true
        "weeks": weeks,
    }


if __name__ == "__main__":
    if os.path.exists(OUT):
        raise SystemExit(f"{OUT} already exists; delete it first if you really want to re-seed.")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(build(), f, indent=1)
    doc = build()
    assert len(doc["weeks"]) == 34 and all(len(w["days"]) == 5 for w in doc["weeks"])
    print(f"Wrote {OUT}: 34 weeks x 5 days, {len(doc['children'])} children.")
