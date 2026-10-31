// SPDX-License-Identifier: MIT OR Apache-2.0
#pragma once
#include "fcst/thermal_assembly.hpp"
#include <array>
#include <limits>

namespace fcst::radiation {
using Vec3 = std::array<double,3>;
struct OpticalDataset {
  std::string solar_band="solar", infrared_band="infrared";
  double minimum_temperature=0, maximum_temperature=10000;
  std::string condition="unspecified", provenance="caller constant-gray declaration";
  std::array<double,2> absolute_uncertainty{0,0}; // Solar, infrared; not sampling error.
  bool operator==(const OpticalDataset&) const=default;
};
struct Optics {
  double solar_absorptance=1, ir_emittance=1;
  bool active=true;
  OpticalDataset dataset{};
};
struct Facet {
  std::string id, surface_id, group;
  std::size_t node=0;
  std::array<Vec3,3> vertices;
  Optics front;
  Optics back{1,1,false};
};
struct Patch {
  std::string id, surface_id, group;
  std::size_t node;
  bool back;
  double area;
  Optics optics;
};
struct Ray { Vec3 origin, direction; };
struct Hit { std::size_t facet; bool back; double distance; };
class IntersectionBackend {
 public:
  virtual ~IntersectionBackend()=default;
  virtual std::optional<Hit> intersect(const Ray&, std::optional<std::size_t> ignore={}) const=0;
};
// Immutable median BVH; deterministic nearest-hit/tie policy, no external runtime.
class Mesh final : public IntersectionBackend {
 public:
  explicit Mesh(std::vector<Facet>, std::vector<std::string> excluded_facets={});
  std::optional<Hit> intersect(const Ray&, std::optional<std::size_t> ignore={}) const override;
  const std::vector<Facet>& facets() const;
  const std::vector<Patch>& patches() const;
  std::optional<std::size_t> patch(std::size_t facet, bool back) const;
  std::size_t storage_bytes() const;
 private:
  struct Impl;
  std::shared_ptr<const Impl> impl_;
  friend struct Sampler;
};
struct Count { std::size_t target; std::uint64_t hits; };
struct Row {
  std::size_t source;
  std::uint64_t samples, escaped=0, blocked=0;
  std::vector<Count> counts;
};
struct Sampling {
  std::uint64_t seed=1701, samples=4096;
  std::size_t maximum_entries=1000000;
};
// Each row has an independent stream keyed by seed and stable surface/side ID.
// A caller can stream rows without allocating an all-pairs exchange table.
Row trace_row(const Mesh&, std::size_t source, const Sampling&, const IntersectionBackend* backend=nullptr);
struct Interval { double estimate, lower, upper; };
Interval wilson(std::uint64_t hits, std::uint64_t samples, double normal_quantile);
struct Edge { std::size_t first, second; double area_factor; };
struct Diagnostics {
  double maximum_raw_reciprocity=0, maximum_correction=0, maximum_raw_closure=0;
  std::size_t raw_entries=0;
};
class Exchange {
 public:
  // Records must contain every source exactly once; raw evidence remains available.
  Exchange(std::vector<Patch>, std::vector<Row>, std::size_t maximum_edges=1000000);
  const std::vector<Patch>& patches() const { return patches_; }
  const std::vector<Row>& raw() const { return raw_; }
  const std::vector<Edge>& edges() const { return edges_; }
  const std::vector<double>& escape() const { return escape_; }
  const Diagnostics& diagnostics() const { return diagnostics_; }
  std::vector<Edge> page(std::size_t offset, std::size_t limit) const;
 private:
  std::vector<Patch> patches_;
  std::vector<Row> raw_;
  std::vector<Edge> edges_;
  std::vector<double> escape_;
  Diagnostics diagnostics_;
};
Exchange trace(const Mesh&, const Sampling&);
struct Evaluation {
  std::vector<double> radiosity, solar_radiosity, internal_power, environment;
  std::size_t iterations=0;
  double linear_defect=0;
};
struct RadiosityOptions {
  double background_temperature=0, tolerance=1e-12;
  std::size_t maximum_iterations=100000;
  // Incident W/m2 on each patch, already projected/occluded by an environment model.
  std::vector<double> solar_incident;
};
Evaluation evaluate(const Exchange&, std::span<const double> node_temperatures, const RadiosityOptions& = {});
// Separate conservative internal_power and external callbacks; bounded node Jacobian.
std::vector<thermal::PowerBinding> bind(std::shared_ptr<const Exchange>, std::string radiation_id,
  std::string environment_id, RadiosityOptions = {}, std::size_t maximum_dependencies=65536);
std::string inspect(std::string_view, bool steady=false);
} // namespace fcst::radiation
