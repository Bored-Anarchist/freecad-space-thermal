// SPDX-License-Identifier: MIT OR Apache-2.0
#include "fcst/thermal.hpp"
#include <algorithm>
#include <cmath>
#include <utility>

namespace fcst::thermal {
namespace {
double finite(double value) {
  if (!std::isfinite(value)) throw Error("range");
  return value == 0 ? 0 : value;
}
void bounds(double lo, double hi) {
  if (!std::isfinite(lo) || !std::isfinite(hi) || lo < 0 || lo >= hi) throw Error("range");
}
}
Error::Error(std::string code_, std::string entity, std::string source)
    : std::runtime_error("Thermal input or property rejected"), code(std::move(code_)),
      entity_id(std::move(entity)), source_map_id(std::move(source)) {}
PropertyLaw::PropertyLaw(double constant, double lo, double hi)
    : y_{constant}, minimum_(lo), maximum_(hi) {
  bounds(lo, hi);
  if (!std::isfinite(constant) || constant <= 0) throw Error("range");
}
PropertyLaw::PropertyLaw(std::vector<double> temperatures, std::vector<double> values,
                        Interpolation interpolation, Extrapolation extrapolation,
                        std::vector<std::size_t> discontinuities, double lo, double hi)
    : x_(std::move(temperatures)), y_(std::move(values)), jumps_(std::move(discontinuities)),
      interpolation_(interpolation), extrapolation_(extrapolation), minimum_(lo), maximum_(hi) {
  bounds(lo, hi);
  if (x_.size() < 2 || x_.size() > 16384 || x_.size() != y_.size()) throw Error("range");
  if ((interpolation_ != Interpolation::linear && interpolation_ != Interpolation::previous) ||
      (extrapolation_ != Extrapolation::error && extrapolation_ != Extrapolation::clamp)) throw Error("range");
  for (std::size_t i = 0; i < x_.size(); ++i) {
    if (!std::isfinite(x_[i]) || x_[i] < lo || x_[i] > hi ||
        !std::isfinite(y_[i]) || y_[i] <= 0 || (i && x_[i] <= x_[i-1])) throw Error("range");
    if (i && interpolation_ == Interpolation::linear)
      finite((y_[i] - y_[i-1]) / (x_[i] - x_[i-1]));
  }
  std::sort(jumps_.begin(), jumps_.end());
  if (std::adjacent_find(jumps_.begin(), jumps_.end()) != jumps_.end()) throw Error("range");
  for (auto i : jumps_) if (i == 0 || i >= x_.size() || interpolation_ != Interpolation::previous) throw Error("range");
  // Every actual step must be declared, including a changed final endpoint.
  if (interpolation_ == Interpolation::previous)
    for (std::size_t i = 1; i < y_.size(); ++i)
      if (y_[i] != y_[i-1] && !std::binary_search(jumps_.begin(), jumps_.end(), i)) throw Error("range");
  if (extrapolation_ == Extrapolation::error && (x_.front() != lo || x_.back() != hi)) throw Error("range");
}
void PropertyLaw::check_temperature(double t) const {
  if (!std::isfinite(t) || t < minimum_ || t > maximum_) throw Error("range");
}
Sample PropertyLaw::sample(double t) const {
  check_temperature(t);
  if (x_.empty()) return {y_.front(), 0, false};
  if (t < x_.front() || t > x_.back()) {
    if (extrapolation_ != Extrapolation::clamp) throw Error("range");
    return {t < x_.front() ? y_.front() : y_.back(), 0, false};
  }
  auto right = std::upper_bound(x_.begin(), x_.end(), t);
  std::size_t i = static_cast<std::size_t>(right - x_.begin()) - 1;
  bool jump = std::binary_search(jumps_.begin(), jumps_.end(), i) && t == x_[i];
  if (interpolation_ == Interpolation::previous) return {y_[i], 0, jump};
  if (i + 1 == x_.size()) --i;
  double fraction = (t - x_[i]) / (x_[i+1] - x_[i]);
  return {finite(std::lerp(y_[i], y_[i+1], fraction)),
          finite((y_[i+1] - y_[i]) / (x_[i+1] - x_[i])), false};
}
double PropertyLaw::integral(double from, double to) const {
  check_temperature(from); check_temperature(to);
  if (from == to) return 0;
  bool reverse = from > to;
  double a = std::min(from, to), b = std::max(from, to), total = 0;
  std::vector<double> cuts{a};
  for (double x : x_) if (x > a && x < b) cuts.push_back(x);
  cuts.push_back(b);
  for (std::size_t i = 1; i < cuts.size(); ++i) {
    double left = cuts[i-1], right = cuts[i];
    // Split at every knot; previous is right-continuous and never bridges a jump.
    double mean = sample(left).value;
    if (interpolation_ == Interpolation::linear && !x_.empty())
      mean = finite(mean / 2 + sample(right).value / 2);
    total = finite(total + finite((right-left) * mean));
  }
  return reverse ? -total : total;
}
double Material::specific_enthalpy_change(double from, double to) const {
  return specific_heat.integral(from, to);
}
Material::Material(std::string id_, PropertyLaw density_, PropertyLaw specific_heat_, PropertyLaw conductivity_,
                   std::optional<Tensor> tensor_, std::optional<std::string> frame_)
    : id(std::move(id_)), density(std::move(density_)), specific_heat(std::move(specific_heat_)),
      conductivity(std::move(conductivity_)), conductivity_tensor(std::move(tensor_)), frame_id(std::move(frame_)) {
  if (conductivity_tensor.has_value() != frame_id.has_value()) throw Error("frame", id);
  if (!conductivity_tensor) return;
  const auto& k = *conductivity_tensor;
  double scale = 0;
  for (std::size_t i = 0; i < 3; ++i)
    for (std::size_t j = 0; j < 3; ++j) {
      if (!std::isfinite(k[i][j]) || k[i][j] != k[j][i]) throw Error("range", id);
      scale = std::max(scale,std::abs(k[i][j]));
    }
  if (scale == 0 || k[0][0] <= 0) throw Error("range", id);
  const double l00 = std::sqrt(k[0][0]/scale), l10 = k[1][0]/scale/l00, l20 = k[2][0]/scale/l00;
  const double pivot = k[1][1]/scale-l10*l10;
  if (!std::isfinite(pivot) || pivot <= 0) throw Error("range", id);
  const double l21 = (k[2][1]/scale-l20*l10)/std::sqrt(pivot);
  const double last = k[2][2]/scale-l20*l20-l21*l21;
  if (!std::isfinite(last) || last <= 0) throw Error("range", id);
}
Tensor Material::tensor(double t) const {
  if (conductivity_tensor) { (void)conductivity.sample(t); return *conductivity_tensor; }
  double k = conductivity.sample(t).value;
  return {{{k,0,0},{0,k,0},{0,0,k}}};
}
Model::Model(Data data) : data_(std::move(data)) {}
double Model::storage_capacity(std::size_t index, double t) const {
  const auto& node = data_.nodes.at(index);
  if (!std::isfinite(t) || t < 0) throw Error("range", node.id);
  if (node.classification != NodeClass::capacitive) return 0;
  if (!node.material_index) return node.capacity;
  try { return finite(node.mass * data_.materials.at(*node.material_index).specific_heat.sample(t).value); }
  catch (Error& e) { e.entity_id = node.id; throw; }
}
double Model::storage_change(std::size_t index, double from, double to) const {
  const auto& node = data_.nodes.at(index);
  if (!std::isfinite(from) || !std::isfinite(to) || from < 0 || to < 0) throw Error("range", node.id);
  if (node.classification != NodeClass::capacitive) return 0;
  try {
    if (!node.material_index) return finite(node.capacity * (to-from));
    return finite(node.mass * data_.materials.at(*node.material_index).specific_enthalpy_change(from, to));
  } catch (Error& e) { e.entity_id = node.id; throw; }
}
} // namespace fcst::thermal
