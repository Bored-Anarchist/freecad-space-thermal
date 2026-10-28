// SPDX-License-Identifier: MIT OR Apache-2.0
// Bounded Q0 experiment, deliberately separate from the production worker API.
#include <cvode/cvode.h>
#include <cvode/cvode_ls.h>
#include <nvector/nvector_serial.h>
#include <sunmatrix/sunmatrix_dense.h>
#include <sunmatrix/sunmatrix_band.h>
#include <sunlinsol/sunlinsol_dense.h>
#include <sunlinsol/sunlinsol_band.h>
#include <windows.h>
#include <psapi.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <cstdio>
#include <stdexcept>
#include <string>

namespace {
using State = std::array<double, 3>;
void check(int flag) { if (flag < 0) throw std::runtime_error("backend_failure"); }
struct Resources {
  SUNContext context = nullptr;
  N_Vector y = nullptr, b = nullptr;
  SUNMatrix matrix = nullptr;
  SUNLinearSolver linear = nullptr;
  void* cv = nullptr;
  explicit Resources(sunindextype n, bool band, sunindextype width) {
    check(SUNContext_Create(SUN_COMM_NULL, &context));
    y = N_VNew_Serial(n, context); b = N_VNew_Serial(n, context);
    matrix = band ? SUNBandMatrix(n, width, width, context) : SUNDenseMatrix(n, n, context);
    if (!y || !b || !matrix) throw std::runtime_error("allocation_failure");
    linear = band ? SUNLinSol_Band(y, matrix, context) : SUNLinSol_Dense(y, matrix, context);
    if (!linear) throw std::runtime_error("allocation_failure");
  }
  ~Resources() {
    if (cv) CVodeFree(&cv);
    if (linear) SUNLinSolFree(linear);
    if (matrix) SUNMatDestroy(matrix);
    if (b) N_VDestroy(b);
    if (y) N_VDestroy(y);
    if (context) SUNContext_Free(&context);
  }
  Resources(const Resources&) = delete;
  Resources& operator=(const Resources&) = delete;
};
double peak_memory() {
  PROCESS_MEMORY_COUNTERS info{}; info.cb = sizeof(info);
  if (!GetProcessMemoryInfo(GetCurrentProcess(), &info, sizeof(info))) throw std::runtime_error("memory_unavailable");
  return static_cast<double>(info.PeakWorkingSetSize);
}
struct Model {
  // SI inputs: capacity and slope, conductance and slope, radiation W/K^4,
  // boundary K, heater W, thermostat thresholds K. Zero g2 selects analytic seed.
  double c1, c2, slope1, slope2, g1, g2, gb, gslope, radiation, boundary, power, low, high;
  bool heater = true;
  double conductance(double t, double a) const { return g1 * (1 + gslope * (t + a - 2 * boundary)); }
  double rad(double a) const { return radiation * (std::pow(a, 4) - std::pow(boundary, 4)); }
  double residual(double a, const State& y) const {
    return conductance(y[0], a) * (y[0] - a) - g2 * (a - y[1]) - rad(a);
  }
  double algebraic(const State& y) const {
    if (g2 == 0) return boundary;
    double lo = std::min({y[0], y[1], boundary}), hi = std::max({y[0], y[1], boundary});
    for (int i = 0; i < 60; ++i) {
      const double mid = (lo + hi) / 2;
      if (residual(mid, y) > 0) lo = mid; else hi = mid;
    }
    return (lo + hi) / 2;
  }
  State rhs(const State& y) const {
    const double a = algebraic(y), q = conductance(y[0], a) * (y[0] - a);
    const double p = heater ? power : 0, loss = gb * (y[1] - boundary);
    const double cap1 = c1 + slope1 * (y[0] - boundary), cap2 = c2 + slope2 * (y[1] - boundary);
    if (cap1 <= 0 || cap2 <= 0 || y[0] <= 0 || y[1] <= 0) throw std::runtime_error("property_domain");
    return {(p - q) / cap1, g2 == 0 ? 0 : (g2 * (a - y[1]) - loss) / cap2,
            g2 == 0 ? p - q : p - loss - rad(a)};
  }
  std::array<State, 3> jacobian(const State& y) const {
    const double a = algebraic(y), q = conductance(y[0], a) * (y[0] - a), g = conductance(y[0], a);
    const double qt = g + g1 * gslope * (y[0] - a), qa = -g + g1 * gslope * (y[0] - a);
    const double rd = 4 * radiation * std::pow(a, 3), denom = g2 + rd - qa;
    const double at = g2 == 0 ? 0 : qt / denom, au = g2 == 0 ? 0 : g2 / denom;
    const double cap1 = c1 + slope1 * (y[0] - boundary), cap2 = c2 + slope2 * (y[1] - boundary);
    const double f1 = ((heater ? power : 0) - q) / cap1;
    const double f2 = g2 == 0 ? 0 : (g2 * (a - y[1]) - gb * (y[1] - boundary)) / cap2;
    return {{{-(qt + qa * at) / cap1 - f1 * slope1 / cap1, -qa * au / cap1, 0},
             {g2 * at / cap2, g2 == 0 ? 0 : (g2 * (au - 1) - gb) / cap2 - f2 * slope2 / cap2, 0},
             {g2 == 0 ? -qt : -rd * at, g2 == 0 ? 0 : -gb - rd * au, 0}}};
  }
};
State state(N_Vector y) { return {NV_Ith_S(y, 0), NV_Ith_S(y, 1), NV_Ith_S(y, 2)}; }
int rhs(sunrealtype, N_Vector y, N_Vector f, void* raw) {
  try {
    const auto values = static_cast<Model*>(raw)->rhs(state(y));
    for (int i = 0; i < 3; ++i) NV_Ith_S(f, i) = values[i];
    return 0;
  } catch (...) { return -1; }
}
int roots(sunrealtype, N_Vector y, sunrealtype* out, void* raw) {
  const auto& m = *static_cast<Model*>(raw);
  out[0] = NV_Ith_S(y, 0) - (m.heater ? m.high : m.low); return 0;
}
int jac(sunrealtype, N_Vector y, N_Vector, SUNMatrix a, void* raw, N_Vector, N_Vector, N_Vector) {
  const auto values = static_cast<Model*>(raw)->jacobian(state(y));
  for (int i = 0; i < 3; ++i) for (int j = 0; j < 3; ++j) {
    if (SUNMatGetID(a) == SUNMATRIX_DENSE) SM_ELEMENT_D(a, i, j) = values[i][j];
    else SM_ELEMENT_B(a, i, j) = values[i][j];
  }
  return 0;
}
void sample(double t, const State& y, const Model& m) {
  std::cout << "{\"time_s\":" << t << ",\"state\":[" << y[0] << ',' << y[1] << ',' << y[2]
            << "],\"algebraic_K\":" << m.algebraic(y) << ",\"heater\":" << (m.heater ? "true" : "false") << '}';
}
void integrate(bool band, bool adams, const std::string& mode) {
  Model m{}; double start, end, interval, rtol, atol; State y{}; int heater;
  if (!(std::cin >> m.c1 >> m.c2 >> m.slope1 >> m.slope2 >> m.g1 >> m.g2 >> m.gb >> m.gslope
        >> m.radiation >> m.boundary >> m.power >> m.low >> m.high >> start >> end >> interval
        >> rtol >> atol >> y[0] >> y[1] >> y[2] >> heater)) throw std::runtime_error("invalid_input");
  const std::array<double, 21> inputs{m.c1,m.c2,m.slope1,m.slope2,m.g1,m.g2,m.gb,m.gslope,
    m.radiation,m.boundary,m.power,m.low,m.high,start,end,interval,rtol,atol,y[0],y[1],y[2]};
  if (!std::all_of(inputs.begin(), inputs.end(), [](double v) { return std::isfinite(v); }) ||
      m.c1 <= 0 || m.c2 <= 0 || m.g1 <= 0 || m.g2 < 0 || m.gb < 0 || m.gslope < 0 ||
      m.slope1 < 0 || m.slope2 < 0 || m.radiation < 0 || m.boundary <= 0 || m.power < 0 ||
      m.low >= m.high || start < 0 || end <= start || end > 1000 || interval < .001 ||
      (end - start) / interval > 10000 || rtol <= 0 || rtol > .01 || atol <= 0 || atol > .01 ||
      (heater != 0 && heater != 1)) throw std::runtime_error("invalid_input");
  m.heater = heater != 0;
  if ((m.heater && y[0] >= m.high) || (!m.heater && y[0] <= m.low)) throw std::runtime_error("inconsistent_initial_state");
  // Check the owned Jacobian against centered differences before every solve.
  const auto j = m.jacobian(y); double jac_error = 0;
  for (int col = 0; col < 3; ++col) {
    State plus = y, minus = y; plus[col] += .001; minus[col] -= .001;
    const auto fp = m.rhs(plus), fm = m.rhs(minus);
    for (int row = 0; row < 3; ++row) jac_error = std::max(jac_error, std::abs(j[row][col] - (fp[row] - fm[row]) / .002));
  }
  Resources r(3, band, 2);
  if (mode == "steady") {
    // Heater is forced on for this equilibrium fixture, independent of thermostat mode.
    double norm = 1;
    for (int iteration = 0; iteration < 100 && norm > 1e-11; ++iteration) {
      const auto f = m.rhs(y); const auto jj = m.jacobian(y);
      norm = std::max(std::abs(f[0]), std::abs(f[1]));
      const double det = jj[0][0] * jj[1][1] - jj[0][1] * jj[1][0];
      if (std::abs(det) < 1e-20) throw std::runtime_error("singular_equilibrium");
      y[0] -= (f[0]*jj[1][1] - f[1]*jj[0][1])/det;
      y[1] -= (jj[0][0]*f[1] - jj[1][0]*f[0])/det;
    }
    if (norm > 1e-11) throw std::runtime_error("equilibrium_not_converged");
    std::cout << "{\"status\":\"completed\",\"residual\":" << norm << ",\"samples\":[";
    sample(0, y, m); std::cout << "],\"peak_memory_bytes\":" << peak_memory() << '}'; return;
  }
  for (int i = 0; i < 3; ++i) NV_Ith_S(r.y, i) = y[i];
  r.cv = CVodeCreate(adams ? CV_ADAMS : CV_BDF, r.context); if (!r.cv) throw std::runtime_error("allocation_failure");
  check(CVodeInit(r.cv, rhs, start, r.y)); check(CVodeSetUserData(r.cv, &m));
  check(CVodeSStolerances(r.cv, rtol, atol)); check(CVodeSetLinearSolver(r.cv, r.linear, r.matrix));
  check(CVodeSetJacFn(r.cv, jac)); check(CVodeSetMaxNumSteps(r.cv, 100000));
  check(CVodeRootInit(r.cv, 1, roots));
  int direction = m.heater ? 1 : -1; check(CVodeSetRootDirection(r.cv, &direction));
  std::string events; double t = start; int count = 0; long steps = 0, evaluations = 0;
  auto accumulate = [&]() {
    long n = 0; check(CVodeGetNumSteps(r.cv, &n)); steps += n;
    check(CVodeGetNumRhsEvals(r.cv, &n)); evaluations += n;
  };
  std::cout << "{\"status\":\"" << (mode == "cancel" ? "cancelled" : "completed")
            << "\",\"jacobian_error\":" << jac_error << ",\"samples\":[";
  sample(t, y, m);
  for (int index = 1; t < end - 1e-12; ++index) {
    const double target = std::min(end, start + index * interval);
    for (;;) {
      const int flag = CVode(r.cv, target, r.y, &t, CV_NORMAL); check(flag);
      if (flag != CV_ROOT_RETURN) break;
      if (++count > 10000) throw std::runtime_error("event_limit");
      if (!events.empty()) events += ',';
      // Preserve full event-time precision independently of stream formatting.
      char value[64]; const int length = snprintf(value, sizeof(value), "%.17g", t);
      if (length <= 0) throw std::runtime_error("event_encoding");
      events += value; m.heater = !m.heater; accumulate();
      check(CVodeReInit(r.cv, t, r.y));
      direction = m.heater ? 1 : -1; check(CVodeSetRootDirection(r.cv, &direction));
      if (t >= target - 1e-12) break;
    }
    std::cout << ','; sample(t, state(r.y), m);
  }
  accumulate();
  std::cout << "],\"events_s\":[" << events << "],\"steps\":" << steps << ",\"rhs_evaluations\":" << evaluations
            << ",\"method\":\"" << (adams ? "ADAMS" : "BDF") << "\",\"linear_solver\":\"" << (band ? "band" : "dense")
            << "\",\"peak_memory_bytes\":" << peak_memory() << '}';
}
void scale(bool band, int n) {
  if (n < 16 || n > 100000 || (!band && n > 256)) throw std::runtime_error("invalid_input");
  Resources r(n, band, 5);
  auto exact = [n](int i) { return 1.0 + static_cast<double>(i) / n; };
  for (int i = 0; i < n; ++i) {
    double value = 0;
    for (int k = std::max(0, i - 5); k <= std::min(n - 1, i + 5); ++k) {
      const double a = i == k ? 12 : -1;
      if (band) SM_ELEMENT_B(r.matrix, i, k) = a; else SM_ELEMENT_D(r.matrix, i, k) = a;
      value += a * exact(k);
    }
    NV_Ith_S(r.b, i) = value;
  }
  check(SUNLinSolInitialize(r.linear)); check(SUNLinSolSetup(r.linear, r.matrix));
  check(SUNLinSolSolve(r.linear, r.matrix, r.y, r.b, 0));
  double error = 0, residual = 0;
  for (int i = 0; i < n; ++i) {
    error = std::max(error, std::abs(NV_Ith_S(r.y, i) - exact(i)));
    double ax = 0;
    for (int k = std::max(0, i - 5); k <= std::min(n - 1, i + 5); ++k) ax += (i == k ? 12 : -1) * NV_Ith_S(r.y, k);
    residual = std::max(residual, std::abs(ax - NV_Ith_S(r.b, i)));
  }
  std::cout << "{\"status\":\"completed\",\"nodes\":" << n << ",\"directed_links\":" << 10 * n - 30
            << ",\"max_error\":" << error << ",\"max_residual\":" << residual << ",\"peak_memory_bytes\":" << peak_memory() << '}';
}
}
int main(int argc, char** argv) {
  std::cout << std::setprecision(17);
  try {
    if (argc == 2 && std::string(argv[1]) == "info") {
      std::cout << "{\"execution_mode\":\"fcst_native\",\"scope\":\"q0_prototype\",\"sundials\":\"7.3.0\",\"compiler\":\"MSVC\",\"compiler_version\":\""
                << FCST_COMPILER_VERSION << "\",\"cmake\":\"" << FCST_CMAKE_VERSION
                << "\",\"abi\":\"x64-dynamic-CRT\",\"floating_point\":\"strict\",\"threads\":1,\"fast_math\":false}"; return 0;
    }
    if (argc < 3 || (std::string(argv[2]) != "band" && std::string(argv[2]) != "dense" && std::string(argv[2]) != "adams")) throw std::runtime_error("invalid_input");
    const auto start = std::chrono::steady_clock::now();
    // Buffer successful output so exceptions never publish a partial JSON success.
    std::ostringstream output; auto* original = std::cout.rdbuf(output.rdbuf());
    try {
      if (argc == 3 && (std::string(argv[1]) == "integrate" || std::string(argv[1]) == "cancel" || std::string(argv[1]) == "steady"))
        integrate(std::string(argv[2]) != "dense", std::string(argv[2]) == "adams", argv[1]);
      else if (argc == 4 && std::string(argv[1]) == "scale") {
        size_t used = 0; const int n = std::stoi(argv[3], &used);
        if (used != std::string(argv[3]).size()) throw std::runtime_error("invalid_input");
        scale(std::string(argv[2]) == "band", n);
      } else throw std::runtime_error("invalid_input");
    } catch (...) { std::cout.rdbuf(original); throw; }
    std::cout.rdbuf(original);
    const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    auto value = output.str(); value.pop_back();
    std::cout << value << ",\"seconds\":" << seconds << "}\n"; return 0;
  } catch (const std::exception& error) {
    std::string code = error.what();
    const std::array<std::string, 9> allowed{"invalid_input", "inconsistent_initial_state", "property_domain",
      "backend_failure", "allocation_failure", "event_limit", "memory_unavailable", "singular_equilibrium", "equilibrium_not_converged"};
    if (std::find(allowed.begin(), allowed.end(), code) == allowed.end()) code = "invalid_input";
    std::cout << "{\"status\":\"failed\",\"code\":\"" << code << "\"}\n"; return 2;
  }
}
