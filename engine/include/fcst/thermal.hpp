// SPDX-License-Identifier: MIT OR Apache-2.0
#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <tuple>
#include <vector>

namespace fcst::thermal {
struct Error : std::runtime_error {
  std::string code, entity_id, source_map_id;
  explicit Error(std::string code_, std::string entity = {}, std::string source = {});
};
enum class Interpolation { linear, previous };
enum class Extrapolation { error, clamp };
struct Sample { double value, derivative; bool discontinuous; };

// Values are SI. Construction validates the entire supported domain.
class PropertyLaw {
 public:
  PropertyLaw(double constant, double minimum_temperature, double maximum_temperature);
  PropertyLaw(std::vector<double> temperatures, std::vector<double> values,
              Interpolation interpolation, Extrapolation extrapolation,
              std::vector<std::size_t> discontinuities,
              double minimum_temperature, double maximum_temperature);
  Sample sample(double temperature) const;
  double integral(double from_temperature, double to_temperature) const;
 private:
  std::vector<double> x_, y_;
  std::vector<std::size_t> jumps_;
  Interpolation interpolation_ = Interpolation::linear;
  Extrapolation extrapolation_ = Extrapolation::error;
  double minimum_, maximum_;
  void check_temperature(double temperature) const;
};
using Tensor = std::array<std::array<double, 3>, 3>;
struct Material {
  Material(std::string id_, PropertyLaw density_, PropertyLaw specific_heat_, PropertyLaw conductivity_,
           std::optional<Tensor> tensor_, std::optional<std::string> frame_);
  std::string id;
  PropertyLaw density, specific_heat, conductivity;
  std::optional<Tensor> conductivity_tensor;
  std::optional<std::string> frame_id;
  double specific_enthalpy_change(double from, double to) const;
  Tensor tensor(double temperature) const;
};
enum class NodeClass { capacitive, algebraic, prescribed };
struct Node {
  std::string id, submodel_id;
  NodeClass classification;
  double temperature, capacity;
  std::optional<std::size_t> equation, differential_index, algebraic_index;
  std::optional<std::size_t> material_index;
  double mass = 0;
};
struct Conductor { std::string id; std::size_t from, to; double conductance; };
struct Load { std::string id; std::size_t node; double power; std::optional<std::string> expression_id; bool active; };
struct Environment {
  std::string id, frame_id, epoch, time_scale;
  double background_temperature, solar_flux, time_origin;
};
struct Radiation {
  std::string id, environment_id, method;
  std::vector<std::string> facet_ids, excluded_facet_ids;
};
struct SourceIdentity {
  std::string source_map_id, source_revision, source_tool, source_version;
  std::string name_space, handle, entity_id;
  std::optional<std::string> submodel_handle;
  std::optional<std::uint64_t> node_number;
};
struct Component {
  std::vector<std::size_t> nodes;
  bool prescribed_anchor = false;
  bool storage_anchor = false;
  // For the nonnegative conductive graph only; radiation/other callbacks may add anchors later.
  bool steady_conduction_singular = false;
  bool transient_algebraic_singular = false;
};
struct Data {
  std::string project_id, model_hash, preparation_hash, canonical_snapshot;
  std::optional<std::string> case_id;
  std::vector<Node> nodes;
  std::vector<Material> materials;
  std::vector<Conductor> conductors;
  std::vector<Load> loads;
  std::vector<Environment> environments;
  std::vector<Radiation> radiation;
  std::vector<std::string> active_environment_ids, active_control_ids, spatial_element_ids;
  std::vector<SourceIdentity> source_identities;
  std::map<std::string, std::vector<std::size_t>> sources_by_entity;
  std::map<std::tuple<std::string, std::string, std::string>, std::size_t> source_index;
  std::vector<Component> components;
  std::vector<std::string> deferred_entity_ids;
  std::size_t differential_count = 0, algebraic_count = 0;
};
class Model {
 public:
  const Data& data() const { return data_; }
  double storage_capacity(std::size_t node, double temperature) const;
  Sample storage_capacity_sample(std::size_t node, double temperature) const;
  double storage_change(std::size_t node, double from, double to) const;
 private:
  explicit Model(Data data);
  friend Model load(std::string_view input);
  const Data data_;
};
// Bounded, strict thermal-input-v1 JSON. Owns a frozen, SI-normalized copy.
Model load(std::string_view input);
std::string inspect(std::string_view input);
} // namespace fcst::thermal
