// Copyright 2026 VirtusCo
//
// Heartbeat latency regression test for the ESP32 motor bridge.
//
// Purpose: Verify that timer callback jitter remains below 50ms even under
// heavy CPU load.  The ESP32 motor controller firmware enforces a 500ms
// heartbeat watchdog — if the bridge misses a heartbeat, the motors stop
// immediately with passenger luggage loaded.  This test catches latency
// regressions before they reach the robot.
//
// Test methodology:
//   1. Spawn N CPU-intensive background threads (simulate Nav2 + AI inference)
//   2. Run a simulated heartbeat timer at 200ms intervals (matching the
//      default heartbeat_interval parameter)
//   3. Measure the jitter (actual interval - target interval) for each tick
//   4. Assert: max jitter < 50ms over 30 seconds of measurement
//   5. Report: mean, P95, P99, and max jitter statistics
//
// This test runs in CI without ROS 2 or hardware dependencies.
// It validates that the C++ timer infrastructure meets real-time requirements
// that Python's GIL cannot guarantee.

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <numeric>
#include <thread>
#include <vector>

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

/// Target heartbeat interval in milliseconds (matches the ROS 2 node default).
static constexpr double TARGET_INTERVAL_MS = 200.0;

/// Total measurement duration in seconds.
static constexpr int MEASUREMENT_DURATION_SEC = 30;

/// Maximum allowed jitter in milliseconds.
/// The ESP32 watchdog timeout is 500ms.  With a 200ms heartbeat interval,
/// we have 300ms of slack.  Allowing 50ms jitter keeps a 250ms safety margin.
static constexpr double MAX_JITTER_MS = 50.0;

/// Number of CPU-intensive background threads to simulate Nav2 + AI load.
static constexpr int NUM_BACKGROUND_THREADS = 4;

// ---------------------------------------------------------------------------
// CPU stress worker
// ---------------------------------------------------------------------------

/// Burn CPU cycles to simulate Nav2 SLAM and AI inference load.
/// Performs floating-point math (similar to costmap updates and matrix ops).
static void cpu_stress_worker(std::atomic<bool>& should_stop) {
    volatile double accumulator = 1.0;
    while (!should_stop.load(std::memory_order_relaxed)) {
        // Simulate Nav2 costmap update + AI inference matrix operations
        for (int i = 0; i < 10000; i++) {
            accumulator = std::sin(accumulator) * std::cos(accumulator) + 0.001;
            accumulator = std::sqrt(std::fabs(accumulator) + 1.0);
        }
    }
    // Prevent optimiser from removing the loop
    if (accumulator == -999.999) {
        std::printf("unreachable\n");
    }
}

// ---------------------------------------------------------------------------
// Percentile calculation
// ---------------------------------------------------------------------------

/// Compute the Pth percentile from a sorted vector.
static double percentile(const std::vector<double>& sorted_data, double p) {
    if (sorted_data.empty()) { return 0.0; }
    double index = (p / 100.0) * static_cast<double>(sorted_data.size() - 1);
    size_t lo = static_cast<size_t>(std::floor(index));
    size_t hi = static_cast<size_t>(std::ceil(index));
    if (lo == hi || hi >= sorted_data.size()) {
        return sorted_data[lo];
    }
    double frac = index - static_cast<double>(lo);
    return sorted_data[lo] * (1.0 - frac) + sorted_data[hi] * frac;
}

// ---------------------------------------------------------------------------
// Main test
// ---------------------------------------------------------------------------

int main() {
    std::printf("=== ESP32 Motor Bridge: Heartbeat Latency Regression Test ===\n\n");
    std::printf("Configuration:\n");
    std::printf("  Target interval:     %.0f ms\n", TARGET_INTERVAL_MS);
    std::printf("  Measurement duration: %d seconds\n", MEASUREMENT_DURATION_SEC);
    std::printf("  Max allowed jitter:  %.0f ms\n", MAX_JITTER_MS);
    std::printf("  Background threads:  %d\n\n", NUM_BACKGROUND_THREADS);

    // --- Start CPU stress threads ---
    std::atomic<bool> should_stop{false};
    std::vector<std::thread> stress_threads;
    stress_threads.reserve(NUM_BACKGROUND_THREADS);

    std::printf("Starting %d CPU stress threads...\n", NUM_BACKGROUND_THREADS);
    for (int i = 0; i < NUM_BACKGROUND_THREADS; i++) {
        stress_threads.emplace_back(cpu_stress_worker, std::ref(should_stop));
    }

    // Give stress threads time to saturate CPU
    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    // --- Measure heartbeat jitter ---
    std::printf("Measuring heartbeat jitter for %d seconds...\n\n",
                MEASUREMENT_DURATION_SEC);

    std::vector<double> jitter_samples;
    int expected_samples = static_cast<int>(
        MEASUREMENT_DURATION_SEC * 1000.0 / TARGET_INTERVAL_MS);
    jitter_samples.reserve(expected_samples + 10);

    auto measurement_start = std::chrono::steady_clock::now();
    auto measurement_end = measurement_start +
        std::chrono::seconds(MEASUREMENT_DURATION_SEC);

    auto last_tick = std::chrono::steady_clock::now();

    while (std::chrono::steady_clock::now() < measurement_end) {
        // Simulate the heartbeat timer: sleep for target interval
        std::this_thread::sleep_for(
            std::chrono::microseconds(
                static_cast<int64_t>(TARGET_INTERVAL_MS * 1000.0)));

        auto now = std::chrono::steady_clock::now();
        double actual_interval_ms = std::chrono::duration<double, std::milli>(
            now - last_tick).count();
        last_tick = now;

        // Jitter = |actual - target|
        double jitter_ms = std::fabs(actual_interval_ms - TARGET_INTERVAL_MS);
        jitter_samples.push_back(jitter_ms);
    }

    // --- Stop stress threads ---
    should_stop.store(true, std::memory_order_relaxed);
    for (auto& t : stress_threads) {
        t.join();
    }

    // --- Compute statistics ---
    if (jitter_samples.empty()) {
        std::fprintf(stderr, "ERROR: No samples collected!\n");
        return 1;
    }

    std::vector<double> sorted = jitter_samples;
    std::sort(sorted.begin(), sorted.end());

    double mean_jitter = std::accumulate(
        jitter_samples.begin(), jitter_samples.end(), 0.0) /
        static_cast<double>(jitter_samples.size());
    double max_jitter = sorted.back();
    double p50 = percentile(sorted, 50.0);
    double p95 = percentile(sorted, 95.0);
    double p99 = percentile(sorted, 99.0);

    std::printf("Results (%zu samples):\n", jitter_samples.size());
    std::printf("  Mean jitter:   %6.2f ms\n", mean_jitter);
    std::printf("  P50  jitter:   %6.2f ms\n", p50);
    std::printf("  P95  jitter:   %6.2f ms\n", p95);
    std::printf("  P99  jitter:   %6.2f ms\n", p99);
    std::printf("  Max  jitter:   %6.2f ms\n", max_jitter);
    std::printf("  Threshold:     %6.2f ms\n\n", MAX_JITTER_MS);

    // --- Assert ---
    if (max_jitter > MAX_JITTER_MS) {
        std::fprintf(stderr,
            "FAIL: Max jitter %.2f ms exceeds threshold %.2f ms!\n"
            "\n"
            "This means the heartbeat timer experienced unacceptable latency\n"
            "under CPU load.  On the real robot, this would cause the ESP32\n"
            "motor controller watchdog to trigger (500ms timeout), stopping\n"
            "the motors mid-task with passenger luggage loaded.\n"
            "\n"
            "Possible causes:\n"
            "  - System scheduler not giving the bridge process enough CPU\n"
            "  - Other processes consuming too many cycles\n"
            "  - Thread priority misconfiguration\n"
            "\n"
            "If this test fails in CI, do NOT ignore it.  This is a safety\n"
            "regression that could cause luggage drops in production.\n",
            max_jitter, MAX_JITTER_MS);
        return 1;
    }

    std::printf("PASS: All heartbeat jitter samples within %.0f ms threshold.\n",
                MAX_JITTER_MS);
    std::printf("The C++ timer infrastructure meets the ESP32 watchdog requirements.\n");

    return 0;
}
