// Copyright 2026 VirtusCo
//
// Intent classifier — pre-compiled regex + keyword matching for the Porter
// AI inference hot path.  Replaces the Python regex dispatcher with C++17
// static-init patterns that compile once and match in microseconds.
//
// Supported intents (aligned with PassengerCommand.msg):
//   NAVIGATE, FOLLOW, STOP, WAIT, INFO_QUERY, WEIGH, ASSIST, UNKNOWN
//
// Thread-safety: all regex objects are const after static initialisation.

#include "virtus_ai_core.hpp"

#include <algorithm>
#include <cctype>
#include <string>
#include <vector>

namespace virtus_ai {

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Convert a UTF-8 string to lowercase (ASCII portion only).
/// Non-ASCII bytes are passed through unchanged — this is fine because our
/// regex patterns only target ASCII keywords.
static std::string to_lower(const std::string& s) {
    std::string out;
    out.reserve(s.size());
    for (char c : s) {
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

/// Normalise a destination string for consistent output.
/// "Gate C5" → "gate_c5", "Check-in B" → "checkin_b", "Terminal 3" → "terminal_3"
static std::string normalise_destination(const std::string& raw) {
    std::string s = to_lower(raw);

    // Remove common filler words
    // Replace hyphens and spaces with underscores
    std::string out;
    out.reserve(s.size());
    for (char c : s) {
        if (c == ' ' || c == '-') {
            out.push_back('_');
        } else if (std::isalnum(static_cast<unsigned char>(c)) || c == '_') {
            out.push_back(c);
        }
        // Drop other punctuation
    }

    // Collapse consecutive underscores
    std::string collapsed;
    collapsed.reserve(out.size());
    bool last_was_underscore = false;
    for (char c : out) {
        if (c == '_') {
            if (!last_was_underscore) {
                collapsed.push_back('_');
            }
            last_was_underscore = true;
        } else {
            collapsed.push_back(c);
            last_was_underscore = false;
        }
    }

    // Trim leading/trailing underscores
    size_t start = collapsed.find_first_not_of('_');
    size_t end = collapsed.find_last_not_of('_');
    if (start == std::string::npos) {
        return collapsed;
    }
    return collapsed.substr(start, end - start + 1);
}

// ---------------------------------------------------------------------------
// Pre-compiled regex patterns — static const, compiled once at load time
// ---------------------------------------------------------------------------

/// Pattern entry: regex, intent name, whether it captures a destination group.
struct PatternEntry {
    std::regex pattern;
    std::string intent;
    bool has_destination;     // If true, first capture group is destination
    float base_confidence;    // Base confidence for this pattern type
};

/// Build the static pattern table.  Called once on first use (Meyer's singleton).
static const std::vector<PatternEntry>& get_patterns() {
    static const std::vector<PatternEntry> patterns = {
        // ---------------------------------------------------------------
        // NAVIGATE — gate navigation
        // ---------------------------------------------------------------
        {std::regex(
            R"(\b(?:take\s+me\s+to|go\s+to|navigate\s+to|bring\s+me\s+to|head\s+to|walk\s+me\s+to|find)\s+(?:gate\s+)?([a-zA-Z]\d{1,3})\b)",
            std::regex::icase | std::regex::optimize),
         "NAVIGATE", true, 0.95f},

        // NAVIGATE — "where is gate X" / "how do I get to gate X"
        {std::regex(
            R"(\b(?:where\s+is|how\s+(?:do\s+I\s+)?get\s+to|directions?\s+to)\s+(?:gate\s+)?([a-zA-Z]\d{1,3})\b)",
            std::regex::icase | std::regex::optimize),
         "NAVIGATE", true, 0.90f},

        // NAVIGATE — check-in desk
        {std::regex(
            R"(\b(?:take\s+me\s+to|go\s+to|navigate\s+to|find|where\s+is)\s+(?:the\s+)?check[\s-]?in\s+(?:desk\s+|counter\s+)?([a-zA-Z](?:\d{1,3})?)\b)",
            std::regex::icase | std::regex::optimize),
         "NAVIGATE", true, 0.90f},

        // NAVIGATE — baggage belt / carousel
        {std::regex(
            R"(\b(?:take\s+me\s+to|go\s+to|find|where\s+is)\s+(?:the\s+)?(?:baggage|luggage)\s+(?:belt|carousel|claim)\s*(\d{1,3})?\b)",
            std::regex::icase | std::regex::optimize),
         "NAVIGATE", true, 0.90f},

        // NAVIGATE — terminal
        {std::regex(
            R"(\b(?:take\s+me\s+to|go\s+to|navigate\s+to|find|where\s+is)\s+(?:the\s+)?terminal\s+(\d{1,3}|[a-zA-Z])\b)",
            std::regex::icase | std::regex::optimize),
         "NAVIGATE", true, 0.90f},

        // NAVIGATE — generic "take me to <destination>"
        {std::regex(
            R"(\b(?:take\s+me\s+to|go\s+to|navigate\s+to|bring\s+me\s+to)\s+(?:the\s+)?(.{2,30}?)(?:\s*[.!?]|$))",
            std::regex::icase | std::regex::optimize),
         "NAVIGATE", true, 0.80f},

        // ---------------------------------------------------------------
        // FOLLOW — follow me / escort
        // ---------------------------------------------------------------
        {std::regex(
            R"(\b(?:follow\s+me|come\s+with\s+me|escort\s+me|walk\s+with\s+me|accompany\s+me)\b)",
            std::regex::icase | std::regex::optimize),
         "FOLLOW", false, 0.95f},

        // ---------------------------------------------------------------
        // STOP — emergency stop / halt
        // ---------------------------------------------------------------
        {std::regex(
            R"(\b(?:stop|halt|freeze|don'?t\s+move|stay|e[\s-]?stop|emergency\s+stop)\b)",
            std::regex::icase | std::regex::optimize),
         "STOP", false, 0.95f},

        // ---------------------------------------------------------------
        // WAIT — wait / hold / pause
        // ---------------------------------------------------------------
        {std::regex(
            R"(\b(?:wait|hold\s+on|pause|one\s+moment|just\s+a\s+(?:moment|second|sec|minute|min))\b)",
            std::regex::icase | std::regex::optimize),
         "WAIT", false, 0.95f},

        // ---------------------------------------------------------------
        // WEIGH — luggage weighing
        // ---------------------------------------------------------------
        {std::regex(
            R"(\b(?:weigh|weight|how\s+heavy|measure|scale)\s+(?:\w+\s+)*?(?:my\s+)?(?:luggage|bag|bags|suitcase|baggage)\b)",
            std::regex::icase | std::regex::optimize),
         "WEIGH", false, 0.95f},

        // WEIGH — "how much does my bag weigh"
        {std::regex(
            R"(\b(?:how\s+much\s+does?\s+(?:my\s+)?(?:luggage|bag|bags|suitcase|baggage)\s+weigh)\b)",
            std::regex::icase | std::regex::optimize),
         "WEIGH", false, 0.90f},

        // WEIGH — "how heavy is my bag" (with "is" between heavy and bag)
        {std::regex(
            R"(\b(?:how\s+heavy\s+is\s+(?:my\s+)?(?:luggage|bag|bags|suitcase|baggage))\b)",
            std::regex::icase | std::regex::optimize),
         "WEIGH", false, 0.95f},

        // ---------------------------------------------------------------
        // ASSIST — accessibility / wheelchair / help
        // ---------------------------------------------------------------
        {std::regex(
            R"(\b(?:wheelchair|accessibility|disabled|special\s+assist(?:ance)?|mobility\s+(?:aid|assistance)|help\s+me\s+with)\b)",
            std::regex::icase | std::regex::optimize),
         "ASSIST", false, 0.90f},

        // ---------------------------------------------------------------
        // INFO_QUERY — flight information
        // ---------------------------------------------------------------
        {std::regex(
            R"(\b(?:flight|departure|arrival|boarding)\s+(?:status|info(?:rmation)?|time|gate|board(?:ing)?)\b)",
            std::regex::icase | std::regex::optimize),
         "INFO_QUERY", false, 0.90f},

        // INFO_QUERY — flight number pattern (e.g. "BA456", "EK203")
        {std::regex(
            R"(\b(?:what|when|where)\s+.*?\b([A-Z]{2}\d{2,4})\b)",
            std::regex::icase | std::regex::optimize),
         "INFO_QUERY", false, 0.85f},

        // INFO_QUERY — facilities (restroom, lounge, food, shop)
        {std::regex(
            R"(\b(?:where\s+(?:is|are)\s+(?:the\s+)?(?:nearest|closest)?|find\s+(?:me\s+)?(?:a\s+|the\s+)?)\s*(?:restroom|bathroom|toilet|washroom|lounge|food|restaurant|cafe|coffee|shop|store|pharmacy|atm|bank)\b)",
            std::regex::icase | std::regex::optimize),
         "INFO_QUERY", false, 0.90f},

        // INFO_QUERY — general questions
        {std::regex(
            R"(\b(?:what|when|where|how|which|tell\s+me\s+about|can\s+you\s+tell\s+me)\b)",
            std::regex::icase | std::regex::optimize),
         "INFO_QUERY", false, 0.60f},
    };
    return patterns;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

IntentResult classify_intent(const std::string& text) {
    IntentResult result;
    result.intent = "UNKNOWN";
    result.confidence = 0.0f;

    // Detect language first
    result.language = detect_language(text);

    // Lowercase for matching
    std::string lower = to_lower(text);

    const auto& patterns = get_patterns();
    float best_confidence = 0.0f;

    for (const auto& entry : patterns) {
        std::smatch match;
        if (std::regex_search(lower, match, entry.pattern)) {
            float conf = entry.base_confidence;

            // Boost confidence for longer/more specific matches
            size_t match_len = match[0].length();
            float coverage = static_cast<float>(match_len) /
                             static_cast<float>(std::max(lower.size(), static_cast<size_t>(1)));
            // Small boost for higher coverage (max +0.05)
            conf = std::min(1.0f, conf + coverage * 0.05f);

            if (conf > best_confidence) {
                best_confidence = conf;
                result.intent = entry.intent;
                result.confidence = conf;

                // Extract destination if present
                if (entry.has_destination && match.size() > 1 && match[1].matched) {
                    std::string raw_dest = match[1].str();
                    result.destination = normalise_destination(raw_dest);
                } else {
                    result.destination.clear();
                }
            }
        }
    }

    return result;
}

std::vector<IntentResult> classify_batch(const std::vector<std::string>& texts) {
    std::vector<IntentResult> results;
    results.reserve(texts.size());
    for (const auto& text : texts) {
        results.push_back(classify_intent(text));
    }
    return results;
}

}  // namespace virtus_ai
