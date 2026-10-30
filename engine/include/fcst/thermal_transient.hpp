// SPDX-License-Identifier: MIT OR Apache-2.0
#pragma once
#include "fcst/thermal_steady.hpp"

namespace fcst::thermal {
// All records use SI and immutable model/equation order. No host/runtime solver.
struct SchedulePoint { double time, factor; };
struct LoadSchedule { std::string load_id; std::vector<SchedulePoint> points; };
struct TransientOptions {
  double start=0, end=1, initial_step=.01, minimum_step=1e-12, maximum_step=1;
  double absolute_temperature_tolerance=1e-5, relative_temperature_tolerance=1e-6;
  double absolute_energy_tolerance=1e-8, relative_energy_tolerance=1e-8;
  double event_time_tolerance=1e-8, minimum_event_separation=1e-10;
  std::size_t maximum_attempts=100000, maximum_events=10000, maximum_newton_iterations=30;
  std::size_t maximum_result_values=2000000;
  std::vector<double> output_times; // Strictly increasing, exact step boundaries, includes start/end.
  std::vector<double> temperature_tolerances; // Optional per-equation absolute K tolerances.
  std::vector<LoadSchedule> schedules; // Right continuous; first point must cover start.
  // Exact compiled callback registration/build digest; required when callbacks exist.
  std::string callback_revision;
  SparseLuSettings linear;
};
struct KernelProfile {
  std::size_t residual_evaluations=0, jacobian_evaluations=0, linear_solves=0, newton_iterations=0, event_probes=0;
  double assembly_seconds=0, linear_seconds=0, total_seconds=0;
};
struct BackendCapabilities {
  std::string execution_mode="fcst_native", linear="fcst_sparse_lu", nonlinear="fcst_damped_newton";
  std::string transient="fcst_enthalpy_backward_euler_step_doubling";
  std::string source_revision, compiler, compiler_version;
  bool stiff=true, index_one_dae=true, enthalpy=true, events=true, checkpoint=true;
  bool external_reference=false, durable_job_solver=false;
};
BackendCapabilities thermal_backend_capabilities();
struct EnergyBudget {
  std::vector<double> storage_change, external_energy, conductive_energy, boundary_energy; // J per full node.
  double defect=0, absolute_exchange=0;
};
struct TransientSample {
  double time=0;
  Balance balance; // Instantaneous continuous residual; algebraic storage is exactly zero.
  std::vector<double> rate; // Differential K/s only.
  std::vector<double> storage_change; // J from original initial condition.
  OperatingState operating;
  std::map<std::string,double> duty_cycles; // On time / elapsed original run time.
  EnergyBudget run_energy;
  bool valid=false;
};
struct StepRecord {
  double start=0, end=0, error_norm=0;
  bool accepted=false;
  std::string reason;
  EnergyBudget energy; // Only accepted steps contribute to cumulative budgets.
};
struct EventRecord {
  double time=0;
  std::string entity_id, kind; // schedule or heater; schedules first, then UUID order.
  double before=0, after=0;
};
struct TransientCheckpoint {
  unsigned version=1;
  std::string configuration_id, checksum;
  double time=0, origin=0, next_step=0;
  std::vector<double> temperature, initial_temperature;
  OperatingState operating;
  std::map<std::string,double> last_switch, on_seconds;
  EnergyBudget run_energy;
  std::size_t accepted_steps=0, rejected_steps=0, event_count=0;
};
struct TransientResult {
  bool valid=false;
  std::string reason="not_started", entity_id, source_map_id;
  std::string model_hash, preparation_hash, configuration_id;
  BackendCapabilities backend;
  KernelProfile profile;
  std::vector<TransientSample> samples;
  std::vector<StepRecord> steps;
  std::vector<EventRecord> events;
  std::optional<TransientCheckpoint> checkpoint; // Last committed, post-event state only.
};
// Invalid input throws a bounded Error. Numerical failures return valid=false,
// retain committed samples/checkpoint and report rejected attempts explicitly.
TransientResult solve_transient(const Assembly&, const TransientOptions&,
                                std::optional<TransientCheckpoint> restart={});
std::string inspect_transient(std::string_view);
std::string inspect_thermal_capabilities();
// Shared owned SHA-256 implementation, also used for checkpoint/configuration binding.
std::string thermal_digest(std::string_view);
} // namespace fcst::thermal
