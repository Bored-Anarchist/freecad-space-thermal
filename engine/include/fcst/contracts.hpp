// SPDX-License-Identifier: MIT OR Apache-2.0
#pragma once
#include <string>
#include <string_view>
#include "fcst/contract_types.hpp"
namespace fcst {
// Bounded JSON input, safe diagnostic output. No Python or solver dependency.
std::string inspect_contract(std::string_view kind, std::string_view input);
}
