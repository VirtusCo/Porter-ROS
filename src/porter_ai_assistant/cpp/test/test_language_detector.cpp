// Copyright 2026 VirtusCo
//
// Test suite for the language detector C++ hot path.
// 15+ test cases covering English, Malayalam, Hindi, Tamil detection via
// both Unicode script analysis and transliterated keyword matching.
//
// Uses simple assert() + main() pattern — no gtest dependency.

#include "virtus_ai_core.hpp"

#include <cassert>
#include <cstdio>
#include <string>

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static int tests_passed = 0;
static int tests_failed = 0;

#define ASSERT_EQ(a, b) \
    do { \
        if ((a) != (b)) { \
            std::fprintf(stderr, "  FAIL: %s == %s ('%s' != '%s') at %s:%d\n", \
                #a, #b, std::string(a).c_str(), std::string(b).c_str(), \
                __FILE__, __LINE__); \
            tests_failed++; \
            return; \
        } \
    } while (0)

#define RUN_TEST(name) \
    do { \
        std::printf("  %-55s", #name "..."); \
        int before = tests_failed; \
        test_##name(); \
        if (tests_failed == before) { \
            tests_passed++; \
            std::printf("PASS\n"); \
        } else { \
            std::printf("FAIL\n"); \
        } \
    } while (0)

// ---------------------------------------------------------------------------
// English detection
// ---------------------------------------------------------------------------

static void test_english_basic() {
    auto lang = virtus_ai::detect_language("Take me to gate C5 please");
    ASSERT_EQ(lang, "en");
}

static void test_english_question() {
    auto lang = virtus_ai::detect_language("Where is the nearest restaurant?");
    ASSERT_EQ(lang, "en");
}

static void test_english_numbers() {
    auto lang = virtus_ai::detect_language("Flight BA456 departs at 14:30");
    ASSERT_EQ(lang, "en");
}

static void test_english_empty() {
    auto lang = virtus_ai::detect_language("");
    ASSERT_EQ(lang, "en");
}

// ---------------------------------------------------------------------------
// Malayalam detection — Unicode script (U+0D00..U+0D7F)
// ---------------------------------------------------------------------------

static void test_malayalam_unicode() {
    // "ente gate evideyaanu" in Malayalam script
    // Using actual Malayalam Unicode characters
    auto lang = virtus_ai::detect_language(
        "\xe0\xb4\x8e\xe0\xb4\xa8\xe0\xb5\x8d\xe0\xb4\xb1\xe0\xb5\x86 "
        "\xe0\xb4\x97\xe0\xb5\x87\xe0\xb4\xb1\xe0\xb5\x8d\xe0\xb4\xb1\xe0\xb5\x8d "
        "\xe0\xb4\x8e\xe0\xb4\xb5\xe0\xb4\xbf\xe0\xb4\x9f\xe0\xb5\x86\xe0\xb4\xaf\xe0\xb4\xbe\xe0\xb4\xa3\xe0\xb5\x8d");
    ASSERT_EQ(lang, "ml");
}

static void test_malayalam_transliterated() {
    // Transliterated Malayalam with distinctive keywords
    auto lang = virtus_ai::detect_language("ente gate evide aanu?");
    ASSERT_EQ(lang, "ml");
}

static void test_malayalam_keywords_single() {
    // Even a single distinctive keyword should trigger
    auto lang = virtus_ai::detect_language("njan gate poyi");
    ASSERT_EQ(lang, "ml");
}

// ---------------------------------------------------------------------------
// Hindi detection — Unicode script (U+0900..U+097F)
// ---------------------------------------------------------------------------

static void test_hindi_unicode() {
    // "mera gate kahan hai" in Devanagari
    auto lang = virtus_ai::detect_language(
        "\xe0\xa4\xae\xe0\xa5\x87\xe0\xa4\xb0\xe0\xa4\xbe "
        "\xe0\xa4\x97\xe0\xa5\x87\xe0\xa4\x9f "
        "\xe0\xa4\x95\xe0\xa4\xb9\xe0\xa4\xbe\xe0\xa4\x81 "
        "\xe0\xa4\xb9\xe0\xa5\x88");
    ASSERT_EQ(lang, "hi");
}

static void test_hindi_transliterated() {
    // Transliterated Hindi with distinctive keywords
    auto lang = virtus_ai::detect_language("mujhe batao kahan hai mera gate");
    ASSERT_EQ(lang, "hi");
}

static void test_hindi_keywords_hinglish() {
    // Hinglish: mix of Hindi transliterated and English
    auto lang = virtus_ai::detect_language("mera flight kya hai status batao");
    ASSERT_EQ(lang, "hi");
}

// ---------------------------------------------------------------------------
// Tamil detection — Unicode script (U+0B80..U+0BFF)
// ---------------------------------------------------------------------------

static void test_tamil_unicode() {
    // "enna gate" in Tamil script
    auto lang = virtus_ai::detect_language(
        "\xe0\xae\x8e\xe0\xae\xa9\xe0\xaf\x8d\xe0\xae\xa9 "
        "\xe0\xae\x95\xe0\xaf\x87\xe0\xae\x9f\xe0\xaf\x8d");
    ASSERT_EQ(lang, "ta");
}

static void test_tamil_transliterated() {
    // Transliterated Tamil with distinctive keywords
    auto lang = virtus_ai::detect_language("enakku enge irukku gate eppadi poga");
    ASSERT_EQ(lang, "ta");
}

static void test_tamil_keywords_tanglish() {
    // Tanglish: mix of Tamil transliterated and English
    auto lang = virtus_ai::detect_language("naan flight gate enge sollu");
    ASSERT_EQ(lang, "ta");
}

// ---------------------------------------------------------------------------
// Mixed script detection — dominant language wins
// ---------------------------------------------------------------------------

static void test_mixed_malayalam_dominant() {
    // More Malayalam characters than anything else
    auto lang = virtus_ai::detect_language(
        "\xe0\xb4\x8e\xe0\xb4\xa8\xe0\xb5\x8d\xe0\xb4\xb1\xe0\xb5\x86 "
        "\xe0\xb4\x97\xe0\xb5\x87\xe0\xb4\xb1\xe0\xb5\x8d\xe0\xb4\xb1\xe0\xb5\x8d "
        "gate C5");
    ASSERT_EQ(lang, "ml");
}

static void test_mixed_hindi_dominant() {
    // More Devanagari than other scripts
    auto lang = virtus_ai::detect_language(
        "\xe0\xa4\xae\xe0\xa5\x87\xe0\xa4\xb0\xe0\xa4\xbe "
        "\xe0\xa4\x97\xe0\xa5\x87\xe0\xa4\x9f "
        "C5 "
        "\xe0\xa4\x95\xe0\xa4\xb9\xe0\xa4\xbe\xe0\xa4\x81");
    ASSERT_EQ(lang, "hi");
}

// ---------------------------------------------------------------------------
// Edge cases
// ---------------------------------------------------------------------------

static void test_only_numbers() {
    auto lang = virtus_ai::detect_language("123 456 789");
    ASSERT_EQ(lang, "en");  // Default to English for numeric-only
}

static void test_only_punctuation() {
    auto lang = virtus_ai::detect_language("!!! ??? ...");
    ASSERT_EQ(lang, "en");  // Default to English
}

static void test_single_word_english() {
    auto lang = virtus_ai::detect_language("hello");
    ASSERT_EQ(lang, "en");
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

int main() {
    std::printf("=== Virtus AI Core: Language Detector Tests ===\n\n");

    // English
    RUN_TEST(english_basic);
    RUN_TEST(english_question);
    RUN_TEST(english_numbers);
    RUN_TEST(english_empty);

    // Malayalam
    RUN_TEST(malayalam_unicode);
    RUN_TEST(malayalam_transliterated);
    RUN_TEST(malayalam_keywords_single);

    // Hindi
    RUN_TEST(hindi_unicode);
    RUN_TEST(hindi_transliterated);
    RUN_TEST(hindi_keywords_hinglish);

    // Tamil
    RUN_TEST(tamil_unicode);
    RUN_TEST(tamil_transliterated);
    RUN_TEST(tamil_keywords_tanglish);

    // Mixed script
    RUN_TEST(mixed_malayalam_dominant);
    RUN_TEST(mixed_hindi_dominant);

    // Edge cases
    RUN_TEST(only_numbers);
    RUN_TEST(only_punctuation);
    RUN_TEST(single_word_english);

    std::printf("\n=== Results: %d passed, %d failed ===\n",
                tests_passed, tests_failed);

    return tests_failed > 0 ? 1 : 0;
}
