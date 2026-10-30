// SPDX-License-Identifier: MIT OR Apache-2.0
#include "fcst/thermal_transient.hpp"
#include "fcst/build_info.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <locale>
#include <set>
#include <sstream>

namespace fcst::thermal {
namespace {
using Clock=std::chrono::steady_clock;
struct Failure { std::string reason, entity; };
double finite(double v) { if (!std::isfinite(v)) throw Error("range"); return v; }
bool digest(const std::string& s) { return s.size()==64 && s.find_first_not_of("0123456789abcdef")==std::string::npos; }
double seconds(Clock::time_point t) { return std::chrono::duration<double>(Clock::now()-t).count(); }
void values(std::span<const double> v,std::size_t size) {
  if (v.size()!=size) throw Error("dimension"); for (double x:v) (void)finite(x);
}
EnergyBudget empty_budget(std::size_t n) {
  EnergyBudget b; for (auto* v:{&b.storage_change,&b.external_energy,&b.conductive_energy,&b.boundary_energy}) v->assign(n,0); return b;
}
void add(EnergyBudget& a,const EnergyBudget& b) {
  for (auto pair:{std::pair{&a.storage_change,&b.storage_change},std::pair{&a.external_energy,&b.external_energy},
                 std::pair{&a.conductive_energy,&b.conductive_energy},std::pair{&a.boundary_energy,&b.boundary_energy}})
    for (std::size_t i=0;i<pair.first->size();++i) (*pair.first)[i]=finite((*pair.first)[i]+(*pair.second)[i]);
  a.absolute_exchange=finite(a.absolute_exchange+b.absolute_exchange);
  long double defect=0; for (std::size_t i=0;i<a.storage_change.size();++i) defect+=a.storage_change[i]-static_cast<long double>(a.external_energy[i]);
  a.defect=finite(static_cast<double>(defect));
}
void budget_values(const EnergyBudget& b,std::size_t n) {
  for (auto* v:{&b.storage_change,&b.external_energy,&b.conductive_energy,&b.boundary_energy}) values(*v,n);
  (void)finite(b.defect); if (finite(b.absolute_exchange)<0) throw Error("checkpoint");
}
void write_state(std::ostream& s,const OperatingState& v) {
  for (const auto& [id,on]:v.heaters) s<<id<<':'<<on<<';'; s<<'|';
  for (const auto& [id,f]:v.load_factors) s<<id<<':'<<f<<';'; s<<'|';
}
void write_vector(std::ostream& s,std::span<const double> v) { s<<v.size()<<':'; for (double x:v) s<<x<<';'; }
std::ostringstream stream() { std::ostringstream s; s.imbue(std::locale::classic()); s<<std::hexfloat; return s; }
std::string checksum(const TransientCheckpoint& c) {
  auto s=stream(); s<<"FCST-transient-checkpoint-1:"<<c.version<<':'<<c.configuration_id<<':'<<c.time<<':'<<c.origin<<':'<<c.next_step;
  write_vector(s,c.temperature); write_vector(s,c.initial_temperature); write_state(s,c.operating);
  for (const auto& [id,v]:c.last_switch) s<<id<<':'<<v<<';'; s<<'|';
  for (const auto& [id,v]:c.on_seconds) s<<id<<':'<<v<<';';
  for (auto* v:{&c.run_energy.storage_change,&c.run_energy.external_energy,&c.run_energy.conductive_energy,&c.run_energy.boundary_energy}) write_vector(s,*v);
  s<<c.run_energy.defect<<':'<<c.run_energy.absolute_exchange<<':'<<c.accepted_steps<<':'<<c.rejected_steps<<':'<<c.event_count;
  return thermal_digest(s.str());
}
std::string configuration(const Assembly& a,const TransientOptions& o) {
  auto s=stream(); s<<"FCST-enthalpy-BE-doubling-1:"<<FCST_SOURCE_REVISION<<':'<<a.model().data().preparation_hash<<':'<<o.start<<':'
    <<o.minimum_step<<':'<<o.maximum_step<<':'<<o.absolute_temperature_tolerance<<':'<<o.relative_temperature_tolerance<<':'
    <<o.absolute_energy_tolerance<<':'<<o.relative_energy_tolerance<<':'<<o.event_time_tolerance<<':'<<o.minimum_event_separation<<':'
    <<o.maximum_newton_iterations<<':'<<o.callback_revision<<':'<<o.linear.maximum_dimension<<':'<<o.linear.maximum_nonzeros<<':'
    <<o.linear.pivot_tolerance<<':'<<o.linear.backward_error_tolerance<<':'<<o.linear.maximum_refinements;
  write_vector(s,o.temperature_tolerances); write_state(s,a.operating_state());
  for (const auto& schedule:o.schedules) { s<<schedule.load_id<<':'; for (const auto& p:schedule.points) s<<p.time<<':'<<p.factor<<';'; }
  return thermal_digest(s.str());
}
class TimedLinear final : public LinearBackend {
 public:
  TimedLinear(SparseLuSettings settings,KernelProfile& p):backend_(settings),profile_(p) {}
  SolveResult solve(const SparseMatrix& a,std::span<const double> rhs,const SolveOptions& o) const override {
    auto t=Clock::now(); ++profile_.linear_solves;
    auto result=backend_.solve(a,rhs,o); profile_.linear_seconds+=seconds(t); return result;
  }
 private: SparseLuBackend backend_; KernelProfile& profile_;
};
struct Engine {
  const TransientOptions& o;
  KernelProfile& profile;
  std::shared_ptr<const LinearBackend> linear;
  Engine(const TransientOptions& options,KernelProfile& p):o(options),profile(p),linear(std::make_shared<TimedLinear>(o.linear,p)) {}
  std::vector<double> nonlinear(const Assembly& a,double t,std::span<const double> previous,double h,bool initialize) {
    const auto n=a.sparsity()->dimension(); std::vector<double> initial(previous.begin(),previous.end());
    NewtonSettings settings; settings.absolute_step_tolerance=1e-10; settings.relative_step_tolerance=1e-12;
    settings.lower_bounds.assign(n,0); settings.upper_bounds.assign(n,std::numeric_limits<double>::infinity());
    for (const auto& node:a.model().data().nodes) if (node.equation && node.material_index) {
      const auto& cp=a.model().data().materials.at(*node.material_index).specific_heat;
      settings.lower_bounds[*node.equation]=cp.minimum_temperature(); settings.upper_bounds[*node.equation]=cp.maximum_temperature();
    }
    auto evaluate=[&,initial](std::span<const double> x,bool jacobian) {
      auto start=Clock::now(); ++profile.residual_evaluations; if(jacobian) ++profile.jacobian_evaluations;
      try {
        auto v=jacobian?(initialize?a.steady_linearize(t,x):a.step_linearize(t,x,initial,h)):
          Linearization{initialize?a.steady_residual(t,x):a.step_residual(t,x,initial,h),SparseMatrix(a.sparsity()),SparseMatrix(a.sparsity())};
        // Fixed differential initial conditions replace their rows, never their capacities.
        if (initialize) for (const auto& node:a.model().data().nodes) if (node.differential_index) {
          auto row=*node.equation; v.balance.residual[row]=x[row]-initial[row];
        }
        profile.assembly_seconds+=seconds(start);
        return v;
      } catch (const Error& e) {
        profile.assembly_seconds+=seconds(start);
        if (e.code=="range") throw EvaluationDomainError(e); throw;
      }
    };
    auto seed=evaluate(initial,true); std::vector<double> limits(n,1e-12); std::set<std::size_t> fixed;
    if (initialize) for (const auto& node:a.model().data().nodes) if (node.differential_index) fixed.insert(*node.equation);
    const auto& p=*a.sparsity();
    for (std::size_t i=0;i<n;++i) {
      if(fixed.contains(i)) { limits[i]=1e-10; continue; }
      for (std::size_t k=p.offsets()[i];k<p.offsets()[i+1];++k)
        limits[i]=std::max(limits[i],finite(std::abs(seed.d_temperature.values()[k])*std::max(1.0,std::abs(initial[p.columns()[k]]))*1e-12));
    }
    NonlinearProblem problem{a.sparsity(),[&](std::span<const double> x,bool jacobian) {
      auto v=evaluate(x,jacobian); SparseMatrix j(a.sparsity());
      for (std::size_t i=0;i<n;++i) {
        v.balance.residual[i]=finite(v.balance.residual[i]/limits[i]);
        if (jacobian) for (std::size_t k=p.offsets()[i];k<p.offsets()[i+1];++k) {
          const auto column=p.columns()[k];
          double entry=fixed.contains(i)?(column==i?1.:0.):v.d_temperature.values()[k];
          j.add({i,column},finite(entry/limits[i]));
        }
      }
      return NonlinearEvaluation{std::move(v.balance.residual),jacobian?std::optional<SparseMatrix>(std::move(j)):std::nullopt};
    }};
    auto result=solve_nonlinear(DampedNewtonBackend(settings,linear),problem,initial,{1,0,o.maximum_newton_iterations});
    profile.newton_iterations+=result.iterations;
    if (result.status!=SolveStatus::converged) {
      std::string entity;
      if(result.diagnostics.failure_index)for(const auto& node:a.model().data().nodes)if(node.equation==result.diagnostics.failure_index)entity=node.id;
      throw Failure{std::string(reason_code(result.diagnostics.reason)),entity};
    }
    if (initialize) for (auto i:fixed) result.solution[i]=initial[i];
    return result.solution;
  }
  std::vector<double> consistent(const Assembly& a,double t,std::span<const double> x) { return nonlinear(a,t,x,0,true); }
  Balance instantaneous(const Assembly& a,double t,std::span<const double> x,std::vector<double>& rate) {
    auto start=Clock::now(); auto b=a.steady_residual(t,x); rate.assign(a.model().data().differential_count,0);
    for (std::size_t i=0;i<a.model().data().nodes.size();++i) {
      const auto& node=a.model().data().nodes[i];
      if (node.differential_index) rate[*node.differential_index]=finite(-b.residual[*node.equation]/a.model().storage_capacity(i,b.temperature[i]));
    }
    auto result=a.residual({t,std::vector<double>(x.begin(),x.end()),rate}); profile.residual_evaluations+=2;
    profile.assembly_seconds+=seconds(start); return result;
  }
  bool triggered(const Assembly& a,const Control& c,double t,std::span<const double> x) {
    auto start=Clock::now(); auto b=a.steady_residual(t,x); ++profile.residual_evaluations; profile.assembly_seconds+=seconds(start);
    return a.operating_state().heaters.at(c.id)?b.temperature[c.sensor]>=c.off_above:b.temperature[c.sensor]<=c.on_below;
  }
  EnergyBudget energy(const Assembly& a,double t,std::span<const double> old,std::span<const double> x,double h) {
    auto start=Clock::now(); auto b=a.step_residual(t,x,old,h); ++profile.residual_evaluations; profile.assembly_seconds+=seconds(start);
    auto result=empty_budget(a.model().data().nodes.size()); long double defect=0;
    for (std::size_t i=0;i<result.storage_change.size();++i) {
      const auto& node=a.model().data().nodes[i];
      result.storage_change[i]=node.equation?a.model().storage_change(i,old[*node.equation],x[*node.equation]):0;
      result.external_energy[i]=finite(h*finite(b.load_in[i]+b.environment_in[i]+b.boundary_power[i]));
      result.conductive_energy[i]=finite(h*b.conductive_in[i]); result.boundary_energy[i]=finite(h*b.boundary_power[i]);
      const double reference=finite(std::abs(result.storage_change[i])+std::abs(result.external_energy[i])+std::abs(result.conductive_energy[i])+std::abs(h*b.radiation_in[i]));
      if (node.equation && std::abs(h*b.residual[*node.equation])>o.absolute_energy_tolerance+o.relative_energy_tolerance*reference)
        throw Failure{"energy_imbalance",node.id};
      result.absolute_exchange=finite(result.absolute_exchange+reference);
      defect+=result.storage_change[i]-static_cast<long double>(result.external_energy[i]);
    }
    for (const auto& term:b.internal_terms) if (std::abs(h*term.net_power)>o.absolute_energy_tolerance+o.relative_energy_tolerance*std::abs(h)*term.absolute_power)
      throw Failure{"energy_imbalance",term.entity_id};
    result.defect=finite(static_cast<double>(defect));
    if (std::abs(result.defect)>o.absolute_energy_tolerance+o.relative_energy_tolerance*result.absolute_exchange ||
        std::abs(h*b.internal_exchange_defect)>o.absolute_energy_tolerance+o.relative_energy_tolerance*result.absolute_exchange) throw Failure{"energy_imbalance",{}};
    return result;
  }
  struct Trial { std::vector<double> mid, end; double error=0; EnergyBudget energy; };
  Trial trial(const Assembly& a,double t,std::span<const double> x,double h) {
    auto full=nonlinear(a,t+h,x,h,false);
    auto mid=nonlinear(a,t+h/2,x,h/2,false); auto end=nonlinear(a,t+h,mid,h/2,false);
    Trial result{std::move(mid),std::move(end),0,{}};
    for (std::size_t i=0;i<x.size();++i) {
      double limit=(o.temperature_tolerances.empty()?o.absolute_temperature_tolerance:o.temperature_tolerances[i])+
        o.relative_temperature_tolerance*std::max(std::abs(x[i]),std::abs(result.end[i]));
      result.error=std::max(result.error,finite(std::abs(result.end[i]-full[i])/limit));
    }
    result.energy=energy(a,t+h/2,x,result.mid,h/2); add(result.energy,energy(a,t+h,result.mid,result.end,h/2));
    return result;
  }
};
void validate(const Assembly& a,const TransientOptions& o) {
  for (double v:{o.start,o.end,o.initial_step,o.minimum_step,o.maximum_step,o.absolute_temperature_tolerance,
      o.relative_temperature_tolerance,o.absolute_energy_tolerance,o.relative_energy_tolerance,o.event_time_tolerance,o.minimum_event_separation}) (void)finite(v);
  if(o.end<=o.start || o.initial_step<=0 || o.minimum_step<=0 || o.maximum_step<o.minimum_step ||
     o.absolute_temperature_tolerance<=0 || o.relative_temperature_tolerance<0 || o.absolute_energy_tolerance<0 || o.relative_energy_tolerance<0 ||
     o.event_time_tolerance<=0 || o.minimum_event_separation<0 || o.maximum_attempts==0 || o.maximum_attempts>1000000 ||
     o.maximum_events==0 || o.maximum_events>100000 || o.maximum_newton_iterations==0 || o.maximum_newton_iterations>1000 ||
     o.maximum_result_values==0 || o.maximum_result_values>10000000 ||
     o.output_times.size()<2 || o.output_times.size()>10000 || o.output_times.front()!=o.start || o.output_times.back()!=o.end) throw Error("range");
  double last=-std::numeric_limits<double>::infinity(); for (double t:o.output_times) { if(finite(t)<=last) throw Error("range"); last=t; }
  if (!o.temperature_tolerances.empty()) { values(o.temperature_tolerances,a.sparsity()->dimension()); for(double v:o.temperature_tolerances) if(v<=0)throw Error("range"); }
  if (a.has_callbacks() && !digest(o.callback_revision)) throw Error("callback_revision");
  if (!o.callback_revision.empty() && !digest(o.callback_revision)) throw Error("callback_revision");
  if (o.schedules.size()>10000) throw Error("limit"); std::string previous;
  for (const auto& s:o.schedules) {
    if (s.load_id<=previous || s.points.empty() || s.points.size()>10000 || s.points.front().time>o.start) throw Error("schedule");
    previous=s.load_id; last=-std::numeric_limits<double>::infinity();
    if (std::none_of(a.model().data().loads.begin(),a.model().data().loads.end(),[&](const auto& l){return l.id==s.load_id && l.active;})) throw Error("reference",s.load_id);
    for (const auto& p:s.points) { if(finite(p.time)<=last || finite(p.factor)<0)throw Error("schedule",s.load_id); last=p.time; }
  }
  for (const auto& c:a.model().data().controls) if(c.on_below>=c.off_above)throw Error("range",c.id);
}
void schedule_at(OperatingState& s,const TransientOptions& o,double t) {
  for (const auto& schedule:o.schedules) for (const auto& point:schedule.points) {
    if(point.time>t)break; s.load_factors[schedule.load_id]=point.factor;
  }
}
double next_schedule(const TransientOptions& o,double t) {
  double result=o.end; for(const auto& s:o.schedules) for(const auto& p:s.points) if(p.time>t) {result=std::min(result,p.time);break;} return result;
}
void checkpoint_check(const Assembly& a,const TransientOptions& o,const TransientCheckpoint& c,const std::string& id) {
  if(c.version!=1 || c.configuration_id!=id || !digest(c.checksum) || checksum(c)!=c.checksum || c.origin!=o.start ||
     finite(c.time)<o.start || c.time>=o.end || finite(c.next_step)<=0 || c.next_step>o.maximum_step ||
     c.accepted_steps>1000000 || c.rejected_steps>1000000 || c.event_count>100000)throw Error("checkpoint");
  values(c.temperature,a.sparsity()->dimension()); values(c.initial_temperature,a.sparsity()->dimension());
  budget_values(c.run_energy,a.model().data().nodes.size()); (void)a.with_operating_state(c.operating);
  if(c.on_seconds.size()!=a.model().data().controls.size())throw Error("checkpoint");
  for(const auto& control:a.model().data().controls) {
    if(!c.on_seconds.contains(control.id) || finite(c.on_seconds.at(control.id))<0 || c.on_seconds.at(control.id)>c.time-c.origin)throw Error("checkpoint");
  }
  for(const auto& [key,t]:c.last_switch) if(!c.operating.heaters.contains(key) || finite(t)>c.time || t<c.origin)throw Error("checkpoint");
  auto expected=c.operating; schedule_at(expected,o,c.time); if(expected!=c.operating)throw Error("checkpoint");
}
} // namespace

BackendCapabilities thermal_backend_capabilities() {
  BackendCapabilities c; c.source_revision=FCST_SOURCE_REVISION; c.compiler=FCST_COMPILER; c.compiler_version=FCST_COMPILER_VERSION; return c;
}
TransientResult solve_transient(const Assembly& base,const TransientOptions& o,std::optional<TransientCheckpoint> restart) {
  validate(base,o); auto started=Clock::now(); TransientResult out; out.backend=thermal_backend_capabilities();
  out.model_hash=base.model().data().model_hash; out.preparation_hash=base.model().data().preparation_hash; out.configuration_id=configuration(base,o);
  if(restart) checkpoint_check(base,o,*restart,out.configuration_id);
  Engine engine(o,out.profile); auto a=base; TransientCheckpoint c; std::size_t stored=0;
  auto reserve_values=[&](std::size_t count) {if(count>o.maximum_result_values-stored)throw Failure{"result_limit",{}};stored+=count;};
  c.configuration_id=out.configuration_id; c.time=o.start; c.origin=o.start; c.next_step=std::min(o.initial_step,o.maximum_step);
  c.temperature=a.initial_temperature(); c.initial_temperature=c.temperature; c.operating=a.operating_state();
  c.run_energy=empty_budget(a.model().data().nodes.size()); for(const auto& control:a.model().data().controls)c.on_seconds.emplace(control.id,0);
  if(restart)c=*restart;
  auto seal=[&] { c.checksum=checksum(c); out.checkpoint=c; };
  auto record_event=[&](const std::string& id,const std::string& kind,double before,double after) {
    if(c.event_count>=o.maximum_events)throw Failure{"event_limit",id};
    reserve_values(4);
    out.events.push_back({c.time,id,kind,before,after}); ++c.event_count;
  };
  auto update_events=[&](bool initial,const std::set<std::string>& located) {
    // Each batch reads one pre-event temperature/state. Schedules precede heaters;
    // immutable assembly replacement followed by algebraic reinitialization.
    auto state=c.operating; schedule_at(state,o,c.time);
    for(const auto& s:o.schedules) {
      double before=c.operating.load_factors.contains(s.load_id)?c.operating.load_factors.at(s.load_id):1;
      double after=state.load_factors.at(s.load_id); if(before!=after)record_event(s.load_id,"schedule",before,after);
    }
    for(unsigned pass=0;pass<32;++pass) {
      auto before=a.with_operating_state(state); auto next=state; bool changed=false;
      for(const auto& control:a.model().data().controls) {
        if(!engine.triggered(before,control,c.time,c.temperature) && !(pass==0 && located.contains(control.id)))continue;
        const bool on=state.heaters.at(control.id);
        if(c.last_switch.contains(control.id) && c.time-c.last_switch.at(control.id)<=o.minimum_event_separation)throw Failure{"chattering",control.id};
        next.heaters[control.id]=!on; c.last_switch[control.id]=c.time; changed=true;
        record_event(control.id,"heater",on?1.:0.,on?0.:1.);
      }
      state=std::move(next); a=a.with_operating_state(state);
      if(changed || pass==0) c.temperature=engine.consistent(a,c.time,c.temperature);
      if(!changed)break;
      if(pass==31)throw Failure{"chattering",{}};
    }
    c.operating=state; if(initial)c.initial_temperature=c.temperature;
  };
  auto sample=[&] {
    reserve_values(a.model().data().nodes.size()*20+c.operating.heaters.size()*4);
    TransientSample s; s.time=c.time; s.balance=engine.instantaneous(a,c.time,c.temperature,s.rate); s.operating=c.operating;
    s.storage_change.resize(a.model().data().nodes.size());
    for(std::size_t i=0;i<s.storage_change.size();++i) {
      const auto& node=a.model().data().nodes[i]; s.storage_change[i]=node.equation?a.model().storage_change(i,c.initial_temperature[*node.equation],c.temperature[*node.equation]):0;
    }
    for(const auto& [id,v]:c.on_seconds)s.duty_cycles[id]=c.time==c.origin?0:v/(c.time-c.origin);
    s.run_energy=c.run_energy; s.valid=true; out.samples.push_back(std::move(s));
  };
  try {
    a=a.with_operating_state(c.operating);
    auto consistent=engine.consistent(a,c.time,c.temperature);
    if(restart) {
      for(std::size_t i=0;i<c.temperature.size();++i)if(std::abs(c.temperature[i]-consistent[i])>1e-8)throw Error("checkpoint");
      for(const auto& control:a.model().data().controls)if(engine.triggered(a,control,c.time,c.temperature))throw Error("checkpoint");
    } else { c.temperature=std::move(consistent); update_events(true,{}); }
    seal(); sample(); std::size_t attempts=0;
    while(c.time<o.end) {
      if(++attempts>o.maximum_attempts)throw Failure{"attempt_limit",{}};
      auto output=std::upper_bound(o.output_times.begin(),o.output_times.end(),c.time);
      double stop=std::min(next_schedule(o,c.time),output==o.output_times.end()?o.end:*output);
      double h=std::min({c.next_step,o.maximum_step,stop-c.time});
      if(h<o.minimum_step || c.time+h==c.time || c.time+h/2==c.time)throw Failure{"step_underflow",{}};
      Engine::Trial trial; std::string failure;
      try { trial=engine.trial(a,c.time,c.temperature,h); }
      catch(const Failure& f) {
        failure=f.reason;
        if(f.reason=="energy_imbalance") {
          reserve_values(4);out.steps.push_back({c.time,c.time+h,0,false,f.reason,{}});throw;
        }
      }
      catch(const EvaluationDomainError&) {failure="domain";}
      if(!failure.empty() || trial.error>1) {
        reserve_values(4);
        out.steps.push_back({c.time,c.time+h,failure.empty()?trial.error:0,false,failure.empty()?"tolerance":failure,{}});
        ++c.rejected_steps; c.next_step=h*(failure.empty()?std::clamp(.8/std::sqrt(trial.error),.1,.5):.25); continue;
      }
      // Locate the first directional crossing in either accepted half. Bisection
      // solves the implicit path again; no interpolated temperatures are accepted.
      std::map<std::string,double> roots;
      for(const auto& control:a.model().data().controls) {
        bool middle=engine.triggered(a,control,c.time+h/2,trial.mid), end=engine.triggered(a,control,c.time+h,trial.end);
        if(!middle && !end)continue;
        double lo=middle?0:h/2,hi=middle?h/2:h;
        for(unsigned probe=0;probe<80 && hi-lo>o.event_time_tolerance;++probe) {
          double mid=lo+(hi-lo)/2; if(c.time+mid==c.time+lo || c.time+mid==c.time+hi)break;
          ++out.profile.event_probes; auto test=engine.trial(a,c.time,c.temperature,mid);
          if(engine.triggered(a,control,c.time+mid,test.end))hi=mid;else lo=mid;
        }
        roots.emplace(control.id,hi);
      }
      std::set<std::string> located;
      if(!roots.empty()) {
        double first=h; for(const auto& [id,t]:roots) { (void)id; first=std::min(first,t); }
        for(const auto& [id,t]:roots) if(t-first<=o.event_time_tolerance)located.insert(id);
        h=first; trial=engine.trial(a,c.time,c.temperature,h);
        if(trial.error>1) {reserve_values(4);out.steps.push_back({c.time,c.time+h,trial.error,false,"event_tolerance",{}});++c.rejected_steps;c.next_step=h/2;continue;}
      }
      reserve_values(4+a.model().data().nodes.size()*4);
      auto committed=c;
      const double old_time=c.time; c.time=old_time+h; if(located.empty() && std::abs(c.time-stop)<=4*std::numeric_limits<double>::epsilon()*std::max(1.,std::abs(stop)))c.time=stop;
      for(const auto& [id,on]:c.operating.heaters)if(on)c.on_seconds[id]=finite(c.on_seconds[id]+h);
      c.temperature=trial.end; add(c.run_energy,trial.energy); ++c.accepted_steps;
      c.next_step=std::clamp(h*(trial.error==0?2:std::clamp(.9/std::sqrt(trial.error),.5,2.)),o.minimum_step,o.maximum_step);
      // Recompute total storage from original enthalpy rather than summing small increments.
      long double defect=0;
      for(std::size_t i=0;i<a.model().data().nodes.size();++i) {
        const auto& node=a.model().data().nodes[i]; c.run_energy.storage_change[i]=node.equation?a.model().storage_change(i,c.initial_temperature[*node.equation],c.temperature[*node.equation]):0;
        defect+=c.run_energy.storage_change[i]-static_cast<long double>(c.run_energy.external_energy[i]);
      }
      c.run_energy.defect=finite(static_cast<double>(defect));
      if(std::abs(c.run_energy.defect)>o.absolute_energy_tolerance+o.relative_energy_tolerance*c.run_energy.absolute_exchange) { c=committed; throw Failure{"run_energy_imbalance",{}}; }
      const auto events_before=out.events.size();
      bool scheduled=false;
      for(const auto& schedule:o.schedules)for(const auto& point:schedule.points)if(point.time==c.time)scheduled=true;
      try { if(scheduled || !located.empty())update_events(false,located); }
      catch(...) {c=committed;out.events.resize(events_before);throw;}
      out.steps.push_back({old_time,c.time,trial.error,true,"accepted",trial.energy}); seal();
      if(std::binary_search(o.output_times.begin(),o.output_times.end(),c.time) || out.events.size()!=events_before)sample();
    }
    out.valid=true; out.reason="completed";
  } catch(const Failure& f) {out.reason=f.reason;out.entity_id=f.entity;}
    catch(const Error& e) {out.reason=e.code;out.entity_id=e.entity_id;out.source_map_id=e.source_map_id;}
  if(!out.entity_id.empty() && out.source_map_id.empty() && base.model().data().sources_by_entity.contains(out.entity_id))
    out.source_map_id=base.model().data().source_identities.at(base.model().data().sources_by_entity.at(out.entity_id).front()).source_map_id;
  if(!out.checkpoint)out.events.clear();
  out.profile.total_seconds=seconds(started); return out;
}
} // namespace fcst::thermal
