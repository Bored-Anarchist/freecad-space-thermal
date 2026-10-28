cmake_minimum_required(VERSION 3.22)
project(FCSTNumericalCheckpoint LANGUAGES CXX)
find_package(SUNDIALS 7.3.0 EXACT REQUIRED COMPONENTS cvode nvecserial sunmatrixdense sunmatrixband sunlinsoldense sunlinsolband)
add_executable(fcst-numerical main.cpp)
target_compile_features(fcst-numerical PRIVATE cxx_std_20)
target_link_libraries(fcst-numerical PRIVATE SUNDIALS::cvode SUNDIALS::nvecserial
  SUNDIALS::sunmatrixdense SUNDIALS::sunmatrixband SUNDIALS::sunlinsoldense SUNDIALS::sunlinsolband psapi)
target_compile_definitions(fcst-numerical PRIVATE NOMINMAX FCST_COMPILER_VERSION="${CMAKE_CXX_COMPILER_VERSION}"
  FCST_CMAKE_VERSION="${CMAKE_VERSION}")
target_compile_options(fcst-numerical PRIVATE /W4 /WX /permissive- /fp:strict /experimental:deterministic
  "/pathmap:${CMAKE_SOURCE_DIR}=prototype" "/pathmap:${CMAKE_BINARY_DIR}=build")
install(TARGETS fcst-numerical RUNTIME DESTINATION bin)
# A copied installation must resolve every numerical DLL without a toolchain PATH.
install(FILES $<TARGET_RUNTIME_DLLS:fcst-numerical> DESTINATION bin)
