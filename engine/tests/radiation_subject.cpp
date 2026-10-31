// SPDX-License-Identifier: MIT OR Apache-2.0
#include "radiation_fixtures.hpp"
#include "fcst/build_info.hpp"
#include <chrono>
#include <iomanip>
#include <iostream>
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <psapi.h>
using namespace fcst::radiation;
using namespace radiation_fixtures;
int main(int argc,char** argv) {
  try {
    if(argc!=5) return 2;
    std::string geometry=argv[1];auto seed=std::stoull(argv[2]),samples=std::stoull(argv[3]),size=std::stoull(argv[4]);
    auto start=std::chrono::steady_clock::now();
    Mesh mesh(geometry=="spheres"?spheres(static_cast<unsigned>(size)):geometry=="cube"?cube():geometry=="plates"?plates(static_cast<std::size_t>(size)):throw std::runtime_error("geometry"));
    auto built=std::chrono::steady_clock::now();
    // Zero selects the frozen scaling refinements on one immutable BVH.
    const std::vector<std::uint64_t> counts=samples?std::vector<std::uint64_t>{samples}:std::vector<std::uint64_t>{4096,16384,65536};
    for(auto count:counts) {
    auto tracing=std::chrono::steady_clock::now();
    std::cout<<std::setprecision(17)<<"{\"candidate\":\""<<FCST_SOURCE_REVISION<<"\",\"geometry\":\""<<geometry<<"\",\"seed\":"<<seed<<",\"samples\":"<<count
      <<",\"facets\":"<<mesh.facets().size()<<",\"storage_bytes\":"<<mesh.storage_bytes()<<",\"build_seconds\":"<<std::chrono::duration<double>(built-start).count()<<",\"rows\":[";
    for(std::size_t i=0;i<mesh.patches().size();++i) {
      auto r=trace_row(mesh,i,{seed,count,1000});if(i)std::cout<<',';
      std::cout<<"{\"id\":\""<<mesh.patches()[i].id<<"\",\"area\":"<<mesh.patches()[i].area<<",\"escaped\":"<<r.escaped<<",\"blocked\":"<<r.blocked<<",\"counts\":[";
      bool first=true;for(const auto& c:r.counts) { if(!first)std::cout<<',';first=false;std::cout<<"{\"target\":\""<<mesh.patches()[c.target].id<<"\",\"hits\":"<<c.hits<<'}'; }
      std::cout<<"]}";
    }
    PROCESS_MEMORY_COUNTERS memory{};
    if(!GetProcessMemoryInfo(GetCurrentProcess(),&memory,sizeof(memory))) return 1;
    auto ended=std::chrono::steady_clock::now();std::cout<<"],\"trace_seconds\":"<<std::chrono::duration<double>(ended-tracing).count()<<",\"peak_working_set_bytes\":"<<memory.PeakWorkingSetSize<<"}\n";
    }
    return 0;
  } catch(...) { std::cerr<<"radiation_subject_failed\n";return 1; }
}
