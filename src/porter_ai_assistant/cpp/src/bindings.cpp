// Copyright 2026 VirtusCo
//
// pybind11 Python bindings for the Virtus AI Core C++ hot path.
//
// Exposes:
//   - IntentResult, ToolDispatchResult, FormattedResponse (as Python classes)
//   - classify_intent(), dispatch_tool(), format_response() (as module functions)
//   - detect_language(), classify_batch() (as module functions)
//
// Usage from Python:
//   import virtus_ai_core
//   result = virtus_ai_core.classify_intent("Take me to gate C5")
//   print(result.intent, result.destination, result.confidence)

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "virtus_ai_core.hpp"

namespace py = pybind11;

PYBIND11_MODULE(virtus_ai_core, m) {
    m.doc() = "Virtus AI Core — C++ hot path for inference pipeline. "
              "Provides intent classification, tool dispatch, response formatting, "
              "and language detection with sub-millisecond latency.";

    // --- IntentResult ---
    py::class_<virtus_ai::IntentResult>(m, "IntentResult",
        "Result of intent classification for a single utterance.")
        .def(py::init<>())
        .def_readwrite("intent", &virtus_ai::IntentResult::intent,
            "Intent type: NAVIGATE, FOLLOW, STOP, WAIT, INFO_QUERY, WEIGH, ASSIST, UNKNOWN")
        .def_readwrite("destination", &virtus_ai::IntentResult::destination,
            "Extracted destination if NAVIGATE (e.g. 'gate_c5', 'checkin_b')")
        .def_readwrite("confidence", &virtus_ai::IntentResult::confidence,
            "Confidence score 0.0-1.0")
        .def_readwrite("language", &virtus_ai::IntentResult::language,
            "Detected language code (en, ml, hi, ta)")
        .def("__repr__", [](const virtus_ai::IntentResult& r) {
            return "<IntentResult intent='" + r.intent + "' dest='" + r.destination +
                   "' conf=" + std::to_string(r.confidence) +
                   " lang='" + r.language + "'>";
        });

    // --- ToolDispatchResult ---
    py::class_<virtus_ai::ToolDispatchResult>(m, "ToolDispatchResult",
        "Result of tool dispatch — maps an intent to an executable tool call.")
        .def(py::init<>())
        .def_readwrite("tool_name", &virtus_ai::ToolDispatchResult::tool_name,
            "Tool name, e.g. 'get_directions', 'get_flight_status'")
        .def_readwrite("args_json", &virtus_ai::ToolDispatchResult::args_json,
            "Pre-formatted JSON arguments for the tool")
        .def_readwrite("requires_llm", &virtus_ai::ToolDispatchResult::requires_llm,
            "True if LLM inference is needed (complex query)")
        .def("__repr__", [](const virtus_ai::ToolDispatchResult& r) {
            return "<ToolDispatchResult tool='" + r.tool_name +
                   "' requires_llm=" + (r.requires_llm ? "True" : "False") + ">";
        });

    // --- FormattedResponse ---
    py::class_<virtus_ai::FormattedResponse>(m, "FormattedResponse",
        "A formatted response ready for display to the user.")
        .def(py::init<>())
        .def_readwrite("text", &virtus_ai::FormattedResponse::text,
            "Response text in the target language")
        .def_readwrite("language", &virtus_ai::FormattedResponse::language,
            "Language code of the response")
        .def_readwrite("used_template", &virtus_ai::FormattedResponse::used_template,
            "True if a template was used (no LLM needed)")
        .def_readwrite("generation_time_ms", &virtus_ai::FormattedResponse::generation_time_ms,
            "Time taken to generate the response in milliseconds")
        .def("__repr__", [](const virtus_ai::FormattedResponse& r) {
            return "<FormattedResponse template=" +
                   std::string(r.used_template ? "True" : "False") +
                   " time=" + std::to_string(r.generation_time_ms) + "ms>";
        });

    // --- Module-level functions ---
    m.def("classify_intent", &virtus_ai::classify_intent,
        py::arg("text"),
        "Classify a single text utterance into an intent.\n\n"
        "Args:\n"
        "    text: Raw user utterance (UTF-8 string)\n\n"
        "Returns:\n"
        "    IntentResult with intent, destination, confidence, language");

    m.def("dispatch_tool", &virtus_ai::dispatch_tool,
        py::arg("intent"), py::arg("raw_text"),
        "Map a classified intent to a tool invocation.\n\n"
        "Args:\n"
        "    intent: Result from classify_intent()\n"
        "    raw_text: Original user text\n\n"
        "Returns:\n"
        "    ToolDispatchResult with tool_name, args_json, requires_llm");

    m.def("format_response", &virtus_ai::format_response,
        py::arg("tool_name"), py::arg("tool_result_json"),
        py::arg("language") = "en",
        "Format a response from tool output using language-specific templates.\n\n"
        "Args:\n"
        "    tool_name: The tool that produced the result\n"
        "    tool_result_json: JSON string with tool output fields\n"
        "    language: Target language code (default 'en')\n\n"
        "Returns:\n"
        "    FormattedResponse with text, language, used_template");

    m.def("detect_language", &virtus_ai::detect_language,
        py::arg("text"),
        "Detect the primary language of a text string.\n\n"
        "Args:\n"
        "    text: UTF-8 encoded text\n\n"
        "Returns:\n"
        "    ISO 639-1 language code ('en', 'ml', 'hi', 'ta')");

    m.def("classify_batch", &virtus_ai::classify_batch,
        py::arg("texts"),
        "Classify multiple utterances in a single call (batch mode).\n\n"
        "Args:\n"
        "    texts: List of raw user utterances\n\n"
        "Returns:\n"
        "    List of IntentResult, one per input text");
}
