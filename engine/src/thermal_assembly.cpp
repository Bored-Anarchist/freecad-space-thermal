// SPDX-License-Identifier: MIT OR Apache-2.0
#include "fcst/thermal_assembly.hpp"
#include <algorithm>
#include <cmath>
#include <exception>
#include <limits>
#include <set>
#include <utility>

namespace fcst::thermal {
namespace {
double checked(double value) {
  if (!std::isfinite(value)) throw Error("range");
  return value == 0 ? 0 : value;
}
double narrow(long double value) {
  if (!std::isfinite(value) || std::abs(value) > std::numeric_limits<double>::max()) throw Error("range");
  return checked(static_cast<double>(value));
}
void vector_check(std::span<const double> values, std::size_t size, bool temperature = false) {
  if (values.size() != size) throw Error("dimension");
  for (double v : values) if (!std::isfinite(v) || (temperature && v < 0)) throw Error("range");
}
void options_check(const SolveOptions& options) {
  if (!std::isfinite(options.absolute_tolerance) || !std::isfinite(options.relative_tolerance) ||
      options.absolute_tolerance < 0 || options.relative_tolerance < 0 ||
      (options.absolute_tolerance == 0 && options.relative_tolerance == 0) ||
      options.maximum_iterations == 0) throw Error("range");
}
double norm(std::span<const double> values) {
  double result = 0;
  for (double v : values) result = std::max(result, std::abs(checked(v)));
  return result;
}
bool converged(double residual, double reference, const SolveOptions& options) {
  return static_cast<long double>(residual) <= static_cast<long double>(options.absolute_tolerance) +
    static_cast<long double>(options.relative_tolerance)*reference;
}
void result_check(const SolveResult& result, std::size_t size, const SolveOptions& options) {
  switch (result.status) {
    case SolveStatus::converged: case SolveStatus::singular:
    case SolveStatus::nonconverged: case SolveStatus::unsupported: break;
    default: throw Error("backend_result");
  }
  if (result.iterations > options.maximum_iterations ||
      (result.status == SolveStatus::converged && result.solution.size() != size) ||
      (!result.solution.empty() && result.solution.size() != size)) throw Error("backend_result");
  for (double v : result.solution) if (!std::isfinite(v)) throw Error("backend_result");
  if ((result.diagnostics.failure_index && *result.diagnostics.failure_index>=size) ||
      (result.diagnostics.correction_norm && (!std::isfinite(*result.diagnostics.correction_norm) || *result.diagnostics.correction_norm<0))) throw Error("backend_result");
}
NonlinearEvaluation problem_evaluate(const NonlinearProblem& problem, std::span<const double> x, bool jacobian) {
  if (!problem.sparsity || !problem.evaluate) throw Error("dimension");
  vector_check(x, problem.sparsity->dimension());
  NonlinearEvaluation result;
  try { result = problem.evaluate(x, jacobian); }
  catch (const Error&) { throw; }
  catch (...) { throw Error("callback_failure"); }
  vector_check(result.residual, problem.sparsity->dimension());
  if (jacobian != result.jacobian.has_value()) throw Error("backend_result");
  if (jacobian) {
    if (*result.jacobian->sparsity() != *problem.sparsity) throw Error("backend_result");
    for (double v : result.jacobian->values()) (void)checked(v);
  }
  return result;
}
}

Sparsity::Sparsity(std::size_t dimension, std::vector<Entry> entries) : dimension_(dimension) {
  if (dimension > 1000000 || entries.size() > 4000000) throw Error("limit");
  std::sort(entries.begin(), entries.end());
  entries.erase(std::unique(entries.begin(), entries.end()), entries.end());
  offsets_.assign(dimension+1, 0);
  for (const auto& e : entries) {
    if (e.row >= dimension || e.column >= dimension) throw Error("dimension");
    ++offsets_[e.row+1]; columns_.push_back(e.column);
  }
  for (std::size_t i = 1; i < offsets_.size(); ++i) offsets_[i] += offsets_[i-1];
}
std::optional<std::size_t> Sparsity::position(Entry e) const {
  if (e.row >= dimension_ || e.column >= dimension_) throw Error("dimension");
  auto first = columns_.begin() + static_cast<std::ptrdiff_t>(offsets_[e.row]);
  auto last = columns_.begin() + static_cast<std::ptrdiff_t>(offsets_[e.row+1]);
  auto found = std::lower_bound(first, last, e.column);
  if (found == last || *found != e.column) return {};
  return static_cast<std::size_t>(found-columns_.begin());
}
SparseMatrix::SparseMatrix(std::shared_ptr<const Sparsity> sparsity) : sparsity_(std::move(sparsity)) {
  if (!sparsity_) throw Error("dimension");
  values_.assign(sparsity_->nonzeros(), 0);
}
void SparseMatrix::add(Entry entry, double value) {
  auto i = sparsity_->position(entry);
  if (!i) throw Error("sparsity");
  values_[*i] = checked(values_[*i] + checked(value));
}
double SparseMatrix::at(Entry entry) const {
  auto i = sparsity_->position(entry);
  return i ? values_[*i] : 0;
}
std::vector<double> SparseMatrix::multiply(std::span<const double> vector) const {
  vector_check(vector, sparsity_->dimension());
  std::vector<double> result(vector.size(), 0);
  for (std::size_t i = 0; i < result.size(); ++i) {
    long double sum = 0;
    for (std::size_t k = sparsity_->offsets()[i]; k < sparsity_->offsets()[i+1]; ++k)
      sum += static_cast<long double>(values_[k])*vector[sparsity_->columns()[k]];
    result[i] = narrow(sum);
  }
  return result;
}
SparseMatrix Linearization::combined(double coefficient) const {
  (void)checked(coefficient);
  if (*d_temperature.sparsity() != *d_rate.sparsity()) throw Error("dimension");
  SparseMatrix result(d_temperature.sparsity());
  const auto& pattern = *result.sparsity();
  for (std::size_t i = 0; i < pattern.dimension(); ++i)
    for (std::size_t k = pattern.offsets()[i]; k < pattern.offsets()[i+1]; ++k)
      result.add({i, pattern.columns()[k]}, narrow(static_cast<long double>(d_temperature.values()[k]) +
        static_cast<long double>(coefficient)*d_rate.values()[k]));
  return result;
}

struct Assembly::Impl {
  Model model;
  std::vector<PowerBinding> powers;
  std::vector<BoundaryBinding> boundaries;
  std::shared_ptr<const Sparsity> sparsity;
  OperatingState operating;
  double factor(const std::string& id) const {
    double value=operating.load_factors.contains(id)?operating.load_factors.at(id):1;
    for (const auto& c:model.data().controls) if (c.load_id==id && !operating.heaters.at(c.id)) return 0;
    return value;
  }
  void validate_state(const OperatingState& s) const {
    if (s.heaters.size()!=model.data().controls.size()) throw Error("controls_require_state");
    std::set<std::string> loads;
    for (const auto& c:model.data().controls) {
      if (!s.heaters.contains(c.id)) throw Error("controls_require_state",c.id);
      if (!loads.insert(c.load_id).second) throw Error("control_conflict",c.id);
    }
    for (const auto& [id,v]:s.load_factors) {
      if (!std::isfinite(v) || v<0) throw Error("range",id);
      if (std::none_of(model.data().loads.begin(),model.data().loads.end(),[&](const auto& l){return l.id==id && l.active;})) throw Error("reference",id);
    }
  }
  Impl(Model m, std::vector<PowerBinding> p, std::vector<BoundaryBinding> b)
      : model(std::move(m)), powers(std::move(p)), boundaries(std::move(b)) {}
  [[noreturn]] void context(Error error, const std::string& id = {}) const {
    if (!id.empty()) error.entity_id = id;
    const auto& d = model.data();
    if (error.source_map_id.empty() && d.sources_by_entity.contains(error.entity_id))
      error.source_map_id = d.source_identities.at(d.sources_by_entity.at(error.entity_id).front()).source_map_id;
    throw error;
  }
};
OperatingState initial_operating_state(const Model& m) {
  OperatingState s; for (const auto& c:m.data().controls) s.heaters.emplace(c.id,false); return s;
}
Assembly::Assembly(Model model, std::vector<PowerBinding> powers, std::vector<BoundaryBinding> boundaries,
                   std::optional<OperatingState> operating) {
  auto impl = std::make_shared<Impl>(std::move(model), std::move(powers), std::move(boundaries));
  const auto& d = impl->model.data();
  if (!operating && !d.active_control_ids.empty()) impl->context(Error("controls_require_state"), d.active_control_ids.front());
  impl->operating=operating.value_or(OperatingState{}); impl->validate_state(impl->operating);
  if (!d.spatial_element_ids.empty()) impl->context(Error("unsupported_physics"), d.spatial_element_ids.front());
  const std::size_t n = d.differential_count + d.algebraic_count;
  std::vector<Entry> entries;
  for (std::size_t i = 0; i < n; ++i) entries.push_back({i,i});
  for (const auto& c : d.conductors) if (c.conductance > 0) {
    for (auto i : {c.from,c.to}) for (auto j : {c.from,c.to})
      if (d.nodes[i].equation && d.nodes[j].equation) entries.push_back({*d.nodes[i].equation,*d.nodes[j].equation});
  }
  std::map<std::string, const Load*> active_loads;
  for (const auto& load : d.loads) if (load.active) active_loads.emplace(load.id,&load);
  std::set<std::string> required_radiation, required_environment(d.active_environment_ids.begin(), d.active_environment_ids.end());
  for (const auto& r : d.radiation) required_radiation.insert(r.id);
  std::map<std::string, const PowerBinding*> bound;
  // Evaluation order is independent of the order bindings arrive from the caller.
  std::sort(impl->powers.begin(), impl->powers.end(), [](const auto& a, const auto& b) { return a.entity_id < b.entity_id; });
  for (const auto& p : impl->powers) {
    try {
      if (!p.evaluate) throw Error("callback_missing");
      if (!bound.emplace(p.entity_id,&p).second) throw Error("duplicate_id");
      if (p.kind == PowerKind::load) {
        if (!active_loads.contains(p.entity_id)) throw Error("reference");
        if (p.affected_nodes != std::vector<std::size_t>{active_loads.at(p.entity_id)->node}) throw Error("dimension");
      } else if (p.kind == PowerKind::radiation) {
        if (!required_radiation.contains(p.entity_id) || p.affected_nodes.empty()) throw Error("reference");
      } else if (p.kind == PowerKind::environment) {
        if (!required_environment.contains(p.entity_id)) throw Error("reference");
      } else throw Error("range");
      std::set<std::size_t> affected;
      for (auto i : p.affected_nodes)
        if (i >= d.nodes.size() || !affected.insert(i).second) throw Error("dimension");
      std::set<Entry> dependencies;
      for (const auto& e : p.dependencies) {
        if (!affected.contains(e.row) || e.column >= d.nodes.size() || !dependencies.insert(e).second) throw Error("sparsity");
        if (d.nodes[e.row].equation && d.nodes[e.column].equation)
          entries.push_back({*d.nodes[e.row].equation,*d.nodes[e.column].equation});
      }
    } catch (const Error& error) { impl->context(error,p.entity_id); }
  }
  for (const auto& load : d.loads)
    if (load.active && load.expression_id && !bound.contains(load.id)) impl->context(Error("callback_missing"),load.id);
  for (const auto& id : required_radiation)
    if (!bound.contains(id)) impl->context(Error("callback_missing"),id);
  for (const auto& id : required_environment)
    if (!bound.contains(id)) impl->context(Error("callback_missing"),id);
  for (const auto& r : d.radiation) {
    const auto& environment = bound.at(r.environment_id)->affected_nodes;
    for (auto i : bound.at(r.id)->affected_nodes)
      if (std::find(environment.begin(),environment.end(),i) == environment.end()) impl->context(Error("callback_coverage"),r.environment_id);
  }
  std::set<std::size_t> boundary_nodes;
  for (const auto& b : impl->boundaries) {
    if (b.node >= d.nodes.size()) throw Error("dimension");
    if (d.nodes[b.node].classification != NodeClass::prescribed || !b.temperature || !boundary_nodes.insert(b.node).second)
      impl->context(Error("boundary"),d.nodes[b.node].id);
  }
  impl->sparsity = std::make_shared<Sparsity>(n,std::move(entries));
  impl_ = std::move(impl);
}
const Model& Assembly::model() const { return impl_->model; }
Assembly Assembly::with_operating_state(OperatingState s) const {
  impl_->validate_state(s); auto copy=std::make_shared<Impl>(*impl_); copy->operating=std::move(s);
  auto result=*this; result.impl_=std::move(copy); return result;
}
const OperatingState& Assembly::operating_state() const { return impl_->operating; }
bool Assembly::has_callbacks() const { return !impl_->powers.empty() || !impl_->boundaries.empty(); }
const std::shared_ptr<const Sparsity>& Assembly::sparsity() const { return impl_->sparsity; }
std::vector<double> Assembly::initial_temperature() const {
  std::vector<double> result(sparsity()->dimension());
  for (const auto& node : model().data().nodes) if (node.equation) result[*node.equation] = node.temperature;
  return result;
}
bool Assembly::has_temperature_dependent_power() const {
  return std::any_of(impl_->powers.begin(),impl_->powers.end(),[](const auto& p) { return !p.dependencies.empty(); });
}
Balance Assembly::evaluate(Storage mode, double time, std::span<const double> x,
                           std::span<const double> rate, std::span<const double> previous,
                           double seconds, Linearization* derivatives) const {
  const bool jacobian = derivatives != nullptr;
  (void)checked(time);
  const auto& d = model().data();
  vector_check(x,sparsity()->dimension(),true);
  if (mode == Storage::rate) vector_check(rate,d.differential_count);
  if (mode == Storage::enthalpy) {
    vector_check(previous,x.size(),true);
    if (!std::isfinite(seconds) || seconds <= 0) throw Error("range");
  }
  // Residual and energy probes do not need zero-filled derivative matrices.
  Balance b;
  b.temperature.resize(d.nodes.size()); b.residual.resize(x.size());
  for (auto* values : {&b.conductive_in,&b.load_in,&b.radiation_in,&b.environment_in,&b.storage_power,&b.boundary_power})
    values->assign(d.nodes.size(),0);
  b.conductor_power.reserve(d.conductors.size());
  for (std::size_t i = 0; i < d.nodes.size(); ++i) {
    const auto& node = d.nodes[i];
    b.temperature[i] = node.equation ? x[*node.equation] : node.temperature;
  }
  for (const auto& boundary : impl_->boundaries) {
    try {
      b.temperature[boundary.node] = checked(boundary.temperature(time));
      if (b.temperature[boundary.node] < 0) throw Error("range");
    } catch (const Error& error) { impl_->context(error,d.nodes[boundary.node].id); }
      catch (...) { impl_->context(Error("callback_failure"),d.nodes[boundary.node].id); }
  }
  for (const auto& c : d.conductors) {
    try {
      // Compute each oriented flow once, then scatter opposite signs to its endpoints.
      double power = narrow(static_cast<long double>(c.conductance)*(b.temperature[c.from]-static_cast<long double>(b.temperature[c.to])));
      b.conductor_power.push_back(power);
      b.conductive_in[c.from] = checked(b.conductive_in[c.from]-power);
      b.conductive_in[c.to] = checked(b.conductive_in[c.to]+power);
      if (jacobian && c.conductance > 0) {
        for (auto i : {c.from,c.to}) for (auto j : {c.from,c.to})
          if (d.nodes[i].equation && d.nodes[j].equation)
            derivatives->d_temperature.add({*d.nodes[i].equation,*d.nodes[j].equation},i == j ? c.conductance : -c.conductance);
      }
    } catch (const Error& error) { impl_->context(error,c.id); }
  }
  std::set<std::string> bound_loads;
  for (const auto& p : impl_->powers) {
    try {
      PowerEvaluation value;
      try { value = p.evaluate(time,b.temperature,jacobian); }
      catch (...) { throw Error("callback_failure"); }
      vector_check(value.watts,p.affected_nodes.size());
      vector_check(value.d_temperature,jacobian ? p.dependencies.size() : 0);
      if (p.kind==PowerKind::load) {
        const double factor=impl_->factor(p.entity_id);
        for (double& v:value.watts) v=checked(v*factor);
        for (double& v:value.d_temperature) v=checked(v*factor);
      }
      if (p.kind==PowerKind::radiation) {
        long double net=0,absolute=0;
        for (double v:value.watts) { net+=v; absolute+=std::abs(v); }
        b.internal_terms.push_back({p.entity_id,narrow(net),narrow(absolute)});
      }
      auto& destination = p.kind == PowerKind::load ? b.load_in : p.kind == PowerKind::radiation ? b.radiation_in : b.environment_in;
      for (std::size_t k = 0; k < p.affected_nodes.size(); ++k) {
        auto i = p.affected_nodes[k]; destination[i] = checked(destination[i]+value.watts[k]);
      }
      if (p.kind == PowerKind::load) bound_loads.insert(p.entity_id);
      if (jacobian) for (std::size_t k = 0; k < p.dependencies.size(); ++k) {
        const auto& e = p.dependencies[k];
        if (d.nodes[e.row].equation && d.nodes[e.column].equation)
          derivatives->d_temperature.add({*d.nodes[e.row].equation,*d.nodes[e.column].equation},-value.d_temperature[k]);
      }
    } catch (const Error& error) { impl_->context(error,p.entity_id); }
  }
  for (const auto& load : d.loads) if (load.active && !bound_loads.contains(load.id)) {
    try { b.load_in[load.node] = checked(b.load_in[load.node]+checked(load.power*impl_->factor(load.id))); }
    catch (const Error& error) { impl_->context(error,load.id); }
  }
  long double storage_total = 0, external_total = 0, internal_total = 0;
  for (std::size_t i = 0; i < d.nodes.size(); ++i) {
    const auto& node = d.nodes[i];
    try {
      // Algebraic and prescribed nodes have exactly zero storage in every formulation.
      if (node.classification == NodeClass::capacitive) {
        auto capacity = model().storage_capacity_sample(i,b.temperature[i]);
        if (jacobian && mode != Storage::none && capacity.discontinuous) throw Error("nondifferentiable");
        if (mode == Storage::rate) {
          double r = rate[*node.differential_index];
          b.storage_power[i] = checked(capacity.value*r);
          if (jacobian) {
            derivatives->d_temperature.add({*node.equation,*node.equation},checked(capacity.derivative*r));
            derivatives->d_rate.add({*node.equation,*node.equation},capacity.value);
          }
        } else if (mode == Storage::enthalpy) {
          b.storage_power[i] = checked(model().storage_change(i,previous[*node.equation],b.temperature[i])/seconds);
          if (jacobian) derivatives->d_temperature.add({*node.equation,*node.equation},checked(capacity.value/seconds));
        }
      }
      const double external = narrow(static_cast<long double>(b.load_in[i])+b.radiation_in[i]+b.environment_in[i]);
      const double incoming = narrow(static_cast<long double>(external)+b.conductive_in[i]);
      if (node.classification == NodeClass::prescribed) b.boundary_power[i] = -incoming;
      else b.residual[*node.equation] = checked(b.storage_power[i]-incoming);
      storage_total += b.storage_power[i];
      external_total += static_cast<long double>(b.load_in[i])+b.environment_in[i]+b.boundary_power[i];
      internal_total += static_cast<long double>(b.conductive_in[i])+b.radiation_in[i];
    } catch (const Error& error) { impl_->context(error,node.id); }
  }
  b.energy_defect = narrow(storage_total-external_total);
  b.internal_exchange_defect = narrow(internal_total);
  return b;
}
Balance Assembly::residual(const State& s) const { return evaluate(Storage::rate,s.time,s.temperature,s.rate,{},0); }
Linearization Assembly::linearize(const State& s) const {
  Linearization out{{},SparseMatrix(sparsity()),SparseMatrix(sparsity())};
  out.balance = evaluate(Storage::rate,s.time,s.temperature,s.rate,{},0,&out); return out;
}
Balance Assembly::steady_residual(double t, std::span<const double> x) const { return evaluate(Storage::none,t,x,{},{},0); }
Linearization Assembly::steady_linearize(double t, std::span<const double> x) const {
  Linearization out{{},SparseMatrix(sparsity()),SparseMatrix(sparsity())};
  out.balance = evaluate(Storage::none,t,x,{},{},0,&out); return out;
}
Balance Assembly::step_residual(double t, std::span<const double> x, std::span<const double> previous, double seconds) const {
  return evaluate(Storage::enthalpy,t,x,{},previous,seconds);
}
Linearization Assembly::step_linearize(double t, std::span<const double> x, std::span<const double> previous, double seconds) const {
  Linearization out{{},SparseMatrix(sparsity()),SparseMatrix(sparsity())};
  out.balance = evaluate(Storage::enthalpy,t,x,{},previous,seconds,&out); return out;
}
NonlinearProblem Assembly::steady_problem(double time) const {
  (void)checked(time);
  return {sparsity(),[owned = *this,time](std::span<const double> x, bool jacobian) {
    try {
      if (!jacobian) return NonlinearEvaluation{owned.steady_residual(time,x).residual,{}};
      auto result = owned.steady_linearize(time,x);
      return NonlinearEvaluation{std::move(result.balance.residual),std::move(result.d_temperature)};
    } catch (const Error& error) {
      if (error.code == "range") throw EvaluationDomainError(error);
      throw;
    }
  }};
}
NonlinearProblem Assembly::step_problem(double time, std::vector<double> previous, double seconds) const {
  (void)checked(time); vector_check(previous,sparsity()->dimension(),true);
  if (!std::isfinite(seconds) || seconds <= 0) throw Error("range");
  return {sparsity(),[owned = *this,time,previous = std::move(previous),seconds](std::span<const double> x, bool jacobian) {
    if (!jacobian) return NonlinearEvaluation{owned.step_residual(time,x,previous,seconds).residual,{}};
    auto result = owned.step_linearize(time,x,previous,seconds);
    return NonlinearEvaluation{std::move(result.balance.residual),std::move(result.d_temperature)};
  }};
}
SolveResult solve_linear(const LinearBackend& backend, const SparseMatrix& matrix, std::span<const double> rhs, const SolveOptions& options) {
  options_check(options); vector_check(rhs,matrix.sparsity()->dimension());
  SolveResult result;
  try { result = backend.solve(matrix,rhs,options); }
  catch (...) { throw Error("backend_failure"); }
  result_check(result,rhs.size(),options);
  result.residual_norm.reset();
  if (result.solution.size() == rhs.size()) {
    auto residual = matrix.multiply(result.solution);
    for (std::size_t i = 0; i < rhs.size(); ++i) residual[i] = checked(residual[i]-rhs[i]);
    result.residual_norm = norm(residual);
  }
  if (result.status == SolveStatus::converged && (!result.residual_norm || !converged(*result.residual_norm,norm(rhs),options)))
    throw Error("backend_result");
  return result;
}
SolveResult solve_nonlinear(const NonlinearBackend& backend, const NonlinearProblem& problem,
                            std::span<const double> initial, const SolveOptions& options) {
  options_check(options);
  auto initial_value = problem_evaluate(problem,initial,false);
  auto callback_error = std::make_shared<std::exception_ptr>();
  NonlinearProblem guarded{problem.sparsity,[problem,callback_error](std::span<const double> x, bool jacobian) {
    try { return problem_evaluate(problem,x,jacobian); }
    catch (const EvaluationDomainError&) { throw; }
    catch (...) { *callback_error = std::current_exception(); throw; }
  }};
  SolveResult result;
  try { result = backend.solve(guarded,initial,options); }
  catch (...) {
    if (*callback_error) std::rethrow_exception(*callback_error);
    throw Error("backend_failure");
  }
  if (*callback_error) std::rethrow_exception(*callback_error);
  result_check(result,initial.size(),options);
  result.residual_norm.reset();
  if (result.solution.size() == initial.size()) result.residual_norm = norm(problem_evaluate(problem,result.solution,false).residual);
  if (result.status == SolveStatus::converged && (!result.residual_norm || !converged(*result.residual_norm,norm(initial_value.residual),options)))
    throw Error("backend_result");
  return result;
}
} // namespace fcst::thermal
