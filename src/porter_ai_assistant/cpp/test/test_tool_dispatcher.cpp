// Copyright 2026 VirtusCo
//
// Test suite for the tool dispatcher C++ hot path.
// 15+ test cases covering intent-to-tool mapping for all types,
// INFO_QUERY sub-classification, JSON args format, and requires_llm flags.
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

#define ASSERT_TRUE(expr) \
    do { \
        if (!(expr)) { \
            std::fprintf(stderr, "  FAIL: %s at %s:%d\n", #expr, __FILE__, __LINE__); \
            tests_failed++; \
            return; \
        } \
    } while (0)

#define ASSERT_FALSE(expr) \
    do { \
        if ((expr)) { \
            std::fprintf(stderr, "  FAIL: !(%s) at %s:%d\n", #expr, __FILE__, __LINE__); \
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

/// Build an IntentResult for testing.
static virtus_ai::IntentResult make_intent(const std::string& intent,
                                            const std::string& dest,
                                            float conf,
                                            const std::string& lang = "en") {
    virtus_ai::IntentResult r;
    r.intent = intent;
    r.destination = dest;
    r.confidence = conf;
    r.language = lang;
    return r;
}

// ---------------------------------------------------------------------------
// NAVIGATE → get_directions
// ---------------------------------------------------------------------------

static void test_navigate_with_destination() {
    auto intent = make_intent("NAVIGATE", "gate_c5", 0.95f);
    auto result = virtus_ai::dispatch_tool(intent, "Take me to gate C5");
    ASSERT_EQ(result.tool_name, "get_directions");
    ASSERT_FALSE(result.requires_llm);
    // Args should contain the destination
    ASSERT_TRUE(result.args_json.find("gate_c5") != std::string::npos);
}

static void test_navigate_without_destination() {
    auto intent = make_intent("NAVIGATE", "", 0.80f);
    auto result = virtus_ai::dispatch_tool(intent, "Take me somewhere nice");
    ASSERT_EQ(result.tool_name, "get_directions");
    ASSERT_TRUE(result.requires_llm);
}

// ---------------------------------------------------------------------------
// FOLLOW → escort
// ---------------------------------------------------------------------------

static void test_follow_dispatch() {
    auto intent = make_intent("FOLLOW", "", 0.95f);
    auto result = virtus_ai::dispatch_tool(intent, "Follow me");
    ASSERT_EQ(result.tool_name, "escort");
    ASSERT_FALSE(result.requires_llm);
    ASSERT_TRUE(result.args_json.find("follow") != std::string::npos);
}

// ---------------------------------------------------------------------------
// STOP → emergency_stop
// ---------------------------------------------------------------------------

static void test_stop_dispatch() {
    auto intent = make_intent("STOP", "", 0.95f);
    auto result = virtus_ai::dispatch_tool(intent, "Stop!");
    ASSERT_EQ(result.tool_name, "emergency_stop");
    ASSERT_FALSE(result.requires_llm);
}

// ---------------------------------------------------------------------------
// WAIT → hold_position
// ---------------------------------------------------------------------------

static void test_wait_dispatch() {
    auto intent = make_intent("WAIT", "", 0.95f);
    auto result = virtus_ai::dispatch_tool(intent, "Wait here");
    ASSERT_EQ(result.tool_name, "hold_position");
    ASSERT_FALSE(result.requires_llm);
}

// ---------------------------------------------------------------------------
// WEIGH → weigh_luggage
// ---------------------------------------------------------------------------

static void test_weigh_dispatch() {
    auto intent = make_intent("WEIGH", "", 0.95f);
    auto result = virtus_ai::dispatch_tool(intent, "Weigh my bag");
    ASSERT_EQ(result.tool_name, "weigh_luggage");
    ASSERT_FALSE(result.requires_llm);
}

// ---------------------------------------------------------------------------
// ASSIST → request_assistance
// ---------------------------------------------------------------------------

static void test_assist_dispatch() {
    auto intent = make_intent("ASSIST", "", 0.90f);
    auto result = virtus_ai::dispatch_tool(intent, "I need wheelchair assistance");
    ASSERT_EQ(result.tool_name, "request_assistance");
    ASSERT_FALSE(result.requires_llm);
}

// ---------------------------------------------------------------------------
// INFO_QUERY sub-classification
// ---------------------------------------------------------------------------

static void test_info_flight_status() {
    auto intent = make_intent("INFO_QUERY", "", 0.90f);
    auto result = virtus_ai::dispatch_tool(intent, "What is the flight status of BA456?");
    ASSERT_EQ(result.tool_name, "get_flight_status");
    ASSERT_FALSE(result.requires_llm);
    ASSERT_TRUE(result.args_json.find("BA456") != std::string::npos);
}

static void test_info_flight_no_number() {
    auto intent = make_intent("INFO_QUERY", "", 0.90f);
    auto result = virtus_ai::dispatch_tool(intent, "When is my flight departing?");
    ASSERT_EQ(result.tool_name, "get_flight_status");
    ASSERT_TRUE(result.requires_llm);  // No flight number → needs LLM
}

static void test_info_gate() {
    auto intent = make_intent("INFO_QUERY", "", 0.90f);
    auto result = virtus_ai::dispatch_tool(intent, "What gate is my flight at?");
    ASSERT_EQ(result.tool_name, "get_gate_info");
}

static void test_info_restroom() {
    auto intent = make_intent("INFO_QUERY", "", 0.90f);
    auto result = virtus_ai::dispatch_tool(intent, "Where is the nearest restroom?");
    ASSERT_EQ(result.tool_name, "find_nearest");
    ASSERT_FALSE(result.requires_llm);
    ASSERT_TRUE(result.args_json.find("restroom") != std::string::npos);
}

static void test_info_food() {
    auto intent = make_intent("INFO_QUERY", "", 0.90f);
    auto result = virtus_ai::dispatch_tool(intent, "Where can I find a restaurant?");
    ASSERT_EQ(result.tool_name, "find_nearest");
    ASSERT_TRUE(result.args_json.find("food") != std::string::npos);
}

static void test_info_lounge() {
    auto intent = make_intent("INFO_QUERY", "", 0.90f);
    auto result = virtus_ai::dispatch_tool(intent, "Is there a lounge nearby?");
    ASSERT_EQ(result.tool_name, "find_nearest");
    ASSERT_TRUE(result.args_json.find("lounge") != std::string::npos);
}

static void test_info_general() {
    auto intent = make_intent("INFO_QUERY", "", 0.70f);
    auto result = virtus_ai::dispatch_tool(intent, "Tell me about this airport");
    ASSERT_EQ(result.tool_name, "general_info");
    ASSERT_TRUE(result.requires_llm);
}

// ---------------------------------------------------------------------------
// UNKNOWN / low confidence → requires LLM
// ---------------------------------------------------------------------------

static void test_unknown_dispatch() {
    auto intent = make_intent("UNKNOWN", "", 0.0f);
    auto result = virtus_ai::dispatch_tool(intent, "asdfghjkl");
    ASSERT_EQ(result.tool_name, "general_info");
    ASSERT_TRUE(result.requires_llm);
}

static void test_low_confidence_dispatch() {
    auto intent = make_intent("NAVIGATE", "somewhere", 0.40f);
    auto result = virtus_ai::dispatch_tool(intent, "maybe go somewhere");
    ASSERT_EQ(result.tool_name, "general_info");
    ASSERT_TRUE(result.requires_llm);
}

// ---------------------------------------------------------------------------
// JSON args format verification
// ---------------------------------------------------------------------------

static void test_json_args_valid_format() {
    auto intent = make_intent("NAVIGATE", "gate_c5", 0.95f);
    auto result = virtus_ai::dispatch_tool(intent, "Take me to gate C5");
    // Should be valid JSON with opening/closing braces
    ASSERT_TRUE(result.args_json.front() == '{');
    ASSERT_TRUE(result.args_json.back() == '}');
    // Should contain destination key
    ASSERT_TRUE(result.args_json.find("\"destination\"") != std::string::npos);
}

static void test_json_args_escaping() {
    auto intent = make_intent("ASSIST", "", 0.90f);
    auto result = virtus_ai::dispatch_tool(intent,
        "Help me with \"special\" needs");
    // Should have escaped quotes in the JSON
    ASSERT_TRUE(result.args_json.find("\\\"special\\\"") != std::string::npos);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

int main() {
    std::printf("=== Virtus AI Core: Tool Dispatcher Tests ===\n\n");

    // Intent → tool mapping
    RUN_TEST(navigate_with_destination);
    RUN_TEST(navigate_without_destination);
    RUN_TEST(follow_dispatch);
    RUN_TEST(stop_dispatch);
    RUN_TEST(wait_dispatch);
    RUN_TEST(weigh_dispatch);
    RUN_TEST(assist_dispatch);

    // INFO_QUERY sub-classification
    RUN_TEST(info_flight_status);
    RUN_TEST(info_flight_no_number);
    RUN_TEST(info_gate);
    RUN_TEST(info_restroom);
    RUN_TEST(info_food);
    RUN_TEST(info_lounge);
    RUN_TEST(info_general);

    // UNKNOWN / low confidence
    RUN_TEST(unknown_dispatch);
    RUN_TEST(low_confidence_dispatch);

    // JSON format
    RUN_TEST(json_args_valid_format);
    RUN_TEST(json_args_escaping);

    std::printf("\n=== Results: %d passed, %d failed ===\n",
                tests_passed, tests_failed);

    return tests_failed > 0 ? 1 : 0;
}
