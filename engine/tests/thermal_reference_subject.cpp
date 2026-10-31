// SPDX-License-Identifier: MIT OR Apache-2.0
// Native subject adapter only. The external reference programs never link this.
#include "fcst/thermal_transient.hpp"
#include "fcst/build_info.hpp"
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <numeric>

using namespace fcst::thermal;
namespace {
std::string uid(unsigned n) {auto s=std::to_string(n);return "00000000-0000-4000-8000-"+std::string(12-s.size(),'0')+s;}
void array(std::span<const double> v) {std::cout<<'[';for(std::size_t i=0;i<v.size();++i){if(i)std::cout<<',';std::cout<<v[i];}std::cout<<']';}
double sum(const std::vector<double>& v) {return std::accumulate(v.begin(),v.end(),0.);}
}
int main(int argc,char** argv) {
 try {
  if(argc!=3)throw Error("arguments");std::string name=argv[1],file;
  if(name=="cooling")file="single";else if(name=="closed")file="two";else if(name=="dae")file="dae";
  else if(name=="enthalpy" || name=="schedule")file="enthalpy";else if(name=="stiff")file="stiff";
  else if(name=="heater")file="heater";else if(name=="nonlinear")file="nonlinear";else throw Error("case");
  auto path=std::filesystem::path(argv[2])/(file=="nonlinear"?"power-network.json":"transient-"+file+".json");
  std::ifstream stream(path,std::ios::binary);if(!stream)throw Error("fixture");
  auto model=load(std::string(std::istreambuf_iterator<char>(stream),{}));auto operating=initial_operating_state(model);
  std::vector<PowerBinding> bindings;
  if(name=="nonlinear") {
    const double exchange=1e-8*(std::pow(320.,4)-std::pow(310.,4));
    bindings.push_back({uid(12),PowerKind::load,{0},{},[exchange](double,std::span<const double>,bool){return PowerEvaluation{{27+exchange},{}};}});
    bindings.push_back({uid(22),PowerKind::radiation,{0,1},{{0,0},{0,1},{1,0},{1,1}},[](double,std::span<const double> t,bool j){
      double q=-1e-8*(std::pow(t[0],4)-std::pow(t[1],4));
      return PowerEvaluation{{q,-q},j?std::vector<double>{-4e-8*std::pow(t[0],3),4e-8*std::pow(t[1],3),4e-8*std::pow(t[0],3),-4e-8*std::pow(t[1],3)}:std::vector<double>{}};
    }});
    bindings.push_back({uid(14),PowerKind::environment,{0,1,2},{{0,0},{1,1},{2,2}},[exchange](double,std::span<const double> t,bool j){
      return PowerEvaluation{{-.1*(t[0]-250),-exchange/60*(t[1]-250),-.1*(t[2]-250)},j?std::vector<double>{-.1,-exchange/60,-.1}:std::vector<double>{}};
    }});
  } else for(const auto& id:model.data().active_environment_ids)
    bindings.push_back({id,PowerKind::environment,{}, {},[](double,std::span<const double>,bool){return PowerEvaluation{};}});
  Assembly a(std::move(model),bindings,{},operating);TransientOptions o;
  o.absolute_temperature_tolerance=name=="stiff"?1e-5:name=="heater"?5e-8:1e-7;o.relative_temperature_tolerance=0;
  o.initial_step=.01;o.maximum_step=.1;o.callback_revision=std::string(64,'a');
  if(name=="closed")o.output_times={0,.1,.5,1,2};
  else if(name=="stiff")o.output_times={0,1e-6,1e-4,.01,.1,.5,1};
  else if(name=="enthalpy")o.output_times={0,.5,1,2,5,10};
  else if(name=="heater" || name=="nonlinear")o.output_times={0,.5,1,2,3,4,5};
  else if(name=="schedule") {o.output_times={0,.5,1,1.5,2,3,4};o.schedules={{uid(12),{{0,0},{1,1},{2,0}}}};}
  else o.output_times={0,.5,1,2,4};o.end=o.output_times.back();
  auto result=solve_transient(a,o);if(!result.valid)throw Error(result.reason);
  std::cout<<std::setprecision(17)<<"{\"status\":\"passed\",\"execution_mode\":\"fcst_native\",\"case\":\""<<name
    <<"\",\"source_revision\":\""<<FCST_SOURCE_REVISION<<"\",\"preparation_hash\":\""<<a.model().data().preparation_hash
    <<"\",\"temperature_atol_K\":"<<o.absolute_temperature_tolerance<<",\"requested_times\":";array(o.output_times);
  std::cout<<",\"samples\":[";bool first=true;
  for(const auto& s:result.samples) {
    if(!first)std::cout<<',';first=false;std::cout<<"{\"time\":"<<s.time<<",\"temperature\":";array(s.balance.temperature);
    std::cout<<",\"links\":";array(s.balance.conductor_power);
    std::cout<<",\"boundary_power\":"<<sum(s.balance.boundary_power)<<",\"storage_change\":"<<sum(s.storage_change)
      <<",\"external_energy\":"<<sum(s.run_energy.external_energy)<<",\"boundary_energy\":"<<sum(s.run_energy.boundary_energy)
      <<",\"energy_defect\":"<<s.run_energy.defect<<",\"duty\":"<<(s.duty_cycles.empty()?0:s.duty_cycles.begin()->second)<<'}';
  }
  std::cout<<"],\"events\":[";first=true;
  for(const auto& e:result.events) {if(!first)std::cout<<',';first=false;std::cout<<"{\"time\":"<<e.time<<",\"kind\":\""<<e.kind
    <<"\",\"entity_id\":\""<<e.entity_id<<"\",\"before\":"<<e.before<<",\"after\":"<<e.after<<'}';}
  std::cout<<"],\"steady\":";
  if(name=="cooling" || name=="dae" || name=="stiff" || name=="nonlinear") {
    SteadyOptions so;so.absolute_power_tolerance=1e-8;so.absolute_energy_tolerance=1e-8;
    auto steady=solve_steady(a,0,so);if(steady.solve.status!=SolveStatus::converged || !steady.balance)throw Error("steady");
    std::cout<<"{\"temperature\":";array(steady.balance->temperature);std::cout<<",\"boundary_power\":"<<sum(steady.balance->boundary_power)<<'}';
  } else std::cout<<"null";
  std::cout<<"}\n";return 0;
 }catch(const Error& e) {std::cerr<<e.code<<'\n';return 1;}
 catch(...) {std::cerr<<"{\"status\":\"failed\",\"reason\":\"native_subject_failure\"}\n";return 1;}
}
