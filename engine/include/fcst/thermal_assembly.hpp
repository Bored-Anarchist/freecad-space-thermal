// SPDX-License-Identifier: MIT OR Apache-2.0
#pragma once
#include "fcst/thermal.hpp"
#include <compare>
#include <functional>
#include <memory>
#include <span>

namespace fcst::thermal {
struct Entry {
  std::size_t row, column;
  auto operator<=>(const Entry&) const = default;
};
// Square, deterministic CSR. Storage grows with declared edges, never n*n.
class Sparsity {
 public:
  Sparsity(std::size_t dimension, std::vector<Entry> entries);
  std::size_t dimension() const { return dimension_; }
  std::size_t nonzeros() const { return columns_.size(); }
  const std::vector<std::size_t>& offsets() const { return offsets_; }
  const std::vector<std::size_t>& columns() const { return columns_; }
  std::optional<std::size_t> position(Entry entry) const;
  bool operator==(const Sparsity&) const = default;
 private:
  std::size_t dimension_;
  std::vector<std::size_t> offsets_, columns_;
};
class SparseMatrix {
 public:
  explicit SparseMatrix(std::shared_ptr<const Sparsity> sparsity);
  const std::shared_ptr<const Sparsity>& sparsity() const { return sparsity_; }
  std::span<const double> values() const { return values_; }
  void add(Entry entry, double value);
  double at(Entry entry) const;
  std::vector<double> multiply(std::span<const double> vector) const;
 private:
  std::shared_ptr<const Sparsity> sparsity_;
  std::vector<double> values_;
};
enum class PowerKind { load, radiation, environment };
struct PowerEvaluation {
  std::vector<double> watts; // One per affected_nodes entry, positive into the node.
  std::vector<double> d_temperature; // One per dependency when derivatives are requested.
};
struct PowerBinding {
  std::string entity_id;
  PowerKind kind;
  std::vector<std::size_t> affected_nodes;
  std::vector<Entry> dependencies; // Full node indexes, including prescribed nodes.
  std::function<PowerEvaluation(double, std::span<const double>, bool)> evaluate;
};
struct BoundaryBinding {
  std::size_t node;
  std::function<double(double)> temperature; // Independent prescribed K as a function of SI time.
};
struct OperatingState {
  std::map<std::string,bool> heaters;
  std::map<std::string,double> load_factors; // Nonnegative scheduled multipliers, default one.
  bool operator==(const OperatingState&) const = default;
};
OperatingState initial_operating_state(const Model&);
struct State {
  double time;
  std::vector<double> temperature; // Unknown equation order: capacitive and algebraic.
  std::vector<double> rate; // Differential index order only, K/s. Algebraic rates do not exist.
};
struct Balance {
  struct InternalTerm { std::string entity_id; double net_power, absolute_power; };
  std::vector<double> temperature, residual;
  std::vector<double> conductive_in, load_in, radiation_in, environment_in, storage_power, boundary_power;
  std::vector<double> conductor_power; // Positive from conductor.from to conductor.to.
  std::vector<InternalTerm> internal_terms; // Each internal radiation callback, before global cancellation.
  double internal_exchange_defect = 0; // Net conductive plus internal radiation power; ideally zero.
  double energy_defect = 0; // Sum storage - sum external input, including prescribed reservoirs.
};
struct Linearization {
  Balance balance;
  SparseMatrix d_temperature, d_rate;
  SparseMatrix combined(double rate_coefficient) const;
};
struct NonlinearEvaluation {
  std::vector<double> residual;
  std::optional<SparseMatrix> jacobian;
};
struct NonlinearProblem {
  std::shared_ptr<const Sparsity> sparsity;
  std::function<NonlinearEvaluation(std::span<const double>, bool)> evaluate;
};
// A physical trial may be outside the model domain; an algorithm may backtrack.
// Shape, nonfinite protocol values and ordinary callback failures remain fatal.
struct EvaluationDomainError : Error { explicit EvaluationDomainError(const Error& error) : Error(error) {} };
class Assembly {
 public:
  explicit Assembly(Model model, std::vector<PowerBinding> powers = {}, std::vector<BoundaryBinding> boundaries = {},
                    std::optional<OperatingState> operating = {});
  Assembly with_operating_state(OperatingState) const;
  const OperatingState& operating_state() const;
  bool has_callbacks() const;
  const Model& model() const;
  const std::shared_ptr<const Sparsity>& sparsity() const;
  std::vector<double> initial_temperature() const;
  bool has_temperature_dependent_power() const;
  Balance residual(const State& state) const;
  Linearization linearize(const State& state) const;
  Balance steady_residual(double time, std::span<const double> temperature) const;
  Linearization steady_linearize(double time, std::span<const double> temperature) const;
  Balance step_residual(double time, std::span<const double> temperature,
                        std::span<const double> previous_temperature, double seconds) const;
  Linearization step_linearize(double time, std::span<const double> temperature,
                               std::span<const double> previous_temperature, double seconds) const;
  // Factories own their assembly snapshot and fixed time/previous state; no dangling references.
  NonlinearProblem steady_problem(double time) const;
  NonlinearProblem step_problem(double time, std::vector<double> previous_temperature, double seconds) const;
 private:
  struct Impl;
  std::shared_ptr<const Impl> impl_;
  enum class Storage { none, rate, enthalpy };
  Linearization evaluate(Storage storage, double time, std::span<const double> temperature,
                         std::span<const double> rate, std::span<const double> previous,
                         double seconds, bool jacobian) const;
};

enum class SolveStatus { converged, singular, nonconverged, unsupported };
enum class SolveReason {
  none, singular_pivot, fill_limit, numerical_range, linear_residual,
  iteration_limit, line_search_failed, stagnation, bounds, initial_domain,
  model_error, energy_imbalance, unsupported_model
};
struct SolveDiagnostics {
  SolveReason reason = SolveReason::none;
  std::size_t evaluations = 0, rejected_trials = 0;
  std::optional<std::size_t> failure_index;
  std::optional<double> correction_norm;
};
struct SolveOptions {
  double absolute_tolerance = 1e-10, relative_tolerance = 1e-10;
  std::size_t maximum_iterations = 100;
};
struct SolveResult {
  SolveStatus status;
  std::vector<double> solution;
  std::size_t iterations = 0;
  std::optional<double> residual_norm;
  SolveDiagnostics diagnostics{};
};
class LinearBackend {
 public:
  virtual ~LinearBackend() = default;
  virtual SolveResult solve(const SparseMatrix&, std::span<const double> rhs, const SolveOptions&) const = 0;
};
class NonlinearBackend {
 public:
  virtual ~NonlinearBackend() = default;
  virtual SolveResult solve(const NonlinearProblem&, std::span<const double> initial, const SolveOptions&) const = 0;
};
// Validate the backend contract and independently recompute residuals before accepting convergence.
SolveResult solve_linear(const LinearBackend&, const SparseMatrix&, std::span<const double> rhs, const SolveOptions& = {});
SolveResult solve_nonlinear(const NonlinearBackend&, const NonlinearProblem&, std::span<const double> initial, const SolveOptions& = {});
} // namespace fcst::thermal
