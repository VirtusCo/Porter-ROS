// Copyright 2026 VirtusCo
//
// Tool dispatcher — maps classified intents to executable tool calls.
// Performs sub-classification of INFO_QUERY intents by keyword analysis
// to select the appropriate tool (flight status, gate info, find nearest, etc.).
//
// Generates pre-formatted JSON arguments from intent fields, ready for
// direct invocation by the orchestrator without further parsing.
//
// Thread-safety: stateless functions, no mutable globals.

#include "virtus_ai_core.hpp"

#include <algorithm>
#include <cctype>
#include <string>

namespace virtus_ai {

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Convert to lowercase for keyword matching (ASCII only).
static std::string to_lower_td(const std::string& s) {
    std::string out;
    out.reserve(s.size());
    for (char c : s) {
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

/// Escape a string for safe embedding inside a JSON string value.
/// Handles double-quotes, backslashes, and control characters.
static std::string json_escape(const std::string& s) {
    std::string out;
    out.reserve(s.size() + 8);
    for (char c : s) {
        switch (c) {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n";  break;
            case '\r': out += "\\r";  break;
            case '\t': out += "\\t";  break;
            default:
                if (static_cast<unsigned char>(c) < 0x20) {
                    // Control character — skip
                } else {
                    out.push_back(c);
                }
                break;
        }
    }
    return out;
}

/// Check if a lowercase string contains a keyword.
static bool contains(const std::string& haystack, const std::string& needle) {
    return haystack.find(needle) != std::string::npos;
}

// ---------------------------------------------------------------------------
// INFO_QUERY sub-classification
// ---------------------------------------------------------------------------

/// Sub-classify an INFO_QUERY intent into a specific tool based on keywords
/// in the original user text.
///
/// Priority order (most specific first):
///   1. Flight-related keywords → get_flight_status
///   2. Gate-related keywords   → get_gate_info
///   3. Facility keywords       → find_nearest
///   4. Directions keywords     → get_directions
///   5. Default                 → general_info (requires LLM)
struct SubClassResult {
    std::string tool_name;
    std::string args_json;
    bool requires_llm;
};

static SubClassResult sub_classify_info_query(const std::string& lower_text) {
    SubClassResult result;
    result.requires_llm = false;

    // --- Flight information ---
    if (contains(lower_text, "flight") || contains(lower_text, "departure") ||
        contains(lower_text, "arrival") || contains(lower_text, "boarding")) {
        result.tool_name = "get_flight_status";

        // Try to extract flight number (e.g. BA456, EK203)
        std::regex flight_re(R"(\b([a-z]{2}\d{2,4})\b)");
        std::smatch match;
        if (std::regex_search(lower_text, match, flight_re)) {
            std::string flight_num = match[1].str();
            // Uppercase the airline code
            if (flight_num.size() >= 2) {
                flight_num[0] = static_cast<char>(
                    std::toupper(static_cast<unsigned char>(flight_num[0])));
                flight_num[1] = static_cast<char>(
                    std::toupper(static_cast<unsigned char>(flight_num[1])));
            }
            result.args_json = R"({"flight_number": ")" + json_escape(flight_num) + R"("})";
        } else {
            result.args_json = R"({"query": ")" + json_escape(lower_text) + R"("})";
            result.requires_llm = true;
        }
        return result;
    }

    // --- Gate information ---
    if (contains(lower_text, "gate")) {
        result.tool_name = "get_gate_info";

        // Try to extract gate identifier (e.g. C5, B12)
        std::regex gate_re(R"(\b(?:gate\s+)?([a-z]\d{1,3})\b)");
        std::smatch match;
        if (std::regex_search(lower_text, match, gate_re)) {
            std::string gate_id = match[1].str();
            if (!gate_id.empty()) {
                gate_id[0] = static_cast<char>(
                    std::toupper(static_cast<unsigned char>(gate_id[0])));
            }
            result.args_json = R"({"gate": ")" + json_escape(gate_id) + R"("})";
        } else {
            result.args_json = R"({"query": ")" + json_escape(lower_text) + R"("})";
            result.requires_llm = true;
        }
        return result;
    }

    // --- Facilities (restroom, lounge, food, shop, etc.) ---
    static const std::vector<std::pair<std::string, std::string>> facility_keywords = {
        {"restroom",  "restroom"},
        {"bathroom",  "restroom"},
        {"toilet",    "restroom"},
        {"washroom",  "restroom"},
        {"lounge",    "lounge"},
        {"food",      "food"},
        {"restaurant","food"},
        {"cafe",      "food"},
        {"coffee",    "food"},
        {"dining",    "food"},
        {"shop",      "shop"},
        {"store",     "shop"},
        {"pharmacy",  "pharmacy"},
        {"atm",       "atm"},
        {"bank",      "atm"},
    };

    for (const auto& entry : facility_keywords) {
        if (contains(lower_text, entry.first)) {
            result.tool_name = "find_nearest";
            result.args_json = R"({"facility_type": ")" +
                               json_escape(entry.second) + R"("})";
            return result;
        }
    }

    // --- Directions (how do I get to, where is) ---
    if (contains(lower_text, "direction") || contains(lower_text, "how do i get") ||
        contains(lower_text, "how to get") || contains(lower_text, "way to")) {
        result.tool_name = "get_directions";
        result.args_json = R"({"query": ")" + json_escape(lower_text) + R"("})";
        result.requires_llm = true;  // Need LLM to parse complex direction queries
        return result;
    }

    // --- Default: general info query → requires LLM ---
    result.tool_name = "general_info";
    result.args_json = R"({"query": ")" + json_escape(lower_text) + R"("})";
    result.requires_llm = true;
    return result;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

ToolDispatchResult dispatch_tool(const IntentResult& intent, const std::string& raw_text) {
    ToolDispatchResult result;
    result.requires_llm = false;

    std::string lower_text = to_lower_td(raw_text);

    // --- UNKNOWN or very low confidence → always delegate to LLM ---
    if (intent.intent == "UNKNOWN" || intent.confidence < 0.50f) {
        result.tool_name = "general_info";
        result.args_json = R"({"query": ")" + json_escape(raw_text) + R"("})";
        result.requires_llm = true;
        return result;
    }

    // --- NAVIGATE ---
    if (intent.intent == "NAVIGATE") {
        result.tool_name = "get_directions";
        if (!intent.destination.empty()) {
            result.args_json = R"({"destination": ")" +
                               json_escape(intent.destination) + R"("})";
        } else {
            result.args_json = R"({"query": ")" + json_escape(raw_text) + R"("})";
            result.requires_llm = true;
        }
        return result;
    }

    // --- FOLLOW ---
    if (intent.intent == "FOLLOW") {
        result.tool_name = "escort";
        result.args_json = R"({"action": "follow"})";
        return result;
    }

    // --- STOP ---
    if (intent.intent == "STOP") {
        result.tool_name = "emergency_stop";
        result.args_json = R"({"action": "stop"})";
        return result;
    }

    // --- WAIT ---
    if (intent.intent == "WAIT") {
        result.tool_name = "hold_position";
        result.args_json = R"({"action": "wait"})";
        return result;
    }

    // --- WEIGH ---
    if (intent.intent == "WEIGH") {
        result.tool_name = "weigh_luggage";
        result.args_json = R"({"action": "weigh"})";
        return result;
    }

    // --- ASSIST ---
    if (intent.intent == "ASSIST") {
        result.tool_name = "request_assistance";
        result.args_json = R"({"query": ")" + json_escape(raw_text) + R"("})";
        return result;
    }

    // --- INFO_QUERY — sub-classify by keywords ---
    if (intent.intent == "INFO_QUERY") {
        auto sub = sub_classify_info_query(lower_text);
        result.tool_name = sub.tool_name;
        result.args_json = sub.args_json;
        result.requires_llm = sub.requires_llm;
        return result;
    }

    // Fallback: should not reach here, but be safe
    result.tool_name = "general_info";
    result.args_json = R"({"query": ")" + json_escape(raw_text) + R"("})";
    result.requires_llm = true;
    return result;
}

}  // namespace virtus_ai
