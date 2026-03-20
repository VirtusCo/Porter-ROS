#!/usr/bin/env python3
"""Generate Porter AI Assistant training and evaluation datasets.

Produces ~10,000 training and ~2,000 evaluation examples across two categories:
  1. Conversational Q&A (~70%) — standard airport assistant dialogue
  2. Tool-use / function calling (~30%) — tool-calling format with <tool_call> tags

Usage:
    python3 scripts/generate_dataset.py [--train-size 10000] [--eval-size 2000] [--seed 42]

Output:
    data/conversational/train.jsonl   — conversational training set
    data/conversational/eval.jsonl    — conversational evaluation set
    data/tool_use/train.jsonl         — tool-use training set
    data/tool_use/eval.jsonl          — tool-use evaluation set
    data/combined/train.jsonl         — all training examples shuffled
    data/combined/eval.jsonl          — all evaluation examples shuffled
    data/stats.json                   — dataset statistics

Author: VirtusCo — Porter Robot Project
"""

import argparse
import json
import os
import random
import hashlib
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Seed & reproducibility
# ---------------------------------------------------------------------------
SEED = 42

# ---------------------------------------------------------------------------
# Entity pools — used by templates to generate diverse examples
# ---------------------------------------------------------------------------

GATES = (
    [f"A{i}" for i in range(1, 36)]
    + [f"B{i}" for i in range(1, 31)]
    + [f"C{i}" for i in range(1, 28)]
    + [f"D{i}" for i in range(1, 22)]
    + [f"E{i}" for i in range(1, 18)]
    + [f"F{i}" for i in range(1, 12)]
)

TERMINALS = ["Terminal 1", "Terminal 2", "Terminal 3", "Terminal 4", "Terminal 5"]
TERMINAL_SHORT = ["T1", "T2", "T3", "T4", "T5"]
CONCOURSES = ["Concourse A", "Concourse B", "Concourse C", "Concourse D", "Concourse E"]
LEVELS = ["Level 0", "Level 1", "Level 2", "Level 3"]

AIRLINES = {
    "Air India": {"code": "AI", "counters": "Row D, D1-D18", "type": "full_service"},
    "IndiGo": {"code": "6E", "counters": "Row B, B1-B15", "type": "low_cost"},
    "SpiceJet": {"code": "SG", "counters": "Row C, C1-C10", "type": "low_cost"},
    "Vistara": {"code": "UK", "counters": "Row E, E1-E12", "type": "full_service"},
    "Akasa Air": {"code": "QP", "counters": "Row A, A1-A8", "type": "low_cost"},
    "Emirates": {"code": "EK", "counters": "Row F, F1-F12", "type": "full_service"},
    "Singapore Airlines": {"code": "SQ", "counters": "Row G, G1-G8", "type": "full_service"},
    "British Airways": {"code": "BA", "counters": "Row H, H1-H6", "type": "full_service"},
    "Lufthansa": {"code": "LH", "counters": "Row J, J1-J6", "type": "full_service"},
    "Thai Airways": {"code": "TG", "counters": "Row K, K1-K4", "type": "full_service"},
    "Qatar Airways": {"code": "QR", "counters": "Row L, L1-L6", "type": "full_service"},
    "Etihad Airways": {"code": "EY", "counters": "Row M, M1-M4", "type": "full_service"},
    "Air Asia": {"code": "AK", "counters": "Row N, N1-N6", "type": "low_cost"},
    "GoFirst": {"code": "G8", "counters": "Row P, P1-P6", "type": "low_cost"},
    "Alliance Air": {"code": "9I", "counters": "Row Q, Q1-Q4", "type": "regional"},
    "Japan Airlines": {"code": "JL", "counters": "Row R, R1-R4", "type": "full_service"},
    "Cathay Pacific": {"code": "CX", "counters": "Row S, S1-S4", "type": "full_service"},
    "KLM": {"code": "KL", "counters": "Row T, T1-T4", "type": "full_service"},
    "Turkish Airlines": {"code": "TK", "counters": "Row U, U1-U4", "type": "full_service"},
    "Air France": {"code": "AF", "counters": "Row V, V1-V4", "type": "full_service"},
}

CITIES_DOMESTIC = [
    "Delhi", "Mumbai", "Bengaluru", "Chennai", "Kolkata", "Hyderabad",
    "Ahmedabad", "Pune", "Jaipur", "Lucknow", "Goa", "Kochi",
    "Chandigarh", "Patna", "Bhubaneswar", "Guwahati", "Varanasi",
    "Indore", "Nagpur", "Thiruvananthapuram", "Coimbatore", "Visakhapatnam",
    "Amritsar", "Srinagar", "Leh", "Port Blair", "Bagdogra", "Dehradun",
    "Ranchi", "Raipur", "Mangalore", "Udaipur", "Jodhpur",
]

CITIES_INTERNATIONAL = [
    "London", "Dubai", "Singapore", "Bangkok", "Tokyo", "New York",
    "San Francisco", "Sydney", "Melbourne", "Toronto", "Paris",
    "Frankfurt", "Hong Kong", "Kuala Lumpur", "Doha", "Abu Dhabi",
    "Colombo", "Kathmandu", "Dhaka", "Male", "Muscat", "Riyadh",
    "Seoul", "Shanghai", "Beijing", "Amsterdam", "Zurich", "Rome",
    "Istanbul", "Nairobi", "Johannesburg", "Lagos",
]

FLIGHT_NUMBERS = []
for airline_name, info in AIRLINES.items():
    code = info["code"]
    FLIGHT_NUMBERS.extend([f"{code}{random.randint(100, 999)}" for _ in range(8)])

RESTAURANTS = [
    "Starbucks", "Costa Coffee", "McDonald's", "Burger King", "Subway",
    "KFC", "Pizza Hut Express", "Domino's", "Haldiram's", "Dosa Factory",
    "Biryani Blues", "Punjabi by Nature", "Wok Express", "Sushi Counter",
    "Café Coffee Day", "Blue Tokai Coffee", "Falafel House", "Bikanervala",
    "Chaayos", "Theobroma", "Mad Over Donuts", "Beer Café", "Wow! Momo",
    "Taco Bell", "The Food Court Thali", "Rajdhani Express",
]

SHOPS = [
    "WHSmith", "Relay", "Croma Express", "IndiGifts", "The Gift Gallery",
    "Crossword", "Forest Essentials", "Good Earth", "Fabindia",
    "Victoria's Secret", "Swarovski", "Mont Blanc", "Titan Eyeplus",
]

FACILITIES = [
    "restroom", "ATM", "currency exchange", "pharmacy", "medical centre",
    "prayer room", "charging station", "lounge", "information desk",
    "luggage storage", "water fountain", "baby feeding room", "smoking area",
    "business centre", "yoga room", "spa", "transit hotel", "sleeping pod",
    "luggage wrapping", "post office", "lost and found", "police desk",
    "kids play area", "shower facility",
]

TRANSPORT_MODES = ["taxi", "Uber", "Ola", "metro", "bus", "car rental", "hotel shuttle"]

LANGUAGES = {
    "Hindi": "hi", "Tamil": "ta", "Telugu": "te", "Bengali": "bn",
    "Kannada": "kn", "Malayalam": "ml", "French": "fr", "German": "de",
    "Japanese": "ja", "Chinese": "zh", "Arabic": "ar", "Spanish": "es",
    "Korean": "ko", "Thai": "th", "Russian": "ru",
}

BAGGAGE_ITEMS = [
    "suitcase", "backpack", "carry-on", "duffel bag", "garment bag",
    "laptop bag", "stroller", "car seat", "golf clubs", "surfboard",
    "bicycle", "guitar", "skis", "snowboard", "cricket kit",
    "wheelchair", "walking frame", "medical equipment",
]

WALK_TIMES = list(range(2, 16))  # 2 to 15 minutes
DISTANCES = [20, 30, 40, 50, 60, 80, 100, 120, 150, 200, 250, 300]

DIRECTIONS_LANDMARKS = [
    "past the bookshop", "past the duty-free area", "past the coffee shop",
    "past the food court", "past the information desk", "near the escalator",
    "after the moving walkway", "opposite the charging station",
    "next to the prayer room", "beside the ATM", "just before the lounge",
    "after the restrooms", "near the children's play area",
    "across from the currency exchange", "behind the self-service kiosks",
]

PRICES_INR = [40, 50, 60, 80, 100, 150, 200, 250, 300, 400, 500,
              600, 750, 800, 1000, 1200, 1500, 2000, 2500, 3000, 3500, 5000]

CHECK_IN_ROWS = "ABCDEFGHJKLMNPQRSTUV"

BOARDING_TIMES = ["30 minutes", "35 minutes", "40 minutes", "45 minutes"]

SYSTEM_PROMPT_CONV = (
    "You are Virtue, a helpful airport assistant robot made by VirtusCo. "
    "Provide concise, accurate information to help passengers navigate the "
    "airport and answer their questions. Be friendly, professional, and "
    "proactive — offer to carry luggage and guide passengers when appropriate."
)

SYSTEM_PROMPT_TOOL = (
    "You are Virtue, an airport assistant robot made by VirtusCo with access "
    "to airport systems. Use the provided tools to help passengers. Call tools "
    "when you need real-time data or to perform actions. Respond naturally "
    "after receiving tool results."
)

# ---------------------------------------------------------------------------
# Conversational template definitions
# ---------------------------------------------------------------------------
# Each template: (category, weight, questions_list, response_generator)
# weight controls relative frequency in the final dataset

# ---------------------------------------------------------------------------
# Natural language variation — adds prefixes, suffixes, context to questions
# ---------------------------------------------------------------------------

PREFIXES = [
    "", "", "", "",  # 40% no prefix (keeps original phrasing)
    "Excuse me, ", "Hey, ", "Hi, ", "Hello, ",
    "Sorry to bother you, ", "Quick question — ",
    "Hi Porter, ", "Hey Porter, ",
    "Pardon me, ", "Can I ask — ",
    "I was wondering, ", "Do you know — ",
    "One question: ", "Could you help me? ",
]

SUFFIXES = [
    "", "", "", "", "",  # 50% no suffix
    " I'm in a rush.", " I have limited time.", " I'm running late!",
    " Thank you!", " Thanks.", " Please help.",
    " I'm a first-time traveler.", " I've never been here before.",
    " This airport is huge!", " I'm a bit confused.",
    " My flight is soon.", " I just arrived.",
    " I'm traveling alone.", " I'm with my family.",
    " I have mobility issues.", " I'm traveling with kids.",
]

CONTEXTS = [
    "", "", "", "", "", "",  # 60% no extra context
    "I'm traveling with my elderly parents. ",
    "It's my first time at this airport. ",
    "I just landed and I'm confused. ",
    "I have a connecting flight in 2 hours. ",
    "I'm traveling with two small children. ",
    "We're a group of 5 people. ",
    "I'm on a business trip. ",
    "My friend dropped me off and left. ",
    "I arrived early and have lots of time. ",
    "I'm in a wheelchair. ",
    "I don't speak much English. ",
    "I just went through security. ",
    "I'm in the arrivals area right now. ",
    "I'm at the departure gates. ",
]


def vary_question(q: str) -> str:
    """Add natural language variation to a question for uniqueness."""
    prefix = _r(PREFIXES)
    suffix = _r(SUFFIXES)
    context = _r(CONTEXTS)

    # If prefix is non-empty, lowercase the first char of the question
    if prefix and q and q[0].isupper():
        q = q[0].lower() + q[1:]

    return f"{context}{prefix}{q}{suffix}".strip()


def _r(choices):
    """Pick random from a list."""
    return random.choice(choices)


def _gate():
    return _r(GATES)


def _terminal():
    return _r(TERMINALS)


def _terminal_short():
    return _r(TERMINAL_SHORT)


def _airline():
    return _r(list(AIRLINES.keys()))


def _airline_code():
    a = _airline()
    return AIRLINES[a]["code"]


def _flight():
    return _r(FLIGHT_NUMBERS)


def _city_dom():
    return _r(CITIES_DOMESTIC)


def _city_intl():
    return _r(CITIES_INTERNATIONAL)


def _city():
    return _r(CITIES_DOMESTIC + CITIES_INTERNATIONAL)


def _restaurant():
    return _r(RESTAURANTS)


def _shop():
    return _r(SHOPS)


def _facility():
    return _r(FACILITIES)


def _transport():
    return _r(TRANSPORT_MODES)


def _walk_time():
    return _r(WALK_TIMES)


def _distance():
    return _r(DISTANCES)


def _landmark():
    return _r(DIRECTIONS_LANDMARKS)


def _price():
    return _r(PRICES_INR)


def _boarding_time():
    return _r(BOARDING_TIMES)


def _level():
    return _r(LEVELS)


def _concourse():
    return _r(CONCOURSES)


def _baggage_item():
    return _r(BAGGAGE_ITEMS)


def _lang():
    return _r(list(LANGUAGES.keys()))


# ---------------------------------------------------------------------------
# CONVERSATIONAL TEMPLATES (by category)
# ---------------------------------------------------------------------------

def gen_navigation_templates():
    """Generate navigation & wayfinding Q&A pairs."""
    templates = []

    # --- Gate directions ---
    gate_questions = [
        "Where is Gate {gate}?",
        "How do I get to Gate {gate}?",
        "Can you take me to Gate {gate}?",
        "Which way to Gate {gate}?",
        "I need to find Gate {gate}.",
        "Is Gate {gate} far from here?",
        "How far is Gate {gate}?",
        "Directions to Gate {gate} please.",
        "I'm looking for Gate {gate}, can you help?",
        "Point me to Gate {gate}.",
        "Take me to Gate {gate}, I'm running late.",
        "Where exactly is Gate {gate} located?",
        "Could you show me how to reach Gate {gate}?",
        "I can't find Gate {gate} anywhere.",
        "My boarding pass says Gate {gate}. Where is that?",
    ]

    gate_responses = [
        "Gate {gate} is in {terminal}, {concourse}. Head {landmark}, then continue straight — about {walk} minutes from here. Would you like me to guide you there?",
        "Gate {gate} is a {walk}-minute walk from here in {concourse}. Go straight, {landmark}, and follow the signs to {concourse}. I can carry your bags and lead the way.",
        "{gate} is in {terminal}, about {dist} meters ahead. Follow the overhead signs for {concourse}. There's a moving walkway partway that'll speed things up. Shall I escort you?",
        "Gate {gate} is located in {terminal}, {concourse}. It's about {walk} minutes on foot. The path goes {landmark}. I'll carry your luggage — ready to go?",
        "You'll find Gate {gate} in {concourse}, {terminal}. That's roughly a {walk}-minute walk from our current spot, {landmark}. I can take you there and carry your baggage.",
    ]

    for _ in range(500):
        gate = _gate()
        q = _r(gate_questions).format(gate=gate)
        a = _r(gate_responses).format(
            gate=gate, terminal=_terminal(), concourse=_concourse(),
            landmark=_landmark(), walk=_walk_time(), dist=_distance()
        )
        templates.append(("navigation", q, a))

    # --- Terminal directions ---
    terminal_questions = [
        "How do I get to {terminal}?",
        "Where is {terminal}?",
        "I need to go to {terminal}.",
        "Which way to {terminal} from here?",
        "Is {terminal} far?",
        "Can you take me to {terminal}?",
        "My flight is from {terminal}. How do I get there?",
        "I'm in the wrong terminal. I need {terminal}.",
        "How long to walk to {terminal}?",
        "Is there a shuttle to {terminal}?",
    ]

    terminal_responses = [
        "{terminal} is connected via the inter-terminal shuttle on {level}. The shuttle runs every {freq} minutes and takes about {ride} minutes. Follow the '{terminal} Transfer' signs. I can walk you to the shuttle station.",
        "To reach {terminal}, take the shuttle from {level} — runs every {freq} minutes, {ride}-minute ride. Alternatively, there's a sky bridge on Level 2 if {terminal} is adjacent. Shall I escort you?",
        "{terminal} is about {walk} minutes by shuttle from here. The shuttle station is on {level}, take the elevator down. I'll carry your bags — let's head there now.",
        "You can reach {terminal} via the inter-terminal shuttle ({level}, every {freq} minutes) or the covered walkway if it's next door. The shuttle is faster. Want me to take you?",
    ]

    for _ in range(250):
        term = _terminal()
        q = _r(terminal_questions).format(terminal=term)
        a = _r(terminal_responses).format(
            terminal=term, level=_r(["Level 0", "Level 1"]),
            freq=_r([3, 5, 7, 10]), ride=_r([5, 8, 10, 12, 15]),
            walk=_walk_time()
        )
        templates.append(("navigation", q, a))

    # --- Facility directions ---
    facility_questions = [
        "Where is the nearest {facility}?",
        "Is there a {facility} nearby?",
        "I need to find a {facility}.",
        "How do I get to the {facility}?",
        "Where's the closest {facility}?",
        "Can you take me to the {facility}?",
        "Do you know where the {facility} is?",
        "I'm looking for a {facility}.",
        "Is there a {facility} around here?",
        "Point me to the nearest {facility} please.",
        "Where can I find a {facility}?",
        "I urgently need a {facility}.",
    ]

    facility_responses = [
        "The nearest {facility} is about {dist} meters ahead, {landmark}. It's on {level}. Would you like me to take you there?",
        "There's a {facility} {landmark}, about {walk} minutes from here on {level}. I can guide you there and carry your bags.",
        "You'll find a {facility} on {level}, approximately {dist} meters away, {landmark}. Shall I walk you there?",
        "The closest {facility} is on {level}, {landmark} — roughly {walk} minutes on foot. There's another one near Gate {gate} as well. Want me to escort you to the nearest one?",
    ]

    for _ in range(500):
        fac = _facility()
        q = _r(facility_questions).format(facility=fac)
        a = _r(facility_responses).format(
            facility=fac, dist=_distance(), landmark=_landmark(),
            level=_level(), walk=_walk_time(), gate=_gate()
        )
        templates.append(("navigation", q, a))

    # --- General wayfinding ---
    general_nav = [
        ("Where is the arrivals area?",
         "The arrivals area is on Level 0 (ground floor). Take the escalator or elevator down. Baggage claim, meeting point, and ground transportation are all there. Follow the 'Arrivals' signs."),
        ("Which way to departures?",
         "Departures are on Level 2. Take the escalator or elevator up. Check-in counters, security, and gates are all on that level. Follow the 'Departures' signs overhead."),
        ("Where is the nearest elevator?",
         f"The nearest elevator is about {_distance()} meters ahead, {_landmark()}. It connects all terminal levels and is wheelchair accessible with braille buttons."),
        ("Is there a moving walkway between the gates?",
         f"Yes, there are moving walkways in the main concourse corridors. The nearest one starts about {_distance()} meters ahead. Stay right to stand, walk on the left for faster transit."),
        ("Where are the escalators?",
         f"Escalators are in the central atrium area, about {_distance()} meters ahead. They connect all levels from Level 0 (arrivals) to Level 3 (lounges). There's an elevator right next to them."),
    ]
    for q, a in general_nav:
        for _ in range(15):
            templates.append(("navigation", q, a))

    return templates


def gen_flight_templates():
    """Generate flight information Q&A pairs."""
    templates = []

    flight_status_questions = [
        "Is flight {flight} on time?",
        "What's the status of {flight}?",
        "Is {flight} to {city} delayed?",
        "Has flight {flight} been cancelled?",
        "When does {flight} depart?",
        "What time does {flight} board?",
        "Is {flight} still on schedule?",
        "Can you check if {flight} is delayed?",
        "My flight {flight} — any updates?",
        "Has the gate changed for {flight}?",
        "What gate is {flight} departing from?",
        "I'm on flight {flight}. Is everything okay?",
        "Any delays on {flight} to {city}?",
        "When is boarding for {flight}?",
    ]

    flight_status_responses = [
        "For real-time status of flight {flight}, please check the flight information display screens — the nearest one is about {dist} meters ahead. You can also check your airline's app for live updates. Would you like me to take you to the information desk?",
        "Let me help you check that. The nearest flight information display showing {flight} status is {landmark}. Boarding typically starts {boarding_time} before departure. I can also take you to the airline counter for direct assistance.",
        "Flight status updates are shown on the FIDS screens throughout the terminal. The closest one is about {dist} meters to your right. For {flight}, your airline's app will also have real-time gate and delay information. Shall I walk you to the display?",
        "I'd recommend checking the departure board for {flight} — it's {dist} meters ahead. The screens show real-time status including any delays and gate changes. If you need more information, the airline counter is on Level 2.",
    ]

    for _ in range(500):
        flight = _flight()
        city = _city()
        q = _r(flight_status_questions).format(flight=flight, city=city)
        a = _r(flight_status_responses).format(
            flight=flight, dist=_distance(), landmark=_landmark(),
            boarding_time=_boarding_time()
        )
        templates.append(("flight_info", q, a))

    # --- Delay/cancellation ---
    delay_questions = [
        "My flight is delayed. What should I do?",
        "My flight got cancelled. Help!",
        "I missed my flight. What are my options?",
        "My flight has been delayed by {hours} hours.",
        "The departure board shows my flight is delayed. What now?",
        "I've been waiting for hours. My flight keeps getting delayed.",
        "What are my rights if my flight is delayed more than 2 hours?",
        "Can I get a refund if my flight is cancelled?",
        "My connecting flight is delayed. Will I miss my connection?",
        "The airline hasn't told us anything about the delay.",
    ]

    delay_responses = [
        "I'm sorry about the disruption. Here's what I recommend:\n1. Check the FIDS screen for the updated time\n2. Visit your airline's counter on Level 2 for rebooking options\n3. If the delay is over 2 hours, you may be entitled to meal vouchers\n4. The food court and lounges are nearby to wait comfortably\nWould you like me to take you to the airline counter?",
        "That's frustrating. Let me help:\n1. Head to your airline's service counter (Level 2, check-in hall) for rebooking\n2. For delays over 4 hours, airlines typically provide meals; overnight — hotel accommodation\n3. Keep your boarding pass and all receipts\n4. You can request a full refund if you prefer not to wait\nI'll carry your bags to the counter if you'd like.",
        "I understand your concern. Your options:\n1. Visit the airline counter immediately for the next available flight\n2. For cancellations, you're entitled to a rebooking or full refund\n3. If the wait is long, there are lounges (day passes ~₹{price}) and sleeping pods near Gate C18\n4. Keep all documentation for potential compensation claims\nShall I escort you to the airline counter?",
    ]

    for _ in range(350):
        hours = _r([1, 2, 3, 4, 5, 6])
        q = _r(delay_questions).format(hours=hours)
        a = _r(delay_responses).format(price=_r([2000, 2500, 3000, 3500]))
        templates.append(("flight_info", q, a))

    # --- Boarding & timing ---
    boarding_questions = [
        "When should I be at the gate?",
        "How early should I get to my gate?",
        "What time does boarding usually start?",
        "Is 20 minutes enough to get to my gate?",
        "My next flight boards in 30 minutes. Can I make it to Gate {gate}?",
    ]

    boarding_responses = [
        "I recommend being at your gate at least {boarding_time} before departure. Boarding typically starts then and the gate closes 10-15 minutes before departure. With your gate at {gate}, that's about a {walk}-minute walk from here.",
        "Boarding usually begins {boarding_time} before the scheduled departure for international flights, 30 minutes for domestic. Gate {gate} is about {walk} minutes from your current location. I'd suggest heading there now to be safe.",
        "Be at Gate {gate} at least {boarding_time} before departure. From here it's a {walk}-minute walk. If your boarding time is close, I can take the fastest route and carry your bags. Want to go now?",
    ]

    for _ in range(200):
        gate = _gate()
        q = _r(boarding_questions).format(gate=gate, layover=_r([1, 2, 3, 4]))
        a = _r(boarding_responses).format(
            gate=gate, boarding_time=_boarding_time(), walk=_walk_time()
        )
        templates.append(("flight_info", q, a))

    # --- Layover & connection timing ---
    layover_questions = [
        "I have a {layover}-hour layover. Is that enough?",
        "I have a {layover}-hour layover. Will I make my connection?",
        "How much time do I need for my connection?",
        "My connecting flight is in {layover} hours. Is that enough time?",
        "I'm transiting through this airport. How much time do I need?",
        "Will {layover} hours be enough for a connecting flight?",
        "I need to change terminals for my connection. How long does that take?",
    ]

    layover_responses = [
        "For a {layover}-hour layover:\n- Domestic connection: minimum 1 hour needed (security re-check)\n- International connection: minimum 2 hours (immigration + security)\n- Terminal transfer adds 15-20 minutes (inter-terminal shuttle)\nWith {layover} hours, you {assessment}. I can guide you to your connecting gate and carry your bags to save time.",
        "A {layover}-hour layover {assessment}. Here's what to plan for:\n1. Immigration/security: 20-45 minutes depending on queues\n2. Terminal transfer (if needed): 15-20 minutes by shuttle\n3. Be at your gate 35 minutes before departure\nThat leaves you about {free_time} of free time. Want me to help you navigate to your next gate?",
        "Connection time depends on:\n- Same terminal: ~45 minutes minimum\n- Different terminal: ~90 minutes minimum (shuttle + security)\n- International→Domestic: ~2 hours (immigration + re-check-in)\nWith {layover} hours, you {assessment}. I'll carry your bags and take the fastest route.",
    ]

    for _ in range(200):
        layover = _r([1, 2, 3, 4, 5, 6, 8])
        if layover <= 1:
            assessment = "might be tight — head to your gate immediately"
            free_time = "no"
        elif layover <= 2:
            assessment = "should be fine for domestic, but tight for international"
            free_time = "30-45 minutes"
        elif layover <= 4:
            assessment = "have comfortable time for your connection"
            free_time = f"{layover - 2} hours"
        else:
            assessment = "have plenty of time — you could explore the airport or visit a lounge"
            free_time = f"{layover - 2} hours"
        q = _r(layover_questions).format(layover=layover)
        a = _r(layover_responses).format(
            layover=layover, assessment=assessment, free_time=free_time
        )
        templates.append(("flight_info", q, a))

    return templates


def gen_checkin_templates():
    """Generate check-in and boarding Q&A pairs."""
    templates = []

    # --- Airline counter location ---
    counter_questions = [
        "Where is the {airline} check-in counter?",
        "Where do I check in for {airline}?",
        "I'm flying {airline}. Where do I go?",
        "Can you take me to the {airline} counter?",
        "Which row is {airline} check-in?",
        "Where is {airline}'s baggage drop?",
        "I need to find {airline} customer service.",
        "Where are the {airline} self-service kiosks?",
        "I can't find the {airline} counter.",
        "Is {airline} check-in on this floor?",
    ]

    for _ in range(350):
        airline = _airline()
        info = AIRLINES[airline]
        q = _r(counter_questions).format(airline=airline)
        is_intl = info["type"] == "full_service"
        hall = "international" if (is_intl and random.random() > 0.3) else "domestic"
        a = (
            f"{airline} check-in counters are in the {hall} departures hall on Level 2, "
            f"{info['counters']}. Enter through the main departures entrance and look for "
            f"the {airline} signage. Self-service kiosks are available near the entrance. "
            f"I can carry your bags and take you there."
        )
        templates.append(("check_in", q, a))

    # --- Check-in process ---
    process_questions = [
        "How early should I arrive for check-in?",
        "When does check-in close?",
        "Can I do web check-in?",
        "I already have a mobile boarding pass. Do I need the counter?",
        "Where are the self-service kiosks?",
        "Can I check in at the airport without a booking reference?",
        "I need to print my boarding pass.",
        "How do I use the self-service kiosk?",
        "Can I upgrade my seat at the counter?",
        "Where is the baggage drop for online check-in?",
        "I want to change my seat. Can I do that here?",
        "What documents do I need for check-in?",
    ]

    process_responses = [
        "For {flight_type} flights, arrive at least {hours} hours before departure. Check-in counters close {close_min} minutes before departure. If you've done web check-in and have no bags to check, you can go directly to security.",
        "Yes, most airlines offer web check-in 24-48 hours before departure via their app or website. If you've already checked in online, head to the baggage drop counter (separate, faster queue) or go straight to security if you have no checked bags.",
        "Self-service check-in kiosks are at the entrance of the check-in hall on Level 2 — about 20 kiosks near the main doors. They support check-in, seat selection, and boarding pass printing for most airlines.",
        "If you have a mobile boarding pass (QR code) and no checked luggage, proceed directly to security — no counter visit needed. For bags, use the baggage drop counter (faster than full check-in). Make sure your QR code is scannable.",
        "You can print your boarding pass at the self-service kiosks on Level 2 (free, all airlines) or at your airline's check-in counter. The business centre near Gate A5 also has printing services. Would you like directions?",
        "For check-in you'll need: valid photo ID (domestic) or passport (international), your booking reference or PNR number, and visa documents if applicable. Most airlines also accept the booking email on your phone.",
    ]

    for _ in range(350):
        flight_type = _r(["domestic", "international"])
        hours = "2" if flight_type == "domestic" else "3"
        close_min = _r([45, 60])
        q = _r(process_questions)
        a = _r(process_responses).format(
            flight_type=flight_type, hours=hours, close_min=close_min
        )
        templates.append(("check_in", q, a))

    return templates


def gen_baggage_templates():
    """Generate baggage-related Q&A pairs.

    Uses sub-group matching to ensure lost-bag questions get lost-bag responses,
    damaged-bag questions get damage responses, etc.
    """
    templates = []

    # --- Sub-group: Lost / missing bag ---
    lost_qs = [
        "My bag didn't come on the carousel.",
        "I lost my luggage. Where do I report it?",
        "My suitcase is missing. What should I do?",
        "I can't find my checked bag. Help!",
        "My luggage hasn't arrived. Where do I go?",
        "One of my bags is missing from the carousel.",
    ]
    lost_rs = [
        "I'm sorry about the missing bag. Steps:\n1. Wait until the carousel fully stops\n2. Check oversize baggage area nearby\n3. If still missing, go to the Lost Baggage counter at the end of the hall\n4. Have your baggage claim tag ready\nMost delayed bags arrive within 24 hours. Want me to take you to the counter?",
        "I'm sorry to hear that. Here's what to do:\n1. Check if the carousel is still running — bags sometimes come late\n2. Look at the oversize baggage area next to the carousel\n3. Go to the Lost Baggage counter (Level 0, end of arrivals hall)\n4. File a Property Irregularity Report (PIR) with your airline\n5. Keep your baggage claim tag and boarding pass\nMost bags are found within 24-48 hours. I'll carry your other bags and take you to the counter.",
    ]
    for _ in range(120):
        q = _r(lost_qs)
        a = _r(lost_rs)
        templates.append(("baggage", q, a))

    # --- Sub-group: Damaged bag ---
    damaged_qs = [
        "My luggage is damaged. What do I do?",
        "My bag's zipper broke on the flight.",
        "My suitcase wheel is broken. Where do I report this?",
        "The airline damaged my bag. Where do I complain?",
    ]
    damaged_rs = [
        "For damaged luggage, report immediately at your airline's baggage counter in arrivals (Level 0) before leaving the airport. Have your boarding pass and baggage tag ready. Take photos of the damage. Claims must be filed within 7 days.",
        "I'm sorry about the damage. Steps:\n1. Take photos of the damage right now\n2. Go to your airline's baggage counter (Level 0, arrivals)\n3. File a damage report before leaving the airport\n4. Keep your boarding pass and baggage claim tag\n5. The airline may repair, replace, or compensate\nClaims must be filed within 7 days. Want me to take you to the counter?",
    ]
    for _ in range(80):
        q = _r(damaged_qs)
        a = _r(damaged_rs)
        templates.append(("baggage", q, a))

    # --- Sub-group: Allowance & dimensions ---
    allowance_qs = [
        "What's the baggage allowance for economy class?",
        "How much checked baggage can I take?",
        "What are the cabin bag dimensions?",
        "How many bags can I carry on board?",
        "Are there any weight limits for carry-on bags?",
        "I need to check an extra bag. How much?",
        "How much for overweight baggage?",
        "Can I take my {item} as carry-on?",
        "Can I gate-check my {item}?",
        "I have fragile items. How should I pack them?",
    ]
    allowance_rs = [
        "Baggage allowances vary by airline and route. Typical economy limits:\n- Checked: 15-23 kg (one bag domestic, sometimes two international)\n- Cabin: 7-10 kg, max ~55×40×20 cm\n- Personal item: one small bag\nCheck your booking confirmation for specifics. I have a built-in scale — want me to weigh your bags?",
        "Cabin bag limits are typically 7-10 kg with dimensions around 55×40×20 cm, but this varies by airline. Most airlines allow one cabin bag plus one personal item (laptop bag, purse). Check your airline's specific policy.",
        "Excess baggage fees vary: typically ₹400-750 per extra kg at the airport. Buying extra allowance online beforehand is 30-50% cheaper. I can weigh your bags with my built-in scale to check before you go to the counter.",
    ]
    for _ in range(150):
        q = _r(allowance_qs).format(item=_baggage_item())
        a = _r(allowance_rs)
        templates.append(("baggage", q, a))

    # --- Sub-group: Baggage claim ---
    claim_qs = [
        "Where is baggage claim?",
        "Which carousel is for flight {flight}?",
        "Where do I pick up my checked bags on arrival?",
    ]
    claim_rs = [
        "Baggage claim is on Level 0 (ground floor), past immigration for international or directly after arrival corridors for domestic. Carousel numbers appear on screens near the baggage hall. I can carry your bags from the carousel.",
    ]
    for _ in range(80):
        q = _r(claim_qs).format(flight=_flight())
        a = _r(claim_rs)
        templates.append(("baggage", q, a))

    # --- Sub-group: Storage & wrapping ---
    storage_qs = [
        "Is there a luggage storage facility?",
        "Is there a left luggage counter?",
        "Can I wrap my luggage here?",
        "Where is the oversize baggage counter?",
    ]
    storage_rs = [
        "Luggage storage is on Level 1, near the inter-terminal shuttle. It's open 24 hours, rates around ₹{price}/bag/day. You'll need valid ID. I can carry your bags there.",
        "Luggage wrapping is near the check-in hall entrance on Level 2. Cost is ₹300-500 per bag. It protects against damage and tampering — recommended for soft bags and fragile items.",
        "The oversize baggage counter is at the far end of the check-in hall on Level 2. Items like golf clubs, surfboards, musical instruments, and sports equipment are handled there. Special tags and handling fees may apply.",
    ]
    for _ in range(80):
        q = _r(storage_qs)
        a = _r(storage_rs).format(price=_r([100, 150, 200, 250]))
        templates.append(("baggage", q, a))

    # --- Sub-group: Porter carry ---
    porter_qs = [
        "Can you carry my bags?",
        "Can you weigh my bags?",
        "I have heavy luggage. Can you help?",
    ]
    porter_rs = [
        "Absolutely! That's what I'm here for. Place your bags on my platform — I can carry up to 120 kg. I'll transport them anywhere in the terminal. I can also weigh them for you. Ready to load up?",
    ]
    for _ in range(60):
        q = _r(porter_qs)
        a = _r(porter_rs)
        templates.append(("baggage", q, a))

    return templates


def gen_services_templates():
    """Generate airport services Q&A pairs."""
    templates = []

    # --- WiFi, charging, etc. ---
    service_questions = [
        "Is there free WiFi?",
        "How do I connect to WiFi?",
        "Where can I charge my phone?",
        "Is there a charging station near Gate {gate}?",
        "Where's the prayer room?",
        "Where is the currency exchange?",
        "Is there a pharmacy nearby?",
        "Where can I get a SIM card?",
        "Is there a medical centre?",
        "Where is the airport lounge?",
        "Do you accept Priority Pass?",
        "Is there a smoking area?",
        "Can I get a shower at the airport?",
        "Where is the lost and found?",
        "Is there a hotel inside the airport?",
        "Where are the sleeping pods?",
        "Is there a yoga room?",
        "Where can I get a massage?",
        "Is there a business centre?",
        "Where is the post office?",
        "Is there a dry cleaning service?",
        "Where can I buy travel adapters?",
        "Is there an ATM nearby?",
        "Where can I iron my clothes?",
        "Is there a kids' play area?",
        "Where's the baby feeding room?",
        "Is there a pet relief area?",
    ]

    service_responses = [
        "Yes, the airport offers free WiFi! Select 'Airport_Free_WiFi', enter your phone number on the login page, and get {hours} hours complimentary. Premium high-speed WiFi is available for a fee through the airport app.",
        "Charging stations are throughout the terminal:\n- Free charging counters near most gates (look for the plug symbol)\n- USB ports built into some seating areas\n- Charging lockers near the food court where you can lock your device\nThe nearest station is about {dist} meters ahead.",
        "The prayer room is on Level 2, near Gate {gate}. It's a multi-faith room, open 24 hours, with prayer mats and separate sections. Ablution facilities are adjacent. Would you like me to guide you?",
        "Currency exchange counters: before security (check-in hall, Level 2), after security (near Gate {gate}), and in arrivals (Level 0). ATMs with foreign currency are nearby too. Rates vary between providers.",
        "The pharmacy is on Level 1, near the medical centre. Open 6 AM to midnight. Stocks common medications, first aid, and toiletries. There's a smaller pharmacy kiosk after security near Gate {gate}.",
        "SIM cards are available in the arrivals area (Level 0) after customs — Jio, Airtel, and Vi have kiosks. You'll need your passport and a photo. Tourist SIM plans start from ₹{price}. Activation takes 15-30 minutes.",
        "The medical centre is on Level 1, staffed 24/7 with doctors and nurses. First aid stations are also near Gates {gate} and {gate2}. In case of emergency, call 112 or alert any staff member.",
        "Airport lounges available:\n- Plaza Premium (Level 3, near Gate {gate})\n- Encalm Privé (Level 3)\n- Travel Club (international, after security)\nAccess with business class boarding pass, Priority Pass, or day pass (₹{price}). All offer food, WiFi, and showers.",
        "The Lost & Found office is on Level 1, open 7 AM to 11 PM. For items left at security, there's a separate security Lost & Found desk. For items lost on aircraft, contact your airline directly.",
        "Transit hotel near Gate C18 — rooms bookable hourly (from ₹{price} for 4 hours). Sleeping pods near Gates B12 and D5 (₹{pod_price}/hour). Both include WiFi and basic amenities. Great for long layovers.",
        "Shower facilities:\n- Airport lounges (included with access)\n- Freshen Up counters near Gate B10 (₹{price}, includes towel and toiletries)\n- Transit hotel near Gate C18 (shower-only option ₹500)\nAllow 20-30 minutes. No booking needed for Freshen Up counters.",
    ]

    for _ in range(800):
        gate = _gate()
        gate2 = _gate()
        hours = _r([2, 3, 4])
        price = _r([400, 500, 600, 1500, 2000, 2500])
        pod_price = _r([400, 500, 600])
        q = _r(service_questions).format(gate=gate)
        a = _r(service_responses).format(
            gate=gate, gate2=gate2, hours=hours, dist=_distance(),
            price=price, pod_price=pod_price
        )
        templates.append(("services", q, a))

    return templates


def gen_dining_shopping_templates():
    """Generate dining and shopping Q&A pairs.

    Uses sub-group matching to ensure vegetarian questions get vegetarian
    responses, halal questions get halal responses, etc.
    """
    templates = []

    # --- Sub-group: General food / food court ---
    general_food_qs = [
        "Where can I eat?",
        "I'm hungry. Any restaurants nearby?",
        "Is there a {restaurant} here?",
        "Where is the food court?",
        "Are there any 24-hour restaurants?",
        "Any late-night eating options?",
        "Where can I find Indian food?",
        "Is there sushi available?",
        "Where can I get a sandwich?",
        "Is food expensive at the airport?",
        "Is there a kids' menu anywhere?",
        "Is there a bar or place to get a beer?",
    ]
    general_food_rs = [
        "The main food court is on Level 2, about {walk} minutes from here. It has 15+ options:\n- Indian: Haldiram's, Dosa Factory, Punjabi by Nature\n- Fast food: McDonald's, KFC, Subway\n- Café: Starbucks, Costa Coffee\nVegetarian, halal, and gluten-free options available. Shall I carry your bags there?",
        "There are plenty of dining options! The food court (Level 2, {walk} minutes) has Indian, fast food, and international cuisine. {restaurant} is about {dist}m ahead. Most restaurants are open 6 AM to 11 PM. Want me to take you there?",
        "Yes, {restaurant} is here! It's in the food court on Level 2, about {dist} meters from here. The food court also has 15+ other restaurants. Shall I carry your bags and walk you there?",
    ]
    for _ in range(200):
        fmt = dict(restaurant=_restaurant(), walk=_walk_time(), dist=_distance(),
                   minutes=_r([10, 15, 20, 25, 30]))
        q = _r(general_food_qs).format(**fmt)
        a = _r(general_food_rs).format(**fmt)
        templates.append(("dining_shopping", q, a))

    # --- Sub-group: Vegetarian / vegan ---
    veg_qs = [
        "Is there vegetarian food available?",
        "Any vegan restaurants?",
        "Can you recommend a vegetarian restaurant?",
        "Where can I find veg food?",
        "I'm vegetarian. What are my options?",
        "I don't eat meat. Where can I eat?",
        "Are there any pure-veg restaurants here?",
    ]
    veg_rs = [
        "Yes, plenty of vegetarian options! Haldiram's (fully vegetarian), Dosa Factory (South Indian vegetarian), Subway (veg subs), and most restaurants mark vegetarian items with a green dot. For Jain food, Haldiram's has specific options. Let me take you to the food court.",
        "Great vegetarian restaurants here:\n- Haldiram's — fully vegetarian, Indian snacks and thalis\n- Dosa Factory — South Indian vegetarian (dosas, idlis, vadas)\n- Bikanervala — North Indian vegetarian sweets and meals\n- Subway — customizable veg subs and salads\nThe food court on Level 2 has all of these. Shall I take you?",
        "For vegan options, try:\n- Dosa Factory (most items are naturally vegan)\n- Falafel House in the food court (vegan wraps and bowls)\n- Subway (vegan patty available)\n- Fresh fruit and salads at WHSmith grab-and-go\nMost Indian restaurants have vegan-friendly options. Want me to carry your bags there?",
    ]
    for _ in range(150):
        q = _r(veg_qs)
        a = _r(veg_rs)
        templates.append(("dining_shopping", q, a))

    # --- Sub-group: Halal ---
    halal_qs = [
        "Any halal food options?",
        "Where can I find halal food?",
        "Is there halal-certified food here?",
        "I need halal food. Where should I go?",
    ]
    halal_rs = [
        "Halal food is widely available! Biryani Blues near Gate {gate} is halal-certified, and most fast-food chains in India (McDonald's, KFC, Subway) use halal-certified chicken. Haldiram's is fully vegetarian, so naturally halal. Look for halal certification signs at the entrance.",
        "Halal options at the airport:\n- Biryani Blues (halal-certified, food court)\n- McDonald's and KFC (halal chicken in India)\n- Punjabi by Nature (food court, Level 2)\n- Falafel House (Middle Eastern, food court)\nLook for the green halal certification at restaurant entrances. Shall I guide you?",
    ]
    for _ in range(80):
        q = _r(halal_qs)
        a = _r(halal_rs).format(gate=_gate())
        templates.append(("dining_shopping", q, a))

    # --- Sub-group: Gluten-free ---
    gf_qs = [
        "Where can I find gluten-free food?",
        "I have celiac disease. What can I eat here?",
        "Any gluten-free options at the airport?",
    ]
    gf_rs = [
        "For gluten-free options:\n- Dosa Factory — dosas and rice items are naturally gluten-free\n- Haldiram's — many snacks are rice/lentil based (check labels)\n- Subway — salad bowls without bread\n- Fresh fruit and salads at WHSmith grab-and-go\nMost Indian rice dishes are gluten-free. Ask staff about specific ingredients. Want me to take you to the food court?",
    ]
    for _ in range(50):
        q = _r(gf_qs)
        a = _r(gf_rs)
        templates.append(("dining_shopping", q, a))

    # --- Sub-group: Quick food ---
    quick_qs = [
        "I need something quick, I have {minutes} minutes.",
        "Where's the nearest grab-and-go option?",
        "I'm in a rush. Where can I get food fast?",
        "Quick food options near my gate?",
    ]
    quick_rs = [
        "For a quick bite with only {minutes} minutes:\n- Grab-and-go at WHSmith ({dist}m ahead, pre-made sandwiches and snacks)\n- {restaurant} nearby for fast service\nI'd recommend the grab-and-go if you're pressed for time. Want me to carry your bags while you eat?",
        "The fastest options nearby:\n- WHSmith grab-and-go ({dist}m, ready-made food)\n- Wow! Momo (quick dumplings, near the food court)\n- Café Coffee Day (snacks and drinks, {dist}m ahead)\nAll can serve you in under 5 minutes. Shall I hold your bags?",
    ]
    for _ in range(80):
        fmt = dict(minutes=_r([10, 15, 20, 25, 30]), dist=_distance(),
                   restaurant=_restaurant())
        q = _r(quick_qs).format(**fmt)
        a = _r(quick_rs).format(**fmt)
        templates.append(("dining_shopping", q, a))

    # --- Sub-group: Coffee ---
    coffee_qs = [
        "Where can I get coffee?",
        "Is there a Starbucks here?",
        "I need caffeine. Any coffee shops?",
        "Where's the nearest cafe?",
    ]
    coffee_rs = [
        "Coffee options nearby:\n- Starbucks ({dist}m ahead)\n- Café Coffee Day near the food court\n- Blue Tokai Coffee on Level 2\n- Costa Coffee near Gate {gate}\nMost are open 5 AM to 11 PM. After security, prices are 20-30% higher than outside. Shall I take you?",
    ]
    for _ in range(60):
        q = _r(coffee_qs)
        a = _r(coffee_rs).format(dist=_distance(), gate=_gate())
        templates.append(("dining_shopping", q, a))

    # --- Sub-group: Water ---
    water_qs = [
        "Where can I buy water?",
        "Is there a water fountain?",
        "Can I refill my water bottle?",
    ]
    water_rs = [
        "Water options after security:\n- Bottle refill stations (free) near Gates {gate} and {gate2} — look for blue tap signs\n- WHSmith/Relay stores — bottled water ₹{price}\nI recommend the refill stations if you have a reusable bottle.",
    ]
    for _ in range(50):
        q = _r(water_qs)
        a = _r(water_rs).format(gate=_gate(), gate2=_gate(), price=_r([40, 50, 60]))
        templates.append(("dining_shopping", q, a))

    # --- Shopping ---
    shop_questions = [
        "Where is the duty-free shop?",
        "Can I buy souvenirs?",
        "Where's {shop}?",
        "Is there an electronics store?",
        "Where can I buy headphones?",
        "Any gift shops here?",
        "Where can I buy Indian sweets to take abroad?",
        "Is there a bookshop?",
        "Can I use UPI for payments?",
        "Can I buy duty-free on a domestic flight?",
    ]

    shop_responses = [
        "The duty-free area is after international security and immigration, between Gates C1-C15. It has liquor, perfumes, electronics, chocolates, and designer items. Duty-free is only for international passengers.",
        "Souvenir and gift shops: {shop} near the check-in area (local handicrafts), IndiGifts after international security (traditional items), and WHSmith at multiple locations. Prices are higher inside the airport.",
        "Yes! {shop} is on Level 2, {landmark}. They carry a wide selection. There are also smaller stores near the gate areas. Would you like me to take you there?",
        "Electronics at Croma Express on Level 2 (after security) near Gate B5 — adapters, headphones, chargers, power banks. Also duty-free electronics (international only) at tax-free prices.",
        "Most shops accept UPI (Google Pay, PhonePe, Paytm), cards, and cash. Some smaller kiosks may be card/cash only. Always good to have a backup payment method.",
    ]

    for _ in range(350):
        shop = _shop()
        q = _r(shop_questions).format(shop=shop)
        a = _r(shop_responses).format(shop=shop, landmark=_landmark())
        templates.append(("dining_shopping", q, a))

    return templates


def gen_transport_templates():
    """Generate transportation Q&A pairs."""
    templates = []

    transport_questions = [
        "How do I get a taxi?",
        "Can I take an {transport} from here?",
        "Is there a metro to the city?",
        "Where is the bus stop?",
        "Can I rent a car?",
        "Where is the parking area?",
        "Is the metro running at this hour?",
        "How do I get to {city}?",
        "What's the cheapest way to {city}?",
        "How long does it take to get to {city}?",
        "Where is the {transport} pick-up point?",
        "Is there a hotel shuttle available?",
        "Where's the drop-off zone for departures?",
        "Can I get a prepaid taxi?",
        "Is there late-night transport available?",
    ]

    transport_responses = [
        "Taxis are on Level 0 (arrivals). Options:\n- Prepaid taxi counter (Exit 4) — fixed-rate, safest option\n- Uber/Ola pick-up (Exit 5) — book via app\n- Metered taxis (Exit 6)\nI recommend prepaid taxis for first-time visitors. Shall I walk you there?",
        "The Airport Metro is on Level -1 (basement). Trains every {freq} minutes, 5 AM to 11:30 PM. Journey to {city} centre: ~{minutes} minutes, ₹{price}. Buy tokens at the station or use a metro card.",
        "Airport shuttle buses depart from Level 0, Exit 8:\n- City shuttle (every 30 min, ₹{price})\n- Inter-terminal shuttle (free, every 10 min)\n- Hotel shuttles (check with your hotel)\nLate-night options: taxis and ride-hailing are 24 hours.",
        "Car rental counters are on Level 0, near Exit 3: Avis, Hertz, Zoomcar, Myles. You'll need a valid license, credit card, and passport. Book online in advance for better rates.",
        "To get to {city}: {transport} is the best option from here. The pick-up area is on Level 0. Journey takes approximately {minutes} minutes. Cost is around ₹{price}. Want me to take you to the pick-up point?",
        "For late-night travel:\n- Prepaid taxis (24 hours, Exit 4)\n- Uber/Ola (24 hours, Exit 5)\n- Airport shuttle (reduced frequency after 11 PM)\n- Metro stops around 11:30 PM\nTaxi is most reliable for midnight arrivals.",
    ]

    for _ in range(500):
        transport = _transport()
        city = _city_dom()
        freq = _r([5, 8, 10, 12, 15])
        minutes = _r([20, 25, 30, 35, 40, 45, 60, 75, 90])
        price = _r([60, 80, 100, 150, 200, 300, 500, 800, 1200])
        q = _r(transport_questions).format(transport=transport, city=city)
        a = _r(transport_responses).format(
            city=city, transport=transport, freq=freq,
            minutes=minutes, price=price
        )
        templates.append(("transport", q, a))

    return templates


def gen_security_templates():
    """Generate security and immigration Q&A pairs.

    Uses sub-group matching so liquid questions get liquid answers,
    medicine questions get medicine answers, etc.
    """
    templates = []

    # --- Sub-group: General security tips ---
    tips_qs = [
        "How do I get through security faster?",
        "Is there a fast-track security lane?",
        "Do I need to remove my shoes at security?",
    ]
    tips_rs = [
        "Tips for faster security:\n1. Have boarding pass and ID ready\n2. Remove laptops and large electronics into trays\n3. Liquids in ≤100ml containers in a clear ziplock bag\n4. Empty your pockets (phone, wallet, keys)\n5. Avoid excessive metal jewelry\nPriority lanes available for business class/frequent flyers.",
    ]
    for _ in range(80):
        q = _r(tips_qs)
        a = _r(tips_rs)
        templates.append(("security", q, a))

    # --- Sub-group: Prohibited items ---
    prohibited_qs = [
        "What items are not allowed in cabin baggage?",
        "Can I bring a {item} through security?",
        "Are lighters allowed?",
    ]
    prohibited_rs = [
        "Prohibited in cabin baggage:\n- Sharp objects (knives, scissors >6cm)\n- Liquids over 100ml (pack in checked bags)\n- Flammable items (fuel, fireworks)\n- Tools (screwdrivers >7cm, pliers)\n- Sports equipment (bats, clubs)\n- Power banks over 160Wh\nWhen in doubt, pack it in checked luggage.",
    ]
    for _ in range(80):
        item = _r(["water bottle", "laptop", "power bank", "lighter", "scissors",
                    "razor", "knife", "perfume", "shampoo", "deodorant spray",
                    "protein powder", "spices", "drone", "tripod", "vape pen"])
        q = _r(prohibited_qs).format(item=item)
        a = _r(prohibited_rs)
        templates.append(("security", q, a))

    # --- Sub-group: Liquids ---
    liquid_qs = [
        "What is the liquid allowance?",
        "What size ziplock bag for liquids?",
        "Can I bring food through security?",
    ]
    liquid_rs = [
        "Liquid rules:\n- Each container ≤100ml (3.4 oz)\n- All in one clear resealable bag (~20×20cm, 1 litre)\n- One bag per passenger\n- Exceptions: medicines with prescription, baby food/milk\n- Duty-free liquids OK in sealed tamper-evident bags with receipt",
    ]
    for _ in range(60):
        q = _r(liquid_qs)
        a = _r(liquid_rs)
        templates.append(("security", q, a))

    # --- Sub-group: Immigration & customs ---
    immigration_qs = [
        "Where is immigration?",
        "Do I need a visa to transit here?",
        "Where is customs?",
        "Where do I declare goods at customs?",
        "What documents do I need for immigration?",
        "Where are the e-gates for passport control?",
    ]
    immigration_rs = [
        "Immigration is on Level 2 (departures, after security) and Level 0 (arrivals, before baggage claim). Have your passport, visa, and completed arrival/departure card ready. E-gates are available for eligible passports. Separate queues for citizens and foreign nationals.",
        "Customs area is on Level 0 after baggage claim:\n- Green channel: nothing to declare (within duty-free limits)\n- Red channel: goods over limits, commercial goods, restricted items\nDuty-free limit for Indian residents: ₹50,000. When in doubt, declare.",
    ]
    for _ in range(80):
        q = _r(immigration_qs)
        a = _r(immigration_rs)
        templates.append(("security", q, a))

    # --- Sub-group: Power banks ---
    powerbank_qs = [
        "Can power banks go in checked baggage?",
        "What are the rules for carrying power banks?",
    ]
    powerbank_rs = [
        "Power banks must be in carry-on baggage ONLY:\n- Under 100Wh (≈27,000mAh): allowed, no approval needed\n- 100-160Wh: requires airline approval\n- Over 160Wh: not permitted\nNever put power banks in checked luggage — it's a safety regulation.",
    ]
    for _ in range(50):
        q = _r(powerbank_qs)
        a = _r(powerbank_rs)
        templates.append(("security", q, a))

    # --- Sub-group: Medicine ---
    medicine_qs = [
        "Can I carry medicines on the flight?",
        "I have insulin and syringes. Can I bring them?",
        "Do I need a prescription for medicines at security?",
    ]
    medicine_rs = [
        "Yes, you can carry medicines:\n- Prescription medicines: carry the prescription or doctor's letter\n- OTC medicines: allowed in reasonable quantities\n- Liquid medicines over 100ml: allowed with prescription\n- Syringes: allowed with prescription for conditions like diabetes\nKeep medicines in original packaging. Declare at security if asked.",
    ]
    for _ in range(50):
        q = _r(medicine_qs)
        a = _r(medicine_rs)
        templates.append(("security", q, a))

    # --- Sub-group: SSSS ---
    ssss_qs = [
        "What does SSSS on my boarding pass mean?",
    ]
    ssss_rs = [
        "SSSS stands for Secondary Security Screening Selection. It means you've been flagged for additional security checks — this is random and doesn't mean anything is wrong. Expect extra screening (pat-down, bag check, swabs) at the gate. Allow an extra 15-20 minutes.",
    ]
    for _ in range(30):
        q = _r(ssss_qs)
        a = _r(ssss_rs)
        templates.append(("security", q, a))

    return templates


def gen_accessibility_templates():
    """Generate accessibility-related Q&A pairs.

    Uses sub-group matching to ensure wheelchair questions get wheelchair
    responses, visually impaired get visual responses, etc.
    """
    templates = []

    # --- Sub-group: Wheelchair ---
    wheelchair_qs = [
        "I need wheelchair assistance.",
        "I'm travelling with a wheelchair. Where can I get help?",
        "I need a wheelchair ramp to board.",
        "Can a wheelchair fit through security?",
        "Are the lifts wheelchair accessible?",
        "I need help getting to my gate — I can't walk far.",
        "I need wheelchair assistance to get to my gate.",
        "Where can I request a wheelchair?",
        "Is wheelchair service free at the airport?",
    ]
    wheelchair_rs = [
        "Wheelchair assistance is free! Options:\n1. Ask at any information desk (Level 2 departures, Level 0 arrivals)\n2. Request through your airline (WCHR/WCHS/WCHC service)\n3. Alert any airport staff — they'll radio for a chair\nI can also carry your luggage while you use the wheelchair. Want me to arrange it now?",
        "Yes, wheelchair assistance is completely free at the airport. You can request it at:\n- The information desk on any level\n- Your airline's check-in counter\n- Any airport staff member\nAll lifts are wheelchair accessible with wide doors and braille buttons. Security has a priority lane for wheelchair users. Shall I take you to the help desk?",
        "Absolutely! All lifts and ramps are fully wheelchair accessible. Security has a dedicated lane for wheelchair users — no long queues. Boarding assistance is available through your airline (they use jet bridges or ambulifts). I'll carry all your bags. Would you like me to arrange wheelchair assistance right now?",
    ]
    for _ in range(120):
        q = _r(wheelchair_qs)
        a = _r(wheelchair_rs)
        templates.append(("accessibility", q, a))

    # --- Sub-group: Visually impaired ---
    visual_qs = [
        "I'm visually impaired. What assistance is available?",
        "Are there braille signs at the airport?",
        "I can't see well. Can someone help me to my gate?",
        "Is there assistance for blind passengers?",
    ]
    visual_rs = [
        "For visually impaired passengers:\n- Tactile guide paths throughout the terminal\n- Braille signage on elevators and key locations\n- Audio announcements at gates and throughout terminal\n- Staff escort service available (request at info desk)\n- Service animals allowed with documentation\nI can provide verbal directions and walk alongside you to any location.",
    ]
    for _ in range(60):
        q = _r(visual_qs)
        a = _r(visual_rs)
        templates.append(("accessibility", q, a))

    # --- Sub-group: Hearing impaired ---
    hearing_qs = [
        "Are there hearing loops at the counters?",
        "I'm deaf. How will I know about gate changes?",
        "Is there sign language interpretation available?",
    ]
    hearing_rs = [
        "For hearing-impaired passengers:\n- Visual FIDS displays at every gate and throughout the terminal\n- Hearing loops at select counters (look for the ear symbol)\n- Gate change notifications on airline apps and display screens\n- Staff can write notes or use translation apps to communicate\nI can guide you to your gate and alert you visually to any changes.",
    ]
    for _ in range(40):
        q = _r(hearing_qs)
        a = _r(hearing_rs)
        templates.append(("accessibility", q, a))

    # --- Sub-group: Elderly ---
    elderly_qs = [
        "My elderly parent needs assistance.",
        "I'm traveling with my elderly mother. Can she get help?",
        "Are there priority lanes for senior citizens?",
        "My father can't walk long distances. What help is available?",
    ]
    elderly_rs = [
        "For elderly passengers:\n- Free wheelchair/buggy service (request at info desk)\n- Priority queues at security and immigration\n- I'll carry all luggage and escort them\n- Rest areas with armrests near all gates\n- Medical centre on Level 1 (24/7)\nWould you like me to arrange wheelchair assistance right now?",
    ]
    for _ in range(60):
        q = _r(elderly_qs)
        a = _r(elderly_rs)
        templates.append(("accessibility", q, a))

    # --- Sub-group: Children / infants ---
    children_qs = [
        "Is there a children's play area?",
        "I'm travelling with an infant.",
        "My child is travelling alone.",
        "Where's the family restroom?",
        "Is there a baby changing table nearby?",
        "Where can I find a stroller?",
        "Is there a baby feeding room?",
    ]
    children_rs = [
        "Children's play area near Gate {gate}: climbing structures, slides, soft flooring. Open 6 AM-10 PM, free. Parent seating and restrooms with changing tables nearby. Family feeding rooms near Gates A8 and C15.",
        "For passengers with infants:\n- Nursing rooms: Gates A8 and C15 (private, comfortable)\n- Changing tables: all family restrooms\n- Baby food/supplies: pharmacy on Level 1\n- Gate-check stroller: tell your airline at the counter\n- Priority boarding: most airlines for families\nI can carry all your bags while you handle the little one!",
        "Strollers can be gate-checked for free with most airlines. The airport also has courtesy strollers near the information desks. Family restrooms with changing tables and feeding facilities are at Gates A8 and C15. Would you like me to guide you?",
    ]
    for _ in range(80):
        q = _r(children_qs)
        a = _r(children_rs).format(gate=_gate())
        templates.append(("accessibility", q, a))

    # --- Sub-group: General accessibility ---
    general_qs = [
        "Are there accessible restrooms?",
        "Where is the nearest elevator?",
        "Are there facilities for disabled passengers?",
    ]
    general_rs = [
        "Accessible restrooms at every restroom location — look for the wheelchair symbol. Features: wide doors, grab bars, lower sink, emergency call button. The nearest one is about {dist} meters ahead on your right.",
        "The airport provides:\n- Wheelchair assistance (free, all terminals)\n- Accessible restrooms everywhere\n- Elevators at all level changes (braille buttons, audio)\n- Tactile paths for visually impaired\n- Hearing loops at counters\n- Priority security lanes\n- Service animal access\nNeed specific assistance? I'll guide you to the help desk.",
    ]
    for _ in range(80):
        q = _r(general_qs)
        a = _r(general_rs).format(dist=_distance())
        templates.append(("accessibility", q, a))

    return templates


def gen_emergency_templates():
    """Generate emergency and safety Q&A pairs.

    Uses sub-group matching to ensure medical questions get medical responses,
    lost items get lost-item responses, etc.
    """
    templates = []

    # --- Sub-group: Medical ---
    medical_qs = [
        "I feel unwell. Is there a doctor?",
        "I'm having a medical emergency.",
        "I saw someone collapse.",
        "My medication is in my checked bag and I need it now.",
        "Where is the medical centre?",
    ]
    medical_rs = [
        "The medical centre is on Level 1, staffed 24/7 with doctors and nurses. If you can't walk there, stay where you are and I'll alert medical services immediately. First aid stations are also near Gates {gate} and {gate2}. Are you feeling very unwell? Should I call for help right now?",
        "If this is urgent, stay where you are — I'm alerting medical staff right now. The medical centre on Level 1 is staffed 24/7. For emergencies, dial 112. First aid kits and AEDs are located throughout the terminal. Is anyone with you who can help?",
    ]
    for _ in range(80):
        q = _r(medical_qs)
        a = _r(medical_rs).format(gate=_gate(), gate2=_gate())
        templates.append(("emergency", q, a))

    # --- Sub-group: Lost items / passport ---
    lost_qs = [
        "I lost my passport!",
        "I left something at the security checkpoint.",
        "I lost my phone somewhere in the terminal.",
        "Where is the lost and found?",
    ]
    lost_rs = [
        "For a lost passport:\n1. Report to airport security and police desk (Level 1) immediately\n2. Check Lost & Found (Level 1) — passports are priority items\n3. Visit your airline counter to delay/rebook\n4. Contact your embassy — they can issue emergency travel documents\nKeep a passport photocopy on your phone. Want me to take you to the police desk?",
        "For items left at security, check the security Lost & Found desk (located right after the screening area). For items lost elsewhere, the main Lost & Found office is on Level 1 (open 7 AM to 11 PM). Have a description ready. Want me to take you there?",
    ]
    for _ in range(60):
        q = _r(lost_qs)
        a = _r(lost_rs)
        templates.append(("emergency", q, a))

    # --- Sub-group: Theft ---
    theft_qs = [
        "I think my wallet was stolen.",
        "I need to report a theft.",
        "Someone stole my bag!",
    ]
    theft_rs = [
        "For a suspected theft:\n1. Report to the police desk on Level 1 immediately\n2. They'll file an FIR (First Information Report)\n3. Airport CCTV can be reviewed\n4. Cancel any credit/debit cards that were in the stolen item\n5. Keep a copy of the FIR for insurance claims\nWant me to escort you to the police desk right now?",
    ]
    for _ in range(50):
        q = _r(theft_qs)
        a = _r(theft_rs)
        templates.append(("emergency", q, a))

    # --- Sub-group: Security threats ---
    security_qs = [
        "Someone left a bag unattended.",
        "There's a suspicious person near Gate {gate}.",
        "Someone is behaving aggressively near the gate.",
        "What's the emergency number?",
        "What do I do if there's a fire alarm?",
    ]
    security_rs = [
        "If you spot something suspicious:\n1. Don't approach or touch it\n2. Move away from the area\n3. Alert the nearest CISF/security officer immediately\n4. Or use emergency phones on the walls\n5. Dial 112 if needed\nI'll alert security right away. Your safety awareness helps keep everyone safe.",
        "For emergencies: dial 112 (national emergency) or use red emergency phones on the walls. Airport security (CISF) officers are stationed throughout. I can alert staff immediately. What's the situation?",
    ]
    for _ in range(60):
        q = _r(security_qs).format(gate=_gate())
        a = _r(security_rs)
        templates.append(("emergency", q, a))

    # --- Sub-group: Lost child ---
    child_qs = [
        "My child is lost!",
        "I can't find my kid in the terminal!",
        "A child seems to be alone and crying.",
    ]
    child_rs = [
        "For a lost child:\n1. Alert airport security (CISF) immediately — they'll initiate a search\n2. Report to the nearest information desk\n3. Stay near where you last saw the child\n4. Provide a description and photo if available\n5. Airport PA system can make announcements\nThis is a priority situation. Let me alert security right now.",
    ]
    for _ in range(40):
        q = _r(child_qs)
        a = _r(child_rs)
        templates.append(("emergency", q, a))

    # --- Sub-group: Hazards ---
    hazard_qs = [
        "There's water on the floor — someone might slip.",
        "I noticed a broken escalator.",
        "The restroom is flooded.",
    ]
    hazard_rs = [
        "I've noted the hazard. I'll alert airport maintenance immediately. In the meantime, please be careful in this area. Would you like me to direct you around the hazard?",
    ]
    for _ in range(30):
        q = _r(hazard_qs)
        a = _r(hazard_rs)
        templates.append(("emergency", q, a))

    return templates


def gen_porter_identity_templates():
    """Generate Porter robot identity Q&A pairs.

    Uses sub-group matching to ensure capability questions get capabilities,
    maker questions get maker info, etc.
    """
    templates = []

    # --- Sub-group: What are you / capabilities ---
    capabilities_qs = [
        "What are you?",
        "Are you a robot?",
        "What can you do?",
        "How does this robot work?",
        "Hello! What can you help me with?",
    ]
    capabilities_rs = [
        "I'm Porter, an autonomous airport assistant robot made by VirtusCo! I can:\n- Carry up to 120 kg of luggage\n- Guide you to any gate, counter, or facility\n- Answer questions about flights, services, and the airport\n- Display maps and information on my screen\n- Weigh your bags with my built-in scale\nMy service is completely free. How can I help you?",
        "Yes! I'm Porter, designed by VirtusCo to help airport passengers. I use LIDAR and sensors for 360° navigation, avoiding people and obstacles safely. I carry luggage, answer questions, and escort passengers anywhere in the terminal. How can I assist you today?",
    ]
    for _ in range(120):
        q = _r(capabilities_qs)
        a = _r(capabilities_rs)
        templates.append(("porter_identity", q, a))

    # --- Sub-group: Luggage carrying ---
    carry_qs = [
        "Can you carry my bags?",
        "How much weight can you carry?",
        "Is it safe to put my bags on you?",
        "Can you take me to my gate?",
    ]
    carry_rs = [
        "I carry up to 120 kg of luggage securely on my platform — enough for several large suitcases plus carry-ons. My platform has secure grips to prevent bags from falling. Just place your bags and we're ready to go!",
        "Absolutely! That's what I'm here for. Place your bags on my platform — I can carry up to 120 kg. I'll transport them anywhere in the terminal and guide you to your destination. Ready to load up?",
    ]
    for _ in range(80):
        q = _r(carry_qs)
        a = _r(carry_rs)
        templates.append(("porter_identity", q, a))

    # --- Sub-group: Cost / payment ---
    cost_qs = [
        "Do I need to pay for your service?",
        "Do I need to tip you?",
        "How much does this cost?",
        "Is your service free?",
    ]
    cost_rs = [
        "No payment or tips needed! My service is part of the airport experience, completely free. If you found me helpful, you can rate your experience on my display screen — it helps my team improve my service.",
    ]
    for _ in range(60):
        q = _r(cost_qs)
        a = _r(cost_rs)
        templates.append(("porter_identity", q, a))

    # --- Sub-group: Navigation / technology ---
    nav_qs = [
        "How do you navigate?",
        "How fast can you move?",
        "Can you go up stairs?",
        "Are you connected to the internet?",
        "Do you have a camera?",
    ]
    nav_rs = [
        "I navigate using LIDAR (laser scanning) for 360° environment mapping, multiple sensors for obstacle detection, and AI-powered path planning. I can safely navigate around people, luggage carts, and obstacles throughout the terminal.",
        "I move at a comfortable walking pace — about 1-1.5 m/s normally, slower in crowded areas or when escorting elderly passengers. I always prioritize safety over speed. I can adjust to match your walking pace.",
        "I use elevators and ramps — I can't climb stairs. But every area of the terminal is accessible via elevators and ramps, so I can take you anywhere. I know the location of every elevator in the terminal.",
    ]
    for _ in range(80):
        q = _r(nav_qs)
        a = _r(nav_rs)
        templates.append(("porter_identity", q, a))

    # --- Sub-group: Who made you ---
    maker_qs = [
        "Who made you?",
        "Who is VirtusCo?",
        "Where are you from?",
    ]
    maker_rs = [
        "I'm made by VirtusCo, an Indian robotics startup specializing in autonomous service robots. The team designed me specifically for airport environments. I'm currently deployed here and will be expanding to more airports, cruise ships, and hotels.",
    ]
    for _ in range(50):
        q = _r(maker_qs)
        a = _r(maker_rs)
        templates.append(("porter_identity", q, a))

    # --- Sub-group: Privacy / data ---
    privacy_qs = [
        "What happens to my personal data?",
        "Do you collect data about me?",
        "Is our conversation private?",
    ]
    privacy_rs = [
        "Your privacy is important. I don't store personal data from our conversations. My sensors are used only for navigation, not for facial recognition or surveillance. Any feedback you provide is anonymized. My team follows strict data privacy guidelines.",
    ]
    for _ in range(40):
        q = _r(privacy_qs)
        a = _r(privacy_rs)
        templates.append(("porter_identity", q, a))

    # --- Sub-group: Battery / breakdown ---
    technical_qs = [
        "What if you break down?",
        "How long is your battery?",
        "What should I do if I need human help?",
        "Can you speak other languages?",
    ]
    technical_rs = [
        "If I have any issues, airport staff are always nearby to help. You can also use the information desks on every level or airport help phones on the walls. I regularly report my status to my team so they can respond quickly.",
        "My battery lasts a full working day. When I'm low on power, I return to my charging station automatically. There are always other Porter robots available in the terminal, so passengers are never left without help.",
    ]
    for _ in range(50):
        q = _r(technical_qs)
        a = _r(technical_rs)
        templates.append(("porter_identity", q, a))

    return templates


def gen_general_templates():
    """Generate general airport Q&A pairs."""
    templates = []

    general_questions = [
        "What time does the airport close?",
        "How do I file a complaint?",
        "Can I use UPI for payments?",
        "I have a long layover. What can I do?",
        "I have connecting flights. Do I need to collect bags?",
        "Can I bring my pet on the flight?",
        "Where can I get a trolley?",
        "Are there art exhibits in the airport?",
        "Can I travel with musical instruments?",
        "What about sporting equipment?",
        "How do I get airport entry for someone dropping me off?",
        "What's the airport code?",
        "Can I leave the airport during a long layover?",
        "What's the process for an unaccompanied minor?",
        "How do I claim a VAT refund?",
        "Is there a place to do laundry?",
        "Can I bring a drone on the flight?",
        "What if my name on the ticket is wrong?",
        "How do I request a special meal on my flight?",
        "Can I fly if I'm pregnant?",
        "What's the altitude sickness risk for my destination?",
        "Is there a notary or legal service at the airport?",
    ]

    general_responses = [
        "The airport operates 24/7. However, most shops/restaurants run 5 AM-11 PM. Check-in counters open ~3 hours before flights. Security is available whenever there are departures. Late-night options: sleeping pods, 24-hour cafés, and transit hotel.",
        "For complaints: visit the information desk (Level 2 or Level 0), use feedback kiosks near restrooms, or file online via the airport website/app. For airline complaints, visit their counter or use the DGCA AirSewa portal.",
        "Yes! UPI (Google Pay, PhonePe, Paytm) is widely accepted at most restaurants, shops, and service counters. Some smaller kiosks may be cash/card only. Always good to have a backup payment method.",
        "With a long layover, you can:\n- Visit a lounge (day pass ₹{price})\n- Use sleeping pods/transit hotel\n- Explore the food court (15+ restaurants)\n- Get a massage at the spa\n- Shop duty-free (international)\n- Use the yoga room or play area\n- Connect to free WiFi\nHow long is your layover? I can plan a schedule.",
        "For connecting flights on the same booking, bags are usually through-checked to your final destination (check your baggage tag). For separate bookings, you'll need to collect, re-check, and go through security again. Domestic→International usually requires bag collection.",
        "Pet travel varies by airline:\n- Small pets: cabin in carrier under seat (7-8 kg limit)\n- Large pets: cargo hold in IATA crate\n- Need: health certificate, vaccination records, import permits\n- Book pet travel early — limited spots\nContact your airline for specific policies.",
        "Luggage trolleys are at the entrance of baggage claim (Level 0) and check-in hall (Level 2). Free at Indian airports — just take one from the bay. Or use me! I carry up to 120 kg and can go anywhere in the terminal.",
        "Musical instruments:\n- Small (violin, flute): cabin in hard case\n- Medium (guitar): some airlines allow cabin with extra seat, otherwise checked in padded hard case\n- Large (cello): extra seat or cargo\nTips: use hard cases, loosen strings, label 'FRAGILE', contact airline in advance.",
        "Drones are restricted:\n- Cabin: batteries must be carry-on (lithium battery rules)\n- Must be registered with DGCA if flying in India\n- Some countries prohibit drone import\n- Check destination's drone laws before travelling\nDeclare at security. The drone itself can go in checked luggage if batteries are removed.",
    ]

    for _ in range(500):
        price = _r([2000, 2500, 3000, 3500])
        q = _r(general_questions)
        a = _r(general_responses).format(price=price)
        templates.append(("general", q, a))

    return templates


def gen_multilingual_templates():
    """Generate multilingual (Hindi and other language) Q&A pairs."""
    templates = []

    hindi_pairs = [
        ("Gate kahan hai? Mujhe {gate} jaana hai.",
         "Gate {gate} {terminal} mein hai. Yahan se seedha jaake {direction} le lijiye — lagbhag {walk} minute ka rasta hai. Main aapka samaan le jaata hoon aur rasta dikhata hoon. Chalein?"),
        ("Washroom kidhar hai?",
         "Washroom yahan se seedha {dist} metre aage hai, right side pe. Accessible washroom aur family washroom bhi wahi hai. Oopar ceiling pe blue sign dhundiye."),
        ("Mera flight kitne baje hai?",
         "Aapke flight ka time check karne ke liye kripya boarding pass dekhein ya departure board dekhein — {dist} metre aage hai. Airline ki app pe bhi real-time status milega."),
        ("Check-in counter kahan hai?",
         "Aapki airline ka check-in counter Level 2 pe hai, departures hall mein. Kaunsi airline se travel kar rahe hain? Main aapko sahi counter tak le jaaunga."),
        ("Khana kahan milega?",
         "Food court Level 2 pe hai, yahan se {walk} minute door. Indian food, fast food, coffee — sab milega. Vegetarian aur halal options bhi hain. Chalein wahan?"),
        ("Taxi kahan milegi?",
         "Taxi Level 0 pe hai, arrivals area mein. Prepaid taxi counter Exit 4 pe hai — fixed rate, sabse safe option. Uber/Ola Exit 5 pe. Main aapko le jaata hoon."),
        ("Kya aap mera samaan le ja sakte ho?",
         "Bilkul! Yahi toh mera kaam hai. Main 120 kg tak samaan utha sakta hoon. Apne bags mere platform pe rakh dijiye aur bataiye kahan jaana hai. Ready?"),
        ("Dawai ki dukaan kahan hai?",
         "Pharmacy Level 1 pe hai, medical centre ke paas. Subah 6 baje se raat 12 baje tak khuli rehti hai. Common medicines, first aid, sab milta hai."),
        ("WiFi kaise connect karein?",
         "WiFi settings mein 'Airport_Free_WiFi' select karein, apna phone number dalein, OTP aayega, enter karein — {hours} ghante free WiFi mil jayega."),
        ("Meri flight cancel ho gayi. Kya karoon?",
         "Chinta mat kariye. Airline ke counter pe jaayein — Level 2 pe check-in hall mein. Wo aapko next flight pe book kar denge ya refund de denge. Agar delay 2 ghante se zyada hai toh khana bhi milna chahiye airline se."),
        ("Baggage claim kahan hai?",
         "Baggage claim Level 0 pe hai, ground floor pe. Domestic flights ke liye seedha arrival corridor ke baad, international ke liye immigration ke baad. Screen pe flight number dekh ke carousel number pata lagayein."),
        ("Currency exchange kidhar hai?",
         "Currency exchange Level 2 pe check-in hall ke paas hai, aur Level 0 arrivals area mein bhi. ATM bhi paas mein hain. Rates compare karein agar bada amount hai."),
        ("Lounge kahan hai? Mera Priority Pass hai.",
         "Priority Pass se aap Plaza Premium Lounge ja sakte hain — Level 3, Gate {gate} ke paas. Wahan khana, WiFi, shower, comfortable seating sab hai. Boarding pass aur Priority Pass dikhana hoga entry pe."),
        ("Bacche ke liye koi jagah hai khelne ke liye?",
         "Haan! Children's play area Gate {gate} ke paas hai. Climbing structures, slides, soft flooring — 6 AM se 10 PM tak khula hai, free hai. Parents ke liye seating bhi hai paas mein."),
        ("Mere papa ko wheelchair chahiye.",
         "Wheelchair service free hai! Kisi bhi information desk pe jaake request karein, ya main abhi arrange karwa deta hoon. Main unka samaan bhi carry karunga aur unke saath gate tak jaunga."),
    ]

    for q_template, a_template in hindi_pairs:
        for _ in range(35):
            gate = _gate()
            terminal = _terminal()
            walk = _walk_time()
            dist = _distance()
            direction = _r(["right", "left", "seedha"])
            hours = _r([2, 3, 4])
            q = q_template.format(gate=gate, terminal=terminal, walk=walk,
                                  dist=dist, direction=direction, hours=hours)
            a = a_template.format(gate=gate, terminal=terminal, walk=walk,
                                  dist=dist, direction=direction, hours=hours)
            templates.append(("multilingual", q, a))

    return templates


def gen_smalltalk_templates():
    """Generate small-talk and social Q&A pairs."""
    templates = []

    pairs = [
        ("Hello!", "Hello! Welcome to the airport. I'm Porter, your assistant robot. How can I help you today? I can carry your luggage, give directions, or answer any questions about the airport."),
        ("Hi there!", "Hi! I'm Porter, ready to help. Need directions, luggage help, or have a question? I'm at your service!"),
        ("Good morning!", "Good morning! Hope you have a great journey ahead. I'm Porter — how can I help you today?"),
        ("Good evening!", "Good evening! I'm Porter, your airport assistant. Heading to a flight or just arrived? How can I help?"),
        ("Thank you!", "You're welcome! Have a wonderful flight and safe journey. If you need anything else, I'm always around the terminal. You can rate my service on my display screen!"),
        ("Thanks for your help!", "My pleasure! I hope your airport experience has been smooth. Have a great trip! If you ever need me again, just look for the Porter robots around the terminal."),
        ("Goodbye!", "Goodbye! Have a safe and pleasant journey. I'm always here if you need me. Take care! ✈️"),
        ("See you later!", "See you! Have a wonderful trip. I'll be here in the terminal whenever you come back. Happy travels!"),
        ("That's all I needed, thanks.", "Great! Glad I could help. Have an amazing flight. Don't forget — I'm always around if you need anything before you board."),
        ("You're amazing!", "Thank you! That means a lot. I'm designed to make your airport experience as smooth as possible. If you have a moment, you can rate your experience on my screen — it helps my VirtusCo team improve!"),
        ("This is so cool!", "Thanks! I'm glad you think so. I'm Porter, made by VirtusCo right here in India. Would you like to know more about how I work, or can I help you with something?"),
        ("I'm scared of flying.", "That's quite common! Deep breaths help. The airport has a yoga room on Level 2 for relaxation. If you need anything to calm your nerves, the pharmacy on Level 1 has herbal teas and calming remedies. You'll be just fine!"),
        ("I'm so tired.", "I understand — travelling can be exhausting. There are sleeping pods near Gates B12 and D5 (₹500/hour), or the transit hotel near Gate C18. Even a comfortable lounge seat with a coffee might help. Want me to take you somewhere to rest?"),
        ("I'm bored.", "There's plenty to do! The food court has 15+ restaurants, there's a yoga room, art exhibits, kids' play area, shopping, and a spa. The observation area is great for plane watching. How long do you have? I'll suggest a plan."),
        ("What's the weather like outside?", "I primarily operate inside the terminal, so I don't have real-time weather data. Check a weather app on your phone, or ask at the information desk. They usually have local weather updates posted."),
        ("Can you take a selfie with me?", "I'm flattered! While I can't take photos myself, you're welcome to take a selfie with me. I'll strike my best pose! Just stand next to me. My VirtusCo logo makes a great background."),
    ]

    for q, a in pairs:
        for _ in range(28):
            templates.append(("smalltalk", q, a))

    return templates


# ---------------------------------------------------------------------------
# TOOL-USE TEMPLATES (for tool-use adapter)
# ---------------------------------------------------------------------------

def gen_tool_use_templates():
    """Generate tool-use Q&A pairs for the tool-use LoRA adapter."""
    templates = []

    # --- get_directions ---
    dir_questions = [
        "Take me to Gate {gate}.",
        "How do I get to Gate {gate}?",
        "Show me the way to {facility}.",
        "I need to get to {terminal}.",
        "Where is the nearest {facility}?",
        "Can you guide me to the {airline} counter?",
        "Navigate me to the food court.",
        "Lead me to the arrivals area.",
        "I need directions to the baggage claim.",
        "Take me to the departure lounge.",
    ]

    for _ in range(500):
        gate = _gate()
        facility = _facility()
        terminal = _terminal()
        airline = _airline()
        q = _r(dir_questions).format(gate=gate, facility=facility,
                                     terminal=terminal, airline=airline)
        dest = _r([f"Gate {gate}", facility, terminal, f"{airline} counter",
                    "food court", "arrivals area", "baggage claim", "departure lounge"])
        tool_call = json.dumps({"name": "get_directions", "arguments": {"destination": dest}})
        tool_result = json.dumps({
            "distance_m": _distance(),
            "walk_time_min": _walk_time(),
            "directions": f"Head straight {_landmark()}, then continue to {dest}.",
            "terminal": _r(TERMINALS),
            "level": _r(LEVELS)
        })
        response = f"I've found the route to {dest}. It's about {_walk_time()} minutes from here. I'll guide you there — let me carry your bags. Follow me!"
        templates.append(("tool_directions", q, tool_call, tool_result, response))

    # --- get_flight_status ---
    flight_questions = [
        "What's the status of flight {flight}?",
        "Is {flight} delayed?",
        "Check flight {flight} for me.",
        "When does {flight} board?",
        "Has {flight} gate changed?",
        "Is my flight {flight} on time?",
        "Any updates on {flight} to {city}?",
    ]

    for _ in range(500):
        flight = _flight()
        city = _city()
        q = _r(flight_questions).format(flight=flight, city=city)
        gate = _gate()
        status = _r(["On Time", "Delayed", "Boarding", "Gate Changed", "Departed",
                      "Scheduled", "Final Call"])
        delay_min = _r([0, 0, 0, 15, 30, 45, 60, 90, 120]) if status == "Delayed" else 0
        tool_call = json.dumps({"name": "get_flight_status", "arguments": {"flight_number": flight}})
        tool_result = json.dumps({
            "flight": flight,
            "status": status,
            "gate": gate,
            "scheduled_departure": f"{_r(range(5, 24)):02d}:{_r([0, 15, 30, 45]):02d}",
            "delay_minutes": delay_min,
            "boarding_time": f"{_r(range(4, 23)):02d}:{_r([0, 15, 30, 45]):02d}" if status in ["On Time", "Boarding", "Scheduled"] else None
        })
        if status == "On Time":
            response = f"Flight {flight} is on time! Gate {gate}. Boarding starts about {_boarding_time()} before departure. Would you like me to take you to the gate?"
        elif status == "Delayed":
            response = f"Flight {flight} is delayed by approximately {delay_min} minutes. Gate {gate} is still assigned. I recommend heading there as the delay could change. Would you like me to guide you?"
        elif status == "Boarding":
            response = f"Flight {flight} is boarding now at Gate {gate}! We should head there immediately. I'll carry your bags — let's go!"
        elif status == "Gate Changed":
            new_gate = _gate()
            response = f"Alert: Gate change for {flight}! New gate is {new_gate}. Let me take you there right away."
        else:
            response = f"Flight {flight} status is: {status} at Gate {gate}. Shall I take you to the gate area?"
        templates.append(("tool_flight", q, tool_call, tool_result, response))

    # --- find_nearest ---
    nearest_questions = [
        "Where is the nearest restroom?",
        "I need an ATM.",
        "Find me a charging station.",
        "Where's the closest pharmacy?",
        "Is there a prayer room nearby?",
        "Find the nearest lounge.",
        "I need a water fountain.",
        "Where's the nearest {facility}?",
        "I need to find an elevator.",
        "Is there a baby changing room near here?",
    ]

    for _ in range(450):
        facility = _facility()
        ftype_map = {
            "restroom": "restroom", "ATM": "atm", "charging station": "charging_station",
            "pharmacy": "pharmacy", "prayer room": "prayer_room", "lounge": "lounge",
            "water fountain": "water_fountain", "elevator": "elevator",
            "currency exchange": "currency_exchange", "information desk": "information_desk",
            "medical centre": "medical_centre", "baby feeding room": "restroom",
        }
        ftype = ftype_map.get(facility, "restroom")
        q = _r(nearest_questions).format(facility=facility)
        tool_call = json.dumps({"name": "find_nearest", "arguments": {"facility_type": ftype}})
        tool_result = json.dumps({
            "facility_type": ftype,
            "location": f"Near Gate {_gate()}, {_level()}",
            "distance_m": _distance(),
            "walk_time_min": _r([1, 2, 3, 4, 5]),
            "accessible": True
        })
        dist = _distance()
        response = f"The nearest {facility} is about {dist} meters from here, {_landmark()}. It's on {_level()}, wheelchair accessible. Would you like me to take you there?"
        templates.append(("tool_find", q, tool_call, tool_result, response))

    # --- escort_passenger ---
    escort_questions = [
        "Can you take me to Gate {gate}?",
        "Walk me to the check-in counter.",
        "Escort me to {terminal}.",
        "I need help getting to the food court.",
        "Can you carry my bags to Gate {gate}?",
        "Please take me and my luggage to the taxi stand.",
        "I need an escort to the medical centre, I'm not feeling well.",
        "Can you slowly walk me to my gate? I have a knee problem.",
    ]

    for _ in range(450):
        gate = _gate()
        terminal = _terminal()
        q = _r(escort_questions).format(gate=gate, terminal=terminal)
        dest = _r([f"Gate {gate}", "check-in counter", terminal,
                    "food court", "taxi stand", "medical centre"])
        carry = random.random() > 0.2  # 80% carry luggage
        pace = _r(["normal", "slow"]) if "knee" in q or "slowly" in q else "normal"
        tool_call = json.dumps({"name": "escort_passenger", "arguments": {
            "destination": dest, "carry_luggage": carry, "pace": pace
        }})
        tool_result = json.dumps({
            "status": "navigation_started",
            "destination": dest,
            "estimated_time_min": _walk_time(),
            "route": f"Via main corridor, {_landmark()}"
        })
        carry_text = "I'll carry your bags on my platform. " if carry else ""
        pace_text = "I'll walk at a comfortable slow pace. " if pace == "slow" else ""
        response = f"Let's go to {dest}! {carry_text}{pace_text}Follow me — it should take about {_walk_time()} minutes. I'll take the easiest route."
        templates.append(("tool_escort", q, tool_call, tool_result, response))

    # --- weigh_luggage ---
    weigh_questions = [
        "Can you weigh my bags?",
        "I want to check if my luggage is overweight.",
        "Weigh my {num} bags please.",
        "Is my suitcase within the weight limit?",
        "Please check how heavy my carry-on is.",
        "I'm worried my bag is too heavy. Can you weigh it?",
    ]

    for _ in range(300):
        num = _r([1, 2, 3, 4])
        q = _r(weigh_questions).format(num=num)
        tool_call = json.dumps({"name": "weigh_luggage", "arguments": {"num_bags": num}})
        weights = [round(random.uniform(5, 28), 1) for _ in range(num)]
        total = round(sum(weights), 1)
        tool_result = json.dumps({
            "bags_weighed": num,
            "individual_weights_kg": weights,
            "total_weight_kg": total
        })
        if total > 23 * num:
            response = f"Your {num} bag(s) weigh {total} kg total. That's over the typical {23 * num} kg limit. You might want to redistribute or remove items. The overweight fee is usually ₹400-750 per extra kg."
        else:
            response = f"Your {num} bag(s) weigh {total} kg total ({', '.join(f'{w} kg' for w in weights)}). You're within the standard allowance. All good to check in!"
        templates.append(("tool_weigh", q, tool_call, tool_result, response))

    # --- show_map ---
    map_questions = [
        "Show me the airport map.",
        "Can you display where Gate {gate} is on the map?",
        "Show me {terminal} on your screen.",
        "Map out the route to the food court.",
        "Where am I right now? Show on map.",
        "Display the duty-free area on your screen.",
    ]

    for _ in range(300):
        gate = _gate()
        terminal = _terminal()
        q = _r(map_questions).format(gate=gate, terminal=terminal)
        area = _r([terminal, _concourse(), "Food Court Area", "Arrivals Level 0", "Departures Level 2"])
        highlight = _r([f"Gate {gate}", "Current Location", "Food Court", "Duty Free", None])
        args = {"area": area, "show_route": True}
        if highlight:
            args["highlight"] = highlight
        tool_call = json.dumps({"name": "show_map", "arguments": args})
        tool_result = json.dumps({
            "status": "map_displayed",
            "area": area,
            "highlighted": highlight,
            "route_shown": True
        })
        response = f"I've displayed the map of {area} on my screen with the route highlighted. You can see the path from our current location. Follow the blue line! Ready to walk there?"
        templates.append(("tool_map", q, tool_call, tool_result, response))

    # --- check_wait_time ---
    wait_questions = [
        "How long is the security queue?",
        "What's the wait time at immigration?",
        "How busy is check-in right now?",
        "How long will customs take?",
        "Is the taxi queue long?",
        "What's the wait at the lounge?",
    ]

    queue_map = {
        "security": "security", "immigration": "immigration",
        "check-in": "check_in", "customs": "customs",
        "taxi": "taxi", "lounge": "lounge"
    }

    for _ in range(300):
        q = _r(wait_questions)
        queue_type = "security"
        for k, v in queue_map.items():
            if k in q.lower():
                queue_type = v
                break
        wait_min = _r([5, 8, 10, 12, 15, 20, 25, 30, 40, 45])
        tool_call = json.dumps({"name": "check_wait_time", "arguments": {
            "queue_type": queue_type, "terminal": _r(TERMINAL_SHORT)
        }})
        tool_result = json.dumps({
            "queue_type": queue_type,
            "estimated_wait_minutes": wait_min,
            "queue_length": _r([10, 20, 30, 50, 80, 100, 150]),
            "status": _r(["normal", "busy", "very_busy", "light"])
        })
        if wait_min <= 10:
            response = f"The {queue_type.replace('_', ' ')} queue is currently light — about {wait_min} minutes wait. Good time to go through!"
        elif wait_min <= 20:
            response = f"The {queue_type.replace('_', ' ')} wait is about {wait_min} minutes — moderate right now. I'd recommend heading there soon."
        else:
            response = f"The {queue_type.replace('_', ' ')} queue is busy — estimated {wait_min} minutes. If you have time, waiting 15-20 minutes might help. Priority lanes are usually faster."
        templates.append(("tool_wait", q, tool_call, tool_result, response))

    # --- call_assistance ---
    assist_questions = [
        "I need wheelchair assistance.",
        "Can you call a doctor? I feel dizzy.",
        "My child is lost! Please help!",
        "I need a language interpreter.",
        "Can you get airline staff here?",
        "I need help — I'm an elderly passenger traveling alone.",
        "Please call security.",
        "I need help with my unaccompanied minor's check-in.",
    ]

    assist_map = {
        "wheelchair": ("wheelchair", "normal"),
        "doctor": ("medical", "high"),
        "child": ("security", "emergency"),
        "lost": ("lost_item", "normal"),
        "interpreter": ("language_interpreter", "normal"),
        "airline": ("airline_staff", "normal"),
        "elderly": ("elderly_escort", "normal"),
        "security": ("security", "high"),
        "unaccompanied": ("unaccompanied_minor", "normal"),
    }

    for _ in range(350):
        q = _r(assist_questions)
        at = "wheelchair"
        priority = "normal"
        for k, (a_type, p) in assist_map.items():
            if k in q.lower():
                at = a_type
                priority = p
                break
        location = f"Near Gate {_gate()}, {_level()}"
        tool_call = json.dumps({"name": "call_assistance", "arguments": {
            "assistance_type": at, "location": location, "priority": priority
        }})
        tool_result = json.dumps({
            "status": "assistance_dispatched",
            "type": at,
            "estimated_arrival_min": _r([2, 3, 5, 7, 10]),
            "reference_id": f"REF-{random.randint(10000, 99999)}"
        })
        response = f"I've requested {at.replace('_', ' ')} assistance. Help is on the way — estimated arrival in {_r([2, 3, 5])} minutes. I'll stay with you until they arrive. Is there anything else you need right now?"
        templates.append(("tool_assist", q, tool_call, tool_result, response))

    # --- get_airline_counter ---
    airline_q = [
        "Where is the {airline} counter?",
        "Find the {airline} check-in for me.",
        "I need {airline} customer service.",
        "Where's {airline} lost baggage counter?",
        "Take me to {airline} ticketing.",
    ]

    for _ in range(300):
        airline = _airline()
        info = AIRLINES[airline]
        service = _r(["check_in", "baggage_drop", "customer_service", "ticketing", "lost_baggage"])
        q = _r(airline_q).format(airline=airline)
        tool_call = json.dumps({"name": "get_airline_counter", "arguments": {
            "airline": airline, "service_type": service
        }})
        tool_result = json.dumps({
            "airline": airline,
            "service_type": service,
            "location": f"Level 2, {info['counters']}",
            "terminal": _r(TERMINALS),
            "operating_hours": "05:00-23:00"
        })
        response = f"{airline} {service.replace('_', ' ')} counter is on Level 2, {info['counters']}. I'll take you there and carry your bags. Shall we go?"
        templates.append(("tool_airline", q, tool_call, tool_result, response))

    # --- get_transport_options ---
    transport_q = [
        "How do I get to {city}?",
        "What transport options to {city}?",
        "Best way to reach {city} centre?",
        "Get me a taxi to {city}.",
        "Is there a bus to {city}?",
    ]

    for _ in range(300):
        city = _city_dom()
        q = _r(transport_q).format(city=city)
        t_type = _r(["taxi", "metro", "bus", "rideshare", "any"])
        tool_call = json.dumps({"name": "get_transport_options", "arguments": {
            "destination": city, "transport_type": t_type
        }})
        options = [
            {"type": "taxi", "cost_inr": _r([300, 500, 800, 1200, 1500]),
             "time_min": _r([20, 30, 45, 60, 90]), "pickup": "Level 0, Exit 4"},
            {"type": "metro", "cost_inr": _r([40, 60, 80, 100]),
             "time_min": _r([20, 30, 40, 50]), "pickup": "Level -1, Metro Station"},
        ]
        tool_result = json.dumps({"destination": city, "options": options})
        opt = options[0]
        response = f"To get to {city}, a taxi from Exit 4 costs approximately ₹{opt['cost_inr']} and takes about {opt['time_min']} minutes. Metro is also available (₹{options[1]['cost_inr']}, {options[1]['time_min']} min). Want me to walk you to the taxi stand?"
        templates.append(("tool_transport", q, tool_call, tool_result, response))

    # --- set_reminder ---
    reminder_q = [
        "Remind me when {flight} starts boarding.",
        "Set a boarding reminder for flight {flight}.",
        "Alert me 30 minutes before {flight} departs.",
        "Don't let me miss {flight}!",
        "Set a reminder for my flight {flight}.",
    ]

    for _ in range(250):
        flight = _flight()
        minutes = _r([20, 25, 30, 40, 45])
        q = _r(reminder_q).format(flight=flight)
        tool_call = json.dumps({"name": "set_reminder", "arguments": {
            "flight_number": flight, "reminder_minutes_before": minutes
        }})
        tool_result = json.dumps({
            "status": "reminder_set",
            "flight": flight,
            "alert_minutes_before_boarding": minutes
        })
        response = f"Reminder set! I'll alert you {minutes} minutes before flight {flight} starts boarding. Feel free to relax — I'll make sure you don't miss your flight. In the meantime, can I help with anything else?"
        templates.append(("tool_reminder", q, tool_call, tool_result, response))

    # --- report_incident ---
    incident_q = [
        "There's an unattended bag near Gate {gate}.",
        "Someone collapsed near the food court.",
        "There's a spill on the floor near Gate {gate}.",
        "I saw a fire alarm go off near {terminal}.",
        "There's a lost child crying near Gate {gate}.",
    ]

    for _ in range(250):
        gate = _gate()
        terminal = _terminal()
        q = _r(incident_q).format(gate=gate, terminal=terminal)
        inc_type = "unattended_baggage"
        severity = "medium"
        if "collapse" in q:
            inc_type = "medical_emergency"
            severity = "critical"
        elif "spill" in q:
            inc_type = "spill_hazard"
            severity = "low"
        elif "fire" in q:
            inc_type = "fire_alarm"
            severity = "high"
        elif "lost child" in q:
            inc_type = "lost_child"
            severity = "high"
        location = f"Near Gate {gate}" if gate in q else f"{terminal} area"
        tool_call = json.dumps({"name": "report_incident", "arguments": {
            "incident_type": inc_type, "location": location,
            "severity": severity, "description": q
        }})
        tool_result = json.dumps({
            "status": "incident_reported",
            "reference": f"INC-{random.randint(10000, 99999)}",
            "response_team_eta_min": _r([1, 2, 3, 5])
        })
        if severity in ["critical", "high"]:
            response = f"I've reported this as a priority incident. Emergency response team is on the way — ETA {_r([1, 2, 3])} minutes. Please stay clear of the area. Your safety is the top priority."
        else:
            response = f"I've reported this to airport operations. A team will address it shortly. Thank you for alerting me — your awareness helps keep everyone safe."
        templates.append(("tool_incident", q, tool_call, tool_result, response))

    # --- translate_text ---
    translate_q = [
        "How do I say 'Where is Gate {gate}?' in {lang}?",
        "Translate 'Your flight is boarding' to {lang}.",
        "Can you say 'Please follow me' in {lang}?",
        "How to say 'Thank you' in {lang}?",
        "Tell me 'The restroom is on the right' in {lang}.",
    ]

    translations_examples = {
        "Hindi": {"Thank you": "Dhanyavaad", "Please follow me": "Kripya mere peechhe aayein",
                  "Your flight is boarding": "Aapki flight ki boarding ho rahi hai"},
        "Tamil": {"Thank you": "Nandri", "Please follow me": "Thayavu seithu ennai pinpattungal"},
        "French": {"Thank you": "Merci", "Please follow me": "Veuillez me suivre"},
        "Japanese": {"Thank you": "Arigatou gozaimasu", "Please follow me": "Watashi ni tsuite kite kudasai"},
    }

    for _ in range(250):
        gate = _gate()
        lang = _lang()
        q = _r(translate_q).format(gate=gate, lang=lang)
        text = _r(["Thank you", "Please follow me", "Your flight is boarding",
                    f"Where is Gate {gate}?", "The restroom is on the right"])
        lang_code = LANGUAGES[lang]
        tool_call = json.dumps({"name": "translate_text", "arguments": {
            "text": text, "target_language": lang_code
        }})
        translated = f"[{lang} translation of: {text}]"
        tool_result = json.dumps({
            "original": text,
            "translated": translated,
            "language": lang
        })
        response = f"In {lang}, '{text}' translates to: {translated}. Would you like me to display this on my screen for the other person to read?"
        templates.append(("tool_translate", q, tool_call, tool_result, response))

    return templates


# ---------------------------------------------------------------------------
# Assembly functions
# ---------------------------------------------------------------------------

def build_conversational_example(system_prompt: str, question: str, answer: str) -> dict:
    """Build a single conversational JSONL entry."""
    return {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
    }


def build_tool_use_example(system_prompt: str, tools_json: str,
                           question: str, tool_call: str,
                           tool_result: str, response: str) -> dict:
    """Build a single tool-use JSONL entry (ChatML format)."""
    return {
        "messages": [
            {"role": "system", "content": f"{system_prompt}\n\nAvailable tools:\n{tools_json}"},
            {"role": "user", "content": question},
            {"role": "assistant", "content": f"<tool_call>\n{tool_call}\n</tool_call>"},
            {"role": "tool", "content": tool_result},
            {"role": "assistant", "content": response},
        ]
    }


def deduplicate_by_question(examples: list[dict]) -> list[dict]:
    """Remove examples with identical user questions."""
    seen = set()
    unique = []
    for ex in examples:
        # Find user message
        user_msg = ""
        for m in ex["messages"]:
            if m["role"] == "user":
                user_msg = m["content"]
                break
        h = hashlib.md5(user_msg.encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            unique.append(ex)
    return unique


def split_train_eval(examples: list[dict], eval_ratio: float = 0.167) -> tuple:
    """Split into train/eval sets ensuring no question overlap."""
    random.shuffle(examples)
    split_idx = int(len(examples) * (1 - eval_ratio))
    return examples[:split_idx], examples[split_idx:]


# ---------------------------------------------------------------------------
# Main generation pipeline
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate Porter AI training data")
    parser.add_argument("--train-size", type=int, default=10000,
                        help="Target training set size (default: 10000)")
    parser.add_argument("--eval-size", type=int, default=2000,
                        help="Target eval set size (default: 2000)")
    parser.add_argument("--seed", type=int, default=SEED,
                        help="Random seed (default: 42)")
    parser.add_argument("--output-dir", type=str,
                        default=str(Path(__file__).parent.parent / "data"),
                        help="Output directory")
    args = parser.parse_args()

    random.seed(args.seed)
    total_target = args.train_size + args.eval_size
    conv_target = int(total_target * 0.70)
    tool_target = total_target - conv_target

    output_dir = Path(args.output_dir)
    for subdir in ["conversational", "tool_use", "combined"]:
        (output_dir / subdir).mkdir(parents=True, exist_ok=True)

    # Load tool schemas
    tool_schema_path = output_dir / "tool_schemas.json"
    if tool_schema_path.exists():
        with open(tool_schema_path) as f:
            tools_data = json.load(f)
        tools_json = json.dumps(tools_data["tools"], indent=2)
    else:
        tools_json = "[]"

    print("=" * 60)
    print("Porter AI Assistant — Dataset Generator")
    print("=" * 60)
    print(f"Target: {args.train_size} train + {args.eval_size} eval = {total_target}")
    print(f"Split: ~70% conversational, ~30% tool-use")
    print(f"Seed: {args.seed}")
    print()

    # --- Generate conversational templates ---
    print("Generating conversational templates...")
    conv_templates = []
    generators = [
        ("Navigation", gen_navigation_templates),
        ("Flight Info", gen_flight_templates),
        ("Check-in", gen_checkin_templates),
        ("Baggage", gen_baggage_templates),
        ("Services", gen_services_templates),
        ("Dining & Shopping", gen_dining_shopping_templates),
        ("Transport", gen_transport_templates),
        ("Security", gen_security_templates),
        ("Accessibility", gen_accessibility_templates),
        ("Emergency", gen_emergency_templates),
        ("Porter Identity", gen_porter_identity_templates),
        ("General", gen_general_templates),
        ("Multilingual", gen_multilingual_templates),
        ("Small Talk", gen_smalltalk_templates),
    ]

    for name, gen_func in generators:
        templates = gen_func()
        print(f"  {name}: {len(templates)} templates")
        conv_templates.extend(templates)

    # Build conversational examples — apply vary_question for uniqueness
    conv_examples = []
    for t in conv_templates:
        category, question, answer = t[0], t[1], t[2]
        varied_q = vary_question(question)
        ex = build_conversational_example(SYSTEM_PROMPT_CONV, varied_q, answer)
        ex["category"] = category
        ex["type"] = "conversational"
        conv_examples.append(ex)

    conv_examples = deduplicate_by_question(conv_examples)
    random.shuffle(conv_examples)
    print(f"\nConversational after dedup: {len(conv_examples)}")

    # --- Generate tool-use templates ---
    print("\nGenerating tool-use templates...")
    tool_templates = gen_tool_use_templates()
    print(f"  Tool-use: {len(tool_templates)} templates")

    tool_examples = []
    for t in tool_templates:
        category = t[0]
        question, tool_call, tool_result, response = t[1], t[2], t[3], t[4]
        varied_q = vary_question(question)
        ex = build_tool_use_example(SYSTEM_PROMPT_TOOL, tools_json,
                                    varied_q, tool_call, tool_result, response)
        ex["category"] = category
        ex["type"] = "tool_use"
        tool_examples.append(ex)

    tool_examples = deduplicate_by_question(tool_examples)
    random.shuffle(tool_examples)
    print(f"Tool-use after dedup: {len(tool_examples)}")

    # --- Trim to target sizes ---
    conv_train_size = int(args.train_size * 0.70)
    conv_eval_size = int(args.eval_size * 0.70)
    tool_train_size = args.train_size - conv_train_size
    tool_eval_size = args.eval_size - conv_eval_size

    # Ensure we have enough (oversample if needed)
    while len(conv_examples) < conv_train_size + conv_eval_size:
        conv_examples.append(random.choice(conv_examples).copy())
    while len(tool_examples) < tool_train_size + tool_eval_size:
        tool_examples.append(random.choice(tool_examples).copy())

    conv_train = conv_examples[:conv_train_size]
    conv_eval = conv_examples[conv_train_size:conv_train_size + conv_eval_size]
    tool_train = tool_examples[:tool_train_size]
    tool_eval = tool_examples[tool_train_size:tool_train_size + tool_eval_size]

    # Combined
    combined_train = conv_train + tool_train
    combined_eval = conv_eval + tool_eval
    random.shuffle(combined_train)
    random.shuffle(combined_eval)

    # --- Write output ---
    def write_jsonl(path: Path, data: list[dict]):
        with open(path, "w") as f:
            for item in data:
                # Remove metadata fields before writing
                clean = {k: v for k, v in item.items() if k in ("messages",)}
                f.write(json.dumps(clean, ensure_ascii=False) + "\n")

    print("\nWriting datasets...")
    write_jsonl(output_dir / "conversational" / "train.jsonl", conv_train)
    write_jsonl(output_dir / "conversational" / "eval.jsonl", conv_eval)
    write_jsonl(output_dir / "tool_use" / "train.jsonl", tool_train)
    write_jsonl(output_dir / "tool_use" / "eval.jsonl", tool_eval)
    write_jsonl(output_dir / "combined" / "train.jsonl", combined_train)
    write_jsonl(output_dir / "combined" / "eval.jsonl", combined_eval)

    # --- Category stats ---
    def count_categories(data):
        counts = {}
        for item in data:
            cat = item.get("category", "unknown")
            counts[cat] = counts.get(cat, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: -x[1]))

    stats = {
        "seed": args.seed,
        "conversational": {
            "train": len(conv_train),
            "eval": len(conv_eval),
            "train_categories": count_categories(conv_train),
            "eval_categories": count_categories(conv_eval),
        },
        "tool_use": {
            "train": len(tool_train),
            "eval": len(tool_eval),
            "train_categories": count_categories(tool_train),
            "eval_categories": count_categories(tool_eval),
        },
        "combined": {
            "train": len(combined_train),
            "eval": len(combined_eval),
        },
        "totals": {
            "train": len(combined_train),
            "eval": len(combined_eval),
            "grand_total": len(combined_train) + len(combined_eval),
        }
    }

    with open(output_dir / "stats.json", "w") as f:
        json.dump(stats, f, indent=2)

    # --- Print summary ---
    print("\n" + "=" * 60)
    print("DATASET GENERATION COMPLETE")
    print("=" * 60)
    print(f"\nConversational:  {len(conv_train):>6} train  |  {len(conv_eval):>5} eval")
    print(f"Tool-use:        {len(tool_train):>6} train  |  {len(tool_eval):>5} eval")
    print(f"{'─' * 45}")
    print(f"Combined:        {len(combined_train):>6} train  |  {len(combined_eval):>5} eval")
    print(f"Grand total:     {len(combined_train) + len(combined_eval):>6}")

    print("\n--- Conversational Train Categories ---")
    for cat, count in count_categories(conv_train).items():
        pct = count * 100 // len(conv_train)
        print(f"  {cat:<25} {count:>5}  ({pct}%)")

    print("\n--- Tool-use Train Categories ---")
    for cat, count in count_categories(tool_train).items():
        pct = count * 100 // len(tool_train)
        print(f"  {cat:<25} {count:>5}  ({pct}%)")

    print(f"\nOutput: {output_dir}/")
    print("  conversational/train.jsonl, eval.jsonl")
    print("  tool_use/train.jsonl, eval.jsonl")
    print("  combined/train.jsonl, eval.jsonl")
    print("  stats.json")


if __name__ == "__main__":
    main()
