// SPDX-License-Identifier: MIT OR Apache-2.0
#include "fcst/diagnostic.hpp"
namespace fcst {
std::string_view code_name(DiagnosticCode code) noexcept {
  switch (code) {
    case DiagnosticCode::ok: return "ok";
    case DiagnosticCode::invalid_argument: return "invalid_argument";
    case DiagnosticCode::not_implemented: return "not_implemented";
  }
  return "invalid_argument";
}
}
