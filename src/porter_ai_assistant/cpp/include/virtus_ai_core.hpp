// Copyright 2026 VirtusCo
//
// C++ hot path for AI inference pipeline — replaces Python regex + dispatch overhead
// Target: <1ms per classify call (vs 10-15ms in Python, 80-120ms under GIL contention)
//
// This module provides:
//   1. Intent classification via pre-compiled regex + keyword matching
//   2. Tool dispatch mapping (intent → tool name + pre-formatted JSON args)
//   3. Template-based response formatting (bypasses LLM for simple queries)
//   4. Fast language detection (Unicode script + transliteration keywords)
//   5. Batch classification for multi-utterance pipelines
//
// All functions are thread-safe (no mutable global state after static init).

#pragma once

#include <string>
#include <vector>
#include <regex>
#include <unordered_map>

namespace virtus_ai {

/// Result of intent classification for a single utterance.
struct IntentResult {
    std::string intent;       // NAVIGATE, FOLLOW, STOP, WAIT, INFO_QUERY, WEIGH, ASSIST, UNKNOWN
    std::string destination;  // Extracted destination if NAVIGATE (e.g. "gate_c5", "checkin_b")
    float confidence;         // 0.0-1.0
    std::string language;     // Detected ISO 639-1 language code (en, ml, hi, ta)
};

/// Classify a single text utterance into an intent.
///
/// Applies pre-compiled regex patterns in priority order.
/// Returns the highest-confidence match, or UNKNOWN if no pattern hits.
///
/// @param text  Raw user utterance (UTF-8)
/// @return      IntentResult with intent, destination, confidence, language
IntentResult classify_intent(const std::string& text);

/// Result of tool dispatch — maps an intent to an executable tool call.
struct ToolDispatchResult {
    std::string tool_name;    // e.g. "get_directions", "get_flight_status"
    std::string args_json;    // Pre-formatted JSON arguments
    bool requires_llm;        // True if LLM inference needed (complex query)
};

/// Map a classified intent to a tool invocation.
///
/// For well-known intents (NAVIGATE, FOLLOW, etc.), returns the tool name
/// and pre-formatted JSON arguments. For UNKNOWN or low-confidence intents,
/// sets requires_llm=true to delegate to the LLM.
///
/// @param intent   Result from classify_intent()
/// @param raw_text Original user text (used for sub-classification of INFO_QUERY)
/// @return         ToolDispatchResult with tool_name, args_json, requires_llm
ToolDispatchResult dispatch_tool(const IntentResult& intent, const std::string& raw_text);

/// A formatted response ready for display to the user.
struct FormattedResponse {
    std::string text;
    std::string language;
    bool used_template;       // True if template was used (no LLM needed)
    float generation_time_ms;
};

/// Format a response from tool output using language-specific templates.
///
/// For common tool results, fills a template with extracted variables
/// (e.g. gate number, terminal, distance). Falls back to requires_llm=true
/// (via used_template=false) for complex responses that need LLM generation.
///
/// @param tool_name         The tool that produced the result
/// @param tool_result_json  JSON string with tool output fields
/// @param language          Target language code (default "en")
/// @return                  FormattedResponse with text, language, used_template
FormattedResponse format_response(
    const std::string& tool_name,
    const std::string& tool_result_json,
    const std::string& language = "en");

/// Detect the primary language of a text string.
///
/// Uses Unicode script ranges for non-Latin scripts:
///   - Malayalam:  U+0D00..U+0D7F
///   - Devanagari: U+0900..U+097F (Hindi)
///   - Tamil:      U+0B80..U+0BFF
///
/// For Latin-script text, checks transliterated keyword patterns
/// (e.g. "ente", "evide" for Malayalam; "kahan", "kya" for Hindi).
///
/// @param text  UTF-8 encoded text
/// @return      ISO 639-1 language code ("en", "ml", "hi", "ta")
std::string detect_language(const std::string& text);

/// Classify multiple utterances in a single call (batch mode).
///
/// Equivalent to calling classify_intent() on each text, but expressed
/// as a batch for convenient pybind11 vectorized usage.
///
/// @param texts  Vector of raw user utterances
/// @return       Vector of IntentResult, one per input text
std::vector<IntentResult> classify_batch(const std::vector<std::string>& texts);

}  // namespace virtus_ai
