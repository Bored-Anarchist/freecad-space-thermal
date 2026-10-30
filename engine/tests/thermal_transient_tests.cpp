// SPDX-License-Identifier: MIT OR Apache-2.0
#include "fcst/thermal_transient.hpp"
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
using namespace fcst::thermal;
namespace {
void require(bool ok) {if(!ok)throw std::runtime_error("acceptance_failed");}
void near(double a,double b,double atol=1e-7) {require(std::isfinite(a) && std::abs(a-b)<=atol);}
std::string uid(unsigned n) {auto v=std::to_string(n);return "00000000-0000-4000-8000-"+std::string(12-v.size(),'0')+v;}
Model fixture(const std::filesystem::path& root,const std::string& name) {
  std::ifstream file(root/("transient-"+name+".json"),std::ios::binary);require(file.good());
  return load(std::string(std::istreambuf_iterator<char>(file),std::istreambuf_iterator<char>()));
}
Assembly assembly(const std::filesystem::path& root,const std::string& name) {
  auto m=fixture(root,name);auto state=initial_operating_state(m);std::vector<PowerBinding> powers;
  for(const auto& id:m.data().active_environment_ids)powers.push_back({id,PowerKind::environment,{}, {},[](double,std::span<const double>,bool){return PowerEvaluation{};}});
  return Assembly(std::move(m),powers,{},state);
}
TransientOptions options(double end=4) {
  TransientOptions o;o.end=end;o.output_times={0,end/2,end};o.initial_step=.5;o.maximum_step=.5;
  o.absolute_temperature_tolerance=1e-7;o.relative_temperature_tolerance=0;o.callback_revision=std::string(64,'a');return o;
}
void success(const TransientResult& r) {
  if(!r.valid)throw std::runtime_error("unexpected_"+r.reason);
  require(r.reason=="completed" && r.checkpoint && !r.samples.empty());
  for(const auto& sample:r.samples) {require(sample.valid);near(sample.run_energy.defect,0,1e-6);for(double v:sample.balance.residual)near(v,0,1e-6);}
  for(const auto& step:r.steps)if(step.accepted){require(step.error_norm<=1);near(step.energy.defect,0,1e-6);}
}
template<class F>void rejects(F f,const std::string& code) {try{f();}catch(const Error& e){require(e.code==code);return;}throw std::runtime_error("expected_rejection");}
double analytic(double t) {return 300+10*std::exp(-t/2);}
}
int main(int argc,char** argv) {
 try {
  require(argc==3);std::string name=argv[1];std::filesystem::path root(argv[2]);
  if(name=="analytic") {
    auto r=solve_transient(assembly(root,"single"),options());success(r);
    for(const auto& s:r.samples)near(s.balance.temperature[0],analytic(s.time),.002);
    require(r.checkpoint->accepted_steps>100 && r.checkpoint->rejected_steps>0);
    near(r.samples.back().storage_change[0],2*(analytic(4)-310),.004);
  } else if(name=="two-node") {
    auto r=solve_transient(assembly(root,"two"),options(2));success(r);
    for(const auto& s:r.samples) {
      near(s.balance.temperature[0],298+12*std::exp(-10*s.time/3),.002);
      near(s.balance.temperature[1],298-8*std::exp(-10*s.time/3),.002);
      near(2*s.balance.temperature[0]+3*s.balance.temperature[1],1490,1e-7);
    }
  } else if(name=="stiff") {
    auto o=options(1);o.absolute_temperature_tolerance=1e-5;
    auto r=solve_transient(assembly(root,"stiff"),o);success(r);
    // After the 10 ns fast mode, the conserved initial mixed temperature is
    // 300.00099990001 K; the slow mode decays with tau=1.0001 s.
    near(r.samples.back().balance.temperature[1],290+(10.001/1.0001)*std::exp(-1/1.0001),.01);
    require(r.checkpoint->rejected_steps>0 && r.checkpoint->accepted_steps<5000);
  } else if(name=="initialization") {
    auto r=solve_transient(assembly(root,"dae"),options());success(r);
    near(r.samples.front().balance.temperature[0],310);near(r.samples.front().balance.temperature[1],305);
    for(const auto& s:r.samples) {near(s.balance.temperature[0],analytic(s.time),.002);near(s.balance.temperature[1],(s.balance.temperature[0]+300)/2);near(s.balance.storage_power[1],0);require(s.rate.size()==1);}
  } else if(name=="enthalpy") {
    auto r=solve_transient(assembly(root,"enthalpy"),options(10));success(r);
    near(r.samples.back().balance.temperature[0],std::sqrt(95000.),1e-7);
    near(r.samples.back().storage_change[0],50,1e-7);near(r.samples.back().run_energy.external_energy[0],50,1e-7);
  } else if(name=="independent-reference") {
    auto m=fixture(root,"enthalpy");
    auto power=[](double t,double temperature) {return 5+std::sin(t)-1e-8*(std::pow(temperature,4)-std::pow(300.,4));};
    PowerBinding p{uid(12),PowerKind::load,{0},{{0,0}},[power](double t,std::span<const double> temperature,bool jacobian) {
      return PowerEvaluation{{power(t,temperature[0])},jacobian?std::vector<double>{-4e-8*std::pow(temperature[0],3)}:std::vector<double>{}};
    }};
    auto r=solve_transient(Assembly(m,{p}),options(2));success(r);
    // Independent explicit RK4 solves dT/dt=Q/(.02*T), without owned assembly,
    // sparse solve, property integral, residual or implicit step code.
    auto reference=[&](unsigned count) {
      double temperature=300,h=2./count;
      auto f=[&](double t,double value){return power(t,value)/(.02*value);};
      for(unsigned i=0;i<count;++i) {
        double t=i*h,k1=f(t,temperature),k2=f(t+h/2,temperature+h*k1/2),k3=f(t+h/2,temperature+h*k2/2),k4=f(t+h,temperature+h*k3);
        temperature+=h*(k1+2*k2+2*k3+k4)/6;
      }
      return temperature;
    };
    double coarse=reference(2000),fine=reference(4000);near(coarse,fine,1e-9);near(r.samples.back().balance.temperature[0],fine,.002);
  } else if(name=="refinement") {
    auto a=assembly(root,"single");auto o=options();o.absolute_temperature_tolerance=.001;
    auto coarse=solve_transient(a,o);success(coarse);o.absolute_temperature_tolerance=1e-7;
    auto fine=solve_transient(a,o);success(fine);
    double first=std::abs(coarse.samples.back().balance.temperature[0]-analytic(4));double second=std::abs(fine.samples.back().balance.temperature[0]-analytic(4));
    require(first>0 && second<first/20 && fine.checkpoint->accepted_steps>coarse.checkpoint->accepted_steps*10);
  } else if(name=="rejection") {
    auto r=solve_transient(assembly(root,"single"),options());success(r);std::size_t rejected=0;
    for(const auto& s:r.steps)if(!s.accepted) {++rejected;require(s.energy.storage_change.empty() && s.reason=="tolerance");}
    require(rejected==r.checkpoint->rejected_steps);near(r.samples.back().run_energy.storage_change[0],r.samples.back().storage_change[0]);
  } else if(name=="sampling") {
    auto o=options();o.output_times={0,.001,.011,.33,1.123,4};auto r=solve_transient(assembly(root,"single"),o);success(r);
    require(r.samples.size()==o.output_times.size());for(std::size_t i=0;i<o.output_times.size();++i)near(r.samples[i].time,o.output_times[i],0);
    for(const auto& step:r.steps)if(step.accepted)for(double t:o.output_times)require(!(step.start<t && step.end>t));
  } else if(name=="heater") {
    auto o=options(5);auto r=solve_transient(assembly(root,"heater"),o);success(r);
    require(r.events.size()>=5 && r.events[0].entity_id==uid(24));near(r.events[0].time,0,0);
    near(r.events[1].time,std::log(16./5),.002);near(r.events[2].time,std::log(16./5)+std::log(3.),.003);
    require(r.profile.event_probes>0);for(const auto& s:r.samples)require(s.balance.temperature[0]>=294 && s.balance.temperature[0]<=305.001);
    double on=0,last=0;bool enabled=false;for(const auto& e:r.events) {if(enabled)on+=e.time-last;last=e.time;enabled=e.after==1;}if(enabled)on+=5-last;
    near(r.samples.back().duty_cycles.at(uid(24)),on/5,1e-10);
  } else if(name=="schedule") {
    auto o=options(4);o.schedules={{uid(12),{{0,0},{1,1},{2,0}}}};auto r=solve_transient(assembly(root,"enthalpy"),o);success(r);
    require(r.events.size()==3);near(r.events[1].time,1,0);near(r.events[2].time,2,0);
    near(r.samples.back().storage_change[0],5,1e-7);near(r.samples.back().balance.temperature[0],std::sqrt(90500.),1e-7);
    auto switched=options(2);switched.absolute_temperature_tolerance=1e-5;
    switched.schedules={{uid(26),{{0,0},{1,1}}}};
    auto post=solve_transient(assembly(root,"schedule-sensor"),switched);success(post);
    auto event=std::find_if(post.events.begin(),post.events.end(),[&](const auto& e){return e.kind=="heater" && e.after==0;});
    require(event!=post.events.end());near(event->time,1,0);require(!post.checkpoint->operating.heaters.at(uid(24)));
  } else if(name=="simultaneous") {
    auto o=options(2);o.schedules={{uid(27),{{0,1},{1,2}}}};auto r=solve_transient(assembly(root,"simultaneous"),o);success(r);
    require(r.events.size()==5);near(r.events[2].time,1,o.event_time_tolerance);
    require(r.events[2].kind=="schedule" && r.events[3].entity_id==uid(24) && r.events[4].entity_id==uid(25));
    near(r.samples.back().balance.temperature[0],296,1e-6);
  } else if(name=="checkpoint") {
    auto a=assembly(root,"heater");auto o=options(5);o.output_times={0,2.5,5};auto full=solve_transient(a,o);success(full);
    auto first_o=o;first_o.end=2.5;first_o.output_times={0,2.5};auto first=solve_transient(a,first_o);success(first);
    auto resumed=solve_transient(a,o,first.checkpoint);success(resumed);
    near(resumed.samples.back().balance.temperature[0],full.samples.back().balance.temperature[0],1e-10);
    near(resumed.samples.back().duty_cycles.at(uid(24)),full.samples.back().duty_cycles.at(uid(24)),1e-12);
    require(resumed.checkpoint->checksum==full.checkpoint->checksum);
    auto bad=*first.checkpoint;bad.temperature[0]+=.001;rejects([&]{solve_transient(a,o,bad);},"checkpoint");
    o.relative_temperature_tolerance=.001;rejects([&]{solve_transient(a,o,first.checkpoint);},"checkpoint");
  } else if(name=="chattering") {
    auto r=solve_transient(assembly(root,"chattering"),options());require(!r.valid && r.reason=="chattering" && !r.checkpoint);
  } else if(name=="energy") {
    auto m=fixture(root,"single");std::vector<PowerBinding> none;
    auto good=solve_transient(Assembly(m,none,{{1,[](double t){return 300+t;}}}),options());success(good);
    require(good.samples.back().balance.boundary_power[1]!=0);
    // A conservative step can still fail an independently tightened energy budget.
    auto o=options();o.absolute_energy_tolerance=0;o.relative_energy_tolerance=0;
    auto r=solve_transient(assembly(root,"single"),o);require(!r.valid && (r.reason=="energy_imbalance" || r.reason=="run_energy_imbalance"));
    std::ifstream input(root/"power-network.json",std::ios::binary);auto network=load(std::string(std::istreambuf_iterator<char>(input),{}));
    std::vector<PowerBinding> bindings{
      {uid(22),PowerKind::radiation,{0,1},{},[](double,std::span<const double>,bool){return PowerEvaluation{{1,1},{}};}},
      {uid(14),PowerKind::environment,{0,1,2},{},[](double,std::span<const double>,bool){return PowerEvaluation{{0,0,0},{}};}}};
    auto bad=solve_transient(Assembly(network,bindings),options());require(!bad.valid && bad.reason=="energy_imbalance" && bad.entity_id==uid(22));
  } else if(name=="results") {
    auto a=assembly(root,"dae");auto r=solve_transient(a,options());success(r);
    require(r.model_hash==a.model().data().model_hash && r.preparation_hash==a.model().data().preparation_hash && r.configuration_id.size()==64);
    for(const auto& s:r.samples) {require(s.balance.conductor_power.size()==2);near(s.balance.boundary_power[2],s.balance.conductor_power[1]*-1);near(s.balance.storage_power[0],s.rate[0]*2);near(s.balance.energy_defect,0,1e-8);}
  } else if(name=="profiling") {
    auto r=solve_transient(assembly(root,"single"),options());success(r);const auto& p=r.profile;
    require(p.residual_evaluations>0 && p.jacobian_evaluations>0 && p.linear_solves>0 && p.newton_iterations>0);
    require(p.assembly_seconds>0 && p.linear_seconds>0 && p.total_seconds>=p.linear_seconds+p.assembly_seconds);
    const auto& c=r.backend;require(c.execution_mode=="fcst_native" && !c.external_reference && !c.durable_job_solver && c.index_one_dae && c.stiff && c.checkpoint && !c.compiler.empty());
  } else if(name=="limits") {
    auto a=assembly(root,"single");auto o=options();o.maximum_attempts=1;auto r=solve_transient(a,o);require(!r.valid && r.reason=="attempt_limit" && r.checkpoint);
    o=options();o.minimum_step=.1;r=solve_transient(a,o);require(!r.valid && r.reason=="step_underflow");
    o=options();o.maximum_result_values=1;r=solve_transient(a,o);require(!r.valid && r.reason=="result_limit");
    o=options(.0001);o.output_times={0,.0001};o.initial_step=.0001;o.absolute_temperature_tolerance=1;o.maximum_result_values=100;
    r=solve_transient(assembly(root,"parallel"),o);require(!r.valid && r.reason=="result_limit");
    o=options();o.output_times={0,1,1,4};rejects([&]{solve_transient(a,o);},"range");
    o=options();o.schedules={{uid(12),{{0,1}}}};rejects([&]{solve_transient(a,o);},"reference");
    o=options();o.callback_revision.clear();rejects([&]{solve_transient(assembly(root,"heater"),o);},"callback_revision");
  } else if(name=="failures") {
    // An isolated algebraic equation remains singular even with zero residual.
    std::ifstream f(root/"algebraic-network.json",std::ios::binary);auto m=load(std::string(std::istreambuf_iterator<char>(f),{}));
    auto r=solve_transient(Assembly(m),options());require(!r.valid && r.reason=="singular_pivot" && !r.checkpoint);
    auto o=options();o.linear.maximum_nonzeros=1;r=solve_transient(assembly(root,"dae"),o);require(!r.valid && r.reason=="fill_limit");
  } else throw std::runtime_error("unknown_case");
  std::cout<<"{\"status\":\"passed\"}\n";return 0;
 } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
