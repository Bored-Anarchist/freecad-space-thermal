# SPDX-License-Identifier: MIT OR Apache-2.0
cmake_minimum_required(VERSION 3.22)
project(FCSTIndependentIDAReference LANGUAGES CXX)
find_package(SUNDIALS 7.3.0 EXACT REQUIRED COMPONENTS ida nvecserial sunmatrixdense sunlinsoldense)
add_executable(fcst-ida-reference ida_reference.cpp)
target_compile_features(fcst-ida-reference PRIVATE cxx_std_20)
target_link_libraries(fcst-ida-reference PRIVATE SUNDIALS::ida SUNDIALS::nvecserial SUNDIALS::sunmatrixdense SUNDIALS::sunlinsoldense)
target_compile_definitions(fcst-ida-reference PRIVATE NOMINMAX)
target_compile_options(fcst-ida-reference PRIVATE /W4 /WX /permissive- /fp:strict /experimental:deterministic
  "/pathmap:${CMAKE_SOURCE_DIR}=reference" "/pathmap:${CMAKE_BINARY_DIR}=build")
install(TARGETS fcst-ida-reference RUNTIME DESTINATION bin)
install(FILES $<TARGET_RUNTIME_DLLS:fcst-ida-reference> DESTINATION bin)
