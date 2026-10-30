// SPDX-License-Identifier: MIT OR Apache-2.0
#include "fcst/thermal_steady.hpp"
#include <algorithm>
#include <cmath>
#include <map>
#include <numeric>
#include <set>
#include <utility>

namespace fcst::thermal {
namespace {
struct Failure {
  SolveStatus status;
  SolveReason reason;
  std::optional<std::size_t> index;
};
double number(double v) {
  if (!std::isfinite(v)) throw Failure{SolveStatus::nonconverged,SolveReason::numerical_range,{}};
  return v == 0 ? 0 : v;
}
void arguments(std::span<const double> v,std::size_t n) {
  if (v.size()!=n) throw Error("dimension");
  for (double x:v) if (!std::isfinite(x)) throw Error("range");
}
void tolerances(double a,double r) {
  if (!std::isfinite(a) || !std::isfinite(r) || a<0 || r<0 || (a==0 && r==0)) throw Error("range");
}
void options(const SolveOptions& o) {
  tolerances(o.absolute_tolerance,o.relative_tolerance);
  if (o.maximum_iterations==0 || o.maximum_iterations>10000) throw Error("range");
}
double norm(std::span<const double> v) {
  double result=0; for (double x:v) result=std::max(result,std::abs(number(x))); return result;
}
bool acceptable(double value,double reference,const SolveOptions& o) {
  return static_cast<long double>(value)<=static_cast<long double>(o.absolute_tolerance)+
    static_cast<long double>(o.relative_tolerance)*reference;
}
struct Factors {
  std::vector<std::map<std::size_t,double>> rows;
  std::vector<double> row_scale,column_scale;
  std::vector<std::size_t> order;
  explicit Factors(const SparseMatrix& matrix,const SparseLuSettings& settings) {
    const auto& p=*matrix.sparsity(); const auto n=p.dimension();
    if (n>settings.maximum_dimension) throw Failure{SolveStatus::unsupported,SolveReason::fill_limit,{}};
    rows.resize(n); row_scale.resize(n); column_scale.assign(n,0); order.resize(n);
    std::iota(order.begin(),order.end(),0);
    std::vector<std::size_t> position=order;
    std::vector<std::set<std::size_t>> members(n);
    std::size_t count=0;
    for (std::size_t i=0;i<n;++i) {
      for (std::size_t k=p.offsets()[i];k<p.offsets()[i+1];++k) row_scale[i]=std::max(row_scale[i],std::abs(matrix.values()[k]));
      if (row_scale[i]==0) throw Failure{SolveStatus::singular,SolveReason::singular_pivot,i};
      for (std::size_t k=p.offsets()[i];k<p.offsets()[i+1];++k) {
        auto j=p.columns()[k]; double v=matrix.values()[k]/row_scale[i];
        if (v==0) continue;
        if (++count>settings.maximum_nonzeros) throw Failure{SolveStatus::unsupported,SolveReason::fill_limit,i};
        rows[i][j]=v; column_scale[j]=std::max(column_scale[j],std::abs(v)); members[j].insert(i);
      }
    }
    for (std::size_t j=0;j<n;++j) if (column_scale[j]==0) throw Failure{SolveStatus::singular,SolveReason::singular_pivot,j};
    for (auto& row:rows) for (auto& [j,v]:row) v/=column_scale[j];
    for (std::size_t k=0;k<n;++k) {
      std::size_t pivot=n; double biggest=0;
      for (auto r:members[k]) if (position[r]>=k) {
        double v=std::abs(rows[r].at(k));
        if (v>biggest || (v==biggest && pivot!=n && position[r]<position[pivot])) { biggest=v; pivot=r; }
      }
      if (pivot==n || biggest<=settings.pivot_tolerance) throw Failure{SolveStatus::singular,SolveReason::singular_pivot,k};
      auto old=order[k], at=position[pivot];
      std::swap(order[k],order[at]); position[pivot]=k; position[old]=at;
      const double diagonal=rows[pivot].at(k);
      for (auto r:members[k]) if (position[r]>k) {
        double factor=number(rows[r].at(k)/diagonal);
        rows[r][k]=factor; // L coefficient, indexed by pivot step; column order never changes.
        for (auto it=rows[pivot].upper_bound(k);it!=rows[pivot].end();++it) {
          const auto j=it->first; auto found=rows[r].find(j);
          double value=number((found==rows[r].end()?0:found->second)-number(factor*it->second));
          if (value==0) {
            if (found!=rows[r].end()) { rows[r].erase(found); members[j].erase(r); --count; }
          } else if (found!=rows[r].end()) found->second=value;
          else {
            if (++count>settings.maximum_nonzeros) throw Failure{SolveStatus::unsupported,SolveReason::fill_limit,k};
            rows[r].emplace(j,value); members[j].insert(r);
          }
        }
      }
      members[k].clear();
    }
  }
  std::vector<double> solve(std::span<const double> rhs) const {
    const auto n=rows.size(); std::vector<double> y(n),z(n),x(n);
    for (std::size_t i=0;i<n;++i) {
      const auto r=order[i]; double value=number(rhs[r]/row_scale[r]);
      for (auto it=rows[r].begin();it!=rows[r].end() && it->first<i;++it) value=number(value-number(it->second*y[it->first]));
      y[i]=value;
    }
    for (std::size_t i=n;i-- >0;) {
      const auto& row=rows[order[i]]; double value=y[i];
      for (auto it=row.upper_bound(i);it!=row.end();++it) value=number(value-number(it->second*z[it->first]));
      z[i]=number(value/row.at(i)); x[i]=number(z[i]/column_scale[i]);
    }
    return x;
  }
};
NonlinearEvaluation evaluation(const NonlinearProblem& p,std::span<const double> x,bool jacobian) {
  if (!p.sparsity || !p.evaluate) throw Error("dimension");
  arguments(x,p.sparsity->dimension());
  NonlinearEvaluation v;
  try { v=p.evaluate(x,jacobian); }
  catch (const Error&) { throw; }
  catch (...) { throw Error("callback_failure"); }
  arguments(v.residual,x.size());
  if (jacobian!=v.jacobian.has_value() || (jacobian && *v.jacobian->sparsity()!=*p.sparsity)) throw Error("backend_result");
  return v;
}
double correction_norm(std::span<const double> delta,std::span<const double> scales,const NewtonSettings& settings) {
  double result=0;
  for (std::size_t i=0;i<delta.size();++i) {
    double limit=number(settings.absolute_step_tolerance+number(settings.relative_step_tolerance*scales[i]));
    if (limit<=0) throw Failure{SolveStatus::nonconverged,SolveReason::numerical_range,i};
    result=std::max(result,std::abs(number(delta[i]/limit)));
  }
  return result;
}
void context(SteadyResult& out,const Assembly& assembly,std::optional<std::size_t> index) {
  const auto& d=assembly.model().data();
  if (index) for (const auto& node:d.nodes) if (node.equation==index) out.entity_id=node.id;
  if (!out.entity_id.empty() && d.sources_by_entity.contains(out.entity_id))
    out.source_map_id=d.source_identities.at(d.sources_by_entity.at(out.entity_id).front()).source_map_id;
}
}

SparseLuBackend::SparseLuBackend(SparseLuSettings s):settings_(s) {
  if (s.maximum_dimension==0 || s.maximum_dimension>1000000 || s.maximum_nonzeros==0 || s.maximum_nonzeros>4000000 ||
      !std::isfinite(s.pivot_tolerance) || s.pivot_tolerance<=0 || s.pivot_tolerance>=1 ||
      !std::isfinite(s.backward_error_tolerance) || s.backward_error_tolerance<=0 || s.maximum_refinements>8) throw Error("range");
}
SolveResult SparseLuBackend::solve(const SparseMatrix& a,std::span<const double> rhs,const SolveOptions& o) const {
  options(o); arguments(rhs,a.sparsity()->dimension());
  SolveResult result{SolveStatus::nonconverged,{},0,{}};
  try {
    Factors factors(a,settings_); auto x=factors.solve(rhs); const auto& p=*a.sparsity();
    const auto attempts=std::min(o.maximum_iterations,settings_.maximum_refinements+1);
    for (std::size_t attempt=0;attempt<attempts;++attempt) {
      result.iterations=attempt+1; auto residual=a.multiply(x); double backward=0;
      for (std::size_t i=0;i<rhs.size();++i) {
        residual[i]=number(residual[i]-rhs[i]); double denominator=std::abs(rhs[i]);
        for (std::size_t k=p.offsets()[i];k<p.offsets()[i+1];++k)
          denominator=number(denominator+std::abs(number(a.values()[k]*x[p.columns()[k]])));
        const double error=denominator==0 ? std::abs(residual[i]) : std::abs(residual[i])/denominator;
        backward=std::max(backward,error);
      }
      result.residual_norm=norm(residual); result.solution=x;
      if (backward<=settings_.backward_error_tolerance && acceptable(*result.residual_norm,norm(rhs),o)) {
        result.status=SolveStatus::converged; return result;
      }
      if (attempt+1==attempts) break;
      for (double& v:residual) v=-v;
      auto update=factors.solve(residual);
      for (std::size_t i=0;i<x.size();++i) x[i]=number(x[i]+update[i]);
    }
    result.diagnostics.reason=SolveReason::linear_residual;
  } catch (const Failure& failure) {
    result.status=failure.status; result.diagnostics.reason=failure.reason; result.diagnostics.failure_index=failure.index;
  } catch (const Error& error) {
    if (error.code!="range") throw;
    result.diagnostics.reason=SolveReason::numerical_range;
  }
  return result;
}
DampedNewtonBackend::DampedNewtonBackend(NewtonSettings s,std::shared_ptr<const LinearBackend> linear)
    :settings_(std::move(s)),linear_(std::move(linear)) {
  tolerances(settings_.absolute_step_tolerance,settings_.relative_step_tolerance);
  if (!linear_ || !std::isfinite(settings_.armijo) || settings_.armijo<=0 || settings_.armijo>=1 ||
      !std::isfinite(settings_.backtrack_factor) || settings_.backtrack_factor<=0 || settings_.backtrack_factor>=1 ||
      settings_.maximum_backtracks>64) throw Error("range");
}
SolveResult DampedNewtonBackend::solve(const NonlinearProblem& p,std::span<const double> initial,const SolveOptions& o) const {
  options(o); if (!p.sparsity || !p.evaluate) throw Error("dimension"); arguments(initial,p.sparsity->dimension());
  const auto n=initial.size(); std::vector<double> x(initial.begin(),initial.end()),lo(n,-std::numeric_limits<double>::infinity()),hi(n,std::numeric_limits<double>::infinity()),scales(n);
  auto assign=[&](const std::vector<double>& input,std::vector<double>& target) { if (!input.empty()) { if (input.size()!=n) throw Error("dimension"); target=input; } };
  assign(settings_.lower_bounds,lo); assign(settings_.upper_bounds,hi);
  for (std::size_t i=0;i<n;++i) scales[i]=std::max(1.0,std::abs(initial[i]));
  assign(settings_.variable_scales,scales);
  for (std::size_t i=0;i<n;++i) if (std::isnan(lo[i]) || std::isnan(hi[i]) || lo[i]>=hi[i] || x[i]<lo[i] || x[i]>hi[i] ||
      !std::isfinite(scales[i]) || scales[i]<=0) throw Error("range");
  SolveResult result{SolveStatus::nonconverged,x,0,{}}; double reference=0;
  auto finish=[&](SolveStatus status,SolveReason reason) { result.status=status; result.solution=x; result.diagnostics.reason=reason; return result; };
  try {
    for (std::size_t iteration=0;iteration<=o.maximum_iterations;++iteration) {
      result.iterations=iteration;
      auto value=evaluation(p,x,true); ++result.diagnostics.evaluations;
      const double merit=norm(value.residual); result.residual_norm=merit;
      if (iteration==0) reference=merit;
      if (iteration==o.maximum_iterations && !acceptable(merit,reference,o)) return finish(SolveStatus::nonconverged,SolveReason::iteration_limit);
      auto rhs=value.residual; for (double& v:rhs) v=-v;
      auto direction=solve_linear(*linear_,*value.jacobian,rhs,{0,1e-12,4});
      if (direction.status!=SolveStatus::converged) {
        result.diagnostics.failure_index=direction.diagnostics.failure_index;
        return finish(direction.status,direction.diagnostics.reason);
      }
      const auto& delta=direction.solution;
      result.diagnostics.correction_norm=correction_norm(delta,scales,settings_);
      if (acceptable(merit,reference,o) && *result.diagnostics.correction_norm<=1) return finish(SolveStatus::converged,SolveReason::none);
      if (iteration==o.maximum_iterations) return finish(SolveStatus::nonconverged,SolveReason::iteration_limit);
      double alpha=1;
      for (std::size_t i=0;i<n;++i) {
        if (delta[i]>0 && std::isfinite(hi[i])) alpha=std::min(alpha,(hi[i]-x[i])/delta[i]);
        if (delta[i]<0 && std::isfinite(lo[i])) alpha=std::min(alpha,(lo[i]-x[i])/delta[i]);
      }
      if (alpha<=0) return finish(SolveStatus::nonconverged,SolveReason::bounds);
      bool accepted=false;
      for (std::size_t attempt=0;attempt<=settings_.maximum_backtracks;++attempt) {
        std::vector<double> trial(n); bool changed=false,finite_trial=true;
        for (std::size_t i=0;i<n;++i) {
          double v=x[i]+alpha*delta[i];
          if (!std::isfinite(v)) { finite_trial=false; break; }
          trial[i]=std::clamp(v,lo[i],hi[i]); changed|=trial[i]!=x[i];
        }
        if (finite_trial) {
          if (!changed) return finish(SolveStatus::nonconverged,SolveReason::stagnation);
          try {
            ++result.diagnostics.evaluations;
            auto test=evaluation(p,trial,false); const double next=norm(test.residual);
            if (next<=(1-settings_.armijo*alpha)*merit || acceptable(next,reference,o)) { x=std::move(trial); accepted=true; break; }
          } catch (const EvaluationDomainError&) { /* An admissible smaller physical trial may exist. */ }
        }
        ++result.diagnostics.rejected_trials; alpha*=settings_.backtrack_factor;
      }
      if (!accepted) return finish(SolveStatus::nonconverged,SolveReason::line_search_failed);
    }
  } catch (const Failure& failure) { return finish(failure.status,failure.reason); }
  return finish(SolveStatus::nonconverged,SolveReason::iteration_limit);
}

SteadyResult solve_steady(const Assembly& a,double time,const SteadyOptions& o,std::optional<std::vector<double>> initial) {
  tolerances(o.absolute_power_tolerance,o.relative_power_tolerance);
  tolerances(o.absolute_temperature_tolerance,o.relative_temperature_tolerance);
  if (!std::isfinite(time) || !std::isfinite(o.absolute_energy_tolerance) || o.absolute_energy_tolerance<0 ||
      !std::isfinite(o.relative_energy_tolerance) || o.relative_energy_tolerance<0 || o.maximum_iterations==0 || o.maximum_iterations>10000) throw Error("range");
  if (o.method!=SteadyMethod::automatic && o.method!=SteadyMethod::direct_linear && o.method!=SteadyMethod::damped_newton) throw Error("range");
  SteadyResult out; auto x=initial ? std::move(*initial) : a.initial_temperature(); const auto n=a.sparsity()->dimension();
  arguments(x,n);
  out.method=o.method==SteadyMethod::automatic ? (a.has_temperature_dependent_power()?SteadyMethod::damped_newton:SteadyMethod::direct_linear) : o.method;
  out.solve.solution=x;
  if (out.method==SteadyMethod::direct_linear && a.has_temperature_dependent_power()) {
    out.solve.status=SolveStatus::unsupported; out.solve.diagnostics.reason=SolveReason::unsupported_model; return out;
  }
  NewtonSettings settings; settings.absolute_step_tolerance=o.absolute_temperature_tolerance; settings.relative_step_tolerance=o.relative_temperature_tolerance;
  settings.lower_bounds.assign(n,0); settings.upper_bounds.assign(n,std::numeric_limits<double>::infinity()); settings.variable_scales.resize(n);
  for (const auto& node:a.model().data().nodes) if (node.equation && node.material_index) {
    const auto& cp=a.model().data().materials.at(*node.material_index).specific_heat;
    settings.lower_bounds[*node.equation]=cp.minimum_temperature(); settings.upper_bounds[*node.equation]=cp.maximum_temperature();
  }
  auto size_check=[&](const auto& v) { if (!v.empty() && v.size()!=n) throw Error("dimension"); };
  for (const auto* v:{&o.lower_temperature,&o.upper_temperature,&o.temperature_scales,&o.power_scales}) size_check(*v);
  for (double scale:o.power_scales) if (!std::isfinite(scale) || scale<=0) throw Error("range");
  auto linear=std::make_shared<SparseLuBackend>(o.linear);
  for (std::size_t i=0;i<n;++i) {
    if (!o.lower_temperature.empty()) { if (!std::isfinite(o.lower_temperature[i])) throw Error("range"); settings.lower_bounds[i]=std::max(settings.lower_bounds[i],o.lower_temperature[i]); }
    if (!o.upper_temperature.empty()) { if (std::isnan(o.upper_temperature[i])) throw Error("range"); settings.upper_bounds[i]=std::min(settings.upper_bounds[i],o.upper_temperature[i]); }
    if (settings.lower_bounds[i]>=settings.upper_bounds[i]) throw Error("range");
    settings.variable_scales[i]=o.temperature_scales.empty()?std::max(1.0,std::abs(x[i])):o.temperature_scales[i];
    if (!std::isfinite(settings.variable_scales[i]) || settings.variable_scales[i]<=0) throw Error("range");
    if (x[i]<settings.lower_bounds[i] || x[i]>settings.upper_bounds[i]) {
      out.solve.diagnostics.reason=SolveReason::initial_domain; context(out,a,i); return out;
    }
  }
  if (out.method==SteadyMethod::direct_linear) settings.maximum_backtracks=0;
  try {
    auto seed=a.steady_linearize(time,x); out.power_scales=o.power_scales;
    if (out.power_scales.empty()) {
      out.power_scales.assign(n,0);
      for (const auto& node:a.model().data().nodes) if (node.equation) {
        const auto i=*node.equation, j=static_cast<std::size_t>(&node-a.model().data().nodes.data());
        out.power_scales[i]=std::max({std::abs(seed.balance.residual[i]),std::abs(seed.balance.load_in[j]),std::abs(seed.balance.environment_in[j]),std::abs(seed.balance.radiation_in[j]),std::abs(seed.balance.conductive_in[j])});
        for (std::size_t k=a.sparsity()->offsets()[i];k<a.sparsity()->offsets()[i+1];++k)
          out.power_scales[i]=std::max(out.power_scales[i],number(std::abs(seed.d_temperature.values()[k])*settings.variable_scales[a.sparsity()->columns()[k]]));
        if (out.power_scales[i]==0) out.power_scales[i]=1; // A zero row must still pass the Jacobian rank check.
      }
    }
    out.residual_limits.resize(n);
    for (std::size_t i=0;i<n;++i) {
      if (!std::isfinite(out.power_scales[i]) || out.power_scales[i]<=0) throw Error("range");
      out.residual_limits[i]=number(o.absolute_power_tolerance+number(o.relative_power_tolerance*out.power_scales[i]));
      if (out.residual_limits[i]<=0) throw Failure{SolveStatus::nonconverged,SolveReason::numerical_range,i};
    }
    auto count=std::make_shared<std::size_t>(0);
    auto raw=a.steady_problem(time); auto limits=out.residual_limits;
    NonlinearProblem scaled{raw.sparsity,[raw,limits,count](std::span<const double> t,bool jacobian) {
      ++*count; auto value=raw.evaluate(t,jacobian);
      try {
        for (std::size_t i=0;i<t.size();++i) value.residual[i]=number(value.residual[i]/limits[i]);
        if (jacobian) {
          SparseMatrix matrix(raw.sparsity);
          for (std::size_t i=0;i<t.size();++i)
            for (std::size_t k=raw.sparsity->offsets()[i];k<raw.sparsity->offsets()[i+1];++k)
              matrix.add({i,raw.sparsity->columns()[k]},number(value.jacobian->values()[k]/limits[i]));
          value.jacobian=std::move(matrix);
        }
      } catch (const Failure&) { throw EvaluationDomainError(Error("range")); }
      return value;
    }};
    DampedNewtonBackend backend(settings,linear);
    out.solve=solve_nonlinear(backend,scaled,x,{1,0,o.maximum_iterations});
    out.solve.diagnostics.evaluations=*count+2;
    if (out.solve.solution.size()==n) {
      out.balance=a.steady_residual(time,out.solve.solution); out.scaled_residual.resize(n);
      for (std::size_t i=0;i<n;++i) out.scaled_residual[i]=number(out.balance->residual[i]/out.residual_limits[i]);
      if (out.solve.status==SolveStatus::converged) {
        for (const auto& term:out.balance->internal_terms) {
          const double limit=number(o.absolute_energy_tolerance+number(o.relative_energy_tolerance*term.absolute_power));
          if (std::abs(term.net_power)>limit) {
            out.solve.status=SolveStatus::nonconverged; out.solve.diagnostics.reason=SolveReason::energy_imbalance;
            out.entity_id=term.entity_id; break;
          }
        }
        // Energy accuracy is relative to actual exchanged power, not G*T or
        // Jacobian scales, which can hide a lost temperature gradient.
        double reference=0;
        for (const auto* values:{&out.balance->load_in,&out.balance->environment_in,&out.balance->radiation_in,&out.balance->boundary_power,&out.balance->conductive_in})
          for (double v:*values) reference=number(reference+std::abs(v));
        double allowed=number(o.absolute_energy_tolerance+number(o.relative_energy_tolerance*reference));
        if (norm(out.scaled_residual)>1 || std::abs(out.balance->energy_defect)>allowed || std::abs(out.balance->internal_exchange_defect)>allowed) {
          out.solve.status=SolveStatus::nonconverged; out.solve.diagnostics.reason=SolveReason::energy_imbalance;
        }
      }
    }
    context(out,a,out.solve.diagnostics.failure_index);
  } catch (const Failure& failure) {
    out.solve.status=failure.status; out.solve.diagnostics.reason=failure.reason; context(out,a,failure.index);
  } catch (const Error& error) {
    out.solve.status=SolveStatus::nonconverged;
    out.solve.diagnostics.reason=error.code=="range"?SolveReason::initial_domain:SolveReason::model_error;
    out.entity_id=error.entity_id; out.source_map_id=error.source_map_id;
  }
  return out;
}
std::string_view reason_code(SolveReason r) {
  switch (r) {
    case SolveReason::none:return "converged"; case SolveReason::singular_pivot:return "singular_pivot";
    case SolveReason::fill_limit:return "fill_limit"; case SolveReason::numerical_range:return "numerical_range";
    case SolveReason::linear_residual:return "linear_residual"; case SolveReason::iteration_limit:return "iteration_limit";
    case SolveReason::line_search_failed:return "line_search_failed"; case SolveReason::stagnation:return "stagnation";
    case SolveReason::bounds:return "bounds"; case SolveReason::initial_domain:return "initial_domain";
    case SolveReason::model_error:return "model_error"; case SolveReason::energy_imbalance:return "energy_imbalance";
    case SolveReason::unsupported_model:return "unsupported_model";
  }
  return "model_error";
}
std::string_view status_code(SolveStatus s) {
  switch (s) {
    case SolveStatus::converged:return "converged"; case SolveStatus::singular:return "singular";
    case SolveStatus::nonconverged:return "nonconverged"; case SolveStatus::unsupported:return "unsupported";
  }
  return "nonconverged";
}
} // namespace fcst::thermal
