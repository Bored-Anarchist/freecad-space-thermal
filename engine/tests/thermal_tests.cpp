// SPDX-License-Identifier: MIT OR Apache-2.0
#include "fcst/thermal.hpp"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <string>
#include <type_traits>
#include <utility>

using namespace fcst::thermal;
namespace {
void require(bool okay) { if (!okay) throw std::runtime_error("acceptance_failed"); }
void near(double observed, double expected, double tolerance = 1e-12) {
  require(std::isfinite(observed) && std::abs(observed-expected) <= tolerance*std::max(1.0, std::abs(expected)));
}
template<class F> void rejects(F function) {
  bool rejected = false;
  try { function(); } catch (const Error&) { rejected = true; }
  require(rejected);
}
std::string fixture(const char* path) {
  std::ifstream file(path, std::ios::binary);
  require(file.good());
  return {std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>()};
}
}
int main(int argc, char** argv) {
  try {
    require(argc == 3);
    std::string name = argv[1];
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double inf = std::numeric_limits<double>::infinity();
    if (name == "constant-law") {
      PropertyLaw law(3, 200, 400);
      for (double t : {200., 300., 400.}) { near(law.sample(t).value, 3); near(law.sample(t).derivative, 0); }
      near(law.integral(200, 400), 600); near(law.integral(400, 200), -600);
      near(law.integral(300, 300), 0);
      rejects([&] { law.sample(199); }); rejects([&] { law.integral(300, 401); });
    } else if (name == "linear-law") {
      // Independently specified cp(T)=T/100, and a slope change at 300 K.
      PropertyLaw law({200,300,400}, {2,3,5}, Interpolation::linear, Extrapolation::error, {}, 200, 400);
      near(law.sample(250).value, 2.5); near(law.sample(300).derivative, .02);
      near(law.sample(400).value, 5); near(law.sample(400).derivative, .02);
      near(law.integral(200,400), 650); near(law.integral(275,325), 153.125);
      near(law.integral(200,275)+law.integral(275,400), 650);
      double h = 1e-3;
      near((law.integral(200,350+h)-law.integral(200,350-h))/(2*h), law.sample(350).value, 1e-9);
    } else if (name == "previous-law") {
      PropertyLaw law({200,300,400}, {2,5,7}, Interpolation::previous, Extrapolation::error, {1,2}, 200, 400);
      near(law.sample(299.999).value, 2); near(law.sample(300).value, 5);
      require(law.sample(300).discontinuous); require(!law.sample(301).discontinuous);
      near(law.sample(400).value, 7); require(law.sample(400).discontinuous);
      near(law.integral(200,400), 700); near(law.integral(350,250), -350);
      near(law.integral(200,300)+law.integral(300,400), 700);
    } else if (name == "clamped-law") {
      PropertyLaw law({250,350}, {2,4}, Interpolation::linear, Extrapolation::clamp, {}, 200,400);
      near(law.sample(200).value,2); near(law.sample(400).value,4);
      near(law.sample(249).derivative,0); near(law.integral(200,400),600);
      rejects([&] { law.sample(401); });
      PropertyLaw step({250,350}, {2,4}, Interpolation::previous, Extrapolation::clamp, {1}, 200,400);
      near(step.integral(200,400), 500);
    } else if (name == "invalid-laws") {
      for (double invalid : {0., -1., nan, inf}) rejects([&] { PropertyLaw law(invalid,200,400); });
      rejects([&] { PropertyLaw law(1,400,200); });
      rejects([&] { PropertyLaw law(1,-1,400); });
      rejects([&] { PropertyLaw law(1,200,inf); });
      auto invalid = [&](std::vector<double> x, std::vector<double> y, Interpolation interpolation,
                         std::vector<std::size_t> jumps) {
        rejects([&] { PropertyLaw law(x,y,interpolation,Extrapolation::error,jumps,200,400); });
      };
      invalid({200,200},{1,2},Interpolation::linear,{});
      invalid({200,400},{1},Interpolation::linear,{});
      invalid({200,400},{1,0},Interpolation::linear,{});
      invalid({200,400},{1,nan},Interpolation::linear,{});
      invalid({200,inf},{1,2},Interpolation::linear,{});
      invalid({250,350},{1,2},Interpolation::linear,{});
      invalid({200,400},{1,2},Interpolation::linear,{1});
      invalid({200,400},{1,2},Interpolation::previous,{});
      invalid({200,400},{1,2},Interpolation::previous,{0,1});
      invalid({200,400},{1,2},Interpolation::previous,{1,1});
      invalid({200,400},{1,2},Interpolation::previous,{2});
      PropertyLaw law(1,200,400);
      rejects([&] { law.sample(nan); }); rejects([&] { law.integral(nan,300); });
      rejects([&] { PropertyLaw huge(1e308,0,1e308); (void)huge.integral(0,1e308); });
    } else if (name == "storage") {
      auto model = load(fixture(argv[2]));
      near(model.storage_capacity(0,350),7);
      near(model.storage_change(0,300,350),325);
      near(model.storage_change(0,350,300),-325);
      near(model.storage_change(0,200,300)+model.storage_change(0,300,400),1200);
      near(model.storage_capacity(1,300),0); near(model.storage_change(2,200,400),0);
      near(model.data().materials.at(0).density.sample(250).value,2);
      rejects([&] { model.storage_capacity(0,401); });
      rejects([&] { model.storage_change(0,nan,300); });
    } else if (name == "tensor") {
      auto model = load(fixture(argv[2]));
      auto tensor = model.data().materials.at(0).tensor(300);
      // q=-K grad(T), for grad(T)=(1,2,3), in the declared material frame.
      const std::array<double,3> gradient{1,2,3}, expected{-4,-7,-12};
      for (std::size_t i = 0; i < 3; ++i) {
        double flux = 0;
        for (std::size_t j = 0; j < 3; ++j) flux -= tensor[i][j]*gradient[j];
        near(flux,expected[i]);
      }
      Material isotropic{"synthetic", PropertyLaw(1,200,400), PropertyLaw(1,200,400), PropertyLaw(4,200,400), {}, {}};
      auto k = isotropic.tensor(300); near(k[0][0],4); near(k[0][1],0);
      rejects([&] { model.data().materials.at(0).tensor(401); });
    } else if (name == "immutable-loading") {
      static_assert(std::is_same_v<decltype(std::declval<Model>().data()), const Data&>);
      auto bytes = fixture(argv[2]); auto model = load(bytes); auto hash = model.data().preparation_hash;
      bytes.assign("untrusted replacement");
      const auto& d = model.data();
      require(d.preparation_hash == hash && d.nodes.size() == 3);
      require(d.nodes[0].equation == 0 && d.nodes[0].differential_index == 0);
      require(d.nodes[1].equation == 1 && d.nodes[1].algebraic_index == 0);
      require(!d.nodes[2].equation && d.differential_count == 1 && d.algebraic_count == 1);
      require(d.source_identities.size() == 3 && d.source_index.size() == 3);
      require(d.sources_by_entity.at(d.nodes[0].id).size() == 2);
      require(d.source_identities[0].node_number == 101);
      require(d.components.size() == 1 && !d.components[0].steady_conduction_singular);
      near(d.nodes[0].temperature,300); near(d.conductors[0].conductance,2); near(d.loads[0].power,5);
    } else if (name == "case-loading") {
      auto path = std::string(argv[2]);
      path.replace(path.rfind("material-network.json"), std::string("material-network.json").size(), "case-network.json");
      auto model = load(fixture(path.c_str()));
      const auto& d = model.data();
      near(d.nodes[0].temperature,350); near(d.conductors[0].conductance,0);
      near(d.loads[0].power,7); require(d.loads[0].active && !d.loads[1].active);
      near(model.storage_change(0,300,350),300); // constant explicit 6 J/K, no material binding
      require(d.components.size() == 2 && d.case_id.has_value());
    } else throw std::runtime_error("unknown_case");
    std::cout << "{\"status\":\"passed\"}\n";
    return 0;
  } catch (...) {
    // Raw fixture values, source identities and paths never enter the public result.
    std::cout << "{\"status\":\"failed\"}\n";
    return 1;
  }
}
