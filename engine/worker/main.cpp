// SPDX-License-Identifier: MIT OR Apache-2.0
#include "fcst/build_info.hpp"
#include "fcst/diagnostic.hpp"
#include <iostream>
#include <string_view>
int main(int argc, char* argv[]) {
  if (argc == 2 && std::string_view(argv[1]) == "--build-info") {
    std::cout << "{\"engine\":\"fcst_native\",\"version\":\"" << FCST_VERSION
              << "\",\"compiler\":\"" << FCST_COMPILER
              << "\",\"compiler_version\":\"" << FCST_COMPILER_VERSION
              << "\",\"source_revision\":\"" << FCST_SOURCE_REVISION
              << "\",\"cxx_standard\":20,\"solver_available\":false,\"protocol_version\":1}\n";
    return 0;
  }
  if (argc == 2 && std::string_view(argv[1]) == "--self-test") {
    return fcst::code_name(fcst::DiagnosticCode::invalid_argument) == "invalid_argument" ? 0 : 1;
  }
  // Never echo untrusted arguments or claim an unimplemented solve succeeded.
  std::cerr << "{\"code\":\"not_implemented\",\"message\":\"WP-02 worker skeleton; solving is not implemented\"}\n";
  return 2;
}
