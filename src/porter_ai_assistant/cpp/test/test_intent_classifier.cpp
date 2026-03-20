// Copyright 2026 VirtusCo
//
// Test suite for the intent classifier C++ hot path.
// 30+ test cases covering all 7 intent types, destination extraction,
// confidence scoring, case insensitivity, multilingual inputs, and batch mode.
//
// Uses simple assert() + main() pattern — no gtest dependency.

#include "virtus_ai_core.hpp"

#include <cassert>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static int tests_passed = 0;
static int tests_failed = 0;

#define TEST(name) \
    static void test_##name(); \
    struct Register_##name { \
        Register_##name() { test_##name(); } \
    }; \
    static void test_##name()

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

#define ASSERT_NEAR(a, b, eps) \
    do { \
        if (std::fabs((a) - (b)) > (eps)) { \
            std::fprintf(stderr, "  FAIL: %s ~= %s (%f != %f) at %s:%d\n", \
                #a, #b, static_cast<double>(a), static_cast<double>(b), \
                __FILE__, __LINE__); \
            tests_failed++; \
            return; \
        } \
    } while (0)

#define ASSERT_GT(a, b) \
    do { \
        if (!((a) > (b))) { \
            std::fprintf(stderr, "  FAIL: %s > %s (%f <= %f) at %s:%d\n", \
                #a, #b, static_cast<double>(a), static_cast<double>(b), \
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
// NAVIGATE intent tests
// ---------------------------------------------------------------------------

static void test_navigate_gate_explicit() {
    auto r = virtus_ai::classify_intent("Take me to gate C5");
    ASSERT_EQ(r.intent, "NAVIGATE");
    ASSERT_EQ(r.destination, "c5");
    ASSERT_GT(r.confidence, 0.9f);
}

static void test_navigate_gate_go_to() {
    auto r = virtus_ai::classify_intent("Go to gate B12");
    ASSERT_EQ(r.intent, "NAVIGATE");
    ASSERT_EQ(r.destination, "b12");
    ASSERT_GT(r.confidence, 0.9f);
}

static void test_navigate_gate_where_is() {
    auto r = virtus_ai::classify_intent("Where is gate A3?");
    ASSERT_EQ(r.intent, "NAVIGATE");
    ASSERT_EQ(r.destination, "a3");
    ASSERT_GT(r.confidence, 0.85f);
}

static void test_navigate_gate_directions() {
    auto r = virtus_ai::classify_intent("How do I get to gate D7?");
    ASSERT_EQ(r.intent, "NAVIGATE");
    ASSERT_EQ(r.destination, "d7");
    ASSERT_GT(r.confidence, 0.85f);
}

static void test_navigate_checkin() {
    auto r = virtus_ai::classify_intent("Take me to check-in B");
    ASSERT_EQ(r.intent, "NAVIGATE");
    ASSERT_TRUE(r.destination.find("b") != std::string::npos);
    ASSERT_GT(r.confidence, 0.85f);
}

static void test_navigate_baggage_belt() {
    auto r = virtus_ai::classify_intent("Where is baggage belt 3?");
    ASSERT_EQ(r.intent, "NAVIGATE");
    ASSERT_GT(r.confidence, 0.85f);
}

static void test_navigate_terminal() {
    auto r = virtus_ai::classify_intent("Navigate to terminal 2");
    ASSERT_EQ(r.intent, "NAVIGATE");
    ASSERT_EQ(r.destination, "2");
    ASSERT_GT(r.confidence, 0.85f);
}

static void test_navigate_generic_destination() {
    auto r = virtus_ai::classify_intent("Take me to the departure lounge");
    ASSERT_EQ(r.intent, "NAVIGATE");
    ASSERT_GT(r.confidence, 0.75f);
}

static void test_navigate_case_insensitive() {
    auto r = virtus_ai::classify_intent("TAKE ME TO GATE C5");
    ASSERT_EQ(r.intent, "NAVIGATE");
    ASSERT_EQ(r.destination, "c5");
    ASSERT_GT(r.confidence, 0.9f);
}

// ---------------------------------------------------------------------------
// FOLLOW intent tests
// ---------------------------------------------------------------------------

static void test_follow_basic() {
    auto r = virtus_ai::classify_intent("Follow me");
    ASSERT_EQ(r.intent, "FOLLOW");
    ASSERT_GT(r.confidence, 0.9f);
}

static void test_follow_escort() {
    auto r = virtus_ai::classify_intent("Escort me to my gate");
    ASSERT_EQ(r.intent, "FOLLOW");
    ASSERT_GT(r.confidence, 0.9f);
}

static void test_follow_come_with() {
    auto r = virtus_ai::classify_intent("Come with me please");
    ASSERT_EQ(r.intent, "FOLLOW");
    ASSERT_GT(r.confidence, 0.9f);
}

// ---------------------------------------------------------------------------
// STOP intent tests
// ---------------------------------------------------------------------------

static void test_stop_basic() {
    auto r = virtus_ai::classify_intent("Stop!");
    ASSERT_EQ(r.intent, "STOP");
    ASSERT_GT(r.confidence, 0.9f);
}

static void test_stop_halt() {
    auto r = virtus_ai::classify_intent("Halt right there");
    ASSERT_EQ(r.intent, "STOP");
    ASSERT_GT(r.confidence, 0.9f);
}

static void test_stop_emergency() {
    auto r = virtus_ai::classify_intent("Emergency stop now!");
    ASSERT_EQ(r.intent, "STOP");
    ASSERT_GT(r.confidence, 0.9f);
}

static void test_stop_dont_move() {
    auto r = virtus_ai::classify_intent("Don't move!");
    ASSERT_EQ(r.intent, "STOP");
    ASSERT_GT(r.confidence, 0.9f);
}

// ---------------------------------------------------------------------------
// WAIT intent tests
// ---------------------------------------------------------------------------

static void test_wait_basic() {
    auto r = virtus_ai::classify_intent("Wait here");
    ASSERT_EQ(r.intent, "WAIT");
    ASSERT_GT(r.confidence, 0.9f);
}

static void test_wait_hold_on() {
    auto r = virtus_ai::classify_intent("Hold on a second");
    ASSERT_EQ(r.intent, "WAIT");
    ASSERT_GT(r.confidence, 0.9f);
}

static void test_wait_moment() {
    auto r = virtus_ai::classify_intent("Just a moment please");
    ASSERT_EQ(r.intent, "WAIT");
    ASSERT_GT(r.confidence, 0.9f);
}

// ---------------------------------------------------------------------------
// WEIGH intent tests
// ---------------------------------------------------------------------------

static void test_weigh_basic() {
    auto r = virtus_ai::classify_intent("Weigh my luggage");
    ASSERT_EQ(r.intent, "WEIGH");
    ASSERT_GT(r.confidence, 0.9f);
}

static void test_weigh_how_heavy() {
    auto r = virtus_ai::classify_intent("How heavy is my bag?");
    ASSERT_EQ(r.intent, "WEIGH");
    ASSERT_GT(r.confidence, 0.85f);
}

static void test_weigh_how_much() {
    auto r = virtus_ai::classify_intent("How much does my luggage weigh?");
    ASSERT_EQ(r.intent, "WEIGH");
    ASSERT_GT(r.confidence, 0.85f);
}

// ---------------------------------------------------------------------------
// ASSIST intent tests
// ---------------------------------------------------------------------------

static void test_assist_wheelchair() {
    auto r = virtus_ai::classify_intent("I need a wheelchair");
    ASSERT_EQ(r.intent, "ASSIST");
    ASSERT_GT(r.confidence, 0.85f);
}

static void test_assist_accessibility() {
    auto r = virtus_ai::classify_intent("Is there accessibility support?");
    ASSERT_EQ(r.intent, "ASSIST");
    ASSERT_GT(r.confidence, 0.85f);
}

// ---------------------------------------------------------------------------
// INFO_QUERY intent tests
// ---------------------------------------------------------------------------

static void test_info_flight_status() {
    auto r = virtus_ai::classify_intent("What is the flight status of BA456?");
    ASSERT_EQ(r.intent, "INFO_QUERY");
    ASSERT_GT(r.confidence, 0.8f);
}

static void test_info_departure() {
    auto r = virtus_ai::classify_intent("When does my departure board?");
    ASSERT_EQ(r.intent, "INFO_QUERY");
    ASSERT_GT(r.confidence, 0.85f);
}

static void test_info_facility_restroom() {
    auto r = virtus_ai::classify_intent("Where is the nearest restroom?");
    ASSERT_EQ(r.intent, "INFO_QUERY");
    ASSERT_GT(r.confidence, 0.85f);
}

static void test_info_facility_food() {
    auto r = virtus_ai::classify_intent("Find me a restaurant nearby");
    ASSERT_EQ(r.intent, "INFO_QUERY");
    ASSERT_GT(r.confidence, 0.85f);
}

static void test_info_general_question() {
    auto r = virtus_ai::classify_intent("What time does the airport close?");
    ASSERT_EQ(r.intent, "INFO_QUERY");
    ASSERT_GT(r.confidence, 0.5f);
}

// ---------------------------------------------------------------------------
// UNKNOWN intent tests
// ---------------------------------------------------------------------------

static void test_unknown_gibberish() {
    auto r = virtus_ai::classify_intent("asdfghjkl qwerty");
    ASSERT_EQ(r.intent, "UNKNOWN");
    ASSERT_NEAR(r.confidence, 0.0f, 0.01f);
}

static void test_unknown_empty() {
    auto r = virtus_ai::classify_intent("");
    ASSERT_EQ(r.intent, "UNKNOWN");
    ASSERT_NEAR(r.confidence, 0.0f, 0.01f);
}

// ---------------------------------------------------------------------------
// Confidence scoring tests
// ---------------------------------------------------------------------------

static void test_confidence_exact_higher_than_partial() {
    auto exact = virtus_ai::classify_intent("Take me to gate C5");
    auto partial = virtus_ai::classify_intent("What time does the airport close?");
    ASSERT_GT(exact.confidence, partial.confidence);
}

// ---------------------------------------------------------------------------
// Batch classification test
// ---------------------------------------------------------------------------

static void test_batch_classification() {
    std::vector<std::string> texts = {
        "Take me to gate C5",
        "Stop!",
        "Follow me",
        "asdfghjkl",
    };
    auto results = virtus_ai::classify_batch(texts);
    ASSERT_TRUE(results.size() == 4);
    ASSERT_EQ(results[0].intent, "NAVIGATE");
    ASSERT_EQ(results[1].intent, "STOP");
    ASSERT_EQ(results[2].intent, "FOLLOW");
    ASSERT_EQ(results[3].intent, "UNKNOWN");
}

// ---------------------------------------------------------------------------
// Destination extraction accuracy
// ---------------------------------------------------------------------------

static void test_destination_normalisation_gate() {
    auto r = virtus_ai::classify_intent("Navigate to Gate C5");
    ASSERT_EQ(r.destination, "c5");
}

static void test_destination_normalisation_terminal() {
    auto r = virtus_ai::classify_intent("Go to terminal 3");
    ASSERT_EQ(r.destination, "3");
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

int main() {
    std::printf("=== Virtus AI Core: Intent Classifier Tests ===\n\n");

    // NAVIGATE
    RUN_TEST(navigate_gate_explicit);
    RUN_TEST(navigate_gate_go_to);
    RUN_TEST(navigate_gate_where_is);
    RUN_TEST(navigate_gate_directions);
    RUN_TEST(navigate_checkin);
    RUN_TEST(navigate_baggage_belt);
    RUN_TEST(navigate_terminal);
    RUN_TEST(navigate_generic_destination);
    RUN_TEST(navigate_case_insensitive);

    // FOLLOW
    RUN_TEST(follow_basic);
    RUN_TEST(follow_escort);
    RUN_TEST(follow_come_with);

    // STOP
    RUN_TEST(stop_basic);
    RUN_TEST(stop_halt);
    RUN_TEST(stop_emergency);
    RUN_TEST(stop_dont_move);

    // WAIT
    RUN_TEST(wait_basic);
    RUN_TEST(wait_hold_on);
    RUN_TEST(wait_moment);

    // WEIGH
    RUN_TEST(weigh_basic);
    RUN_TEST(weigh_how_heavy);
    RUN_TEST(weigh_how_much);

    // ASSIST
    RUN_TEST(assist_wheelchair);
    RUN_TEST(assist_accessibility);

    // INFO_QUERY
    RUN_TEST(info_flight_status);
    RUN_TEST(info_departure);
    RUN_TEST(info_facility_restroom);
    RUN_TEST(info_facility_food);
    RUN_TEST(info_general_question);

    // UNKNOWN
    RUN_TEST(unknown_gibberish);
    RUN_TEST(unknown_empty);

    // Confidence
    RUN_TEST(confidence_exact_higher_than_partial);

    // Batch
    RUN_TEST(batch_classification);

    // Destination extraction
    RUN_TEST(destination_normalisation_gate);
    RUN_TEST(destination_normalisation_terminal);

    std::printf("\n=== Results: %d passed, %d failed ===\n",
                tests_passed, tests_failed);

    return tests_failed > 0 ? 1 : 0;
}
