// SPDX-License-Identifier: MIT OR Apache-2.0
#pragma once
#include "fcst/thermal_assembly.hpp"
#include <limits>

namespace fcst::thermal {
struct SparseLuSettings {
  std::size_t maximum_dimension = 100000, maximum_nonzeros = 1000000;
  double pivot_tolerance = 64*std::numeric_limits<double>::epsilon();
  double backward_error_tolerance = 1e-12;
  std::size_t maximum_refinements = 3;
};
class SparseLuBackend final : public LinearBackend {
 public:
  explicit SparseLuBackend(SparseLuSettings settings = {});
  SolveResult solve(const SparseMatrix&, std::span<const double>, const SolveOptions&) const override;
 private:
  const SparseLuSettings settings_;
};
struct NewtonSettings {
  double absolute_step_tolerance = 1e-8, relative_step_tolerance = 1e-10;
  double armijo = 1e-4, backtrack_factor = .5;
  std::size_t maximum_backtracks = 32;
  std::vector<double> lower_bounds, upper_bounds, variable_scales;
};
class DampedNewtonBackend final : public NonlinearBackend {
 public:
  explicit DampedNewtonBackend(NewtonSettings settings = {},
    std::shared_ptr<const LinearBackend> linear = std::make_shared<SparseLuBackend>());
  SolveResult solve(const NonlinearProblem&, std::span<const double>, const SolveOptions&) const override;
 private:
  const NewtonSettings settings_;
  const std::shared_ptr<const LinearBackend> linear_;
};
enum class SteadyMethod { automatic, direct_linear, damped_newton };
struct SteadyOptions {
  SteadyMethod method = SteadyMethod::automatic;
  double absolute_power_tolerance = 0, relative_power_tolerance = 1e-10;
  double absolute_temperature_tolerance = 1e-8, relative_temperature_tolerance = 1e-10;
  double absolute_energy_tolerance = 0, relative_energy_tolerance = 1e-10;
  std::size_t maximum_iterations = 50;
  std::vector<double> power_scales, temperature_scales, lower_temperature, upper_temperature;
  SparseLuSettings linear;
};
struct SteadyResult {
  SolveResult solve{SolveStatus::nonconverged,{},0,{}};
  SteadyMethod method = SteadyMethod::automatic;
  std::optional<Balance> balance;
  std::vector<double> power_scales, residual_limits, scaled_residual;
  std::string entity_id, source_map_id;
};
// All scales/limits are frozen at the initial state. Convergence also requires
// an independently recomputed physical energy budget and a nonsingular Jacobian.
SteadyResult solve_steady(const Assembly&, double time = 0, const SteadyOptions& = {},
                          std::optional<std::vector<double>> initial = {});
std::string_view reason_code(SolveReason reason);
std::string_view status_code(SolveStatus status);
std::string inspect_steady(std::string_view input);
} // namespace fcst::thermal
