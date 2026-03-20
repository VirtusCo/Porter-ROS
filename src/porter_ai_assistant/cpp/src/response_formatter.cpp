// Copyright 2026 VirtusCo
//
// Template-based response formatter — generates natural-language responses
// from tool output JSON without invoking the LLM.
//
// Supports 4 languages (en, ml, hi, ta) with 15+ templates each for common
// airport queries.  Falls back to used_template=false when the tool result
// doesn't match any known template pattern.
//
// JSON parsing here is intentionally minimal (key-value extraction by regex)
// to avoid adding a JSON library dependency.  The tool_result_json is always
// flat (no nesting) in the Porter pipeline.
//
// Thread-safety: all template maps are const after static initialisation.

#include "virtus_ai_core.hpp"

#include <chrono>
#include <regex>
#include <string>
#include <unordered_map>
#include <vector>

namespace virtus_ai {

// ---------------------------------------------------------------------------
// Minimal JSON value extraction
// ---------------------------------------------------------------------------

/// Extract the string value for a given key from a flat JSON object.
/// Returns empty string if key not found.
///
/// Only handles flat JSON: {"key": "value", "key2": "value2"}
/// Does not handle nested objects, arrays, or escaped quotes inside values.
static std::string json_get(const std::string& json, const std::string& key) {
    // Look for "key": "value" or "key": value (for numbers/bools)
    std::string pattern = "\"" + key + "\"\\s*:\\s*\"([^\"]*)\"";
    std::regex re(pattern);
    std::smatch match;
    if (std::regex_search(json, match, re) && match.size() > 1) {
        return match[1].str();
    }

    // Try unquoted value (number, bool, null)
    std::string pattern2 = "\"" + key + "\"\\s*:\\s*([^,}\\s]+)";
    std::regex re2(pattern2);
    if (std::regex_search(json, match, re2) && match.size() > 1) {
        return match[1].str();
    }

    return "";
}

// ---------------------------------------------------------------------------
// Template definitions per language
// ---------------------------------------------------------------------------

/// A response template with placeholders: {gate}, {terminal}, {facility},
/// {distance}, {direction}, {flight}, {status}, {time}, {name}, {weight}.
///
/// Placeholders are filled from the tool result JSON using the same key names.
using TemplateMap = std::unordered_map<std::string, std::vector<std::string>>;

/// English templates indexed by tool_name.
static const TemplateMap& get_templates_en() {
    static const TemplateMap templates = {
        {"get_directions", {
            "Gate {gate} is located in {terminal}. {directions}",
            "To reach {destination}, {directions}",
            "Head towards {destination}. It's about {distance} from here.",
        }},
        {"get_gate_info", {
            "Gate {gate} is in Terminal {terminal}. {status}",
            "Gate {gate}: {status}. Located in {terminal}.",
        }},
        {"get_flight_status", {
            "Flight {flight_number} is {status}. Departure at {time} from Gate {gate}.",
            "Flight {flight_number}: {status}. Gate {gate}, Terminal {terminal}.",
            "Your flight {flight_number} is currently {status}.",
        }},
        {"find_nearest", {
            "The nearest {facility_type} is {name}, about {distance} {direction}.",
            "You'll find a {facility_type} ({name}) {distance} {direction} from here.",
            "There's a {facility_type} nearby — {name}, {distance} {direction}.",
        }},
        {"weigh_luggage", {
            "Your luggage weighs {weight} kg.",
            "The weight of your bag is {weight} kg. The airline limit is typically 23 kg for economy.",
        }},
        {"escort", {
            "I'll follow you now. Please walk at a comfortable pace and I'll stay close behind.",
            "Following mode activated. I'm right behind you.",
        }},
        {"emergency_stop", {
            "Stopping immediately. All motors halted.",
            "Emergency stop engaged. I've stopped completely.",
        }},
        {"hold_position", {
            "I'll wait right here. Let me know when you're ready to go.",
            "Holding position. Take your time.",
        }},
        {"request_assistance", {
            "I've notified airport staff for assistance. Someone will be with you shortly.",
            "Assistance request sent. A staff member should arrive within a few minutes.",
        }},
    };
    return templates;
}

/// Malayalam templates (transliterated + native script mix for display).
static const TemplateMap& get_templates_ml() {
    static const TemplateMap templates = {
        {"get_directions", {
            "Gate {gate} {terminal}-il aanu. {directions}",
            "{destination}-ilekku pokan, {directions}",
        }},
        {"get_flight_status", {
            "Flight {flight_number} {status} aanu. Gate {gate}, samayam {time}.",
            "Ningalude flight {flight_number} ippol {status} aanu.",
        }},
        {"find_nearest", {
            "Ettavum aduttha {facility_type} {name} aanu, {distance} {direction}.",
        }},
        {"weigh_luggage", {
            "Ningalude luggage {weight} kg aanu.",
        }},
        {"escort", {
            "Njan ningale follow cheyyaam. Sukhamaayi nadakkuka.",
        }},
        {"emergency_stop", {
            "Ippol thanne nirthi. Ellaa motors-um nilachhu.",
        }},
        {"hold_position", {
            "Njan ividé nilkkaam. Ningal ready aakumbol ariyikkuka.",
        }},
    };
    return templates;
}

/// Hindi templates.
static const TemplateMap& get_templates_hi() {
    static const TemplateMap templates = {
        {"get_directions", {
            "Gate {gate} Terminal {terminal} mein hai. {directions}",
            "{destination} tak jaane ke liye, {directions}",
        }},
        {"get_flight_status", {
            "Flight {flight_number} ka status {status} hai. Gate {gate}, samay {time}.",
            "Aapki flight {flight_number} abhi {status} hai.",
        }},
        {"find_nearest", {
            "Sabse nazdeeki {facility_type} {name} hai, {distance} {direction}.",
        }},
        {"weigh_luggage", {
            "Aapka luggage {weight} kg hai.",
        }},
        {"escort", {
            "Main aapke saath chalunga. Aaram se chaliye.",
        }},
        {"emergency_stop", {
            "Turant ruk gaya. Sab motors band hain.",
        }},
        {"hold_position", {
            "Main yahaan rukukga. Jab tayaar ho, bataiye.",
        }},
    };
    return templates;
}

/// Tamil templates.
static const TemplateMap& get_templates_ta() {
    static const TemplateMap templates = {
        {"get_directions", {
            "Gate {gate} Terminal {terminal}-il irukkiRathu. {directions}",
            "{destination}-ku poga, {directions}",
        }},
        {"get_flight_status", {
            "Flight {flight_number} nilamai {status}. Gate {gate}, neram {time}.",
            "Ungal flight {flight_number} ippozhuthu {status}.",
        }},
        {"find_nearest", {
            "Miga arugil ulla {facility_type} {name}, {distance} {direction}.",
        }},
        {"weigh_luggage", {
            "Ungal luggage {weight} kg.",
        }},
        {"escort", {
            "Naan ungalai pin thodarvEn. Vasathiyaaga nadangal.",
        }},
        {"emergency_stop", {
            "Udanadi niRuththinEn. Ellaa motors-um niRuththappattathu.",
        }},
        {"hold_position", {
            "Naan ingE kaaththirukkiREn. Neenga thayaaraanavudan sollungal.",
        }},
    };
    return templates;
}

/// Select the template map for a given language code.
static const TemplateMap& get_templates_for_lang(const std::string& lang) {
    if (lang == "ml") { return get_templates_ml(); }
    if (lang == "hi") { return get_templates_hi(); }
    if (lang == "ta") { return get_templates_ta(); }
    return get_templates_en();  // Default
}

// ---------------------------------------------------------------------------
// Template filling
// ---------------------------------------------------------------------------

/// Replace all occurrences of {placeholder} in a template with values
/// extracted from the tool result JSON.
///
/// Known placeholders: gate, terminal, directions, destination, distance,
/// direction, flight_number, status, time, name, facility_type, weight, action.
static std::string fill_template(const std::string& tmpl, const std::string& json) {
    static const std::vector<std::string> placeholders = {
        "gate", "terminal", "directions", "destination", "distance",
        "direction", "flight_number", "status", "time", "name",
        "facility_type", "weight", "action", "query",
    };

    std::string result = tmpl;
    bool has_unfilled = false;

    for (const auto& ph : placeholders) {
        std::string token = "{" + ph + "}";
        size_t pos = result.find(token);
        if (pos != std::string::npos) {
            std::string value = json_get(json, ph);
            if (value.empty()) {
                has_unfilled = true;
            } else {
                // Replace all occurrences of this placeholder
                while ((pos = result.find(token)) != std::string::npos) {
                    result.replace(pos, token.length(), value);
                }
            }
        }
    }

    // If any placeholder couldn't be filled, this template is incomplete
    if (has_unfilled) {
        return "";  // Signal: template didn't work
    }

    return result;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

FormattedResponse format_response(
    const std::string& tool_name,
    const std::string& tool_result_json,
    const std::string& language) {

    auto start = std::chrono::steady_clock::now();

    FormattedResponse response;
    response.language = language;
    response.used_template = false;

    const auto& templates = get_templates_for_lang(language);
    auto it = templates.find(tool_name);

    if (it != templates.end()) {
        // Try each template variant until one fills completely
        for (const auto& tmpl : it->second) {
            std::string filled = fill_template(tmpl, tool_result_json);
            if (!filled.empty()) {
                response.text = filled;
                response.used_template = true;
                break;
            }
        }
    }

    // If no template worked, set empty text — caller should use LLM
    if (!response.used_template) {
        response.text = "";
    }

    auto end = std::chrono::steady_clock::now();
    response.generation_time_ms = std::chrono::duration<float, std::milli>(
        end - start).count();

    return response;
}

}  // namespace virtus_ai
