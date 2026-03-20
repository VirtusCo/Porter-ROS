cmake_minimum_required(VERSION 3.16)
project(virtus_ai_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Source files for the core library (everything except bindings)
set(CORE_SOURCES
    src/intent_classifier.cpp
    src/tool_dispatcher.cpp
    src/response_formatter.cpp
    src/language_detector.cpp
)

# Try to find pybind11 for Python module build
find_package(pybind11 QUIET)

if(pybind11_FOUND)
    message(STATUS "pybind11 found — building Python module")
    pybind11_add_module(virtus_ai_core
        ${CORE_SOURCES}
        src/bindings.cpp
    )
    target_include_directories(virtus_ai_core PUBLIC include)
    target_compile_options(virtus_ai_core PRIVATE
        $<$<CXX_COMPILER_ID:GNU,Clang>:-Wall -Wextra -Wpedantic>
        $<$<CXX_COMPILER_ID:MSVC>:/W4>
    )
else()
    message(STATUS "pybind11 not found — building standalone static library")
    add_library(virtus_ai_core STATIC ${CORE_SOURCES})
    target_include_directories(virtus_ai_core PUBLIC include)
    target_compile_options(virtus_ai_core PRIVATE
        $<$<CXX_COMPILER_ID:GNU,Clang>:-Wall -Wextra -Wpedantic>
        $<$<CXX_COMPILER_ID:MSVC>:/W4>
    )
endif()

# ---------------------------------------------------------------------------
# Tests — always build (no gtest dependency, standalone assert + main)
# ---------------------------------------------------------------------------
enable_testing()

# Test: intent classifier (30+ test cases)
add_executable(test_intent_classifier
    test/test_intent_classifier.cpp
    ${CORE_SOURCES}
)
target_include_directories(test_intent_classifier PRIVATE include)
target_compile_options(test_intent_classifier PRIVATE
    $<$<CXX_COMPILER_ID:GNU,Clang>:-Wall -Wextra -Wpedantic>
    $<$<CXX_COMPILER_ID:MSVC>:/W4>
)
add_test(NAME test_intent_classifier COMMAND test_intent_classifier)

# Test: tool dispatcher (15+ test cases)
add_executable(test_tool_dispatcher
    test/test_tool_dispatcher.cpp
    ${CORE_SOURCES}
)
target_include_directories(test_tool_dispatcher PRIVATE include)
target_compile_options(test_tool_dispatcher PRIVATE
    $<$<CXX_COMPILER_ID:GNU,Clang>:-Wall -Wextra -Wpedantic>
    $<$<CXX_COMPILER_ID:MSVC>:/W4>
)
add_test(NAME test_tool_dispatcher COMMAND test_tool_dispatcher)

# Test: language detector (15+ test cases)
add_executable(test_language_detector
    test/test_language_detector.cpp
    ${CORE_SOURCES}
)
target_include_directories(test_language_detector PRIVATE include)
target_compile_options(test_language_detector PRIVATE
    $<$<CXX_COMPILER_ID:GNU,Clang>:-Wall -Wextra -Wpedantic>
    $<$<CXX_COMPILER_ID:MSVC>:/W4>
)
add_test(NAME test_language_detector COMMAND test_language_detector)
