// SPDX-License-Identifier: MIT OR Apache-2.0
#pragma once
#include <string>
#include <string_view>
#include "fcst/contract_types.hpp"
namespace fcst {
// Bounded JSON input, safe diagnostic output. No Python or solver dependency.
std::string inspect_contract(std::string_view kind, std::string_view input);
int run_worker(const std::string& root, const std::string& job_id);
}
