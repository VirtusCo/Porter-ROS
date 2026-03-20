// Copyright 2026 VirtusCo
//
// Fast language detection for the Porter AI inference hot path.
//
// Two-pass strategy:
//   1. Unicode script detection — count codepoints in known script ranges
//      (Malayalam, Devanagari/Hindi, Tamil).  Dominant script wins.
//   2. Keyword fallback for Latin-script transliterations — checks for
//      language-specific romanized keywords (e.g. "ente"/"evide" → Malayalam,
//      "kahan"/"kya" → Hindi, "eppadi"/"enge" → Tamil).
//   3. Default: English ("en").
//
// Thread-safety: all keyword lists are const after static initialisation.

#include "virtus_ai_core.hpp"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <string>
#include <vector>

namespace virtus_ai {

// ---------------------------------------------------------------------------
// Unicode script ranges (UTF-8 → codepoint decoding)
// ---------------------------------------------------------------------------

/// Decode one UTF-8 codepoint starting at data[i].
/// Returns the codepoint value and advances i past the decoded bytes.
/// Returns 0xFFFD (replacement character) on invalid sequences.
static uint32_t decode_utf8(const std::string& data, size_t& i) {
    uint32_t cp = 0;
    unsigned char c = static_cast<unsigned char>(data[i]);

    if (c < 0x80) {
        // ASCII
        cp = c;
        i += 1;
    } else if ((c & 0xE0) == 0xC0) {
        // 2-byte sequence
        if (i + 1 >= data.size()) { i = data.size(); return 0xFFFD; }
        cp = (c & 0x1F) << 6;
        cp |= (static_cast<unsigned char>(data[i + 1]) & 0x3F);
        i += 2;
    } else if ((c & 0xF0) == 0xE0) {
        // 3-byte sequence
        if (i + 2 >= data.size()) { i = data.size(); return 0xFFFD; }
        cp = (c & 0x0F) << 12;
        cp |= (static_cast<unsigned char>(data[i + 1]) & 0x3F) << 6;
        cp |= (static_cast<unsigned char>(data[i + 2]) & 0x3F);
        i += 3;
    } else if ((c & 0xF8) == 0xF0) {
        // 4-byte sequence
        if (i + 3 >= data.size()) { i = data.size(); return 0xFFFD; }
        cp = (c & 0x07) << 18;
        cp |= (static_cast<unsigned char>(data[i + 1]) & 0x3F) << 12;
        cp |= (static_cast<unsigned char>(data[i + 2]) & 0x3F) << 6;
        cp |= (static_cast<unsigned char>(data[i + 3]) & 0x3F);
        i += 4;
    } else {
        // Invalid leading byte
        i += 1;
        return 0xFFFD;
    }

    return cp;
}

/// Classify a Unicode codepoint into a language script.
/// Returns "ml" for Malayalam, "hi" for Devanagari, "ta" for Tamil,
/// or empty string for other scripts (Latin, digits, punctuation, etc.).
static std::string classify_codepoint(uint32_t cp) {
    // Malayalam: U+0D00..U+0D7F
    if (cp >= 0x0D00 && cp <= 0x0D7F) { return "ml"; }

    // Devanagari (Hindi): U+0900..U+097F
    if (cp >= 0x0900 && cp <= 0x097F) { return "hi"; }

    // Tamil: U+0B80..U+0BFF
    if (cp >= 0x0B80 && cp <= 0x0BFF) { return "ta"; }

    return "";
}

// ---------------------------------------------------------------------------
// Transliteration keyword lists
// ---------------------------------------------------------------------------

/// Malayalam transliterated keywords commonly used in Romanized Malayalam.
static const std::vector<std::string>& get_ml_keywords() {
    static const std::vector<std::string> kw = {
        "ente", "evide", "enik", "ningal", "enikku", "njan", "venam",
        "aanu", "alla", "engane", "eppo", "entha", "poyikko", "vaa",
        "sukham", "nanni", "dayavayi", "sthalam", "vimaanam",
    };
    return kw;
}

/// Hindi transliterated keywords (Romanized Hindi/Hinglish).
static const std::vector<std::string>& get_hi_keywords() {
    static const std::vector<std::string> kw = {
        "kahan", "kya", "mujhe", "mera", "aapka", "kitna", "kaise",
        "chahiye", "hai", "hain", "nahin", "nahi", "karo", "batao",
        "dhanyavaad", "shukriya", "kidhar", "dikha", "samaan",
    };
    return kw;
}

/// Tamil transliterated keywords (Romanized Tamil/Tanglish).
static const std::vector<std::string>& get_ta_keywords() {
    static const std::vector<std::string> kw = {
        "eppadi", "enge", "enakku", "naan", "ungal", "evvalavu", "enna",
        "vendum", "irukku", "illai", "sollu", "ponga", "vaanga",
        "nandri", "thayavu", "idam", "vimanam",
    };
    return kw;
}

/// Convert to lowercase for keyword matching.
static std::string to_lower_ld(const std::string& s) {
    std::string out;
    out.reserve(s.size());
    for (char c : s) {
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

/// Check if any keyword from the list appears as a word in the text.
/// Uses simple substring matching (keywords are short and distinctive enough
/// that substring matching is acceptable for transliterated text).
static int count_keyword_hits(const std::string& lower_text,
                              const std::vector<std::string>& keywords) {
    int hits = 0;
    for (const auto& kw : keywords) {
        // Look for word boundary: keyword surrounded by non-alpha or start/end
        size_t pos = 0;
        while ((pos = lower_text.find(kw, pos)) != std::string::npos) {
            // Check left boundary
            bool left_ok = (pos == 0) ||
                           !std::isalpha(static_cast<unsigned char>(lower_text[pos - 1]));
            // Check right boundary
            size_t end_pos = pos + kw.size();
            bool right_ok = (end_pos >= lower_text.size()) ||
                            !std::isalpha(static_cast<unsigned char>(lower_text[end_pos]));

            if (left_ok && right_ok) {
                hits++;
            }
            pos = end_pos;
        }
    }
    return hits;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

std::string detect_language(const std::string& text) {
    if (text.empty()) {
        return "en";
    }

    // --- Pass 1: Unicode script detection ---
    int ml_count = 0;
    int hi_count = 0;
    int ta_count = 0;
    int total_script = 0;

    size_t i = 0;
    while (i < text.size()) {
        uint32_t cp = decode_utf8(text, i);
        std::string script = classify_codepoint(cp);
        if (script == "ml") { ml_count++; total_script++; }
        else if (script == "hi") { hi_count++; total_script++; }
        else if (script == "ta") { ta_count++; total_script++; }
    }

    // If we found significant non-Latin script characters, use that
    if (total_script >= 3) {
        // Return the dominant script
        if (ml_count >= hi_count && ml_count >= ta_count) { return "ml"; }
        if (hi_count >= ml_count && hi_count >= ta_count) { return "hi"; }
        return "ta";
    }

    // --- Pass 2: Transliteration keyword detection ---
    std::string lower = to_lower_ld(text);

    int ml_hits = count_keyword_hits(lower, get_ml_keywords());
    int hi_hits = count_keyword_hits(lower, get_hi_keywords());
    int ta_hits = count_keyword_hits(lower, get_ta_keywords());

    // Need at least 2 keyword hits to be confident
    int max_hits = std::max({ml_hits, hi_hits, ta_hits});
    if (max_hits >= 2) {
        if (ml_hits == max_hits) { return "ml"; }
        if (hi_hits == max_hits) { return "hi"; }
        return "ta";
    }

    // Even a single distinctive keyword is worth considering if no other language matched
    if (max_hits >= 1) {
        if (ml_hits == max_hits) { return "ml"; }
        if (hi_hits == max_hits) { return "hi"; }
        if (ta_hits == max_hits) { return "ta"; }
    }

    // --- Default: English ---
    return "en";
}

}  // namespace virtus_ai
