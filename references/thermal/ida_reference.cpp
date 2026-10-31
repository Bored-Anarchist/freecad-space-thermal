// SPDX-License-Identifier: MIT OR Apache-2.0
// Independent literal benchmark equations. No FCST model, assembler or solver.
#include <ida/ida.h>
#include <ida/ida_ls.h>
#include <nvector/nvector_serial.h>
#include <sunmatrix/sunmatrix_dense.h>
#include <sunlinsol/sunlinsol_dense.h>
#include <sundials/sundials_config.h>
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
void check(int status) {if(status<0)throw std::runtime_error("reference_failure");}
void array(const std::vector<double>& v) {std::cout<<'[';for(std::size_t i=0;i<v.size();++i){if(i)std::cout<<',';std::cout<<v[i];}std::cout<<']';}
struct Event {double time;std::string kind;double before,after;};
struct Model {
  std::string name;std::vector<double> initial,times,capacity;std::size_t m=0;
  bool heater_on=true;double scheduled_power=0,on_seconds=0,last_switch=0;
  std::vector<Event> events;
  explicit Model(std::string n):name(std::move(n)) {
    if(name=="cooling") {initial={310,300};capacity={2,0};times={0,.5,1,2,4};}
    else if(name=="closed") {initial={310,290};capacity={2,3};times={0,.1,.5,1,2};}
    else if(name=="dae") {initial={310,350,300};capacity={2,0,0};times={0,.5,1,2,4};}
    else if(name=="enthalpy") {initial={300};capacity={6};times={0,.5,1,2,5,10};}
    else if(name=="stiff") {initial={310,300,290};capacity={1e-4,1,0};times={0,1e-6,1e-4,.01,.1,.5,1};}
    else if(name=="heater") {initial={294,290};capacity={1,0};times={0,.5,1,2,3,4,5};events.push_back({0,"heater",0,1});}
    else if(name=="schedule") {initial={300};capacity={6};times={0,.5,1,1.5,2,3,4};events.push_back({0,"schedule",1,0});}
    else if(name=="nonlinear") {initial={300,300,300};capacity={6,0,0};times={0,.5,1,2,3,4,5};}
    else throw std::runtime_error("case");m=initial.size();
  }
  double boundary(const std::vector<double>& x) const {
    if(name=="cooling" || name=="heater")return -(x[0]-x[1]);
    if(name=="dae")return -2*(x[1]-x[2]);
    if(name=="stiff")return -(x[1]-x[2]);
    if(name=="nonlinear")return -2*(x[1]-x[2])+.1*(x[2]-250);
    return 0;
  }
  double external(const std::vector<double>& x) const {
    if(name=="closed")return 0;if(name=="enthalpy")return 5;if(name=="schedule")return scheduled_power;
    if(name=="heater")return (heater_on?20:0)+boundary(x);
    if(name=="nonlinear") {
      const double k=1e-8*(std::pow(320.,4)-std::pow(310.,4));
      return 27+k-.1*(x[0]-250)-k/60*(x[1]-250)-.1*(x[2]-250)+boundary(x);
    }
    return boundary(x);
  }
  double storage(const std::vector<double>& x) const {
    if(name=="enthalpy" || name=="schedule" || name=="nonlinear")return .01*(x[0]*x[0]-90000);
    double value=0;for(std::size_t i=0;i<m;++i)value+=capacity[i]*(x[i]-initial[i]);return value;
  }
  std::vector<double> links(const std::vector<double>& x) const {
    if(name=="cooling" || name=="heater")return {x[0]-x[1]};
    if(name=="closed")return {4*(x[0]-x[1])};
    if(name=="dae" || name=="nonlinear")return {2*(x[0]-x[1]),2*(x[1]-x[2])};
    if(name=="stiff")return {1e4*(x[0]-x[1]),x[1]-x[2]};return {};
  }
};
int residual(sunrealtype,N_Vector y,N_Vector yp,N_Vector r,void* data) {
  auto& m=*static_cast<Model*>(data);std::vector<double> t(m.m);
  for(std::size_t i=0;i<m.m;++i){t[i]=NV_Ith_S(y,static_cast<sunindextype>(i));if(!std::isfinite(t[i]) || t[i]<=0 || t[i]>1000)return 1;}
  auto put=[&](int i,double value){NV_Ith_S(r,i)=value;};
  if(m.name=="cooling") {put(0,2*NV_Ith_S(yp,0)+t[0]-t[1]);put(1,t[1]-300);}
  else if(m.name=="closed") {put(0,2*NV_Ith_S(yp,0)+4*(t[0]-t[1]));put(1,3*NV_Ith_S(yp,1)-4*(t[0]-t[1]));}
  else if(m.name=="dae") {put(0,2*NV_Ith_S(yp,0)+2*(t[0]-t[1]));put(1,2*(t[1]-t[0])+2*(t[1]-t[2]));put(2,t[2]-300);}
  else if(m.name=="enthalpy" || m.name=="schedule")put(0,.02*t[0]*NV_Ith_S(yp,0)-(m.name=="enthalpy"?5:m.scheduled_power));
  else if(m.name=="stiff") {put(0,1e-4*NV_Ith_S(yp,0)+1e4*(t[0]-t[1]));put(1,NV_Ith_S(yp,1)-1e4*(t[0]-t[1])+t[1]-t[2]);put(2,t[2]-290);}
  else if(m.name=="heater") {put(0,NV_Ith_S(yp,0)-(m.heater_on?20:0)+t[0]-t[1]);put(1,t[1]-290);}
  else {
    const double q=1e-8*(std::pow(t[0],4)-std::pow(t[1],4)),k=1e-8*(std::pow(320.,4)-std::pow(310.,4));
    put(0,.02*t[0]*NV_Ith_S(yp,0)-(27+k)+2*(t[0]-t[1])+q+.1*(t[0]-250));
    put(1,-2*(t[0]-t[1])+2*(t[1]-t[2])-q+k/60*(t[1]-250));put(2,t[2]-300);
  }
  NV_Ith_S(r,static_cast<sunindextype>(m.m))=NV_Ith_S(yp,static_cast<sunindextype>(m.m))-m.external(t);
  NV_Ith_S(r,static_cast<sunindextype>(m.m+1))=NV_Ith_S(yp,static_cast<sunindextype>(m.m+1))-m.boundary(t);return 0;
}
int root(sunrealtype,N_Vector y,N_Vector,sunrealtype* g,void* data) {auto& m=*static_cast<Model*>(data);g[0]=NV_Ith_S(y,0)-(m.heater_on?305:295);return 0;}
struct Solver {
  Model& m;SUNContext context=nullptr;N_Vector y=nullptr,yp=nullptr,id=nullptr;SUNMatrix matrix=nullptr;SUNLinearSolver linear=nullptr;void* memory=nullptr;
  double time=0,tolerance;long steps=0,evaluations=0;
  Solver(Model& model,double tol):m(model),tolerance(tol) {
    check(SUNContext_Create(SUN_COMM_NULL,&context));auto n=static_cast<sunindextype>(m.m+2);
    y=N_VNew_Serial(n,context);yp=N_VNew_Serial(n,context);id=N_VNew_Serial(n,context);
    if(!y || !yp || !id)throw std::runtime_error("allocation");N_VConst(0,y);N_VConst(0,yp);N_VConst(1,id);
    for(std::size_t i=0;i<m.m;++i){NV_Ith_S(y,static_cast<sunindextype>(i))=m.initial[i];NV_Ith_S(id,static_cast<sunindextype>(i))=m.capacity[i]>0?1:0;}
    matrix=SUNDenseMatrix(n,n,context);linear=SUNLinSol_Dense(y,matrix,context);memory=IDACreate(context);
    if(!matrix || !linear || !memory)throw std::runtime_error("allocation");
    check(IDAInit(memory,residual,0,y,yp));check(IDASetUserData(memory,&m));check(IDASetLinearSolver(memory,linear,matrix));
    check(IDASStolerances(memory,tolerance,tolerance));check(IDASetId(memory,id));check(IDASetMaxNumSteps(memory,100000));
    check(IDASetMaxStep(memory,.025));initialize(false);
  }
  ~Solver(){if(memory)IDAFree(&memory);if(linear)SUNLinSolFree(linear);if(matrix)SUNMatDestroy(matrix);if(id)N_VDestroy(id);if(yp)N_VDestroy(yp);if(y)N_VDestroy(y);if(context)SUNContext_Free(&context);}
  void accumulate(){long n=0;check(IDAGetNumSteps(memory,&n));steps+=n;check(IDAGetNumResEvals(memory,&n));evaluations+=n;}
  void initialize(bool reinit) {
    if(reinit){accumulate();check(IDAReInit(memory,time,y,yp));}
    check(IDASetStopTime(memory,time+1000));check(IDACalcIC(memory,IDA_YA_YDP_INIT,time+.001));check(IDAGetConsistentIC(memory,y,yp));
    if(m.name=="heater"){check(IDARootInit(memory,1,root));int direction=m.heater_on?1:-1;check(IDASetRootDirection(memory,&direction));}
  }
  void advance(double target) {
    while(time<target) {
      double stop=target;if(m.name=="schedule"){if(time<1)stop=std::min(stop,1.);else if(time<2)stop=std::min(stop,2.);}
      check(IDASetStopTime(memory,stop));int flag=IDASolve(memory,stop,&time,y,yp,IDA_NORMAL);check(flag);
      if(std::abs(time-stop)<1e-13 && flag!=IDA_ROOT_RETURN)time=stop;
      if(flag==IDA_ROOT_RETURN) {
        if(m.events.size()>10000 || time-m.last_switch<1e-9)throw std::runtime_error("chatter");
        if(m.heater_on)m.on_seconds+=time-m.last_switch;
        m.events.push_back({time,"heater",m.heater_on?1.:0.,m.heater_on?0.:1.});m.heater_on=!m.heater_on;m.last_switch=time;initialize(true);
      } else if(m.name=="schedule" && (time==1 || time==2)) {
        double next=time==1?5.:0.;m.events.push_back({time,"schedule",m.scheduled_power/5,next/5});m.scheduled_power=next;initialize(true);
      }
    }
  }
  std::vector<double> temperature() const {std::vector<double> v(m.m);for(std::size_t i=0;i<m.m;++i)v[i]=NV_Ith_S(y,static_cast<sunindextype>(i));return v;}
  void sample(double target) const {
    auto x=temperature();double energy=NV_Ith_S(y,static_cast<sunindextype>(m.m));
    double duty=m.name=="heater" && target>0?(m.on_seconds+(m.heater_on?target-m.last_switch:0))/target:0;
    std::cout<<"{\"time\":"<<target<<",\"temperature\":";array(x);std::cout<<",\"links\":";array(m.links(x));
    std::cout<<",\"boundary_power\":"<<m.boundary(x)<<",\"storage_change\":"<<m.storage(x)<<",\"external_energy\":"<<energy
      <<",\"boundary_energy\":"<<NV_Ith_S(y,static_cast<sunindextype>(m.m+1))<<",\"energy_defect\":"<<m.storage(x)-energy<<",\"duty\":"<<duty<<'}';
  }
};
}
int main(int argc,char** argv) {
 try {
  if(argc!=3)throw std::runtime_error("arguments");Model m(argv[1]);std::string level=argv[2];
  if(level!="coarse" && level!="fine")throw std::runtime_error("level");double tolerance=level=="fine"?1e-11:1e-9;
  Solver solver(m,tolerance);std::cout<<std::setprecision(17)<<"{\"status\":\"passed\",\"execution_mode\":\"reference_external\",\"backend\":\"sundials_ida\",\"version\":\""<<SUNDIALS_VERSION
    <<"\",\"case\":\""<<m.name<<"\",\"level\":\""<<level<<"\",\"tolerance\":"<<tolerance<<",\"samples\":[";
  for(std::size_t i=0;i<m.times.size();++i){if(i)std::cout<<',';solver.advance(m.times[i]);solver.sample(m.times[i]);}
  std::cout<<"],\"events\":[";
  for(std::size_t i=0;i<m.events.size();++i){if(i)std::cout<<',';const auto& e=m.events[i];std::cout<<"{\"time\":"<<e.time<<",\"kind\":\""<<e.kind<<"\",\"before\":"<<e.before<<",\"after\":"<<e.after<<'}';}
  std::cout<<"],\"steady\":";
  if(m.name=="cooling" || m.name=="dae" || m.name=="stiff" || m.name=="nonlinear") {
    solver.advance(100);auto x=solver.temperature();std::cout<<"{\"temperature\":";array(x);std::cout<<",\"boundary_power\":"<<m.boundary(x)<<'}';
  }else std::cout<<"null";
  solver.accumulate();std::cout<<",\"statistics\":{\"steps\":"<<solver.steps<<",\"residual_evaluations\":"<<solver.evaluations<<"}}\n";return 0;
 } catch(...) {std::cerr<<"{\"status\":\"failed\",\"reason\":\"ida_reference_failure\"}\n";return 1;}
}
