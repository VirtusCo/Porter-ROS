# Virtue AI Assistant — Training Data

## Overview

Training and evaluation datasets for the Virtue AI Assistant, an on-device LLM
running on Raspberry Pi 4/5. Uses a **modular LoRA adapter strategy** with
separate conversational and tool-use adapters.

## Strategy: Modular LoRA Adapters

| Adapter | Base Model | Dataset | Purpose |
|---------|-----------|---------|---------|
| **Conversational** | Qwen 2.5 1.5B Instruct | `conversational/` | Airport Q&A, wayfinding, services |
| **Tool-Use** | Qwen 2.5 1.5B Instruct | `tool_use/` | Function calling, real-time data |

Adapters are separate LoRA weight files — dynamically loaded at inference time,
never merged. A query classifier routes to the appropriate adapter.

**Training tips:**
- Learning rate: `2e-5` (low to minimize catastrophic forgetting)
- Train conversational adapter first, then tool-use adapter separately
- Use simplified JSON schemas for small model accuracy (~85%+)

## Dataset Statistics

| Split | Conversational | Tool-Use | Total |
|-------|---------------|----------|-------|
| **Train** | 7,000 | 3,000 | **10,000** |
| **Eval** | 1,400 | 600 | **2,000** |
| **Total** | 8,400 | 3,600 | **12,000** |

- **Zero overlap** between train and eval question text (verified)
- 13,894 unique examples generated prior to splitting (no oversampling)
- All examples validated (valid JSON, correct message structure)

## File Structure

```
data/
├── README.md                        ← This file
├── system_prompts.yaml              ← 12 prompt templates (conv + tool-use)
├── tool_schemas.json                ← 14 tool definitions for tool-use adapter
├── stats.json                       ← Auto-generated statistics
├── airport_qa_train.jsonl           ← Legacy seed dataset (116 examples)
├── airport_qa_eval.jsonl            ← Legacy seed dataset (44 examples)
│
├── conversational/                  ← Conversational LoRA training data
│   ├── train.jsonl                  ← 7,000 examples
│   └── eval.jsonl                   ← 1,400 examples
│
└── tool_use/                        ← Tool-use LoRA training data
    ├── train.jsonl                  ← 3,000 examples
    └── eval.jsonl                   ← 600 examples
```

## Conversational Dataset (14 Categories)

| Category | Train | % | Description |
|----------|-------|---|-------------|
| Navigation | ~974 | 14% | Gate/terminal/facility directions, wayfinding |
| Flight Info | ~843 | 12% | Flight status, delays, boarding, connections |
| Dining & Shopping | ~709 | 10% | Restaurants, duty-free, shops, prices |
| Services | ~593 | 8% | WiFi, lounges, prayer rooms, medical, etc. |
| Check-in | ~536 | 8% | Counter locations, process, kiosks |
| Baggage | ~498 | 7% | Allowances, lost bags, storage, weighing |
| Security | ~449 | 6% | Prohibited items, liquids, immigration |
| Transport | ~389 | 6% | Taxi, metro, bus, car rental |
| Multilingual | ~378 | 5% | Hindi/Hinglish Q&A |
| General | ~370 | 5% | Airport hours, complaints, pets, drones |
| Virtue Identity | ~359 | 5% | Robot capabilities, company, privacy |
| Accessibility | ~349 | 5% | Wheelchair, elderly, families |
| Small Talk | ~315 | 4% | Greetings, goodbye, social |
| Emergency | ~238 | 3% | Medical, security, lost child, theft |

## Tool-Use Dataset (14 Tools)

### Tools Defined

| Tool | Description | Train % |
|------|-------------|---------|
| `get_flight_status` | Check real-time flight status | 11% |
| `get_directions` | Get walking directions to location | 10% |
| `find_nearest` | Find nearest facility (ATM, restroom) | 10% |
| `escort_passenger` | Navigate with passenger + carry bags | 9% |
| `call_assistance` | Request wheelchair, medical, security | 8% |
| `get_transport_options` | Ground transport to city | 7% |
| `get_airline_counter` | Locate airline service counter | 6% |
| `weigh_luggage` | Weigh passenger's bags | 6% |
| `check_wait_time` | Queue wait estimates | 6% |
| `show_map` | Display airport map on screen | 6% |
| `translate_text` | Translate text to another language | 6% |
| `report_incident` | Report safety/security incident | 5% |
| `set_reminder` | Set boarding/flight reminder | 5% |

### Tool-Use Format (ChatML)

```json
{
  "messages": [
    {"role": "system", "content": "You are Virtue... Available tools: [...]"},
    {"role": "user", "content": "Take me to Gate B12"},
    {"role": "assistant", "content": "<tool_call>{\"name\": \"get_directions\", \"arguments\": {\"destination\": \"Gate B12\"}}</tool_call>"},
    {"role": "tool", "content": "{\"distance_m\": 200, \"walk_time_min\": 5, ...}"},
    {"role": "assistant", "content": "Gate B12 is about 5 minutes from here. Let me carry your bags!"}
  ]
}
```

## System Prompts (12 templates)

`system_prompts.yaml` provides context-specific prompts:

| Prompt Key | Context | Adapter |
|------------|---------|---------|
| `default` | General queries | Conversational |
| `wayfinding` | Navigation/directions | Conversational |
| `flight_info` | Flight-related | Conversational |
| `accessibility` | Disability/family | Conversational |
| `baggage` | Luggage queries | Conversational |
| `security` | Security & immigration | Conversational |
| `shopping_dining` | Food & shopping | Conversational |
| `emergency` | Emergency situations | Conversational |
| `hindi` | Hindi interaction | Conversational |
| `identity` | About Virtue / Porter robot | Conversational |
| `tool_use` | Tool calling mode | Tool-Use |
| `tool_conversational` | Tool mode, no call needed | Tool-Use |

## Generation

Datasets are generated programmatically via `scripts/generate_dataset.py`:

- **Entity substitution**: 150+ gates, 20 airlines, 33 domestic + 32 international
  cities, 26 restaurants, 24 facilities, 18 baggage types, 15 languages
- **Natural language variation**: Random prefixes, suffixes, and context phrases
  (~3,360 combinations per base question)
- **Deduplication**: MD5 hash of user question — no duplicates

### Regenerate

```bash
cd src/porter_ai_assistant
python3 scripts/generate_dataset.py --train-size 10000 --eval-size 2000 --seed 42
```

Options: `--train-size`, `--eval-size`, `--seed`, `--output-dir`

## Conversational Format

```json
{
  "messages": [
    {"role": "system", "content": "You are Virtue, a helpful airport assistant..."},
    {"role": "user", "content": "Where is Gate B12?"},
    {"role": "assistant", "content": "Gate B12 is in Terminal B, Concourse B..."}
  ]
}
```

Compatible with: HuggingFace TRL (`SFTTrainer`), Axolotl, llama.cpp fine-tune, OpenAI API.

## Design Principles

1. **Conversational tone** — Natural passenger-robot dialogue
2. **Actionable responses** — Every answer includes next steps
3. **Proactive assistance** — Virtue volunteers to carry bags and escort
4. **Safety-first** — Emergency responses prioritize safety
5. **Honest limitations** — Directs to FIDS screens for live data
6. **Cultural awareness** — Indian airport context (₹, Indian airlines, Hindi)
7. **Concise for RPi** — Responses designed for <300 token generation

## License

Proprietary to VirtusCo. Internal use only until open-source release decision.
