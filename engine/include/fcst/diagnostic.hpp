// SPDX-License-Identifier: MIT OR Apache-2.0
#pragma once
#include <string_view>
namespace fcst {
enum class DiagnosticCode { ok, invalid_argument, not_implemented };
struct Diagnostic {
  DiagnosticCode code;
  std::string_view message;
};
[[nodiscard]] std::string_view code_name(DiagnosticCode code) noexcept;
}
