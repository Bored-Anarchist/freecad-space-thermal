// SPDX-License-Identifier: MIT OR Apache-2.0
#include "fcst/thermal_assembly.hpp"
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <numeric>
#include <string>

using namespace fcst::thermal;
namespace {
void require(bool okay) { if (!okay) throw std::runtime_error("acceptance_failed"); }
void near(double observed, double expected, double tolerance = 1e-10) {
  require(std::isfinite(observed) && std::abs(observed-expected) <= tolerance*std::max(1.0,std::abs(expected)));
}
template<class F> Error rejects(F function, const std::string& code) {
  try { function(); } catch (const Error& e) { require(e.code == code); return e; }
  throw std::runtime_error("expected_rejection");
}
Model fixture(const std::filesystem::path& folder, const std::string& name = "material-network.json") {
  std::ifstream file(folder/name,std::ios::binary);
  require(file.good());
  return load(std::string(std::istreambuf_iterator<char>(file),std::istreambuf_iterator<char>()));
}
std::string uid(unsigned n) {
  auto number = std::to_string(n);
  return "00000000-0000-4000-8000-" + std::string(12-number.size(),'0') + number;
}
PowerBinding constant_load(double watts) {
  return {uid(12),PowerKind::load,{0},{},[watts](double,std::span<const double>,bool) { return PowerEvaluation{{watts},{}}; }};
}
std::vector<PowerBinding> powers() {
  PowerBinding load_term{uid(12),PowerKind::load,{0},{{0,1}},[](double time,std::span<const double> t,bool jacobian) {
    double delta = t[1]-300;
    return PowerEvaluation{{5+.01*delta*delta+.5*time},jacobian ? std::vector<double>{.02*delta} : std::vector<double>{}};
  }};
  PowerBinding radiation{uid(22),PowerKind::radiation,{0,1},{{0,0},{0,1},{1,0},{1,1}},[](double,std::span<const double> t,bool jacobian) {
    double q = -1e-8*(std::pow(t[0],4)-std::pow(t[1],4));
    double a = -4e-8*std::pow(t[0],3), b = 4e-8*std::pow(t[1],3);
    return PowerEvaluation{{q,-q},jacobian ? std::vector<double>{a,b,-a,-b} : std::vector<double>{}};
  }};
  PowerBinding environment{uid(14),PowerKind::environment,{0,1,2},{{0,0},{1,1},{2,2}},[](double,std::span<const double> t,bool jacobian) {
    return PowerEvaluation{{-.1*(t[0]-250),-.1*(t[1]-250),-.1*(t[2]-250)},
      jacobian ? std::vector<double>{-.1,-.1,-.1} : std::vector<double>{}};
  }};
  return {load_term,radiation,environment};
}
void conservation(const Balance& b) {
  auto sum = [](const auto& values) { return std::accumulate(values.begin(),values.end(),0.0); };
  near(sum(b.conductive_in),0);
  near(sum(b.radiation_in),0); // The synthetic fixture's radiation term is closed internal exchange.
  near(b.energy_defect,sum(b.residual));
  near(sum(b.storage_power)-sum(b.load_in)-sum(b.radiation_in)-sum(b.environment_in)-sum(b.boundary_power),b.energy_defect);
}
struct ExactLinear final : LinearBackend {
  SolveResult result{SolveStatus::converged,{5,2.5},1,999};
  bool throws = false;
  SolveResult solve(const SparseMatrix& matrix,std::span<const double> rhs,const SolveOptions&) const override {
    near(matrix.at({0,0}),2); near(matrix.at({0,1}),-2); near(matrix.at({1,1}),4);
    near(rhs[0],5); near(rhs[1],0);
    if (throws) throw Error("opaque-marker");
    return result;
  }
};
struct ExactNonlinear final : NonlinearBackend {
  SolveResult result{SolveStatus::converged,{305,302.5},1,999};
  bool throws = false, invalid_probe = false;
  SolveResult solve(const NonlinearProblem& problem,std::span<const double> initial,const SolveOptions&) const override {
    if (throws) throw Error("opaque-marker");
    if (invalid_probe) {
      // A backend cannot swallow malformed problem evaluations and still claim success.
      try { (void)problem.evaluate(std::vector<double>{1},true); } catch (...) {}
    }
    auto value = problem.evaluate(initial,true);
    near(value.residual[0],-5); near(value.jacobian->at({0,0}),2); near(value.jacobian->at({1,1}),4);
    return result;
  }
};
}
int main(int argc,char** argv) {
  try {
    require(argc == 3);
    std::string name = argv[1];
    std::filesystem::path folder(argv[2]);
    double nan = std::numeric_limits<double>::quiet_NaN();
    if (name == "balance") {
      Assembly network(fixture(folder));
      auto b = network.residual({0,{320,310},{1}});
      near(b.storage_power[0],6.4); near(b.conductor_power[0],20); near(b.conductor_power[1],20);
      near(b.residual[0],21.4); near(b.residual[1],0); near(b.boundary_power[2],-20);
      near(b.energy_defect,21.4); conservation(b);
      auto replaced = Assembly(fixture(folder),{constant_load(10)}).residual({0,{320,310},{0}});
      near(replaced.load_in[0],10); near(replaced.residual[0],10); conservation(replaced);
      auto backflow = network.residual({0,{280,290},{0}});
      near(backflow.conductor_power[0],-20); near(backflow.boundary_power[2],20);
      near(backflow.residual[0],-25); conservation(backflow);
    } else if (name == "algebraic-boundary") {
      Assembly network(fixture(folder));
      auto result = network.linearize({0,{330,315},{2}});
      near(result.balance.residual[1],0); near(result.balance.storage_power[1],0);
      near(result.d_rate.at({1,1}),0); near(result.d_rate.at({0,0}),6.6);
      near(result.d_temperature.at({1,0}),-2); near(result.d_temperature.at({1,1}),4);
      near(result.balance.boundary_power[2],-30); conservation(result.balance);
      Assembly fixed(fixture(folder,"prescribed-network.json"));
      auto all = fixed.residual({0,{}, {}});
      require(all.residual.empty() && fixed.sparsity()->dimension() == 0);
      near(all.boundary_power[0],-5); near(all.energy_defect,0);
      for (double storage : all.storage_power) near(storage,0);
      auto zero = fixed.steady_linearize(0,{}); require(zero.d_temperature.values().empty());
    } else if (name == "enthalpy-step") {
      Assembly network(fixture(folder));
      auto result = network.step_linearize(5,std::vector<double>{350,325},std::vector<double>{300,300},5);
      near(result.balance.storage_power[0],65); near(result.balance.residual[0],110);
      near(result.balance.residual[1],0); near(result.d_temperature.at({0,0}),3.4);
      near(result.d_temperature.at({0,1}),-2); near(result.d_temperature.at({1,1}),4);
      for (double mass : result.d_rate.values()) near(mass,0);
      conservation(result.balance);
      auto reverse = network.step_residual(5,std::vector<double>{300,300},std::vector<double>{350,325},5);
      near(reverse.storage_power[0],-65); conservation(reverse);
    } else if (name == "jacobian-differences") {
      Assembly network(fixture(folder,"power-network.json"),powers());
      State state{1.25,{320,310},{.7}};
      const double h = 1e-3, alpha = .4;
      auto jac = network.linearize(state); auto combined = jac.combined(alpha);
      conservation(jac.balance);
      for (std::size_t j = 0; j < state.temperature.size(); ++j) {
        auto plus = state, minus = state;
        plus.temperature[j] += h; minus.temperature[j] -= h;
        auto p = network.residual(plus), m = network.residual(minus);
        auto sp = network.steady_residual(state.time,plus.temperature), sm = network.steady_residual(state.time,minus.temperature);
        auto sj = network.steady_linearize(state.time,state.temperature);
        auto ep = network.step_residual(state.time,plus.temperature,std::vector<double>{300,300},2);
        auto em = network.step_residual(state.time,minus.temperature,std::vector<double>{300,300},2);
        auto ej = network.step_linearize(state.time,state.temperature,std::vector<double>{300,300},2);
        for (std::size_t i = 0; i < p.residual.size(); ++i) {
          near((p.residual[i]-m.residual[i])/(2*h),jac.d_temperature.at({i,j}),2e-8);
          near((sp.residual[i]-sm.residual[i])/(2*h),sj.d_temperature.at({i,j}),2e-8);
          near((ep.residual[i]-em.residual[i])/(2*h),ej.d_temperature.at({i,j}),2e-8);
        }
        for (const auto& node : network.model().data().nodes) if (node.equation == j && node.differential_index) {
          plus.rate[*node.differential_index] += alpha*h; minus.rate[*node.differential_index] -= alpha*h;
        }
        p = network.residual(plus); m = network.residual(minus);
        for (std::size_t i = 0; i < p.residual.size(); ++i) near((p.residual[i]-m.residual[i])/(2*h),combined.at({i,j}),2e-8);
      }
      auto plus = state, minus = state; plus.rate[0] += h; minus.rate[0] -= h;
      auto p = network.residual(plus), m = network.residual(minus);
      for (std::size_t i = 0; i < p.residual.size(); ++i) near((p.residual[i]-m.residual[i])/(2*h),jac.d_rate.at({i,0}),2e-8);
      near(jac.d_rate.at({0,1}),0); near(jac.d_rate.at({1,1}),0);
    } else if (name == "callback-contracts") {
      auto good = powers();
      rejects([&] { Assembly a(fixture(folder,"power-network.json")); },"callback_missing");
      for (const auto& mode : {"duplicate","node","dependency","missing-function","coverage"}) {
        auto bindings = good;
        if (std::string(mode) == "duplicate") bindings.push_back(bindings.front());
        if (std::string(mode) == "node") bindings[0].affected_nodes = {999};
        if (std::string(mode) == "dependency") bindings[0].dependencies.push_back({0,1});
        if (std::string(mode) == "missing-function") bindings[0].evaluate = {};
        if (std::string(mode) == "coverage") { bindings[2].affected_nodes = {0}; bindings[2].dependencies = {{0,0}}; }
        rejects([&] { Assembly a(fixture(folder,"power-network.json"),bindings); },
          std::string(mode) == "duplicate" ? "duplicate_id" : std::string(mode) == "node" ? "dimension" :
          std::string(mode) == "dependency" ? "sparsity" : std::string(mode) == "missing-function" ? "callback_missing" : "callback_coverage");
      }
      auto invalid = good;
      invalid[0].evaluate = [](double,std::span<const double>,bool) { return PowerEvaluation{{1},{}}; };
      Assembly wrong(fixture(folder,"power-network.json"),invalid);
      rejects([&] { wrong.linearize({0,{320,310},{0}}); },"dimension");
      invalid[0].evaluate = [nan](double,std::span<const double>,bool) { return PowerEvaluation{{nan},{}}; };
      rejects([&] { Assembly(fixture(folder,"power-network.json"),invalid).residual({0,{320,310},{0}}); },"range");
      invalid[0].evaluate = [](double,std::span<const double>,bool) -> PowerEvaluation { throw std::runtime_error("opaque-marker"); };
      auto error = rejects([&] { Assembly(fixture(folder,"power-network.json"),invalid).residual({0,{320,310},{0}}); },"callback_failure");
      require(error.entity_id == uid(12) && std::string(error.what()).find("opaque-marker") == std::string::npos);
    } else if (name == "boundary-callback") {
      Assembly network(fixture(folder),{},{{2,[](double t) { return 300+2*t; }}});
      auto b = network.residual({5,{330,320},{0}});
      near(b.temperature[2],310); near(b.residual[1],0); near(b.boundary_power[2],-20); conservation(b);
      Assembly coupled(fixture(folder,"power-network.json"),powers(),{{2,[](double) { return 310.; }}});
      auto effective = coupled.residual({0,{330,320},{0}});
      near(effective.environment_in[2],-6); near(effective.boundary_power[2],-14); conservation(effective);
      rejects([&] { Assembly a(fixture(folder),{},{{0,[](double) { return 300.; }}}); },"boundary");
      rejects([&] { Assembly a(fixture(folder),{},{{2,[](double) { return 300.; }},{2,[](double) { return 300.; }}}); },"boundary");
      rejects([&] { Assembly(fixture(folder),{},{{2,[nan](double) { return nan; }}}).residual({0,{320,310},{0}}); },"range");
      rejects([&] { Assembly(fixture(folder),{},{{2,[](double) { return -1.; }}}).residual({0,{320,310},{0}}); },"range");
    } else if (name == "singular-components") {
      Assembly algebraic(fixture(folder,"algebraic-network.json"));
      auto a = algebraic.linearize({0,{300,300,300},{}});
      near(a.balance.residual[0],-5);
      for (double mass : a.d_rate.values()) near(mass,0);
      require(algebraic.model().data().components.front().transient_algebraic_singular);
      Assembly isolated(fixture(folder,"isolated-network.json"));
      auto i = isolated.residual({0,{300,300},{1}});
      near(i.residual[0],1); near(i.residual[1],0); conservation(i);
      require(!isolated.model().data().components.front().transient_algebraic_singular);
    } else if (name == "sparsity") {
      // 100,000-node tridiagonal manufactured operator: bounded sparse storage only.
      constexpr std::size_t n = 100000;
      std::vector<Entry> entries; entries.reserve(3*n);
      for (std::size_t i = 0; i < n; ++i) {
        entries.push_back({i,i}); if (i) entries.push_back({i,i-1}); if (i+1<n) entries.push_back({i,i+1});
      }
      entries.push_back({0,0}); std::reverse(entries.begin(),entries.end());
      auto pattern = std::make_shared<Sparsity>(n,std::move(entries));
      require(pattern->nonzeros() == 3*n-2 && pattern->offsets().size() == n+1);
      SparseMatrix matrix(pattern); std::vector<double> x(n);
      for (std::size_t i = 0; i < n; ++i) {
        x[i] = 1+static_cast<double>(i)/n;
        matrix.add({i,i},2); if (i) matrix.add({i,i-1},-1); if (i+1<n) matrix.add({i,i+1},-1);
      }
      auto y = matrix.multiply(x);
      near(y.front(),1-1.0/n); near(y.back(),2);
      for (std::size_t i = 1; i+1<n; ++i) near(y[i],0);
      near(matrix.at({0,n-1}),0);
      rejects([&] { matrix.add({0,n-1},1); },"sparsity");
      rejects([&] { Sparsity invalid(2,{{2,0}}); },"dimension");
      // A callback adds a nonlocal coupling absent from the conductive graph.
      PowerBinding nonlocal{uid(12),PowerKind::load,{0},{{0,1}},[](double,std::span<const double> t,bool jacobian) {
        return PowerEvaluation{{7+.5*(t[1]-300)},jacobian ? std::vector<double>{.5} : std::vector<double>{}};
      }};
      Assembly isolated(fixture(folder,"isolated-network.json"),{nonlocal});
      auto jac = isolated.steady_linearize(0,std::vector<double>{300,310});
      require(isolated.sparsity()->nonzeros() == 3);
      near(jac.d_temperature.at({0,1}),-.5); near(jac.d_temperature.at({1,0}),0);
      near(jac.balance.residual[0],-12);
    } else if (name == "backend-linear") {
      Assembly network(fixture(folder));
      auto jac = network.steady_linearize(0,network.initial_temperature());
      ExactLinear backend;
      auto result = solve_linear(backend,jac.d_temperature,std::vector<double>{5,0});
      require(result.status == SolveStatus::converged); near(*result.residual_norm,0);
      backend.result.solution = {0,0};
      rejects([&] { solve_linear(backend,jac.d_temperature,std::vector<double>{5,0}); },"backend_result");
      backend.result = {SolveStatus::singular,{},0,{}};
      require(solve_linear(backend,jac.d_temperature,std::vector<double>{5,0}).status == SolveStatus::singular);
      backend.result = {SolveStatus::converged,{5},1,{}};
      rejects([&] { solve_linear(backend,jac.d_temperature,std::vector<double>{5,0}); },"backend_result");
      backend.throws = true;
      rejects([&] { solve_linear(backend,jac.d_temperature,std::vector<double>{5,0}); },"backend_failure");
      rejects([&] { solve_linear(backend,jac.d_temperature,std::vector<double>{5,0},{-1,0,1}); },"range");
    } else if (name == "backend-nonlinear") {
      // Analytic-answer adapters verify the interface; no production solver is supplied.
      auto problem = Assembly(fixture(folder)).steady_problem(0);
      ExactNonlinear backend;
      auto result = solve_nonlinear(backend,problem,std::vector<double>{300,300});
      require(result.status == SolveStatus::converged); near(*result.residual_norm,0);
      backend.result.solution = {300,300};
      rejects([&] { solve_nonlinear(backend,problem,std::vector<double>{300,300}); },"backend_result");
      backend.result = {SolveStatus::nonconverged,{},2,{}};
      require(solve_nonlinear(backend,problem,std::vector<double>{300,300}).status == SolveStatus::nonconverged);
      backend.throws = true;
      rejects([&] { solve_nonlinear(backend,problem,std::vector<double>{300,300}); },"backend_failure");
      backend.throws = false; backend.invalid_probe = true;
      rejects([&] { solve_nonlinear(backend,problem,std::vector<double>{300,300}); },"dimension");
      auto step = Assembly(fixture(folder)).step_problem(5,{300,300},5);
      auto value = step.evaluate(std::vector<double>{350,325},true);
      near(value.residual[0],110); near(value.jacobian->at({0,0}),3.4);
    } else if (name == "assembly-safety") {
      Assembly network(fixture(folder));
      rejects([&] { network.residual({nan,{300,300},{0}}); },"range");
      rejects([&] { network.residual({0,{300},{0}}); },"dimension");
      rejects([&] { network.residual({0,{300,300},{0,0}}); },"dimension");
      rejects([&] { network.residual({0,{300,300},{nan}}); },"range");
      auto e = rejects([&] { network.residual({0,{450,300},{0}}); },"range");
      require(e.entity_id == uid(4) && e.source_map_id == uid(11));
      rejects([&] { network.residual({0,{350,300},{std::numeric_limits<double>::max()}}); },"range");
      rejects([&] { network.step_residual(0,std::vector<double>{300,300},std::vector<double>{300,300},0); },"range");
      Assembly jump(fixture(folder,"step-network.json"));
      near(jump.residual({0,{300,300},{0}}).residual[0],-5);
      rejects([&] { jump.linearize({0,{300,300},{0}}); },"nondifferentiable");
      rejects([&] { jump.step_linearize(1,std::vector<double>{300,300},std::vector<double>{250,300},1); },"nondifferentiable");
      near(jump.steady_linearize(0,std::vector<double>{300,300}).d_temperature.at({0,0}),2);
    } else if (name == "physics-coverage") {
      rejects([&] { Assembly a(fixture(folder,"expression-network.json")); },"callback_missing");
      Assembly expression(fixture(folder,"expression-network.json"),{constant_load(7)});
      near(expression.steady_residual(0,std::vector<double>{300,300}).residual[0],-7);
      rejects([&] { Assembly a(fixture(folder,"control-network.json")); },"controls_require_state");
      rejects([&] { Assembly a(fixture(folder,"element-network.json")); },"unsupported_physics");
      auto bindings = powers(); std::reverse(bindings.begin(),bindings.end());
      Assembly one(fixture(folder,"power-network.json"),powers()), two(fixture(folder,"power-network.json"),bindings);
      auto a = one.linearize({1,{320,310},{0}}), b = two.linearize({1,{320,310},{0}});
      require(a.balance.residual == b.balance.residual && *one.sparsity() == *two.sparsity());
      near(a.balance.radiation_in[0]+a.balance.radiation_in[1],0); conservation(a.balance);
      const auto& environment = one.model().data().environments.front();
      near(environment.background_temperature,250); require(environment.id == uid(14));
    } else throw std::runtime_error("unknown_case");
    std::cout << "{\"status\":\"passed\"}\n";
    return 0;
  } catch (...) {
    std::cout << "{\"status\":\"failed\"}\n";
    return 1;
  }
}
