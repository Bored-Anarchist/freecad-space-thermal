// SPDX-License-Identifier: MIT OR Apache-2.0
#include "fcst/thermal_steady.hpp"
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>

using namespace fcst::thermal;
namespace {
void require(bool good) { if (!good) throw std::runtime_error("acceptance_failed"); }
void near(double a,double b,double tolerance=1e-8) { require(std::isfinite(a) && std::abs(a-b)<=tolerance*std::max(1.0,std::abs(b))); }
template<class F> void rejects(F f,const std::string& code) {
  try { f(); } catch (const Error& e) { require(e.code==code); return; }
  throw std::runtime_error("expected_rejection");
}
Model fixture(const std::filesystem::path& root,const std::string& name="material-network.json") {
  std::ifstream file(root/name,std::ios::binary); require(file.good());
  return load(std::string(std::istreambuf_iterator<char>(file),std::istreambuf_iterator<char>()));
}
std::string uid(unsigned n) { auto v=std::to_string(n); return "00000000-0000-4000-8000-"+std::string(12-v.size(),'0')+v; }
SparseMatrix matrix(std::size_t n,const std::vector<std::tuple<std::size_t,std::size_t,double>>& values) {
  std::vector<Entry> entries; for (const auto& [i,j,v]:values) { (void)v; entries.push_back({i,j}); }
  SparseMatrix result(std::make_shared<Sparsity>(n,entries));
  for (const auto& [i,j,v]:values) result.add({i,j},v);
  return result;
}
NonlinearProblem scalar(std::function<double(double)> f,std::function<double(double)> derivative) {
  auto pattern=std::make_shared<Sparsity>(1,std::vector<Entry>{{0,0}});
  return {pattern,[f,derivative,pattern](std::span<const double> x,bool jacobian) {
    NonlinearEvaluation result{{f(x[0])},{}};
    if (jacobian) { SparseMatrix j(pattern); j.add({0,0},derivative(x[0])); result.jacobian=std::move(j); }
    return result;
  }};
}
std::vector<PowerBinding> coupled(bool defective=false,bool opposite=false,bool conduction=true) {
  // Manufactured steady solution: T0=320, T1=310, prescribed T2=300 K.
  const double exchange=1e-8*(std::pow(320.,4)-std::pow(310.,4));
  PowerBinding load{uid(12),PowerKind::load,{0},{},[exchange,conduction](double,std::span<const double>,bool) {
    return PowerEvaluation{{(conduction?27:7)+exchange},{}};
  }};
  PowerBinding radiation{uid(22),PowerKind::radiation,{0,1},{{0,0},{0,1},{1,0},{1,1}},[defective](double,std::span<const double> t,bool j) {
    double q=-1e-8*(std::pow(t[0],4)-std::pow(t[1],4));
    if (defective) return PowerEvaluation{{1,1},j?std::vector<double>(4,0):std::vector<double>{}};
    return PowerEvaluation{{q,-q},j?std::vector<double>{-4e-8*std::pow(t[0],3),4e-8*std::pow(t[1],3),4e-8*std::pow(t[0],3),-4e-8*std::pow(t[1],3)}:std::vector<double>{}};
  }};
  PowerBinding environment{uid(14),PowerKind::environment,{0,1,2},{{0,0},{1,1},{2,2}},[exchange](double,std::span<const double> t,bool j) {
    return PowerEvaluation{{-.1*(t[0]-250),-exchange/60*(t[1]-250),-.1*(t[2]-250)},j?std::vector<double>{-.1,-exchange/60,-.1}:std::vector<double>{}};
  }};
  std::vector<PowerBinding> result{load,radiation,environment};
  if (opposite) result.push_back({uid(26),PowerKind::radiation,{0,1},{},[](double,std::span<const double>,bool) { return PowerEvaluation{{-1,-1},{}}; }});
  return result;
}
void successful(const SteadyResult& r) {
  require(r.solve.status==SolveStatus::converged && r.balance.has_value());
  require(r.solve.residual_norm && *r.solve.residual_norm<=1);
  require(r.solve.diagnostics.correction_norm && *r.solve.diagnostics.correction_norm<=1);
  for (double v:r.scaled_residual) require(std::abs(v)<=1);
}
}
int main(int argc,char** argv) {
  try {
    require(argc==3); std::string name=argv[1]; std::filesystem::path root(argv[2]);
    if (name=="lu-analytic") {
      SparseLuBackend backend;
      auto a=matrix(2,{{0,1,2},{1,0,1},{1,1,3}});
      auto result=solve_linear(backend,a,std::vector<double>{4,7});
      require(result.status==SolveStatus::converged); near(result.solution[0],1); near(result.solution[1],2);
      auto later_pivot=matrix(3,{{0,0,1},{0,1,1},{0,2,1},{1,0,1},{1,1,1.001},{1,2,2},{2,0,1},{2,1,3},{2,2,4}});
      auto pivoted=solve_linear(backend,later_pivot,std::vector<double>{6,9.002,19});
      require(pivoted.status==SolveStatus::converged);
      near(pivoted.solution[0],1);near(pivoted.solution[1],2);near(pivoted.solution[2],3);
      auto wide=matrix(2,{{0,0,1e-100},{1,1,1e100}});
      result=solve_linear(backend,wide,std::vector<double>{2e-100,3e100});
      require(result.status==SolveStatus::converged); near(result.solution[0],2); near(result.solution[1],3);
    } else if (name=="lu-sparse") {
      constexpr std::size_t n=10000; std::vector<Entry> entries;
      for (std::size_t i=0;i<n;++i) { entries.push_back({i,i}); if(i)entries.push_back({i,i-1});if(i+1<n)entries.push_back({i,i+1}); }
      SparseMatrix a(std::make_shared<Sparsity>(n,entries)); std::vector<double> rhs(n,0);
      for (std::size_t i=0;i<n;++i) { a.add({i,i},2);if(i)a.add({i,i-1},-1);if(i+1<n)a.add({i,i+1},-1); }
      rhs.front()=1-1.0/n;rhs.back()=2;
      auto r=solve_linear(SparseLuBackend(),a,rhs);
      require(r.status==SolveStatus::converged && a.sparsity()->nonzeros()==3*n-2);
      for (std::size_t i=0;i<n;++i) near(r.solution[i],1+static_cast<double>(i)/n,1e-7);
    } else if (name=="lu-subnormal-tail") {
      constexpr std::size_t n=256;std::vector<Entry> entries;
      for(std::size_t i=0;i<n;++i) {entries.push_back({i,i});if(i)entries.push_back({i,i-1});if(i+1<n)entries.push_back({i,i+1});}
      SparseMatrix a(std::make_shared<Sparsity>(n,entries));std::vector<double> rhs(n,0);rhs[0]=1;
      for(std::size_t i=0;i<n;++i) {a.add({i,i},32);if(i)a.add({i,i-1},-1);if(i+1<n)a.add({i,i+1},-1);}
      auto result=solve_linear(SparseLuBackend(),a,rhs,{0,1e-12,4});require(result.status==SolveStatus::converged);
      const double r=2/(32+std::sqrt(32.*32-4)),eta=std::numeric_limits<double>::denorm_min();
      for(std::size_t i=0;i<n;++i) {
        double expected=(std::pow(r,static_cast<double>(i+1))-std::pow(r,static_cast<double>(2*n+1-i)))/(1-std::pow(r,static_cast<double>(2*n+2)));
        require(std::abs(result.solution[i]-expected)<=1e-11*std::abs(expected)+16*eta);
      }
      // Quantization allowance cannot authorize a failed relative-only global
      // residual: eta/3 has no representable exact solution in this format.
      auto impossible=solve_linear(SparseLuBackend(),matrix(1,{{0,0,3}}),std::vector<double>{eta},{0,1e-12,4});
      require(impossible.status==SolveStatus::nonconverged && impossible.diagnostics.reason==SolveReason::linear_residual);
    } else if (name=="linear") {
      Assembly a(fixture(root)); auto r=solve_steady(a); successful(r);
      require(r.method==SteadyMethod::direct_linear && r.solve.iterations==1);
      near(r.balance->temperature[0],305); near(r.balance->temperature[1],302.5); near(r.balance->boundary_power[2],-5);
      near(r.balance->energy_defect,0); for(double v:r.balance->storage_power)near(v,0);
      auto fixed=solve_steady(Assembly(fixture(root,"prescribed-network.json")));successful(fixed);
      require(fixed.solve.solution.empty());near(fixed.balance->boundary_power[0],-5);
      SteadyOptions o;o.method=SteadyMethod::damped_newton;
      auto second=solve_steady(a,0,o);successful(second);near(second.balance->temperature[0],305);
    } else if (name=="nonlinear") {
      Assembly a(fixture(root,"power-network.json"),coupled());auto r=solve_steady(a);successful(r);
      require(r.method==SteadyMethod::damped_newton && r.solve.iterations>1);
      near(r.balance->temperature[0],320,1e-9);near(r.balance->temperature[1],310,1e-9);near(r.balance->boundary_power[2],-15);
      near(r.balance->energy_defect,0,1e-7);near(r.balance->internal_exchange_defect,0,1e-7);
      SteadyOptions direct;direct.method=SteadyMethod::direct_linear;
      require(solve_steady(a,0,direct).solve.status==SolveStatus::unsupported);
      Assembly anchored(fixture(root,"steady-environment-anchor.json"),coupled(false,false,false));
      require(anchored.model().data().components.front().steady_conduction_singular);
      auto environment_anchor=solve_steady(anchored);successful(environment_anchor);
      near(environment_anchor.balance->temperature[0],320,1e-9);near(environment_anchor.balance->temperature[1],310,1e-9);
    } else if (name=="line-search") {
      auto p=scalar([](double x){return x*x-1;},[](double x){return 2*x;});
      auto r=solve_nonlinear(DampedNewtonBackend(),p,std::vector<double>{.1},{1e-12,0,50});
      require(r.status==SolveStatus::converged && r.diagnostics.rejected_trials>=2);near(r.solution[0],1);
      auto large=scalar([](double x){return std::pow(x/1e308,3)-4.913;},[](double x){return 3*std::pow(x/1e308,2)/1e308;});
      auto large_result=solve_nonlinear(DampedNewtonBackend(),large,std::vector<double>{1e308},{1e-12,0,50});
      require(large_result.status==SolveStatus::converged && large_result.diagnostics.rejected_trials>0);
      near(large_result.solution[0],1.7e308,1e-10);
    } else if (name=="domain-backtracking") {
      auto logarithm=[](double x) {if(x<=0)throw EvaluationDomainError(Error("range"));return std::log(x);};
      auto p=scalar(logarithm,[](double x){return 1/x;});
      auto r=solve_nonlinear(DampedNewtonBackend(),p,std::vector<double>{10},{1e-12,0,50});
      require(r.status==SolveStatus::converged && r.diagnostics.rejected_trials>=2);near(r.solution[0],1);
    } else if (name=="scaling") {
      auto r=solve_steady(Assembly(fixture(root,"steady-scaled-components.json")));successful(r);
      near(r.balance->temperature[0],302);near(r.balance->temperature[2],303);
      require(r.power_scales[1]/r.power_scales[0]>1e190);
      require(r.residual_limits[0]<1e-105 && r.residual_limits[1]>1e90);
    } else if (name=="singular") {
      for (const auto& file:{"algebraic-network.json","steady-singular-zero.json","isolated-network.json"}) {
        auto r=solve_steady(Assembly(fixture(root,file)));
        require(r.solve.status==SolveStatus::singular && r.solve.diagnostics.reason==SolveReason::singular_pivot);
        require(!r.entity_id.empty());
      }
    } else if (name=="limits") {
      auto star=matrix(4,{{0,0,4},{0,1,1},{0,2,1},{0,3,1},{1,0,1},{1,1,2},{2,0,1},{2,2,2},{3,0,1},{3,3,2}});
      SparseLuSettings limit;limit.maximum_nonzeros=10;
      auto fill=solve_linear(SparseLuBackend(limit),star,std::vector<double>{7,3,3,3});
      require(fill.status==SolveStatus::unsupported && fill.diagnostics.reason==SolveReason::fill_limit);
      auto bounds=solve_steady(Assembly(fixture(root,"steady-outside-domain.json")));
      require(bounds.solve.status==SolveStatus::nonconverged && bounds.solve.diagnostics.reason==SolveReason::bounds);
      require(bounds.balance && bounds.balance->temperature[0]<=400);
      auto p=scalar([](double x){return std::exp(x)+1;},[](double x){return std::exp(x);});
      auto exhausted=solve_nonlinear(DampedNewtonBackend(),p,std::vector<double>{0},{1e-12,0,3});
      require(exhausted.status==SolveStatus::nonconverged && exhausted.diagnostics.reason==SolveReason::iteration_limit);
    } else if (name=="energy") {
      auto bad=solve_steady(Assembly(fixture(root,"power-network.json"),coupled(true)));
      require(bad.solve.status==SolveStatus::nonconverged && bad.solve.diagnostics.reason==SolveReason::energy_imbalance);
      near(bad.balance->energy_defect,2);require(bad.entity_id==uid(22));
      auto cancelled=solve_steady(Assembly(fixture(root,"steady-opposite-defects.json"),coupled(true,true)));
      require(cancelled.solve.status==SolveStatus::nonconverged && cancelled.solve.diagnostics.reason==SolveReason::energy_imbalance);
      near(cancelled.balance->energy_defect,0,1e-7);require(cancelled.entity_id==uid(22));
      auto unresolved=solve_steady(Assembly(fixture(root,"steady-temperature-resolution.json")));
      require(unresolved.solve.status==SolveStatus::nonconverged && unresolved.solve.diagnostics.reason==SolveReason::energy_imbalance);
      near(unresolved.balance->energy_defect,-5);
    } else if (name=="stopping") {
      auto false_step=scalar([](double){return 1.;},[](double){return 1e300;});
      auto r=solve_nonlinear(DampedNewtonBackend(),false_step,std::vector<double>{1},{1e-12,0,10});
      require(r.status==SolveStatus::nonconverged && r.diagnostics.reason==SolveReason::stagnation);
      NewtonSettings n;n.maximum_backtracks=5;
      auto wrong=scalar([](double x){return x*x-1;},[](double x){return -2*x;});
      r=solve_nonlinear(DampedNewtonBackend(n),wrong,std::vector<double>{2},{1e-12,0,10});
      require(r.status==SolveStatus::nonconverged && r.diagnostics.reason==SolveReason::line_search_failed);
    } else if (name=="options") {
      Assembly a(fixture(root));
      SteadyOptions invalid;invalid.relative_power_tolerance=0;
      rejects([&]{solve_steady(a,0,invalid);},"range");
      invalid={};invalid.power_scales={1};rejects([&]{solve_steady(a,0,invalid);},"dimension");
      invalid={};invalid.power_scales={-1,1};rejects([&]{solve_steady(a,0,invalid);},"range");
      invalid={};invalid.lower_temperature={400,0};invalid.upper_temperature={300,1000};rejects([&]{solve_steady(a,0,invalid);},"range");
      auto domain=solve_steady(a,0,{},std::vector<double>{199,300});
      require(domain.solve.status==SolveStatus::nonconverged && domain.solve.diagnostics.reason==SolveReason::initial_domain);
      require(domain.entity_id==uid(4) && domain.source_map_id==uid(11));
      SparseLuSettings bad;bad.pivot_tolerance=0;rejects([&]{SparseLuBackend b(bad);},"range");
    } else throw std::runtime_error("unknown_case");
    std::cout<<"{\"status\":\"passed\"}\n";return 0;
  } catch (...) { std::cout<<"{\"status\":\"failed\"}\n";return 1; }
}
